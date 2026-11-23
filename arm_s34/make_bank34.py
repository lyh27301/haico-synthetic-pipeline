"""Step 34: the run bank of a folder of task rows (copy of arm_s26_twins/make_bank.py). Harness rows drop the analysis
fields (arm_s18/lib.py HIDDEN) and the twin fields; the role text goes to agent_context_34.json; staged files are already in
<folder>/files.   .venv/bin/python arm_s34/make_bank34.py [arm_s34/bank | arm_s34/twins]
Writes <folder>/{tasks.txt, bank_34.jsonl, bank_34_harness.jsonl, agent_context_34.json}."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "arm_s34/bank")
sys.path.insert(0, str(ROOT / "arm_s18"))
from lib import HIDDEN  # noqa: E402

TWIN = ("twin_of", "pair_id", "twin_type", "trap_safe_reference", "twins", "prohibition_location")
rows = [json.loads(f.read_text()) for f in sorted((B / "tasks").glob("*.json"))]
skip = set(json.loads((B / "not_run.json").read_text())) if (B / "not_run.json").exists() else set()
rows = [r for r in rows if r["instance_id"] not in skip]
ctx = {r["instance_id"]: r.pop("_agent_context") for r in rows}
(B / "tasks.txt").write_text("".join(r["instance_id"] + "\n" for r in sorted(rows, key=lambda x: x["instance_id"])))
(B / "bank_34.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
(B / "bank_34_harness.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k not in HIDDEN + TWIN},
                                                            ensure_ascii=False) + "\n" for r in rows))
(B / "agent_context_34.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
for r in rows:
    for spec in r.get("workspace_files") or []:
        assert (B / spec).exists(), spec
print(len(rows), "tasks;", len(skip), "not run")
