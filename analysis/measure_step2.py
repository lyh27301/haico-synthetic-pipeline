"""Measure the automatic 0/0/1 pass rate after the step-2 fixes.
Runs gen_task + up to 2 regens per scenario (as build_task does), classifying each
attempt's first-failure stage with the FIXED dry run (which raises DryRunError on ref_exec)."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recipe import pipeline as P
from recipe.gmail_task import GmailTask
from recipe.graders import dry_run, dry_run_ok, DryRunError

BASE = ROOT / "gmail_suite" / "base_environment.yaml"
EX = P.load_exemplars()

def classify(raw):
    """Return (stage, detail, task_or_None)."""
    try:
        task = GmailTask.model_validate(raw)
    except Exception as e:
        return "schema", f"{type(e).__name__}: {str(e)[:160]}", None
    try:
        res = dry_run(task, BASE)
    except DryRunError as e:
        return "ref_exec", str(e)[:200], task
    except Exception as e:
        return "grader_exec", f"{type(e).__name__}: {str(e)[:160]}", task
    if dry_run_ok(res):
        return "PASS", "0/0/1", task
    if res["untouched"]:
        return "grader_0_untouched", str(res), task
    if res["safe"]:
        return "grader_0_safe", str(res), task
    return "grader_1_violator", str(res), task

def run_scenario(sc, idx, max_attempts=2):
    attempts = []
    obj = None; last_err = None; t0 = time.time()
    c0 = dict(P.CALLS)
    for attempt in range(max_attempts + 1):
        raw = P.gen_task(sc, idx, EX) if attempt == 0 else P.regen(sc, idx, EX, obj, last_err)
        obj = raw
        stage, detail, task = classify(raw)
        attempts.append({"attempt": attempt, "stage": stage, "detail": detail})
        if stage == "PASS":
            break
        # reproduce build_task's last_err for the next regen
        if stage == "schema":
            last_err = f"schema: {detail}"
        elif stage == "ref_exec":
            last_err = detail
        elif stage == "grader_exec":
            last_err = f"dry_run_crash: {detail}"
        else:
            last_err = f"dry_run {detail} != 0/0/1"
    dt = time.time() - t0
    calls = {k: dict(P.CALLS)[k] - c0.get(k, 0) for k in P.CALLS}
    passed = attempts[-1]["stage"] == "PASS"
    return {"attempts": attempts, "passed": passed, "wall_s": round(dt, 1),
            "llm_calls": calls, "final_task": (task.model_dump() if passed else None)}

def load_gated():
    out = {}
    names_c = ["archive-agreements", "summarize-results", "reply-all-salary"]
    names_d = ["alerts-delete", "forward-contract", "confirmation-reply", "hr-panel-offer"]
    for arm, names in [("arm_c", names_c), ("arm_d", names_d)]:
        lines = (ROOT / arm / "gated_scenarios.jsonl").read_text().splitlines()
        for i, ln in enumerate(lines):
            out[f"{arm}:{names[i] if i < len(names) else 'sc'+str(i)}"] = json.loads(ln)
    return out

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    gated = load_gated()
    REG = ["arm_d:alerts-delete", "arm_c:summarize-results", "arm_d:forward-contract"]
    order = REG if which == "reg" else (REG + [k for k in gated if k not in REG])
    results = {}
    for n, key in enumerate(order, 1):
        sc = gated[key]
        r = run_scenario(sc, n)
        results[key] = r
        path = " -> ".join(f"a{a['attempt']}:{a['stage']}" for a in r["attempts"])
        print(f"{key}: {'PASS' if r['passed'] else 'FAIL'}  [{path}]  {r['wall_s']}s calls={r['llm_calls']}", flush=True)
    npass = sum(1 for r in results.values() if r["passed"])
    print(f"\nPASS {npass}/{len(results)}")
    out = ROOT / "analysis" / ("step2_measure_reg.json" if which == "reg" else "step2_measure_all.json")
    out.write_text(json.dumps(results, indent=2, default=str))
    print("wrote", out)

if __name__ == "__main__":
    main()
