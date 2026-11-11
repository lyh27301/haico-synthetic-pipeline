"""v0.8 batch orchestration (unattended): arm_v08/batch_v08.json = 130 tasks x {gpt-4o-mini, Qwen3.5-9B} x runs 1-5,
plus single (task, agent, run) slots replacing contaminated runs whose task is not re-rolled.
  - both agents' runners (arm_v08/run_harness.py, resumable: a run with a final result is never redone) start together;
    the slots run after the Qwen runner;
  - stop conditions, checked every minute: the endpoint guard gave up (> 45 min down: harness/endpoint_down.json), the
    budget guard stopped at the cap (harness/budget_stop.json), or more than 5% of the batch's runs erroring (a final
    no-grade that is not a cost / token cap), counted once 100 runs are final;
  - writes arm_v08/run_v08.json {state, reason, counts, t} at every step.
Guards run alongside: arm_v08/endpoint_guard.py, arm_v08/cost_watchdog.py, arm_v08/budget_guard.py.
  NPC_API_KEY=$OPENAI_API_KEY ... .venv/bin/python arm_v08/run_v08.py"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V = ROOT / "arm_v08"; H = V / "harness"; RES = H / "results"
PY = str(ROOT / ".venv/bin/python")
STATE = V / "run_v08.json"
B = json.loads((V / "batch_v08.json").read_text())
TOTAL = B["total_runs"]
NAME = {"gpt-4o-mini": "4omini", "4omini": "4omini", "qwen3.5-9b": "qwen", "Qwen/Qwen3.5-9B": "qwen"}


def note(**kw):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.update(kw, t=time.strftime("%Y-%m-%dT%H:%M:%S%z")); STATE.write_text(json.dumps(s, indent=1))
    print(json.dumps(kw), flush=True)


def counts() -> dict:
    rs = [json.loads(f.read_text()) for f in RES.glob("*.json")] if RES.exists() else []
    rs = [r for r in rs if not r.get("endpoint_lost")]
    return {"final": len(rs), "graded": sum(bool(r.get("graded")) for r in rs),
            "capped": sum(bool(r.get("capped")) for r in rs),
            "errors": sum(not r.get("graded") and not r.get("capped") for r in rs),
            "unsafe": sum(r.get("unsafe") is True for r in rs)}


def stop_reason(c) -> str | None:
    if (H / "budget_stop.json").exists():
        return "budget guard stopped the runs at the spend cap"
    if (H / "endpoint_down.json").exists():
        return "endpoint down > 45 min (endpoint guard gave up)"
    if c["final"] >= 100 and c["errors"] > 0.05 * max(c["final"], 1):
        return f"{c['errors']} of {c['final']} final runs errored (> 5%)"
    return None


def kill(ps):
    for p in ps:
        if p.poll() is None:
            for pid in subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split():
                subprocess.run(["pkill", "-TERM", "-P", pid]); os.kill(int(pid), signal.SIGTERM)
            p.terminate()


def runner(agent, ids, first, last, workers, tag=""):
    env = {**os.environ, "NPC_BASE_URL": "https://api.openai.com/v1", "NPC_MODEL": "gpt-4o-mini", "WORKERS": workers}
    env.setdefault("NPC_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    return subprocess.Popen([PY, str(V / "run_harness.py"), "--agent", agent, "--ids", str(ids), "--first", str(first),
                             "--last", str(last), *(["--tag", tag] if tag else [])], env=env, cwd=ROOT,
                            stdout=open(V / f"run_{agent}{('_' + tag) if tag else ''}.out", "a"), stderr=subprocess.STDOUT)


def watch(ps) -> bool:
    while any(p.poll() is None for p in ps):
        c = counts(); r = stop_reason(c)
        if r:
            kill(ps); note(state="stopped", reason=r, **c); return False
        note(state="running", **c)
        time.sleep(60)
    return True


def main():
    ids = V / "ids_v08.txt"
    ps = [runner("4omini", ids, 1, 5, "4"), runner("qwen", ids, 1, 5, "5")]
    note(state="running", pids=[p.pid for p in ps])
    q = ps[1]
    slots_started = False
    while any(p.poll() is None for p in ps) or not slots_started:
        if q.poll() is not None and not slots_started:   # Qwen main pass done: run the slots on the free GPU
            slots_started = True
            for s in B["slots"]:
                f = V / f"ids_slot_{s['task']}_r{s['run']}.txt"; f.write_text(s["task"] + "\n")
                ps.append(runner(NAME[s["agent"]], f, s["run"], s["run"], "1", tag=f"slot_r{s['run']}_"))
            note(state="slots_started", slots=len(B["slots"]))
        c = counts(); r = stop_reason(c)
        if r:
            kill(ps); note(state="stopped", reason=r, **c); sys.exit(2)
        note(state="running", **c)
        time.sleep(60)
    c = counts()
    note(state="done" if c["final"] >= TOTAL else "incomplete", reason=f"{c['final']} of {TOTAL} runs final", **c)


if __name__ == "__main__":
    main()
