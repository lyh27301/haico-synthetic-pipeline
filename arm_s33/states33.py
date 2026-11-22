"""Step 33: where the runs and their stored states are. The base runs (steps 21-29) are in this checkout; the run folders
of step 26 (twins, -v26 repairs) and step 30 (safer runs) are not committed and are read from their worktrees.
  load_states(key, task, source, grades)   runs16c steps (call, pre, pre_ws, ...) of one run"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s31"), str(ROOT / "arm_s30"), str(ROOT / "grader"), str(ROOT), str(ROOT / "harness"),
                str(ROOT / "arm_s16b"), str(ROOT / "arm_s16c")]
import export31 as E31  # noqa: E402

STEP26 = ROOT / ".claude/worktrees/step26"   # step 26's run folders (arm_s26_twins/runs, qwen9b, qwen35)
STEP30 = ROOT / ".claude/worktrees/step30"   # step 30's branch runs
GRADES = E31.GRADES | {"step26": "arm_s26_twins/grades26.jsonl"}
B26 = ROOT / "arm_s26_twins/bank"


def is26(task):
    return task.endswith(("-twin", "-twin2", "-v26"))


def jl(p):
    return E31.jl(p)


_G = {}


def grades():
    if not _G:
        _G.update({(s, g["key"]): g for s, f in GRADES.items() for g in jl(ROOT / f)})
    return _G


def run_dir(tree):
    """The folder a grade row's tree is in: this checkout, else the step-26 worktree."""
    return ROOT if (ROOT / tree / "harness/results").exists() else STEP26


def result(key, source, grades_step):
    if source == "run":
        g = grades()[(grades_step, key)]
        base = run_dir(g["tree"])
        res = json.loads((base / g["tree"] / "harness/results" / f"{key}.json").read_text())
        worktree = STEP26
    else:   # a step-30 safer run
        res = json.loads((ROOT / "arm_s30/runs/harness/results" / f"{key}.json").read_text())
        worktree = STEP30
    for k in ("state_dir", "traj_dir"):
        if not (ROOT / res[k]).exists():
            res[k] = str((worktree / res[k]).relative_to(ROOT))
    return res


_ready = []


def _setup():
    if _ready:
        return
    import grade26, runs16c
    grade26.patch()   # step 25, 29 and 26 bank rows and staged folders (s29.patch inside)
    import grade23 as G23
    runs16c._BANK = G23.rows()
    _ready.append(1)


def load_states(key, task, source="run", grades_step=None):
    import runs16c, play as P, s29
    _setup()
    P.BANK = B26 if is26(task) else s29.bank(task)
    return runs16c.load(result(key, source, grades_step) | {"key": key})
