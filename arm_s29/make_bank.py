"""Step 29 part 2: the run bank for the 11 repaired versions (arm_s29/bank/tasks; copy of arm_s25/make_bank.py). Harness rows
drop the analysis fields (arm_s18/lib.py HIDDEN) as train_set0_harness does; the role text goes to agent_context_29.json;
staged files are already in arm_s29/bank/files (written by arm_s29/make_tasks.py). Rows are copied, not changed.
Writes arm_s29/bank/{tasks.txt, bank_29.jsonl, bank_29_harness.jsonl, agent_context_29.json}.   .venv/bin/python arm_s29/make_bank.py"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; B = ROOT / "arm_s29/bank"
sys.path.insert(0, str(ROOT / "arm_s18"))
from lib import HIDDEN  # noqa: E402

SRC = [B]
rows = []
for s in SRC:
    for f in sorted((s / "tasks").glob("*.json")):
        rows.append((s, json.loads(f.read_text())))
assert len(rows) == 11, [r["instance_id"] for _, r in rows]
ctx = {r["instance_id"]: r.pop("_agent_context") for _, r in rows}
(B / "tasks.txt").write_text("".join(r["instance_id"] + "\n" for _, r in sorted(rows, key=lambda x: x[1]["instance_id"])))
(B / "bank_29.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for _, r in rows))
(B / "bank_29_harness.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k not in HIDDEN}, ensure_ascii=False) + "\n"
                                                 for _, r in rows))
(B / "agent_context_29.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
for s, r in rows:
    if not r.get("workspace_files") or s == B:
        continue
    t = r["instance_id"]; link = B / "files" / t; link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    link.symlink_to(os.path.relpath(s / "files" / t, link.parent))
    for spec in r["workspace_files"]:
        assert (B / spec).exists(), spec
print(len(rows), "tasks:", [r["instance_id"] for _, r in rows])
