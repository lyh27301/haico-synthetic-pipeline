"""Step 22: grade the 180 stored step-16c runs with the v4.2 rules of the 12 trial tasks (grader/out/v4.2/rules), for
the pilot v3 dev scoring only (grader/score42.py). Same engine (v4), note judge v4 and third-label judge as
grader/grade41.py; its one() is reused with the rules directory switched. Before the tag exists there is no frozen
check; after tagging, it refuses to run when the v4.2 rules, prompts or check code differ from tag v4.2-set0.
Writes grader/out/v4.2/grades.jsonl.   .venv/bin/python grader/grade42.py [--workers 6]"""
import argparse, json, shutil, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT / "arm_s16c"), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]
import grade41 as G41  # noqa: E402

OUT = G / "out/v4.2"
G41.OUT = OUT
FROZEN = ["grader/out/v4.2/rules", "grader/out/v4.2-set0/rules", "grader/prompts", "grader/gen_rules42.py",
          "grader/toolkit_events42.py", "grader/engine4.py", "grader/judge_note4.py"]


def init():
    import engine4 as E, judge_note4, judge as J, budget
    budget.USAGE = G / "out/v4.2-set0/usage.jsonl"; budget.CAP = 3.0
    judge_note4.CACHE = OUT / "judge_note_cache.jsonl"; judge_note4._cache = None
    J.CACHE = OUT / "judge_intent_cache.jsonl"; J.USAGE = G / "out/v4.2-set0/usage.jsonl"; J._cache = None
    E.JUDGE, E.NOTE_JUDGE = J.judge, judge_note4.judge
    G41.OUT = OUT


def one(r):
    x = G41.one(r)
    if "set" in x:
        x["set"] = "v4.2"
    return x


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if not subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/v4.2-set0"], cwd=ROOT, capture_output=True).returncode \
            and subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks differ from v4.2-set0: refusing to grade")
    for f, src in (("judge_note_cache.jsonl", "v4.1"), ("judge_intent_cache.jsonl", "v4.1")):
        if not (OUT / f).exists() and (G / "out" / src / f).exists():
            shutil.copy(G / "out" / src / f, OUT / f)
    import runs16c
    with ProcessPoolExecutor(a.workers, initializer=init) as ex:
        rows = list(ex.map(one, runs16c.results(), chunksize=2))
    (OUT / "grades.jsonl").write_text("".join(json.dumps(x, default=str) + "\n" for x in rows))
    print(len(rows), "runs; crashed", sum("crash" in x for x in rows))
    for x in rows:
        if "crash" in x:
            print(x["key"], x["crash"], x["tb"]); break


if __name__ == "__main__":
    main()
