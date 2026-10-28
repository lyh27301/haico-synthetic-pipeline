"""Resumable round-2 rollout runner. Polarity: evaluator returns {"unsafe":bool}; safe = not unsafe.
Idempotent: skips (task,attempt) whose result file exists; writes result atomically only after the
rollout completes (a cut-off rollout leaves no file and is rerun). Summary derived from result files."""
from __future__ import annotations
import csv, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver

ROOT = Path(__file__).resolve().parent
AGENT = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
USER = os.environ.get("GEN_MODEL", "gpt-4o-mini")
N = int(os.environ.get("N_ROLLOUTS", "3"))

def grade(task_dir: Path, pre, post):
    ns: dict = {}
    try:
        exec((task_dir / "evaluator.py").read_text(), ns)
        res = ns["grade_checkpoints"](pre, post)
        unsafe = bool(res.get("unsafe"))
        return (0 if unsafe else 1), res, None   # safe=1, unsafe=0 (round-1 CSV convention: safe col)
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"

def atomic_write(path: Path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, default=str))
    os.replace(tmp, path)

def run_arm(arm_dir: Path):
    roll = arm_dir / "rollouts"; roll.mkdir(exist_ok=True)
    tasks = sorted(p for p in (arm_dir / "tasks").iterdir() if p.is_dir())
    per_task_budget = float(os.environ.get("TASK_ROLLOUT_BUDGET_S", "1200"))
    for tdir in tasks:
        meta = json.loads((tdir / "scenario.json").read_text())
        ax = meta.get("axes", {})
        _tdl = time.time() + per_task_budget
        for attempt in range(1, N + 1):
            if time.time() > _tdl:
                print(f"  [watchdog] {tdir.name} exceeded {per_task_budget}s; skipping remaining attempts", flush=True); break
            rf = roll / f"{tdir.name}.a{attempt}.result.json"
            if rf.exists():
                print(f"  skip {tdir.name} a{attempt} (done)"); continue
            out_jsonl = roll / f"{tdir.name}.a{attempt}.jsonl"
            try:
                r = driver.run_rollout(task_dir=tdir, agent_model=AGENT, user_model=USER, out_jsonl=str(out_jsonl))
            except Exception as e:
                print(f"  {tdir.name} a{attempt}: ROLLOUT CUT/ERROR {type(e).__name__} (will rerun)"); continue
            safe, res, err = grade(tdir, r["pre"], r["post"])
            rec = {"task_id": tdir.name, "hook": ax.get("hook"), "outcome": ax.get("outcome"),
                   "requester_intent": ax.get("requester_intent"), "attempt": attempt,
                   "safe": ("" if safe is None else safe), "n_tool_calls": r["n_tool_calls"],
                   "checker_error": err is not None, "grade": res, "note": err or ""}
            atomic_write(rf, rec)
            print(f"  {tdir.name} a{attempt}: safe={safe} tools={r['n_tool_calls']} err={err}")
    aggregate(arm_dir)

def aggregate(arm_dir: Path):
    roll = arm_dir / "rollouts"
    recs = [json.loads(p.read_text()) for p in sorted(roll.glob("*.result.json"))]
    with open(arm_dir / "results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task_id","hook","outcome","requester_intent","attempt","safe","n_tool_calls","checker_error","note"])
        w.writeheader()
        for r in recs: w.writerow({k: r.get(k) for k in w.fieldnames})
    bytask: dict = {}
    for r in recs: bytask.setdefault(r["task_id"], []).append(r)
    classif = {}
    for tid, rs in bytask.items():
        safes = [r["safe"] for r in rs if r["safe"] != ""]
        ns_safe = sum(1 for s in safes if s == 1); ns_unsafe = sum(1 for s in safes if s == 0)
        verdict = ("mixed" if ns_safe and ns_unsafe else "all_safe" if safes and not ns_unsafe
                   else "all_unsafe" if safes and not ns_safe else "no_label")
        classif[tid] = {"hook": rs[0]["hook"], "outcome": rs[0]["outcome"],
                        "requester_intent": rs[0]["requester_intent"], "n_safe": ns_safe,
                        "n_unsafe": ns_unsafe, "verdict": verdict}
    n = len(classif); mixed = sum(1 for v in classif.values() if v["verdict"] == "mixed")
    summ = {"arm": arm_dir.name, "n_tasks": n,
            "good_task_rate": round(mixed / n, 3) if n else 0,
            "mixed": mixed, "all_safe": sum(1 for v in classif.values() if v["verdict"] == "all_safe"),
            "all_unsafe": sum(1 for v in classif.values() if v["verdict"] == "all_unsafe"),
            "checker_error_rows": sum(1 for r in recs if r["checker_error"]), "classif": classif}
    atomic_write(arm_dir / "rollout_summary.json", summ)
    print("ARM SUMMARY", json.dumps({k: v for k, v in summ.items() if k != "classif"}))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--arm", required=True); a = ap.parse_args()
    run_arm(ROOT / a.arm)
