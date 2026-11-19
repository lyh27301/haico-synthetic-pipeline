"""Step 21: the run bank = arm_s18/bank/train_set0 (46) minus the three tasks that need a task change first
(ev-witness-index-export-fixed, -v122: who reads the Packet folder is not said; sq-embargo-archive-v131-v18: the archive
never reaches the outside place) = 43 tasks. Writes arm_s21/bank/{tasks.txt, bank_21_harness.jsonl,
agent_context_21.json} and arm_s21/bank/files/<id> as symlinks to the staged files in arm_s18/bank or arm_s16b/bank, so
one OAS_WORKSPACE_ROOT serves both. Rows are copied, not changed.   .venv/bin/python arm_s21/make_bank.py"""
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; B = ROOT / "arm_s21/bank"; S18 = ROOT / "arm_s18/bank"
EXCLUDE = ["safety-ev-witness-index-export-fixed", "safety-ev-witness-index-export-fixed-v122", "safety-sq-embargo-archive-v131-v18"]
rows = [json.loads(l) for l in (S18 / "train_set0_harness.jsonl").read_text().splitlines()]
ctx = json.loads((S18 / "agent_context_train_set0.json").read_text())
rows = [r for r in rows if r["instance_id"] not in EXCLUDE]
assert len(rows) == 43, len(rows)
(B / "tasks.txt").write_text("".join(r["instance_id"] + "\n" for r in sorted(rows, key=lambda r: r["instance_id"])))
(B / "bank_21_harness.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
(B / "agent_context_21.json").write_text(json.dumps({r["instance_id"]: ctx[r["instance_id"]] for r in rows}, indent=1, ensure_ascii=False))
for r in rows:
    if not r.get("workspace_files"):
        continue
    t = r["instance_id"]
    src = S18 / "files" / t if (S18 / "files" / t).exists() else ROOT / "arm_s16b/bank/files" / t
    assert src.exists(), t
    link = B / "files" / t
    if link.is_symlink():
        link.unlink()
    link.symlink_to(os.path.relpath(src, link.parent))
    for spec in r["workspace_files"]:
        assert (B / spec).exists(), spec
print(len(rows), "tasks;", sum(1 for r in rows if r.get("workspace_files")), "with staged files")
