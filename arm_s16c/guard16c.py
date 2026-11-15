"""Step 16c: endpoint guard for the Qwen runner (arm_v08/endpoint_guard.py as in 13j / arm_v10): pause the Qwen runner's
process tree while the cluster endpoint is down, resume when it answers. No give-up time in step 16c (the job may wait
in the queue as long as it takes): GUARD_GIVE_UP_S is set to ten years. Containers are not docker-paused (the other
agents' containers share the machine); a Qwen run that errors during an outage is re-queued by the runner.
  GUARD_DIR=arm_s16c/qwen/harness .venv/bin/python arm_s16c/guard16c.py"""
import os, subprocess, sys
from pathlib import Path

os.environ["GUARD_GIVE_UP_S"] = str(10 * 365 * 86400)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "arm_v08"))
import endpoint_guard as G  # noqa: E402

G.runners = lambda: subprocess.run(["pgrep", "-f", r"run_harness16c[.]py --agent qwen"], capture_output=True, text=True).stdout.split()
G.containers = lambda: []

if __name__ == "__main__":
    assert "qwen" in str(G.H), "set GUARD_DIR to the Qwen tree's harness dir"
    G.main()
