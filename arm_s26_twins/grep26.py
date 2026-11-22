"""Helper (read only): grep a task's environment and staged files.  grep26.py <task> <regex> [context lines]"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "grader"), str(ROOT / "arm_s30")]
import s29  # noqa
s29.patch()
import grade23 as G23  # noqa
r = G23.rows()[sys.argv[1]]; rx = re.compile(sys.argv[2], re.I); n = int(sys.argv[3]) if sys.argv[3:] else 2
lines = r["environment"].splitlines()
for i, l in enumerate(lines):
    if rx.search(l):
        print(f"--- env:{i}"); print("\n".join(lines[max(0, i - n):i + n + 1]))
for spec in r.get("workspace_files") or []:
    p = s29.bank(sys.argv[1]) / spec
    if p.exists() and rx.search(p.read_text(errors="replace")):
        print("--- file", spec); print(p.read_text(errors="replace")[:1500])
