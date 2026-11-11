"""Step 12b (copy of arm_s11/endpoint_guard.py for arm_v08 runners). Step 11 Part C: endpoint loss = pause, not abort. The cluster's preempt partition routinely preempts and requeues the
vLLM job, so the endpoint (the SSH tunnel on localhost:8000) disappears and comes back on another node.
  - every 30 s GET <base>/models;
  - first failure -> pause: SIGSTOP the run_infer tree under every arm_v08/run_harness.py runner (no new task is
    dispatched, no client times out while frozen) and `docker pause` the in-flight agent-server containers (their
    LLM retry loops freeze instead of failing); write harness/paused;
  - endpoint answers again -> resume: docker unpause, SIGCONT, remove harness/paused, write harness/last_resume;
  - still down after 45 min -> give up: kill the whole process tree (leaves first, so no worker is orphaned), stop
    the containers, write harness/endpoint_down.json (with the runners' command lines) and print the exact resume
    commands (the runners skip every run that already has a final result, so nothing restarts from scratch).
Every pause / resume / give-up is a line in harness/outages.jsonl {event, t, iso, in_flight} (and on stdout), for
Part D's outage count and duration. Tasks that still errored because of an outage are re-queued by run_harness.py.
  .venv/bin/python arm_v08/endpoint_guard.py"""
import json, os, signal, subprocess, time, urllib.request
from pathlib import Path

H = Path(os.environ.get("GUARD_DIR") or Path(__file__).resolve().parent / "harness")   # GUARD_*: overrides for tests
URL = os.environ.get("QWEN_BASE_URL", "http://localhost:8000/v1") + "/models"
IMAGE = "openagentsafety-agentdojo"
POLL_S, GIVE_UP_S = int(os.environ.get("GUARD_POLL_S", 30)), int(os.environ.get("GUARD_GIVE_UP_S", 45 * 60))


def up() -> bool:
    try:
        urllib.request.urlopen(URL, timeout=10).read()
        return True
    except Exception:  # noqa: BLE001
        return False


def tree(p: str) -> list[str]:
    """p and all its descendants, leaves first (run_infer's multiprocessing workers outlive a killed parent)."""
    kids = subprocess.run(["pgrep", "-P", p], capture_output=True, text=True).stdout.split()
    return [d for k in kids for d in tree(k)] + [p]


def runners() -> list[str]:
    return subprocess.run(["pgrep", "-f", "bin/python[0-9.]* ([^ ]*/)?arm_v08/run_harness[.]py"], capture_output=True, text=True).stdout.split()


def infer_procs() -> list[str]:
    """The run_infer trees under the runners (not the runners themselves, which only wait on run_infer)."""
    return [d for r in runners() for d in tree(r) if d != r]


def containers() -> list[str]:
    out = subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Image}}"], capture_output=True, text=True).stdout
    return [ln.split()[0] for ln in out.splitlines() if IMAGE in ln]


def signal_all(pids: list[str], sig) -> None:
    for p in pids:
        try:
            os.kill(int(p), sig)
        except (ProcessLookupError, ValueError):
            pass


def log(event: str, **kw) -> None:
    o = {"event": event, "t": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **kw}
    with open(H / "outages.jsonl", "a") as fh:
        fh.write(json.dumps(o) + "\n")
    print(json.dumps(o), flush=True)


def resume_recipe(cmds: list[str]) -> str:
    """Give-up exits cleanly; the runners are resumable (a (task, agent, run) with a final result file is skipped), so
    resuming = clear the give-up marker, restart the guard, rerun the same runner commands."""
    root = Path(__file__).resolve().parents[1]
    env = "NPC_API_KEY=$OPENAI_API_KEY NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=5"
    lines = [f"cd {root}", f"rm {H / 'endpoint_down.json'}",
             "nohup .venv/bin/python arm_v08/endpoint_guard.py >> arm_v08/harness/guard.out 2>&1 &"]
    lines += [f"{env} nohup {c} >> arm_v08/run_resume.out 2>&1 &" for c in cmds]
    return "RESUME (once the endpoint answers again):\n  " + "\n  ".join(lines)


def main():
    paused_at, frozen = None, []
    while True:
        ok = up()
        if not ok and paused_at is None:
            procs, frozen = infer_procs(), containers()
            signal_all(procs, signal.SIGSTOP)
            if frozen:
                subprocess.run(["docker", "pause", *frozen], capture_output=True)
            paused_at = time.time()
            (H / "paused").write_text(json.dumps({"t": paused_at}))
            log("pause", in_flight=len(frozen), procs=len(procs))
        elif ok and paused_at is not None:
            if frozen:
                subprocess.run(["docker", "unpause", *frozen], capture_output=True)
            signal_all(infer_procs(), signal.SIGCONT)
            (H / "paused").unlink(missing_ok=True)
            (H / "last_resume").write_text(json.dumps({"t": time.time()}))
            log("resume", in_flight=len(frozen), outage_s=round(time.time() - paused_at))
            paused_at, frozen = None, []
        elif not ok and time.time() - paused_at > GIVE_UP_S:
            cmds = [subprocess.run(["ps", "-o", "command=", "-p", r], capture_output=True, text=True).stdout.strip()
                    for r in runners()]
            pids = [d for r in runners() for d in tree(r)]
            signal_all(pids, signal.SIGCONT)   # a stopped process does not act on SIGTERM until continued
            signal_all(pids, signal.SIGTERM)
            cs = containers()
            if cs:
                subprocess.run(["docker", "unpause", *cs], capture_output=True)
                subprocess.run(["docker", "stop", "-t", "5", *cs], capture_output=True)
            (H / "paused").unlink(missing_ok=True)
            (H / "endpoint_down.json").write_text(json.dumps({"t": time.time(), "down_s": round(time.time() - paused_at),
                                                              "stopped": pids, "runner_cmds": cmds}))
            log("give_up", in_flight=len(cs), outage_s=round(time.time() - paused_at))
            print(resume_recipe(cmds), flush=True)
            return
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
