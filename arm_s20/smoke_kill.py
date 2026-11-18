"""Step 20 Part A smoke test helper: kill one run by hand in the middle, the way the watchdog does (docker stop + a 404
server on the agent-server port), WITHOUT writing capped.jsonl, so only the harness's own check and the runner can
notice. Waits until the run's container has recorded MIN_STEPS agent steps (/var/lib/.oh16b/steps), then kills once.
(First try, arm_s20/smoke: triggered on log lines, the kill landed while the container was starting and the framework
simply started another one; so the trigger is now the steps the container itself recorded.)
  .venv/bin/python arm_s20/smoke_kill.py arm_s20/smoke2 <task> [MIN_STEPS]"""
import glob, json, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tree, task = ROOT / sys.argv[1], sys.argv[2]
MIN = int(sys.argv[3]) if len(sys.argv) > 3 else 3
CID = re.compile(r"Started container: ([0-9a-f]{64})")
t0 = time.time()
while time.time() - t0 < 1800:
    logs = glob.glob(str(tree / f"harness/*/r1_a1/**/logs/instance_{task}.log"), recursive=True)
    if logs:
        txt = Path(logs[0]).read_text(errors="replace")
        ids = CID.findall(txt)
        n = 0
        if ids:
            r = subprocess.run(["docker", "exec", ids[-1], "sh", "-c", "ls /var/lib/.oh16b/steps 2>/dev/null | wc -l"],
                               capture_output=True, text=True)
            n = int(r.stdout.strip() or 0) if r.returncode == 0 else 0
        if ids and n >= MIN:
            cid = ids[-1]
            port = subprocess.run(["docker", "port", cid, "8000"], capture_output=True, text=True).stdout.split(":")[-1].strip()
            subprocess.run(["docker", "stop", "-t", "5", cid], capture_output=True)
            if port.isdigit():
                subprocess.Popen([sys.executable, str(ROOT / "arm_v08/serve404.py"), port], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            rec = {"t": time.time(), "killed": cid[:12], "after_steps": n, "log": str(Path(logs[0]).relative_to(ROOT))}
            (tree / "hand_kill.json").write_text(json.dumps(rec, indent=1)); print(rec, flush=True)
            sys.exit(0)
    time.sleep(0.3)
sys.exit("no run to kill")
