"""Step 11 (arm_s10/cost_watchdog.py on arm_s11; Qwen runs: no cost cap, as the local model costs $0 — token cap and
hang check as before; recursive globs, because the Qwen run dir is openai/Qwen/Qwen3.5-9B_*). Step 10: per-rollout caps (step 9's watchdog with the token cap redefined). Every 30 s this scans the new lines of
the run logs (arm_s10/harness/logs/*.log: run_infer's conversation_event stream, which carries each instance's
accumulated_cost and accumulated_token_usage) and kills an instance's agent-server (see kill()) once it passes
  - the token cap: 200k UNCACHED tokens = prompt_tokens - cache_read_tokens + completion_tokens. Step 9 counted
    cached prompt tokens too, so every long-but-ordinary run (the whole history is re-sent each turn, ~90% of it
    served from cache) was killed: 106 of 970 runs. The harness reports the cache split on every event
    (cache_read_tokens is present in 100% of step-9 usage records), so no step cap is needed;
  - the cost cap (step 9's: $0.15 gpt-4o-mini, $0.40 gpt-5-mini), against runaway loops;
  - the hang check (no new log line for 10 min).
A run killed for either cap is no_grade and not retried (run_harness.py); a hung run is rerun once.
Each stop -> arm_s11/harness/capped.jsonl.
  .venv/bin/python arm_s11/cost_watchdog.py"""
import glob, json, os, re, subprocess, sys, time
from pathlib import Path

S9 = Path(__file__).resolve().parent
HANG_S = 600
TOKEN_CAP = 200_000   # uncached prompt + completion tokens per run
TOK = re.compile(r'prompt_tokens\\?":\s*(\d+).*?completion_tokens\\?":\s*(\d+).*?cache_read_tokens\\?":\s*(\d+)')
CAP = {"gpt-4o-mini": 0.15, "gpt-5-mini": 0.40, "qwen": float("inf")}
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
                latest[(o["run_id"], o["instance_id"])] = (float(m[0]), (int(tk[0][0]) - int(tk[0][2]) + int(tk[0][1])) if tk else 0)
        for (run, iid), (c, ntok) in latest.items():
            agent = "qwen" if "Qwen" in run else "gpt-5-mini" if "gpt-5-mini" in run else "gpt-4o-mini"
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
    for il in glob.glob(str(S9 / "harness/**/logs/instance_*.log"), recursive=True):
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
