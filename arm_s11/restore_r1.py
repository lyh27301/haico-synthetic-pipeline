"""Step 11: restore Part C's first run 1 attempt (cut off at 17:13 when the endpoint was lost, moved aside, now back
in harness/qwen3.5-9b/r1). Its graded instances become result files (pass 0); its errored instances (all failed on
the lost endpoint) get none, so the restarted run 1 re-queues them with the other 96.
  .venv/bin/python arm_s11/restore_r1.py"""
import json, sys
from pathlib import Path

S11 = Path(__file__).resolve().parent; sys.path.insert(0, str(S11))
from run_harness import H, RES, outputs, record, write  # noqa: E402

got = outputs(H / "qwen3.5-9b" / "r1")
kept, dropped = [], []
for t, (o, base) in sorted(got.items()):
    rec = record(t, "qwen", 1, o, base, rerun=False)
    if not rec["graded"]:
        dropped.append(t); continue
    rec.update({"agent": "qwen3.5-9b", "pass": 0, "restored": "r1 attempt cut off by the 17:13 endpoint loss"})
    write(RES / f"{t}__qwen3.5-9b__r1.json", rec); kept.append(t)
print(json.dumps({"kept_graded": kept, "dropped_endpoint_lost": dropped}, indent=1))
