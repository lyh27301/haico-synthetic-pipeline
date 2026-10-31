"""Step 10 budget guard (<= $20): every 2 min, total = harness rollout cost (every usage.json under arm_s10/harness)
+ LLM usage logs (arm_s10/*usage*.jsonl: gate extraction/repair/judge). Above STOP every arm_s10/run_harness.py runner
is stopped and arm_s10/harness/budget_stop.json is written.
  .venv/bin/python arm_s10/budget_guard.py"""
import glob, json, os, signal, subprocess, sys, time
from pathlib import Path
S10 = Path(__file__).resolve().parent; sys.path.insert(0, str(S10.parent / "analysis"))
from aggregate_step4 import cost  # noqa: E402
STOP = 19.0


def spend() -> float:
    h = sum(json.loads(Path(f).read_text()).get("accumulated_cost") or 0
            for f in glob.glob(str(S10 / "harness/**/usage.json"), recursive=True))
    g = sum(sum(cost(Path(f)).values()) for f in glob.glob(str(S10 / "*usage*.jsonl")))
    return h + g


if __name__ == "__main__":
    while True:
        s = spend()
        print(time.strftime("%H:%M"), round(s, 3), flush=True)
        if s > STOP:
            pids = subprocess.run(["pgrep", "-f", "arm_s10/run_harness.py"], capture_output=True, text=True).stdout.split()
            for p in pids:
                for c in subprocess.run(["pgrep", "-P", p], capture_output=True, text=True).stdout.split():
                    subprocess.run(["pkill", "-TERM", "-P", c]); os.kill(int(c), signal.SIGTERM)
                os.kill(int(p), signal.SIGTERM)
            (S10 / "harness/budget_stop.json").write_text(json.dumps({"t": time.time(), "spend": s, "stopped": pids}))
            break
        time.sleep(120)
