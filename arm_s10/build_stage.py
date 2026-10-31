"""Step 10: the harness task source = step 9's (arm_s9/bank_s9.jsonl) + the tasks step 9 excluded that pass the
step-10 discoverability gate (arm_s10/gate/<id>.json status pass -> v0.4 row; repaired -> rebuilt from arm_s10/tasks/<id>).
  .venv/bin/python arm_s10/build_stage.py -> arm_s10/bank_s10.jsonl, arm_s10/ids_rescued_c.txt"""
import json, sys
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "arm_hf")); sys.path.insert(0, str(ROOT / "analysis"))
from build_bank import row  # noqa: E402

S10 = ROOT / "arm_s10"


def main():
    v04 = {r["instance_id"]: r for r in pq.read_table(ROOT / "arm_hf/out_v04/data/train-00000-of-00001.parquet").to_pylist()}
    out = [json.loads(x) for x in (ROOT / "arm_s9/bank_s9.jsonl").read_text().splitlines()]
    rescued = []
    for t in (S10 / "ids_excluded15.txt").read_text().split():
        st = json.loads((S10 / "gate" / f"{t}.json").read_text())["status"]
        if st == "undiscoverable":
            continue
        r = v04[t]
        if st == "repaired":
            new = row(t, S10 / "tasks" / t)
            new["agent_models"], new["dependencies"] = r["agent_models"], r["dependencies"]
            r = new
        out.append(r); rescued.append(t)
    with open(S10 / "bank_s10.jsonl.tmp", "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    (S10 / "bank_s10.jsonl.tmp").replace(S10 / "bank_s10.jsonl")
    (S10 / "ids_rescued_c.txt").write_text("\n".join(rescued) + "\n")
    print(len(out), "rows;", len(rescued), "rescued")


if __name__ == "__main__":
    main()
