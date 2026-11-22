"""Step 29 part 2: grade the runs of the 11 repaired versions (arm_s29/runs, arm_s29/qwen9b, arm_s29/qwen35) exactly as
grader/grade25.py grades step 25's (grade23's loader, engine v4, judges, frozen-tag check, usage file), with the bank rows
of arm_s29/bank and the rule index grader/out/v4.2-s29/set.json added (additions outside the tag). grade23.py is not
changed: its rows() and rule_index() are extended here, and its staged-file folder (chosen by task suffix inside one())
is switched to arm_s29/bank for -v29 tasks by wrapping runs16c.load, which one() calls right after choosing it.
  .venv/bin/python grader/grade29.py   -> arm_s29/grades29.jsonl"""
import json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "grader"))
import grade23 as G23  # noqa: E402

TREES = ["arm_s29/runs", "arm_s29/qwen9b", "arm_s29/qwen35"]
S29 = ROOT / "grader/out/v4.2-s29/set.json"; B29 = ROOT / "arm_s29/bank"
_rows0, _idx0 = G23.rows, G23.rule_index


def is29(t):
    return t.endswith("-v29") or t.endswith(("-v29a", "-v29b"))


def rows():
    out = _rows0()
    for l in (B29 / "bank_29.jsonl").read_text().splitlines():
        r = json.loads(l); out[r["instance_id"]] = r
    return out


def rule_index():
    idx = _idx0(); idx.update(json.loads(S29.read_text())["tasks"]); return idx


def patch():
    G23.rows = rows; G23.rule_index = rule_index
    import runs16c, play as P
    if getattr(runs16c.load, "_s29", False):
        return
    load0 = runs16c.load

    def load(r):
        if is29(r["task"]):
            P.BANK = B29
        return load0(r)
    load._s29 = True
    runs16c.load = load


def init():
    patch(); G23.init()


def main():
    patch(); G23.init()
    if subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *G23.FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks / engine differ from v4.2-set0: refusing to grade")
    sys.path.insert(0, str(ROOT)); import openai_key
    try:
        openai_key.get("grade29")
    except Exception as e:  # noqa: BLE001
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = [r for t in TREES if (ROOT / t / "harness/results").exists() for r in G23.results([t])]
    with ProcessPoolExecutor(4, initializer=init) as ex:
        out = list(ex.map(G23.one, todo, chunksize=1))
    f = ROOT / "arm_s29/grades29.jsonl"
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
