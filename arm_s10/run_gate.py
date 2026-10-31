"""Step 10 Part C: re-run the discoverability gate (recipe/discover_gate.py: literal search + one repair + the new cue
check) with the step-10 Gmail tools on the tasks step 9 excluded as undiscoverable, from their v0.4 instruction.
Same procedure and record as arm_s9/run_gate.py; outputs arm_s10/gate/<task>.json, repaired copies arm_s10/tasks/<task>.
  USAGE_LOG=arm_s10/gate_usage.jsonl .venv/bin/python arm_s10/run_gate.py --only $(cat arm_s10/ids_excluded15.txt)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "arm_s9"))
import run_gate as G  # noqa: E402

G.OUT = ROOT / "arm_s10" / "gate"
G.TASKS = ROOT / "arm_s10" / "tasks"

if __name__ == "__main__":
    G.main()
