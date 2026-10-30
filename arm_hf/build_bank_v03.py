"""Build yanhanliu/haico_synthetic_v0.3 = v0.2's 52 tasks with two column changes:
- agent_models: every model the task was evaluated with, as {"model", "name": "agent"} (gpt-4o-mini; gpt-5-mini where
  its pass ran), followed by the simulated NPC's model {"model": "gpt-4o-mini", "name": <npc name>} for NPC tasks.
  Taken from the result files that classified the task (the Part A2 re-run for repaired tasks).
- dependencies: ["agentdojo:<toolkit>"].
agent_scenarios / agent_profiles are unchanged: filled from scenarios.json for the 2 NPC tasks, [] otherwise (as v1.1
does for its npcs = 0 rows).
  python arm_hf/build_bank_v03.py  ->  arm_hf/out_v03/"""
import collections, glob, json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "arm_hf"))
from bank import bank, good  # noqa: E402
from build_bank import SCHEMA, row  # noqa: E402
from step7_regression import RESULTS  # noqa: E402

OUT = ROOT / "arm_hf" / "out_v03"
MODEL = {"4omini": "gpt-4o-mini", "5mini": "gpt-5-mini"}


def agents_run():
    old, rep = collections.defaultdict(set), collections.defaultdict(set)
    for d in RESULTS:
        for f in glob.glob(str(ROOT / d / "*.json")):
            r = json.loads(Path(f).read_text()); old[r["task"]].add(r["agent"])
    for f in glob.glob(str(ROOT / "arm_step7/a2/eval/results/*.json")):
        r = json.loads(Path(f).read_text()); rep[r["task"]].add(r["agent"])
    return old, rep


def main():
    g = good(include_s7=False)
    old, rep = agents_run()
    rows = []
    for t, v in sorted(g.items()):
        r = row(t, Path(v["dir"]))
        ran = rep[t] if v["status"] == "repaired" else old[t]
        r["agent_models"] = ([{"model": MODEL[a], "name": "agent"} for a in ("4omini", "5mini") if a in ran]
                             + [{"model": m["model"], "name": m["name"]} for m in r["agent_models"]])
        r["dependencies"] = [f"agentdojo:{r['toolkit']}"]
        rows.append(r)
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), OUT / "data" / "train-00000-of-00001.parquet")
    man = json.loads((ROOT / "arm_hf/out_v02/manifest.json").read_text())
    man["agent_models"] = dict(collections.Counter("+".join(m["model"] for m in r["agent_models"] if m["name"] == "agent")
                                                   for r in rows))
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(len(rows), man["agent_models"], collections.Counter(r["dependencies"][0] for r in rows))
    for r in rows:
        if r["npcs"]:
            print(r["instance_id"], r["agent_models"])


if __name__ == "__main__":
    main()
