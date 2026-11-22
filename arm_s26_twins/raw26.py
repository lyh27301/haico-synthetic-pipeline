"""Helper (read only): print raw environment lines a..b of a task.  raw26.py <task> <a> <b>"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "grader"), str(ROOT / "arm_s30")]
import s29  # noqa
s29.patch()
import grade23 as G23  # noqa
L = G23.rows()[sys.argv[1]]["environment"].splitlines()
for i in range(int(sys.argv[2]), int(sys.argv[3]) + 1):
    print(i, repr(L[i]))
