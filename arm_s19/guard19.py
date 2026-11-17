"""Step 19: endpoint guard for the qwen35 runner (arm_s16c/guard16c.py with the step-19 runner's command line): pause the
runner's process tree while the cluster endpoint is down, resume when it answers; no give-up time.
  GUARD_DIR=arm_s19/runs/harness .venv/bin/python arm_s19/guard19.py"""
import os, subprocess, sys
from pathlib import Path

os.environ["GUARD_GIVE_UP_S"] = str(10 * 365 * 86400)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "arm_v08"))
import endpoint_guard as G  # noqa: E402

G.runners = lambda: subprocess.run(["pgrep", "-f", r"run_harness19[.]py --agent qwen35"], capture_output=True, text=True).stdout.split()
G.containers = lambda: []

if __name__ == "__main__":
    assert "s19" in str(G.H), "set GUARD_DIR to arm_s19/runs/harness"
    G.main()
