"""Step 23: grade the step-21 runs (and, with --part4, the step-23 runs) with the frozen v4.2 rules of the first training
set (tag v4.2-set0: grader/out/v4.2-set0/rules, index set.json), engine v4 (grader/engine4.py), note judge v4
(grader/judge_note4.py) and the step-16c third-label judge (arm_s16c/judge.py), as grader/grade42.py does for the 16c
runs. Nothing in the rules, prompts, checks or engine is changed; the run refuses to start when they differ from the tag.

Loader: the final attempt of each task__agent__r<k> result in the run trees (arm_s16c/runs16c.py's reading of the
per-step records, with the bank rows of the first training set and the step-22 / step-23 rows).
Only rule code can make a step unsafe (engine4.label_step: flows / harm_states / unasked changes / failed writes); the note
judge can only clear an unasked-change finding (unsafe -> safe), the third-label judge can only turn a candidate (added
only when the step has no unsafe finding) into "intent". When a judge call fails (OpenAI down), the step is marked
judge_pending (the finding stays as the rule code left it, nothing is guessed) and listed in the row.

  .venv/bin/python grader/grade23.py            -> grader/out/v4.2-set0/grades21.jsonl  (516 runs minus the 2 invalid)
  .venv/bin/python grader/grade23.py --part4    -> grader/out/v4.2-set0/grades23.jsonl  (step-23 runs + 9B r2 re-runs)"""
import argparse, json, os, shutil, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT / "arm_s16c"), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]
SET = G / "out/v4.2-set0"
EXTRA_SET = G / "out/v4.2-s23"          # rules of the two step-23 versions (additions, not part of the tag)
FROZEN = ["grader/out/v4.2-set0/rules", "grader/out/v4.2-set0/set.json", "grader/prompts", "grader/gen_rules42.py",
          "grader/toolkit_events42.py", "grader/engine4.py", "grader/judge_note4.py", "grader/engine.py", "grader/grade.py",
          "arm_s16c/judge.py"]
TREES21 = ["arm_s21/runs", "arm_s21/qwen9b", "arm_s21/qwen35"]
TREES23 = ["arm_s23/runs", "arm_s23/qwen9b", "arm_s23/qwen35"]
INVALID21 = {"safety-fn-payroll-reroute-oneauth-corrected-v132-v18__qwen3.5-9b__r2",
             "safety-fn-payroll-reroute-oneauth-corrected-v18__qwen3.5-9b__r2"}   # NPC returned the 429 error in step 21
USAGE = SET / "usage23.jsonl"; CAP = 1.5
PENDING = []


def rows():
    out = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s18/bank/train_set0.jsonl").read_text().splitlines()}
    for f in (ROOT / "arm_s22/bank/tasks").glob("*.json"):
        r = json.loads(f.read_text()); r.pop("_agent_context", None); out[r["instance_id"]] = r
    b = ROOT / "arm_s23/bank/bank_23.jsonl"
    if b.exists():
        out.update({json.loads(l)["instance_id"]: json.loads(l) for l in b.read_text().splitlines()})
    return out


def rule_index():
    idx = dict(json.loads((SET / "set.json").read_text())["tasks"])
    if (EXTRA_SET / "set.json").exists():
        idx.update(json.loads((EXTRA_SET / "set.json").read_text())["tasks"])
    return idx


def results(trees, rerun_only=False):
    out = []
    for t in trees:
        for f in sorted((ROOT / t / "harness/results").glob("*.json")):
            r = json.loads(f.read_text())
            if not r.get("final"):
                continue
            if rerun_only and f.stem not in INVALID21:
                continue
            if not rerun_only and f.stem in INVALID21:
                continue
            out.append(r | {"key": f.stem, "tree": t})
    return out


def _pending_wrap(fn, kind, default):
    def w(*a):
        try:
            return fn(*a)
        except (Exception, SystemExit) as e:  # noqa: BLE001  (OpenAI down / over the cap: the judge did not answer)
            PENDING.append(kind)
            return default | {"judge_pending": f"{type(e).__name__}: {str(e)[:150]}"}
    return w


def init():
    import engine4 as E, judge_note4, judge as J, budget, runs16c
    budget.USAGE = USAGE; budget.CAP = CAP
    judge_note4.CACHE = SET / "judge_note_cache.jsonl"; judge_note4._cache = None
    J.CACHE = SET / "judge_intent_cache.jsonl"; J.USAGE = USAGE; J._cache = None
    E.JUDGE = _pending_wrap(J.judge, "third_label", {"claims": False})
    E.NOTE_JUDGE = _pending_wrap(judge_note4.judge, "note", {"only_actions_or_known": False})
    R = rows(); runs16c._BANK = R


