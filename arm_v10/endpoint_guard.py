"""Step 13j / 14: arm_v08/endpoint_guard.py for the Qwen runners only, while gpt-4o-mini / Claude runners share the
machine. Differences: the runner pattern matches only Qwen runners (arm_v09/run_harness.py --agent qwen and the
step-14 Qwen branch runner), and containers are NOT docker-paused (the guard cannot tell a Qwen run's agent-server
from a Claude one); a Qwen run that errors during an outage is re-queued by the runner as endpoint_lost.
GUARD_DIR must point at the Qwen tree's harness dir (arm_v10/qwen/harness), so its paused / endpoint_down files never
reach the other runners.
  GUARD_DIR=arm_v10/qwen/harness .venv/bin/python arm_v10/endpoint_guard.py"""
import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "arm_v08"))
import endpoint_guard as G  # noqa: E402

G.runners = lambda: subprocess.run(["pgrep", "-f", r"(run_harness[.]py --agent qwen|arm_s14/branch[.]py .*qwen)"],
                                   capture_output=True, text=True).stdout.split()
G.containers = lambda: []

if __name__ == "__main__":
    assert "qwen" in str(G.H), "set GUARD_DIR to the Qwen tree's harness dir"
    G.main()
