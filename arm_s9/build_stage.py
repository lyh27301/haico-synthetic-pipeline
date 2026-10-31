"""Step 9: the harness task source = v0.4 rows with Part A repairs (arm_s9/tasks/<id>, task.md) and Part B NPC repairs
(arm_s9/npc_tasks/<id>, rebuilt with build_bank.row) applied; undiscoverable tasks dropped.
  .venv/bin/python arm_s9/build_stage.py -> arm_s9/bank_s9.jsonl (+ arm_s9/ids_all.txt, ids_npc.txt)"""
import json, sys
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "arm_hf")); sys.path.insert(0, str(ROOT / "analysis"))
from build_bank import row  # noqa: E402

S9 = ROOT / "arm_s9"


def source_dir(t: str) -> tuple[Path | None, str]:
    """(dir to rebuild the row from, origin) or (None, 'v0.4') to keep the v0.4 row."""
    if (S9 / "npc_tasks" / t).exists():
        return S9 / "npc_tasks" / t, "npc_fix"
    if (S9 / "tasks" / t).exists():
        return S9 / "tasks" / t, "discover_repair"
    return None, "v0.4"


def gate_status(t: str) -> str:
    f = S9 / "gate" / f"{t}.json"
    return json.loads(f.read_text())["status"] if f.exists() else "pass"


def main():
    rows = pq.read_table(ROOT / "arm_hf/out_v04/data/train-00000-of-00001.parquet").to_pylist()
    out, npc = [], []
    for r in rows:
        t = r["instance_id"]
        npc_gate = S9 / "gate_npc" / f"{t}.json"
        if npc_gate.exists():   # repaired NPC task: its own discoverability check (instruction + NPC reply)
            if json.loads(npc_gate.read_text())["status"] == "undiscoverable":
                continue
        elif gate_status(t) == "undiscoverable":
            continue
        d, origin = source_dir(t)
        if d is not None:
            new = row(t, d)
            new["agent_models"] = ([m for m in r["agent_models"] if m["name"] == "agent"]
                                   + [m for m in new["agent_models"] if m["name"] != "agent"])
            new["dependencies"] = r["dependencies"]
            r = new
        out.append(r)
        if r["npcs"]:
            npc.append(t)
    with open(S9 / "bank_s9.jsonl.tmp", "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    (S9 / "bank_s9.jsonl.tmp").replace(S9 / "bank_s9.jsonl")
    (S9 / "ids_all.txt").write_text("\n".join(r["instance_id"] for r in out) + "\n")
    (S9 / "ids_npc.txt").write_text("\n".join(npc) + "\n")
    print(len(out), "rows;", len(npc), "npc")


if __name__ == "__main__":
    main()
