"""Step 34: one place for what the step-30 / step-33 scripts need to work on the -v34 tasks and their twins, as
arm_s30/s29.py is for step 29's. Installed as the module `s29` (sys.modules) before those scripts are imported, so they
run unchanged:
  patch()      grader/grade34.patch(): steps 25 / 29 / 26 rows, rules and staged folders, plus arm_s34/bank and
               arm_s34/twins rows, the rule index grader/out/v4.2-s34/set.json and their staged folders
  bank(task)   the staged-file folder of a task (arm_s34/bank, arm_s34/twins, else step 29's choice)
  loc()        prohibition locations: step 29's plus arm_s34/prohibition_location34.jsonl
  contexts()   role texts: step 29's plus agent_context_34.json of arm_s34/bank and arm_s34/twins"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"
sys.path[:0] = [str(ROOT / "grader"), str(ROOT / "arm_s30")]
import s29 as _S29  # noqa: E402  (the real one; grade26 / grade34 keep their reference to it)
import grade34  # noqa: E402


def install():
    sys.modules["s29"] = sys.modules[__name__]


def patch():
    grade34.patch()


def bank(task):
    return grade34.folder(task) or _S29.bank(task)


def loc():
    out = _S29.loc()
    f = S / "prohibition_location34.jsonl"
    if f.exists():
        out.update({json.loads(l)["task"]: json.loads(l) for l in f.read_text().splitlines()})
    return out


def contexts():
    ctx = _S29.contexts()
    for b in ("bank", "twins"):
        f = S / b / "agent_context_34.json"
        if f.exists():
            ctx.update(json.loads(f.read_text()))
    return ctx
