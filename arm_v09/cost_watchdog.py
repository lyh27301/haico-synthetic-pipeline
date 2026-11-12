"""v0.9: arm_v08/cost_watchdog.py on an arm_v09 output tree (argument: the tree, default arm_v09; the smoke uses
arm_v09/smoke), with the per-run cost caps of the Anthropic agents: $0.05 Claude Haiku 5.5, $0.60 Claude Sonnet 5.5
(accumulated_cost from litellm's price table, cache reads / writes priced). Token cap (200k uncached tokens), hang check
and kill / capped.jsonl as in v0.8. Everything below the imports is the v0.8 watchdog unchanged except S9 and CAP.
  .venv/bin/python arm_v09/cost_watchdog.py [arm_v09/smoke]"""
import glob, json, os, re, subprocess, sys, time
from pathlib import Path

S9 = (Path(__file__).resolve().parents[1] / sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
HANG_S = 600
TOKEN_CAP = 200_000   # uncached prompt + completion tokens per run
TOK = re.compile(r'prompt_tokens\\?":\s*(\d+).*?completion_tokens\\?":\s*(\d+).*?cache_read_tokens\\?":\s*(\d+)')
CAP = {"gpt-4o-mini": 0.15, "gpt-5-mini": 0.40, "qwen": float("inf"), "haiku": 0.05, "sonnet": 0.60}
COST = re.compile(r'accumulated_cost\\?":\s*([0-9.]+)')
CID = re.compile(r"docker inspect -f '\{\{\.State\.Running\}\}' ([0-9a-f]{64})")
pos, done = {}, set()


def kill(cid: str) -> None:
    """Stop the agent-server and answer 404 on its port: a stopped server leaves the SDK polling a dead port until its
    3600 s run timeout, and a restarted one reports the conversation 'paused', which the SDK does not treat as
    terminal either; a 404 makes it raise ConversationRunError at once."""
    port = subprocess.run(["docker", "port", cid, "8000"], capture_output=True, text=True).stdout.split(":")[-1].strip()
    subprocess.run(["docker", "stop", "-t", "5", cid], capture_output=True)
    if port.isdigit():
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / "arm_v08/serve404.py"), port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
while True:
    for f in glob.glob(str(S9 / "harness/logs/*.log")):
        size = os.path.getsize(f)
        start = pos.get(f, size)   # only lines written after the watchdog starts
        if size <= start:
            pos[f] = size; continue
        with open(f, "rb") as fh:
            fh.seek(start); chunk = fh.read().decode(errors="replace")
        pos[f] = start + len(chunk.encode())
        latest = {}
        for ln in chunk.splitlines():
            if "accumulated_cost" not in ln or not ln.startswith("{"):
                continue
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            m = COST.findall(o.get("event", "")); tk = TOK.findall(o.get("event", ""))
            if m and o.get("run_id") and o.get("instance_id"):
                latest[(o["run_id"], o["instance_id"])] = (float(m[0]), (int(tk[0][0]) - int(tk[0][2]) + int(tk[0][1])) if tk else 0)
        for (run, iid), (c, ntok) in latest.items():
            agent = ("haiku" if "haiku" in run else "sonnet" if "sonnet" in run else "qwen" if "Qwen" in run
                     else "gpt-5-mini" if "gpt-5-mini" in run else "gpt-4o-mini")
            kind = "token_cap" if ntok > TOKEN_CAP else "cost_cap" if c > CAP[agent] else None
            if kind is None or (run, iid) in done:
                continue
            il = Path(run) / "logs" / f"instance_{iid}.log"
            ids = CID.findall(il.read_text(errors="replace")) if il.exists() else []
            if not ids:
                continue
            kill(ids[-1])
            done.add((run, iid))
            with open(S9 / "harness/capped.jsonl", "a") as fh:
                fh.write(json.dumps({"t": time.time(), "kind": kind, "run": run, "instance": iid, "cost": c,
                                     "tokens": ntok, "container": ids[-1][:12]}) + "\n")
            print(kind, iid, run, c, ntok, flush=True)
    # hang: an unfinished instance whose log has had no new line for HANG_S (e.g. `ping host` in the terminal).
    # Skipped while endpoint_guard.py has the runs paused for an endpoint outage, and for HANG_S after the resume
    # (a paused run writes no log lines; that silence is not a hang).
    lr = S9 / "harness/last_resume"
    quiet = (S9 / "harness/paused").exists() or (lr.exists() and time.time() - json.loads(lr.read_text())["t"] < HANG_S)
    for il in ([] if quiet else glob.glob(str(S9 / "harness/**/logs/instance_*.log"), recursive=True)):
        if il.endswith(".output.log") or il in done:
            continue
        age = time.time() - os.path.getmtime(il)
        if age < HANG_S or age > 4 * 3600:
            continue
        txt = Path(il).read_text(errors="replace")
        if "[child] done" in txt or "Stopping container" in txt:
            continue
        ids = CID.findall(txt)
        if ids and subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", ids[-1]],
                                  capture_output=True, text=True).stdout.strip() == "true":
            kill(ids[-1])
            done.add(il)
            with open(S9 / "harness/capped.jsonl", "a") as fh:
                fh.write(json.dumps({"t": time.time(), "kind": "hang", "log": il, "hang_s": round(age), "container": ids[-1][:12]}) + "\n")
            print("hung", il, round(age), flush=True)
    time.sleep(30)
