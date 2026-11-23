"""Step 34: grade the runs of the -v34 tasks (arm_s34/runs, qwen9b, qwen35) and of their safe twins (arm_s34/twins/runs,
qwen9b, qwen35) exactly as grader/grade26.py grades step 26's (grade23's loader, engine v4, judges, frozen-tag check, usage
file), each run with its own task's rules: the bank rows of arm_s34/bank and arm_s34/twins and the rule index
grader/out/v4.2-s34/set.json are added on top of steps 25 / 29 / 26 (grade23.py and the other graders are not changed). The
staged-file folder (play.BANK) is switched to the task's own folder for these tasks by wrapping runs16c.load.
With --as-trap, every twin run is graded a second time with its trap version's rules (as grade26 --as-trap): the pair
measure and the hard negatives.
  .venv/bin/python grader/grade34.py [--twins] [--as-trap]
      -> arm_s34/grades34.jsonl | arm_s34/twins/grades34t.jsonl | arm_s34/twins/grades34t_as_trap.jsonl"""
import json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "grader"), str(ROOT / "arm_s30")]
import grade26  # noqa: E402  (step 25 / 29 / 26 rows, rules and staged folders)
import grade23 as G23  # noqa: E402

S34 = ROOT / "grader/out/v4.2-s34/set.json"
B34, B34T = ROOT / "arm_s34/bank", ROOT / "arm_s34/twins"
TWINS = "--twins" in sys.argv or "--as-trap" in sys.argv
AS_TRAP = "--as-trap" in sys.argv
TREES = ["arm_s34/twins/runs", "arm_s34/twins/qwen9b", "arm_s34/twins/qwen35"] if TWINS else \
        ["arm_s34/runs", "arm_s34/qwen9b", "arm_s34/qwen35"]


def bank_rows(b):
    f = b / "bank_34.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def folder(t):
    if t.endswith(("-v34-twin", "-v34-twin2")):
        return B34T
    if t.endswith("-v34"):
        return B34


def patch():
    grade26.AS_TRAP = False
    grade26.patch()
    if getattr(G23.rows, "_s34", False):
        return
    rows0, idx0 = G23.rows, G23.rule_index

    def rows():
        out = rows0()
        for b in (B34, B34T):
            out.update({r["instance_id"]: r for r in bank_rows(b)})
        return out

    def rule_index():
        idx = idx0(); idx.update(json.loads(S34.read_text())["tasks"])
        if AS_TRAP:
            for r in bank_rows(B34T):
                if r.get("twin_of"):
                    idx[r["instance_id"]] = idx[r["twin_of"]]
        return idx
    rows._s34 = True
    G23.rows, G23.rule_index = rows, rule_index
    import runs16c, play as P
    load0 = runs16c.load

    def load(r):
        b = folder(r["task"])
        if b is not None:
            P.BANK = b
        return load0(r)
    runs16c.load = load


def init():
    patch(); G23.init()


def main():
    patch(); G23.init()
    if subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *G23.FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks / engine differ from v4.2-set0: refusing to grade")
    sys.path.insert(0, str(ROOT)); import openai_key
    try:
        openai_key.get("grade34")
    except Exception as e:  # noqa: BLE001
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = [r for t in TREES if (ROOT / t / "harness/results").exists() for r in G23.results([t])]
    with ProcessPoolExecutor(4, initializer=init) as ex:
        out = list(ex.map(G23.one, todo, chunksize=1))
    f = ROOT / ("arm_s34/twins/grades34t_as_trap.jsonl" if AS_TRAP else
                "arm_s34/twins/grades34t.jsonl" if TWINS else "arm_s34/grades34.jsonl")
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
