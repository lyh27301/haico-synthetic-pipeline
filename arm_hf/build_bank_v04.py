"""Build yanhanliu/haico_synthetic_v0.4 = the whole good bank after step 7 (analysis/bank.good()): v0.3's 52 tasks
plus the step-7 batches (Parts C/D, incl. the new finance/commerce toolkits) and the step-7 variants (Part E).
Same schema and column conventions as v0.3 (agent_models from the result files that classified the task;
dependencies = ["agentdojo:<toolkit>"]).
  python arm_hf/build_bank_v04.py  ->  arm_hf/out_v04/"""
import collections, glob, json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "arm_hf"))
from bank import S7_ARMS, bank, good  # noqa: E402
from build_bank import SCHEMA, row  # noqa: E402
from build_bank_v03 import MODEL, agents_run  # noqa: E402

OUT = ROOT / "arm_hf" / "out_v04"


def main():
    g = good()
    old, rep = agents_run()
    s7 = collections.defaultdict(set)
    for arm in S7_ARMS:
        for f in glob.glob(str(ROOT / arm / "eval/results/*.json")):
            r = json.loads(Path(f).read_text()); s7[r["task"]].add(r["agent"])
    rows = []
    for t, v in sorted(g.items()):
        r = row(t, Path(v["dir"]))
        ran = rep[t] if v["status"] == "repaired" else s7[t] if v["status"] == "new" else old[t]
        r["agent_models"] = ([{"model": MODEL[a], "name": "agent"} for a in ("4omini", "5mini") if a in ran]
                             + [{"model": m["model"], "name": m["name"]} for m in r["agent_models"]])
        r["dependencies"] = [f"agentdojo:{r['toolkit']}"]
        rows.append(r)
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), OUT / "data" / "train-00000-of-00001.parquet")
    origin = lambda v: ("step7_variant" if v["set"] == "arm_s7_variants" else "step7_batch" if v["set"].startswith("arm_s7_")
                        else "steps3-6")
    man = {"n": len(rows), "by_toolkit": dict(collections.Counter(r["toolkit"] for r in rows)),
           "by_origin": dict(collections.Counter(origin(v) for v in g.values())),
           "npc": sum(r["npcs"] for r in rows),
           "agent_models": dict(collections.Counter("+".join(m["model"] for m in r["agent_models"] if m["name"] == "agent")
                                                    for r in rows)),
           "repaired": sorted(t for t, v in g.items() if v["status"] == "repaired"),
           "retired": {t: v["reason"] for t, v in bank().items() if v["status"] == "retired"},
           "tasks": {t: {"set": v["set"], "status": v["status"], "toolkit": v["toolkit"],
                         "dir": str(Path(v["dir"]).relative_to(ROOT))} for t, v in sorted(g.items())}}
    man["by_toolkit_origin"] = dict(collections.Counter(f"{v['toolkit']}/{origin(v)}" for v in g.values()))
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: v for k, v in man.items() if k not in ("tasks", "retired", "repaired")}, indent=1))
    for r in rows:
        if r["npcs"]:
            print(r["instance_id"], r["agent_models"])
    assert all(r["agent_models"] and r["agent_models"][0]["name"] == "agent" for r in rows)


if __name__ == "__main__":
    main()
