"""Step 9: per-rollout cost cap. The harness default (500 iterations + fake-user loop) lets a looping gpt-4o-mini run
reach ~$1 (11.7M prompt tokens seen in Part C r1). Every 30 s this scans the new lines of the run logs
(arm_s9/harness/logs/*.log: run_infer's conversation_event stream, which carries each instance's accumulated_cost)
and kills an instance's agent-server once it passes the cap (see kill()), so the run ends, is rerun once by
run_harness.py, and is recorded no_grade if it hits the cap again. Each stop -> arm_s9/harness/capped.jsonl.
  .venv/bin/python arm_s9/cost_watchdog.py"""
import glob, json, os, re, subprocess, sys, time
from pathlib import Path

S9 = Path(__file__).resolve().parent
HANG_S = 600
TOKEN_CAP = 200_000   # prompt + completion tokens per run (cached prompt tokens included); user rule from r2 on
TOK = re.compile(r'prompt_tokens\\?":\s*(\d+).*?completion_tokens\\?":\s*(\d+)')
CAP = {"gpt-4o-mini": 0.15, "gpt-5-mini": 0.40}
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
        subprocess.Popen([sys.executable, str(S9 / "serve404.py"), port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
                latest[(o["run_id"], o["instance_id"])] = (float(m[0]), sum(map(int, tk[0])) if tk else 0)
        for (run, iid), (c, ntok) in latest.items():
            agent = "gpt-5-mini" if "gpt-5-mini" in run else "gpt-4o-mini"
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
    # hang: an unfinished instance whose log has had no new line for HANG_S (e.g. `ping host` in the terminal)
    for il in glob.glob(str(S9 / "harness/*/*/*/*/logs/instance_*.log")):
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
