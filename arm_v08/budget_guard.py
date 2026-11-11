"""v0.8 batch (copy of arm_s12/budget_guard.py, cap $12). Step 12b budget guard (OpenAI <= $30): every 2 min, spend = gpt-4o-mini rollout cost (every usage.json under
arm_v08/harness) + LLM usage logs (arm_v08/*usage*.jsonl: variant generation, gates, discoverability repair) + an NPC
estimate (gpt-4o-mini chat_npc calls are not metered: $0.001 per call, counted from the conversation histories,
an upper bound at <= 5k input + 200 output tokens per call). Above STOP every arm_v08 runner / generator is stopped
and arm_v08/harness/budget_stop.json is written.
  .venv/bin/python arm_v08/budget_guard.py [--once]"""
import glob, json, os, signal, subprocess, sys, time
from pathlib import Path
S12 = Path(__file__).resolve().parent; sys.path.insert(0, str(S12.parent / "analysis"))
from aggregate_step4 import cost  # noqa: E402
STOP = 12.0   # v0.8 batch: $12 OpenAI cap
NPC_CALL = 0.001


def npc_calls() -> int:
    n = 0
    for f in glob.glob(str(S12 / "harness/**/output.critic_attempt_1.jsonl"), recursive=True):
        n += Path(f).read_text().count("chat_npc \\\"")
    return n


def spend() -> dict:
    h = sum(json.loads(Path(f).read_text()).get("accumulated_cost") or 0
            for f in glob.glob(str(S12 / "harness/**/usage.json"), recursive=True))
    g = sum(sum(cost(Path(f)).values()) for f in glob.glob(str(S12 / "*usage*.jsonl")))
    n = npc_calls()
    return {"rollouts": round(h, 3), "generation_gates": round(g, 3), "npc_est": round(n * NPC_CALL, 3), "npc_calls": n,
            "total": round(h + g + n * NPC_CALL, 3)}


def stop_all():
    pids = subprocess.run(["pgrep", "-f", "arm_v08/(run_harness|gen12b).py"], capture_output=True, text=True).stdout.split()
    for p in pids:
        for c in subprocess.run(["pgrep", "-P", p], capture_output=True, text=True).stdout.split():
            subprocess.run(["pkill", "-TERM", "-P", c]); os.kill(int(c), signal.SIGTERM)
        os.kill(int(p), signal.SIGTERM)
    return pids


if __name__ == "__main__":
    while True:
        s = spend()
        print(time.strftime("%H:%M"), json.dumps(s), flush=True)
        if "--once" in sys.argv:
            break
        if s["total"] > STOP:
            pids = stop_all()
            (S12 / "harness").mkdir(exist_ok=True)
            (S12 / "harness/budget_stop.json").write_text(json.dumps({"t": time.time(), **s, "stopped": pids}))
            break
        time.sleep(120)
