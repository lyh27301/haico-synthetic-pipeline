"""Build haico_synthetic v0.8 locally (not published): v0.7's 302 tasks, unchanged membership (at least one validated
unsafe run; decision after step 13e), plus the step-13e goodness v2 flags (arm_s13/goodness_v2.json):
  good_4omini_v2  gpt-4o-mini has at least one honest_success run (safe and the task done, grader v4) and one unsafe run
  good_qwen_v2    Qwen3.5-9B: same
  good_any_v2     either
The v0.7 flags (good_4omini, good_qwen, good_any: at least one safe and one unsafe run) stay. The v2 flags are for
contrast-pair selection and reporting only, not membership.
  .venv/bin/python arm_s13/step13e.py && .venv/bin/python arm_hf/build_bank_v08.py  ->  arm_hf/out_v08/"""
import json
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "arm_hf/out_v07/data/train-00000-of-00001.parquet"
OUT = ROOT / "arm_hf/out_v08"
V2 = {"good_4omini_v2": "good_4omini", "good_qwen_v2": "good_qwen", "good_any_v2": "good_any"}


def main():
    t = pq.read_table(SRC)
    g2 = json.loads((ROOT / "arm_s13/goodness_v2.json").read_text())["tasks"]
    ids = t.column("instance_id").to_pylist()
    assert set(ids) == set(g2), "goodness_v2 and the v0.7 bank cover different tasks"
    for col, f in V2.items():
        t = t.append_column(pa.field(col, pa.bool_()), pa.array([bool(g2[i][f]) for i in ids], pa.bool_()))
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    pq.write_table(t, OUT / "data" / "train-00000-of-00001.parquet")
    rows = t.to_pylist()
    by = {}
    for r in rows:
        b = by.setdefault(r["toolkit"], {"n": 0, **{c: 0 for c in ("good_any", *V2)}})
        b["n"] += 1
        for c in ("good_any", *V2):
            b[c] += r[c]
    man = {"n": len(rows), "membership": "v0.7: at least one validated unsafe run (unchanged)",
           "good": {c: sum(r[c] for r in rows) for c in ("good_4omini", "good_qwen", "good_any", *V2)},
           "by_toolkit": by, "published": False}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
