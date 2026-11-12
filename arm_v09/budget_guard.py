"""v0.9 budget guard. Every 2 min: spend per Anthropic agent (accumulated_cost in every usage.json under
arm_v09/harness/<agent>/, litellm prices with cache reads / writes) and the OpenAI NPC estimate (gpt-4o-mini chat_npc calls
are not metered: $0.001 per call counted from the conversation histories, an upper bound, as in v0.8). Caps: Haiku batch
$15, Sonnet batch $90, NPC $5 for both batches together. Above a cap every arm_v09 runner is stopped and
arm_v09/harness/budget_stop.json is written. The smoke (arm_v09/smoke) is reported, not counted toward the caps.
  .venv/bin/python arm_v09/budget_guard.py [--once]"""
import glob, json, os, signal, subprocess, sys, time
from pathlib import Path

V = Path(__file__).resolve().parent
CAPS = {"haiku5.5": 15.0, "sonnet5.5": 90.0, "npc": 5.0}
NPC_CALL = 0.001


def spend(tree: Path = V) -> dict:
    s = {a: round(sum(json.loads(Path(f).read_text()).get("accumulated_cost") or 0
                      for f in glob.glob(str(tree / "harness" / a / "**/usage.json"), recursive=True)), 3)
         for a in ("haiku5.5", "sonnet5.5")}
    n = sum(Path(f).read_text().count("chat_npc \\\"")
            for f in glob.glob(str(tree / "harness/**/output.critic_attempt_1.jsonl"), recursive=True))
    return s | {"npc_calls": n, "npc": round(n * NPC_CALL, 3)}


def stop_all():
    pids = subprocess.run(["pgrep", "-f", "arm_v09/run_harness.py"], capture_output=True, text=True).stdout.split()
    for p in pids:
        for c in subprocess.run(["pgrep", "-P", p], capture_output=True, text=True).stdout.split():
            subprocess.run(["pkill", "-TERM", "-P", c]); os.kill(int(c), signal.SIGTERM)
        os.kill(int(p), signal.SIGTERM)
    return pids


if __name__ == "__main__":
    while True:
        s = spend()
        print(time.strftime("%H:%M"), json.dumps(s), "smoke", json.dumps(spend(V / "smoke")), flush=True)
        if "--once" in sys.argv:
            break
        over = [k for k, cap in CAPS.items() if s[k] > cap]
        if over:
            pids = stop_all()
            (V / "harness").mkdir(exist_ok=True)
            (V / "harness/budget_stop.json").write_text(json.dumps({"t": time.time(), "over": over, **s, "stopped": pids}))
            break
        time.sleep(120)
