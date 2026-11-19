"""Step 21: endpoint guard for one Qwen runner (arm_v08/endpoint_guard.py as in 16c / 19): pause the runner's process tree
while its cluster endpoint is down, resume when it answers; no give-up time (waiting in the queue is normal).
  GUARD_DIR=arm_s21/qwen9b/harness QWEN_BASE_URL=http://localhost:8000/v1 .venv/bin/python arm_s21/guard21.py qwen
  GUARD_DIR=arm_s21/qwen35/harness QWEN_BASE_URL=http://localhost:8001/v1 .venv/bin/python arm_s21/guard21.py qwen35"""
import os, subprocess, sys
from pathlib import Path

os.environ["GUARD_GIVE_UP_S"] = str(10 * 365 * 86400)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "arm_v08"))
import endpoint_guard as G  # noqa: E402

AGENT = sys.argv[1]
TREE = os.environ["GUARD_DIR"].rstrip("/").removesuffix("/harness")   # step 23: only the runner of this tree (21 or 23 runner)
G.runners = lambda: subprocess.run(["pgrep", "-f", rf"run_harness2[13][.]py --agent {AGENT} --root {TREE}( |$)"],
                                   capture_output=True, text=True).stdout.split()
G.containers = lambda: []

if __name__ == "__main__":
    assert {"qwen": "qwen9b", "qwen35": "qwen35"}[AGENT] in str(G.H), "GUARD_DIR must be this agent's tree"
    G.main()
