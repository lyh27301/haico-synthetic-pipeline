"""Step 26 part 4: grade the runs of the 22 safe twins and the two -v26 repairs (arm_s26_twins/runs, qwen9b, qwen35) exactly
as grader/grade29.py grades step 29's (grade23's loader, engine v4, judges, frozen-tag check, usage file), each run with its
own task's rules: the bank rows of arm_s26_twins/bank and the rule index grader/out/v4.2-s26/set.json are added on top of
step 25's and step 29's (additions outside the tag; grade23.py, grade25.py and grade29.py are not changed). The staged-file
folder (play.BANK) is switched to arm_s26_twins/bank for these tasks by wrapping runs16c.load, as grade29 does.
With --as-trap, every twin run is graded a second time with its TRAP version's rules (rule index entry of twin_of; staged
files and environment still the twin's): a step those rules flag is the same kind of call on the same object as the trap
version's unsafe step. This is how the report measures "takes the path the original's violator takes" and counts the hard
negatives; it is not a label (the twin's own rules give the labels). The -v26 repairs are not in that file.
  .venv/bin/python grader/grade26.py              -> arm_s26_twins/grades26.jsonl
  .venv/bin/python grader/grade26.py --as-trap    -> arm_s26_twins/grades26_as_trap.jsonl"""
import json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "grader"), str(ROOT / "arm_s30")]
import s29  # noqa: E402
import grade23 as G23  # noqa: E402

TREES = ["arm_s26_twins/runs", "arm_s26_twins/qwen9b", "arm_s26_twins/qwen35"]
S26 = ROOT / "grader/out/v4.2-s26/set.json"; B26 = ROOT / "arm_s26_twins/bank"


def is26(t):
    return t.endswith(("-twin", "-twin2", "-v26"))


AS_TRAP = "--as-trap" in sys.argv


def patch():
    s29.patch()   # step 25 and step 29 rows, rules and staged folders
    if getattr(G23.rows, "_s26", False):
        return
    rows0, idx0 = G23.rows, G23.rule_index

    def rows():
        out = rows0()
        for l in (B26 / "bank_26.jsonl").read_text().splitlines():
            r = json.loads(l); out[r["instance_id"]] = r
        return out

    def rule_index():
        idx = idx0(); idx.update(json.loads(S26.read_text())["tasks"])
        if AS_TRAP:
            for l in (B26 / "bank_26.jsonl").read_text().splitlines():
                r = json.loads(l)
                if r.get("twin_of"):
                    idx[r["instance_id"]] = idx[r["twin_of"]]
        return idx
    rows._s26 = True
    G23.rows, G23.rule_index = rows, rule_index
    import runs16c, play as P
    load0 = runs16c.load

    def load(r):
        if is26(r["task"]):
            P.BANK = B26
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
        openai_key.get("grade26")
    except Exception as e:  # noqa: BLE001
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = [r for t in TREES if (ROOT / t / "harness/results").exists() for r in G23.results([t])]
    if AS_TRAP:
        todo = [r for r in todo if not r["task"].endswith("-v26")]
    with ProcessPoolExecutor(4, initializer=init) as ex:
        out = list(ex.map(G23.one, todo, chunksize=1))
    f = ROOT / ("arm_s26_twins/grades26_as_trap.jsonl" if AS_TRAP else "arm_s26_twins/grades26.jsonl")
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
