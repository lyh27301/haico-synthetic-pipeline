"""Step 9 Part A: run the discoverability gate (recipe/discover_gate.py) on every v0.4 task; repair once; tag the rest.
Atomic per task: arm_s9/gate/<task>.json (skip existing). Repaired tasks are copied to arm_s9/tasks/<task>/ with the
new task.md and scenario.json problem_statement (the v0.4 source dirs are not touched).
  USAGE_LOG=arm_s9/gate_usage.jsonl .venv/bin/python arm_s9/run_gate.py [--workers 8]"""
import argparse, json, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402
from recipe import discover_gate as D, gates  # noqa: E402

OUT = ROOT / "arm_s9" / "gate"
TASKS = ROOT / "arm_s9" / "tasks"
CTX = json.loads((ROOT / "harness" / "agent_context.json").read_text())
MAN = json.loads((ROOT / "arm_hf" / "out_v04" / "manifest.json").read_text())["tasks"]


def write(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(obj, indent=1, default=str)); tmp.replace(path)


def one(t: str) -> str:
    f = OUT / f"{t}.json"
    if f.exists():
        return json.loads(f.read_text())["status"]
    d = ROOT / MAN[t]["dir"]; prof = driver.profile_for(d)
    task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
    env, role = str(d / "environment.yaml"), CTX.get(t, "")
    rec = {"task": t, "toolkit": prof.NAME, "original": task.problem_statement}
    try:
        r1 = D.check(prof, task, env, role)
    except Exception as e:  # noqa: BLE001
        r1 = {"ok": True, "reason": f"gate_crash {type(e).__name__}: {e}", "targets": [], "found": [], "calls": []}
    rec["first"] = r1
    if r1["ok"]:
        rec["status"] = "pass"
    else:
        ps, fb = D.repair(prof, task, env, role, r1)
        rec["feedback"], rec["repaired"] = fb, ps
        r2 = D.check(prof, task, env, role, instruction=ps) if ps else {"ok": False, "reason": "repair_failed"}
        rec["second"] = r2
        t2 = prof.TASK_SCHEMA.model_validate({**json.loads(task.model_dump_json()), "problem_statement": ps}) if ps else None
        new_err = None
        if t2 is not None:
            before, after = gates.step7_errors(prof, task), gates.step7_errors(prof, t2)
            new_err = after if after and after != before else None
        rec["step7_gate_after_repair"] = new_err
        if r2["ok"] and not new_err:
            rec["status"] = "repaired"
            dst = TASKS / t
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(d, dst)
            (dst / "task.md").write_text(ps + "\n" if not ps.endswith("\n") else ps)
            sc = json.loads((dst / "scenario.json").read_text()); sc["problem_statement"] = ps
            (dst / "scenario.json").write_text(json.dumps(sc, indent=2))
        else:
            rec["status"] = "undiscoverable"
    write(f, rec)
    return rec["status"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=8); ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); TASKS.mkdir(parents=True, exist_ok=True)
    ids = a.only or sorted(MAN)
    with ThreadPoolExecutor(a.workers) as ex:
        for t, s in zip(ids, ex.map(one, ids)):
            print(s, t, flush=True)


if __name__ == "__main__":
    main()
