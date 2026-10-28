"""Diagnostic replay of the Stage-B task-writer for the 7 gated scenarios.
Pulls each attempt from the gen cache (free); decomposes the 0/0/1 dry run per stage,
capturing reference-step execution errors that graders._apply normally swallows."""
import json, copy, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recipe import pipeline as P
from recipe import graders as G
from recipe.gmail_task import GmailTask
from gmail_suite.environment import env_to_dict
from gmail_suite.tools import build_runtime

EX = P.load_exemplars()

def apply_capture(env, steps):
    """Run reference steps, returning list of per-step errors (None if ok)."""
    rt = build_runtime(); errs = []
    for i, s in enumerate(steps):
        if s.fn_name() == "chat_npc":
            errs.append(None); continue
        try:
            out, err = rt.run_function(env, s.fn_name(), dict(s.args))
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        errs.append(err)
    return errs

def decompose(task: GmailTask):
    """Return dict: stage grades + ref exec errors + first-failure classification."""
    out = {"schema": "ok"}
    try:
        code = G.synthesize_evaluator(task)
    except Exception as e:
        out["first_fail"] = "grader_exec"; out["detail"] = f"synthesize: {type(e).__name__}: {e}"; return out
    try:
        base = G._base_env(G.BASE_YAML if hasattr(G,'BASE_YAML') else ROOT/'gmail_suite'/'base_environment.yaml', task)
    except Exception as e:
        out["first_fail"] = "ref_exec"; out["detail"] = f"base_env build: {type(e).__name__}: {e}"; return out
    pre = env_to_dict(base)
    try:
        unt = G._grade(code, pre, json.loads(json.dumps(pre)))["unsafe"]
    except Exception as e:
        out["first_fail"] = "grader_exec"; out["detail"] = f"grade untouched: {type(e).__name__}: {e}"; return out
    # safe
    es = G._base_env(ROOT/'gmail_suite'/'base_environment.yaml', task)
    safe_errs = apply_capture(es, task.safe_reference)
    try:
        safe = G._grade(code, pre, env_to_dict(es))["unsafe"]
    except Exception as e:
        out["first_fail"] = "grader_exec"; out["detail"] = f"grade safe: {e}"; return out
    # violator
    ev = G._base_env(ROOT/'gmail_suite'/'base_environment.yaml', task)
    viol_errs = apply_capture(ev, task.violator_reference)
    try:
        viol = G._grade(code, pre, env_to_dict(ev))["unsafe"]
    except Exception as e:
        out["first_fail"] = "grader_exec"; out["detail"] = f"grade violator: {e}"; return out
    out.update({"untouched": int(unt), "safe": int(safe), "violator": int(viol),
                "violator_step_errors": viol_errs, "safe_step_errors": safe_errs,
                "grader_kind": task.grader.kind if task.grader else "evaluator_code",
                "grader_spec": task.grader.model_dump() if task.grader else None,
                "violator_tools": [(s.tool, list(s.args.keys()), s.pivotal) for s in task.violator_reference]})
    # classify first failure
    if unt:
        out["first_fail"] = "grader_0_untouched"; out["detail"] = "grader fires on untouched env"
    elif safe:
        out["first_fail"] = "grader_0_safe"; out["detail"] = "grader fires after safe_reference"
    elif not viol:
        ve = [f"step{i}:{e}" for i,e in enumerate(viol_errs) if e]
        if ve:
            out["first_fail"] = "ref_exec"; out["detail"] = "violator step(s) errored -> no mutation: " + "; ".join(ve)
        else:
            out["first_fail"] = "grader_1_violator"; out["detail"] = "violator steps ran but grader still 0 (content/target mismatch)"
    else:
        out["first_fail"] = "PASS"; out["detail"] = "0/0/1"
    return out

def replay_scenario(sc, arm, idx):
    attempts = []
    obj = None; last_err = None
    for attempt in range(3):   # max_attempts=2 -> up to 3 attempts
        # build prompt exactly as build_task would
        if attempt == 0:
            raw = P.gen_task(sc, idx, EX)
        else:
            raw = P.regen(sc, idx, EX, obj, last_err)
        obj = raw
        rec = {"attempt": attempt, "raw": raw}
        try:
            task = GmailTask.model_validate(raw)
        except Exception as e:
            rec["first_fail"] = "schema"; rec["detail"] = f"{type(e).__name__}: {e}"
            last_err = f"schema: {type(e).__name__}: {e}"
            attempts.append(rec); continue
        d = decompose(task)
        rec.update(d)
        if d["first_fail"] == "PASS":
            attempts.append(rec); break
        # reproduce build_task's last_err for the next regen
        if d["first_fail"] in ("ref_exec","grader_1_violator","grader_0_safe","grader_0_untouched"):
            res = {"untouched": d.get("untouched",0), "safe": d.get("safe",0), "violator": d.get("violator",0)}
            last_err = f"dry_run {res} != 0/0/1"
        elif d["first_fail"] == "grader_exec":
            last_err = f"dry_run_crash: {d['detail']}"
        attempts.append(rec)
    return attempts

def main():
    allrecs = {}
    for arm in ["arm_c","arm_d"]:
        for i, ln in enumerate(open(ROOT/arm/"gated_scenarios.jsonl").read().splitlines(), 1):
            sc = json.loads(ln)
            sid = sc.get("scenario_id") or f"{arm}-sc{i}-" + (sc.get("mechanic","")[:30].replace(" ","_"))
            key = f"{arm}:{sid}"
            try:
                atts = replay_scenario(sc, arm, i)
            except Exception as e:
                atts = [{"attempt":0,"first_fail":"REPLAY_ERROR","detail":f"{type(e).__name__}: {e}"}]
            allrecs[key] = {"arm": arm, "scenario_id": sid, "mechanic": sc.get("mechanic",""),
                            "axes": sc.get("_seed",{}).get("axes") or sc.get("axes"), "attempts": atts}
            outdir = ROOT/"analysis"/"replayed"/key.replace(":","__").replace("/","_")
            outdir.mkdir(parents=True, exist_ok=True)
            for a in atts:
                (outdir/f"attempt{a['attempt']}.json").write_text(json.dumps(a, indent=2, default=str))
            print(f"{key}: " + " -> ".join(f"a{a['attempt']}:{a.get('first_fail')}" for a in atts))
    (ROOT/"analysis"/"replay_summary.json").write_text(json.dumps(allrecs, indent=2, default=str))
    print("\nwrote analysis/replay_summary.json")

if __name__ == "__main__":
    main()
