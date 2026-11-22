"""Step 30 with step 29's repaired (-v29) tasks: one place for the additions the step-30 scripts need.
  patch()      grade25.patch() (step-25 rows and rules) and then grade29's additions on top of it: the arm_s29/bank rows,
               the rule index grader/out/v4.2-s29/set.json, and arm_s29/bank as the staged-file folder of -v29 tasks
               (grade29 wraps runs16c.load). Frozen v4.2 files are not touched.
  bank(task)   the staged-file folder grade23.one / grade29 use for a task (play.BANK).
  loc()        prohibition locations: arm_s30/source/prohibition_location.jsonl plus the -v29 rows of
               arm_s30/source/prohibition_location_v29.jsonl (built by arm_s30/loc29.py)."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s30"
sys.path.insert(0, str(ROOT / "grader"))


def is29(t):
    return t.endswith(("-v29", "-v29a", "-v29b"))


def patch():
    import grade25, grade23 as G23, grade29
    grade25.patch()
    if getattr(G23.rows, "_s30", False):
        return
    grade29._rows0, grade29._idx0 = G23.rows, G23.rule_index   # grade25's, so step 25 and step 29 rows both stay
    grade29.patch()
    G23.rows._s30 = True if hasattr(G23.rows, "__dict__") else None


def bank(task):
    if is29(task):
        return ROOT / "arm_s29/bank"
    return ROOT / ("arm_s23/bank" if task.endswith(("-v22", "-v23")) else "arm_s21/bank")


def loc():
    out = {}
    for f in ("source/prohibition_location.jsonl", "source/prohibition_location_v29.jsonl"):
        if (S / f).exists():
            out.update({json.loads(l)["task"]: json.loads(l) for l in (S / f).read_text().splitlines()})
    return out


def contexts():
    ctx = {}
    for f in ("arm_s21/bank/agent_context_21.json", "arm_s23/bank/agent_context_23.json",
              "arm_s25/bank/agent_context_25.json", "arm_s29/bank/agent_context_29.json"):
        ctx.update(json.loads((ROOT / f).read_text()))
    return ctx
