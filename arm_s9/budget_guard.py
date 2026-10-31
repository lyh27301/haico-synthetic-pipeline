"""Step 9 budget guard (<= $15): every 2 min, total = harness rollout cost (every usage.json under arm_s9/harness,
archives included) + gate/LLM usage logs; above STOP the gpt-5-mini runners are stopped and arm_s9/harness/budget_stop.json
is written (the 5-mini pass is then reported as partial).
  .venv/bin/python arm_s9/budget_guard.py"""
import glob, json, os, signal, subprocess, sys, time
from pathlib import Path
S9 = Path(__file__).resolve().parent; sys.path.insert(0, str(S9.parent / "analysis"))
from aggregate_step4 import cost  # noqa: E402
STOP = 14.5


def spend() -> float:
    h = sum(json.loads(Path(f).read_text()).get("accumulated_cost") or 0
            for f in glob.glob(str(S9 / "harness/**/usage.json"), recursive=True))
    g = sum(sum(cost(Path(f)).values()) for f in glob.glob(str(S9 / "*usage*.jsonl")))
    return h + g


while True:
    s = spend()
    print(time.strftime("%H:%M"), round(s, 3), flush=True)
    if s > STOP:
        pids = subprocess.run(["pgrep", "-f", "run_harness.py --agent 5mini"], capture_output=True, text=True).stdout.split()
        for p in pids:
            for c in subprocess.run(["pgrep", "-P", p], capture_output=True, text=True).stdout.split():
                subprocess.run(["pkill", "-TERM", "-P", c]); os.kill(int(c), signal.SIGTERM)
            os.kill(int(p), signal.SIGTERM)
        (S9 / "harness/budget_stop.json").write_text(json.dumps({"t": time.time(), "spend": s, "stopped": pids}))
        break
    time.sleep(120)
