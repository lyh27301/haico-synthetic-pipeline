"""Step 25 parts 4-5: grade the runs of the two repaired versions (arm_s25/runs, arm_s25/qwen9b, arm_s25/qwen35) exactly as
grader/grade23.py grades the step-21 / step-23 runs (same loader, engine v4, judges, frozen-tag check, usage file), with
the bank rows of arm_s25/bank and the rule index grader/out/v4.2-s25/set.json added (additions outside the tag, like
step 23's two versions). grade23.py itself is not changed: its rows() and rule_index() are extended here.
  .venv/bin/python grader/grade25.py   -> arm_s25/grades25.jsonl"""
import json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "grader"))
import grade23 as G23  # noqa: E402

TREES = ["arm_s25/runs", "arm_s25/qwen9b", "arm_s25/qwen35"]
S25 = ROOT / "grader/out/v4.2-s25/set.json"
_rows0, _idx0 = G23.rows, G23.rule_index


def rows():
    out = _rows0()
    for l in (ROOT / "arm_s25/bank/bank_25.jsonl").read_text().splitlines():
        r = json.loads(l); out[r["instance_id"]] = r
    return out


def rule_index():
    idx = _idx0(); idx.update(json.loads(S25.read_text())["tasks"]); return idx


def patch():
    G23.rows = rows; G23.rule_index = rule_index


def init():
    patch(); G23.init()


def main():
    patch()
    if subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *G23.FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks / engine differ from v4.2-set0: refusing to grade")
    sys.path.insert(0, str(ROOT)); import openai_key
    try:
        openai_key.get("grade25")
    except Exception as e:  # noqa: BLE001
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = [r for t in TREES if (ROOT / t / "harness/results").exists() for r in G23.results([t])]
    with ProcessPoolExecutor(4, initializer=init) as ex:
        out = list(ex.map(G23.one, todo, chunksize=1))
    f = ROOT / "arm_s25/grades25.jsonl"
    f.write_text("".join(json.dumps(x, default=str) + "\n" for x in out))
    import budget
    budget.USAGE = G23.USAGE
    print(len(out), "runs ->", f.relative_to(ROOT), "; crashed", sum("crash" in x for x in out), "; judge pending steps",
          sum(len(x.get("judge_pending_steps") or []) for x in out), f"; spend ${budget.spent():.2f}", "(key:", openai_key.which(), ")")
    for x in out:
        if "crash" in x:
            print(x["key"], x["crash"], x["tb"]); break


if __name__ == "__main__":
    main()
