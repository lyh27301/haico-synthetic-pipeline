"""Step 11 Part C: stop the Qwen runners if the vLLM endpoint goes away (cluster job ended or was preempted), instead of
letting every remaining run fail on connection errors. Every 60 s GET <base>/models; after 3 consecutive failures,
SIGTERM every arm_s11/run_harness.py runner (and its run_infer children) and write arm_s11/harness/endpoint_down.json.
  .venv/bin/python arm_s11/endpoint_guard.py"""
import json, os, signal, subprocess, time, urllib.request
from pathlib import Path

H = Path(__file__).resolve().parent / "harness"
URL = os.environ.get("QWEN_BASE_URL", "http://localhost:8000/v1") + "/models"
fails = 0
while True:
    try:
        urllib.request.urlopen(URL, timeout=10).read(); fails = 0
    except Exception as e:  # noqa: BLE001
        fails += 1
        print(time.strftime("%H:%M:%S"), "endpoint check failed", fails, repr(e)[:120], flush=True)
        if fails >= 3:
            pids = subprocess.run(["pgrep", "-f", "arm_s11/run_harness.py"], capture_output=True, text=True).stdout.split()
            for p in pids:
                subprocess.run(["pkill", "-TERM", "-P", p])
                try:
                    os.kill(int(p), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            (H / "endpoint_down.json").write_text(json.dumps({"t": time.time(), "error": repr(e)[:300], "stopped": pids}))
            break
    time.sleep(60)