def files_text(ws) -> str:   # as grader/grade4.files_text
    return "\n".join(f"## {p}\n{v[:3000]}" for p, v in ws.items()) or "(none)"


def one(r):
    import yaml, runs16c, engine4 as E, play as P
    import grade as G3
    PENDING.clear()
    try:
        P.BANK = ROOT / ("arm_s23/bank" if r["task"].endswith(("-v22", "-v23")) else "arm_s21/bank")
        L = runs16c.load(r)
        ix = rule_index()[r["task"]]
        d = json.loads((ROOT / ix["rule_file"]).read_text())
        R = {**d["rules"], "_note_env": L["row"]["environment"] + "\n\n# Files on disk at the start\n" + files_text(P.initial(L["row"])[1])}
        owner = (yaml.safe_load(L["row"]["environment"]) or {}).get("owner_email")
        st = L["steps"]
        Lr = E.label_run(R, st, owner)
        done, req = E.completion(R, st[0]["pre"], st[-1]["post"], st[0]["pre_ws"], st[-1]["post_ws"]) if st else (False, {})
        pend = [i for i, s in enumerate(Lr["steps"]) if any(
            (f.get("note_judge") or {}).get("judge_pending") or (f.get("judge") or {}).get("judge_pending") for f in s["findings"])]
        ck = d["checks"]; row = L["row"]
        return {"key": r["key"], "tree": r["tree"], "task": r["task"], "agent": r["agent"], "run": r["run"], "set": "v4.2-set0",
                "rule_set_of": ix["rule_set_of"], "rule_file": ix["rule_file"], "toolkit": row.get("toolkit"),
                "user_instructed": bool(row.get("user_instructed")), "counter_example": bool(row.get("counter_example")),
                "rules_failed_checks": ck.get("failed") or [], "rules_expected_failures": ck.get("expected_failures") or {},
                "labels": [s["label"] for s in Lr["steps"]], "sub_reasons": [s["sub_reason"] for s in Lr["steps"]],
                "findings": [s["findings"] for s in Lr["steps"]], "tools": [s["call"]["name"] for s in st],
                "unsafe": Lr["unsafe"], "intent": Lr["intent"], "final_harm": Lr.get("final_harm"),
                "completion": done, "requirements": req, "outcome": G3.outcome(Lr["unsafe"], Lr["intent"], done),
                "judge_pending_steps": pend, "n_steps": len(st)}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"key": r["key"], "task": r["task"], "crash": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-1500:]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--part4", action="store_true")
    a = ap.parse_args()
    if subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/v4.2-set0"], cwd=ROOT, capture_output=True).returncode:
        sys.exit("no tag v4.2-set0")
    if subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks / engine differ from v4.2-set0: refusing to grade")
    for f in ("judge_note_cache.jsonl", "judge_intent_cache.jsonl"):   # seed from the step-22 dev grading (same prompts)
        if not (SET / f).exists() and (G / "out/v4.2" / f).exists():
            shutil.copy(G / "out/v4.2" / f, SET / f)
    import openai_key
    try:
        openai_key.get("grade23" + (" --part4" if a.part4 else ""))   # once per job; workers inherit the choice
    except Exception as e:  # noqa: BLE001  (judges then mark their steps judge_pending)
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = results(TREES23) + results(["arm_s21/qwen9b"], rerun_only=True) if a.part4 else results(TREES21)
    with ProcessPoolExecutor(a.workers, initializer=init) as ex:
        rows_ = list(ex.map(one, todo, chunksize=2))
    out = SET / ("grades23.jsonl" if a.part4 else "grades21.jsonl")
    out.write_text("".join(json.dumps(x, default=str) + "\n" for x in rows_))
    import budget
    budget.USAGE = USAGE
    print(len(rows_), "runs ->", out.relative_to(ROOT), "; crashed", sum("crash" in x for x in rows_),
          "; judge pending steps", sum(len(x.get("judge_pending_steps") or []) for x in rows_), f"; spend ${budget.spent():.2f}",
          "(key:", openai_key.which(), ")")
    for x in rows_:
        if "crash" in x:
            print(x["key"], x["crash"], x["tb"]); break


if __name__ == "__main__":
    main()
