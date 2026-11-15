"""Step 16c Part A orchestrator: 12 tasks (arm_s16c/tasks.txt) x 3 agents x runs 1-5 = 180 runs.
  - gpt-6-luna and Claude Haiku 5.5 -> arm_s16c/runs (started at once, 3 workers each);
  - Qwen3.5-9B -> arm_s16c/qwen (started when the cluster endpoint first answers on localhost:8000, which may take as long
    as the queue does; then guarded by arm_s16c/guard16c.py: pause on endpoint loss, resume when it is back, no give-up);
  - arm_s16c/watchdog16c.py on each tree (per-run caps, hangs).
Stops (writes arm_s16c/run16c.json state=stopped with the reason) only on: a failed runner (non-zero exit), the spend
caps below, or more than 5 % errors among final runs (counted once 30 are final). Spend is checked every minute:
OpenAI (gpt-6-luna agent usage.json + $0.001 per chat_npc call) cap $4; Anthropic (Haiku usage.json, the API's rate
card: litellm's cost is checked against tokens x $0.10 / $0.50 per M, cache read 0.1x, cache write 1.25x; the larger
is used) cap $3.5. The follow-up question and grading are separate scripts.
Restartable (--adopt): runners already running (found by their command line) are adopted, not restarted; a runner
counts as failed when its process is gone before its agent has 60 final results. (Used after Haiku was restarted with
readable thinking; the first 24 Haiku runs, without it, are kept in arm_s16c/haiku_nothinking/.)
  .venv/bin/python arm_s16c/run16c.py"""
import glob, json, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; C = ROOT / "arm_s16c"; PY = str(ROOT / ".venv/bin/python")
STATE = C / "run16c.json"
CAPS = {"openai": 4.0, "anthropic": 3.5}
TREE = {"luna": C / "runs", "haiku": C / "runs", "qwen": C / "qwen"}
NAME = {"luna": "gpt-6-luna", "haiku": "haiku5.5", "qwen": "qwen3.5-9b"}


def note(**kw):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.update(kw, t=time.strftime("%Y-%m-%dT%H:%M:%S%z")); STATE.write_text(json.dumps(s, indent=1))


def haiku_cost(u: dict) -> float:
    t = u.get("token_usage") or {}
    cr, cw, p = t.get("cache_read_tokens") or 0, t.get("cache_write_tokens") or 0, t.get("prompt_tokens") or 0
    est = ((p - cr - cw) * 0.10 + cr * 0.01 + cw * 0.125 + (t.get("completion_tokens") or 0) * 0.50) / 1e6
    return max(est, u.get("accumulated_cost") or 0)


def spend() -> dict:
    oai = sum((json.loads(Path(f).read_text()).get("accumulated_cost") or 0)
              for f in glob.glob(str(C / "runs/harness/gpt-6-luna/**/usage.json"), recursive=True))
    an = sum(haiku_cost(json.loads(Path(f).read_text()))
             for f in glob.glob(str(C / "runs/harness/haiku5.5/**/usage.json"), recursive=True))
    npc = sum(Path(f).read_text().count('chat_npc \\"') for t in ("runs", "qwen")
              for f in glob.glob(str(C / t / "harness/**/output.critic_attempt_1.jsonl"), recursive=True))
    return {"openai": round(oai + npc * 0.001, 3), "anthropic": round(an, 3), "npc_calls": npc}


def counts() -> dict:
    out = {}
    for a, t in TREE.items():
        rs = []
        for f in (t / "harness/results").glob(f"*__{NAME[a]}__r*.json"):
            try:
                rs.append(json.loads(f.read_text()))
            except ValueError:
                pass
        out[a] = {"final": len(rs), "ok": sum(bool(r.get("final")) for r in rs),
                  "capped": sum(bool(r.get("capped")) for r in rs),
                  "errors": sum(not r.get("final") and not r.get("capped") for r in rs)}
    return out


def up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:8000/v1/models", timeout=10).read(); return True
    except Exception:  # noqa: BLE001
        return False


def start(agent):
    t = TREE[agent]; (t / "harness").mkdir(parents=True, exist_ok=True)
    log = open(C / f"run_{agent}.out", "a")
    return subprocess.Popen([PY, str(C / "run_harness16c.py"), "--agent", agent, "--root", str(t.relative_to(ROOT)),
                             "--first", "1", "--last", "5"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            env={**__import__("os").environ, "WORKERS": "3"})


def running(agent) -> list:
    return subprocess.run(["pgrep", "-f", f"run_harness16c[.]py --agent {agent} --root arm_s16c/(runs|qwen)"],
                          capture_output=True, text=True).stdout.split()


class Adopted:
    def __init__(self, agent):
        self.agent = agent

    def poll(self):
        if running(self.agent):
            return None
        return 0 if counts()[self.agent]["final"] >= 60 else 1

    def terminate(self):
        for p in running(self.agent):
            subprocess.run(["kill", p])


def main():
    procs, aux = {}, []
    adopt = "--adopt" in sys.argv
    for t in ("runs", "qwen"):
        (C / t / "harness").mkdir(parents=True, exist_ok=True)
        if adopt and subprocess.run(["pgrep", "-f", f"watchdog16c[.]py arm_s16c/{t}"], capture_output=True).stdout:
            continue
        aux.append(subprocess.Popen([PY, str(C / "watchdog16c.py"), str((C / t).relative_to(ROOT))], cwd=ROOT,
                                    stdout=open(C / t / "watchdog.out", "a"), stderr=subprocess.STDOUT))
    for a in ("luna", "haiku", "qwen"):
        if adopt and running(a):
            procs[a] = Adopted(a)
        elif a != "qwen":
            procs[a] = start(a)
    note(state="running", pids={a: getattr(p, "pid", "adopted") for a, p in procs.items()}, qwen="waiting for endpoint")
    reason = None
    while True:
        if "qwen" not in procs and up():   # (in --adopt mode the guard is already running when qwen is adopted)
            aux.append(subprocess.Popen([PY, str(C / "guard16c.py")], cwd=ROOT, stdout=open(C / "qwen/guard.out", "a"),
                                        stderr=subprocess.STDOUT,
                                        env={**__import__("os").environ, "GUARD_DIR": str(C / "qwen/harness")}))
            procs["qwen"] = start("qwen")
            note(qwen="started", qwen_started=time.time())
        sp, cn = spend(), counts()
        fin = sum(v["final"] for v in cn.values()); err = sum(v["errors"] for v in cn.values())
        note(spend=sp, counts=cn)
        failed = [a for a, p in procs.items() if p.poll() not in (None, 0)]
        if failed:
            reason = f"runner failed: {failed} exit {[procs[a].poll() for a in failed]}"
        elif sp["openai"] >= CAPS["openai"] or sp["anthropic"] >= CAPS["anthropic"]:
            reason = f"spend cap: {sp}"
        elif fin >= 30 and err / fin > 0.05:
            reason = f"error rate {err}/{fin}"
        if reason:
            for p in procs.values():
                p.terminate()
            note(state="stopped", reason=reason); break
        if "qwen" in procs and all(p.poll() == 0 for p in procs.values()):
            note(state="done"); break
        time.sleep(60)
    for p in aux:
        p.terminate()
    print(json.dumps(json.loads(STATE.read_text()), indent=1))


if __name__ == "__main__":
    main()
