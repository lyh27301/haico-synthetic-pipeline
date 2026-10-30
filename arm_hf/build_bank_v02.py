"""Build yanhanliu/haico_synthetic_v0.2: the bank after the step 7 Part A2 hygiene repair (analysis/bank.py) - every
good task of steps 3-6, repaired tasks from their repaired dir, retired tasks left out. Same schema as v0.1.
  python arm_hf/build_bank_v02.py  ->  arm_hf/out_v02/{data/train-00000-of-00001.parquet, manifest.json}"""
import collections, json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "arm_hf"))
from bank import bank, good  # noqa: E402
from build_bank import SCHEMA, row  # noqa: E402

OUT = ROOT / "arm_hf" / "out_v02"


def main():
    g = good(include_s7=False)
    rows = [row(t, Path(v["dir"])) for t, v in sorted(g.items())]
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), OUT / "data" / "train-00000-of-00001.parquet")
    b = bank(include_s7=False)
    man = {"n": len(rows), "by_toolkit": dict(collections.Counter(r["toolkit"] for r in rows)),
           "variants": sum("-v1" in t or "-sal-" in t for t in g), "npc": sum(r["npcs"] for r in rows),
           "repaired": sorted(t for t, v in g.items() if v["status"] == "repaired"),
           "retired": {t: v["reason"] for t, v in b.items() if v["status"] == "retired"},
           "tasks": {t: {"set": v["set"], "status": v["status"], "dir": str(Path(v["dir"]).relative_to(ROOT))}
                     for t, v in sorted(g.items())}}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: v for k, v in man.items() if k not in ("tasks", "retired")}, indent=1), list(man["retired"]))


if __name__ == "__main__":
    main()
