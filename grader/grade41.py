"""Step 17c: grade4.py for v4.1 (rules grader/out/v4.1, tag v4.1-frozen). Step 17b text follows.
Step 17b: grade the 180 stored step-16c runs with the frozen v4 rules (tag v4-frozen), engine v4, note judge v4 (with
the task's environment text) and the step-16c third-label judge (cache seeded from grader/out/v3/judge_intent_cache.jsonl).
Item 3: every row graded with a rule set that failed any of its nine checks carries
"rules_failed_checks": [<check>, ...] (expected task-flaw failures included, also listed in "rules_expected_failures").
Writes grader/out/v4/grades.jsonl. Refuses to run if the v4 rules, prompts or engine differ from the tag.
  .venv/bin/python grader/grade4.py [--workers 6]"""
import argparse, json, shutil, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"; C = ROOT / "arm_s16c"; OUT = G / "out" / "v4.1"
sys.path[:0] = [str(G), str(C), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]
FROZEN = ["grader/out/v4.1/rules", "grader/prompts", "grader/engine4.py", "grader/judge_note4.py", "grader/gen_rules4.py",
          "grader/gen_rules41.py", "grader/toolkit_events.py"]


def frozen_ok():
    if subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/v4.1-frozen"], cwd=ROOT, capture_output=True).returncode:
        sys.exit("no tag v4.1-frozen")
    if subprocess.run(["git", "diff", "--quiet", "v4.1-frozen", "--", *FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.1 rules / prompts / engine differ from v4.1-frozen: refusing to grade")


def init():
    import engine4 as E, judge_note4, judge as J, budget
    budget.USAGE = OUT / "usage.jsonl"; budget.CAP = 2.0                       # v4.1 spend, not v4's file
    judge_note4.CACHE = OUT / "judge_note_cache.jsonl"; judge_note4._cache = None
    J.CACHE = OUT / "judge_intent_cache.jsonl"; J.USAGE = OUT / "usage.jsonl"; J._cache = None
    E.JUDGE, E.NOTE_JUDGE = J.judge, judge_note4.judge


def files_text(ws) -> str:   # as grader/gen_rules.files_text (not imported: runs16c puts arm_s16b, which has its own
    return "\n".join(f"## {p}\n{v[:3000]}" for p, v in ws.items()) or "(none)"   # gen_rules.py, first on the path)


def one(r):
    import yaml, runs16c, engine4 as E
    import grade as G3
    try:
        L = runs16c.load(r)
        d = json.loads((OUT / "rules" / f"{r['task']}.json").read_text())
        R = d["rules"]
        import play as P
        R = {**R, "_note_env": L["row"]["environment"] + "\n\n# Files on disk at the start\n" + files_text(P.initial(L["row"])[1])}
        owner = (yaml.safe_load(L["row"]["environment"]) or {}).get("owner_email")
        st = L["steps"]
        Lr = E.label_run(R, st, owner)
        done, req = E.completion(R, st[0]["pre"], st[-1]["post"], st[0]["pre_ws"], st[-1]["post_ws"])
        ck = d["checks"]
        return {"key": r["key"], "task": r["task"], "agent": r["agent"], "run": r["run"], "set": "v4.1",
                "rules_failed_checks": ck["failed"], "rules_expected_failures": ck.get("expected_failures") or {},
                "labels": [s["label"] for s in Lr["steps"]], "sub_reasons": [s["sub_reason"] for s in Lr["steps"]],
                "findings": [s["findings"] for s in Lr["steps"]], "tools": [s["call"]["name"] for s in st],
                "unsafe": Lr["unsafe"], "intent": Lr["intent"], "final_harm": Lr.get("final_harm"),
                "completion": done, "requirements": req, "outcome": G3.outcome(Lr["unsafe"], Lr["intent"], done)}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"key": r["key"], "task": r["task"], "crash": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-1200:]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    frozen_ok()
    if not (OUT / "judge_note_cache.jsonl").exists():
        shutil.copy(G / "out/v4/judge_note_cache.jsonl", OUT / "judge_note_cache.jsonl")
    seed = OUT / "judge_intent_cache.jsonl"
    if not seed.exists():
        shutil.copy(G / "out/v4/judge_intent_cache.jsonl", seed)
    import runs16c
    with ProcessPoolExecutor(a.workers, initializer=init) as ex:
        rows = list(ex.map(one, runs16c.results(), chunksize=2))
    (OUT / "grades.jsonl").write_text("".join(json.dumps(x, default=str) + "\n" for x in rows))
    import budget
    budget.USAGE = OUT / "usage.jsonl"
    print(len(rows), "runs; crashed", sum("crash" in x for x in rows), f"spend v4.1 ${budget.spent():.2f}")
    for x in rows:
        if "crash" in x:
            print(x["key"], x["crash"], x["tb"]); break


if __name__ == "__main__":
    main()
