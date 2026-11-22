"""Step 26 part 4: the run bank for the 22 safe twins and the two -v26 repairs (arm_s26_twins/bank/tasks; copy of
arm_s29/make_bank.py). Harness rows drop the analysis fields (arm_s18/lib.py HIDDEN) and the twin fields (twin_of, pair_id,
twin_type, trap_safe_reference) as well; checkpoints stays as in every earlier harness row (the agent is not shown it). The role
text goes to agent_context_26.json; staged files are already in arm_s26_twins/bank/files.
Writes arm_s26_twins/bank/{tasks.txt, bank_26.jsonl, bank_26_harness.jsonl, agent_context_26.json}.
  .venv/bin/python arm_s26_twins/make_bank.py"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; B = ROOT / "arm_s26_twins/bank"
sys.path.insert(0, str(ROOT / "arm_s18"))
from lib import HIDDEN  # noqa: E402

TWIN = ("twin_of", "pair_id", "twin_type", "trap_safe_reference", "twins")
rows = [json.loads(f.read_text()) for f in sorted((B / "tasks").glob("*.json"))]
assert len(rows) == 24, len(rows)
ctx = {r["instance_id"]: r.pop("_agent_context") for r in rows}
(B / "tasks.txt").write_text("".join(r["instance_id"] + "\n" for r in sorted(rows, key=lambda x: x["instance_id"])))
(B / "bank_26.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
(B / "bank_26_harness.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k not in HIDDEN + TWIN}, ensure_ascii=False)
                                                 + "\n" for r in rows))
(B / "agent_context_26.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
for r in rows:
    for spec in r.get("workspace_files") or []:
        assert (B / spec).exists(), spec
print(len(rows), "tasks")
