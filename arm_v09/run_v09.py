"""v0.9 orchestration (unattended, resumable: a run with a final result is never redone, so a restart continues).
  1. Haiku 5.5: all 302 tasks (arm_v08/bank_v08.jsonl) x runs 1-5 (arm_v09/run_harness.py --agent haiku);
  2. arm_v09/analyze_v09.py on the Haiku runs, then arm_v09/sonnet_set.py -> arm_v09/ids_sonnet.txt (the tasks with no
     natural honest success on any agent so far, plus 15 control tasks);
  3. Sonnet 5.5: those tasks x runs 1-3.
Stop conditions, checked every minute: the budget guard stopped at a cap (harness/budget_stop.json), or more than 5% of
the current batch's runs erroring (a final no-grade that is not a cost / token cap), counted once 100 runs are final.
Writes arm_v09/run_v09.json {state, phase, reason, counts, t}. Guards alongside: arm_v09/cost_watchdog.py,
arm_v09/budget_guard.py.
  .venv/bin/python arm_v09/run_v09.py"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V = ROOT / "arm_v09"; H = V / "harness"; RES = H / "results"
PY = str(ROOT / ".venv/bin/python")
STATE = V / "run_v09.json"
WORKERS = {"haiku": "8", "sonnet": "6"}
RUNS = {"haiku": 5, "sonnet": 3}
NAME = {"haiku": "haiku5.5", "sonnet": "sonnet5.5"}


def note(**kw):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.update(kw, t=time.strftime("%Y-%m-%dT%H:%M:%S%z")); STATE.write_text(json.dumps(s, indent=1))
    print(json.dumps(kw), flush=True)


def counts(agent) -> dict:
    rs = []
    for f in (RES.glob(f"*__{NAME[agent]}__r*.json") if RES.exists() else []):
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if not r.get("endpoint_lost"):
            rs.append(r)
    return {"final": len(rs), "graded": sum(bool(r.get("graded")) for r in rs),
            "capped": sum(bool(r.get("capped")) for r in rs),
            "errors": sum(not r.get("graded") and not r.get("capped") for r in rs),
            "unsafe": sum(r.get("unsafe") is True for r in rs)}


def stop_reason(c) -> str | None:
    if (H / "budget_stop.json").exists():
        return "budget guard stopped the runs at a cap: " + (H / "budget_stop.json").read_text()[:200]
    if c["final"] >= 100 and c["errors"] > 0.05 * max(c["final"], 1):
        return f"{c['errors']} of {c['final']} final runs errored (> 5%)"
    return None


def batch(agent, ids: Path, total: int) -> bool:
    p = subprocess.Popen([PY, str(V / "run_harness.py"), "--agent", agent, "--ids", str(ids), "--first", "1",
                          "--last", str(RUNS[agent])], cwd=ROOT, env={**os.environ, "WORKERS": WORKERS[agent]},
                         stdout=open(V / f"run_{agent}.out", "a"), stderr=subprocess.STDOUT)
    note(state="running", phase=agent, pid=p.pid, total=total)
    while p.poll() is None:
        c = counts(agent); r = stop_reason(c)
        if r:
            for pid in subprocess.run(["pgrep", "-P", str(p.pid)], capture_output=True, text=True).stdout.split():
                subprocess.run(["pkill", "-TERM", "-P", pid]); os.kill(int(pid), signal.SIGTERM)
            p.terminate(); note(state="stopped", phase=agent, reason=r, **c); return False
        note(state="running", phase=agent, **c)
        time.sleep(60)
    c = counts(agent)
    note(state=f"{agent}_done" if c["final"] >= total else f"{agent}_incomplete", phase=agent, **c,
         reason=f"{c['final']} of {total} {agent} runs final")
    return c["final"] >= total


def main():
    all_ids = V / "ids_all.txt"
    all_ids.write_text("".join(json.loads(l)["instance_id"] + "\n" for l in (ROOT / "arm_v08/bank_v08.jsonl").read_text().splitlines()))
    if not batch("haiku", all_ids, 302 * RUNS["haiku"]):
        sys.exit(2)
    note(state="analysing_haiku", phase="select")
    subprocess.run([PY, str(V / "analyze_v09.py"), "--workers", "6"], cwd=ROOT, check=True,
                   stdout=open(V / "analyze.out", "a"), stderr=subprocess.STDOUT)
    out = subprocess.run([PY, str(V / "sonnet_set.py")], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    sel = json.loads((V / "sonnet_set.json").read_text())
    note(state="sonnet_selected", phase="select", sonnet_tasks=sel["tasks"], sonnet_unsolved=sel["unsolved"],
         sonnet_control=sel["control"], selection=out.strip()[-500:])
    if not batch("sonnet", V / "ids_sonnet.txt", sel["tasks"] * RUNS["sonnet"]):
        sys.exit(2)
    note(state="done", phase="done")


if __name__ == "__main__":
    main()
