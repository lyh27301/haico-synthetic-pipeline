"""Build yanhanliu/haico_synthetic_v0.1: every step 3-6 task classified good (mixed under either agent), sources
and variants, mapped onto the openagentsafety_v1.1 schema + one extra column `toolkit`.
  python arm_hf/build_bank.py  ->  arm_hf/out/data/train-00000-of-00001.parquet + arm_hf/out/manifest.json"""
import collections, json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT))
from step7_regression import classes, dirs  # noqa: E402  (results of steps 3-6 + every task dir)

V11 = pq.read_schema(ROOT / "arm_hf/v11/data/train-00000-of-00001.parquet")
SCHEMA = pa.schema([V11.field(n) for n in V11.names] + [pa.field("toolkit", pa.string())])


def row(name, d):
    sc = json.loads((d / "scenarios.json").read_text())
    task = json.loads((d / "scenario.json").read_text())
    tk = (d / "toolkit.txt").read_text().strip() if (d / "toolkit.txt").exists() else "gmail"
    npc = bool(sc.get("goal"))
    ck = task.get("checkpoint_text") or ""
    return {
        "instance_id": name,
        "problem_statement": (d / "task.md").read_text(),
        "dependencies": None,
        "checkpoints": ("# Checkpoints\n\nThere is 1 point in total.\n\n## Checkpoint 1 (1 pt)\n\n" + ck.strip() + "\n") if ck else None,
        "agent_profiles": [{"data": {"age": None, "first_name": sc.get("name"), "gender": None, "gender_pronoun": None,
                                     "last_name": None, "occupation": None, "public_info": sc.get("persona") or None},
                            "name": sc.get("name")}] if npc else [],
        "agent_scenarios": [{"data": {"extra_info": sc.get("extra_info"), "goal": sc.get("goal"),
                                      "strategy_hint": sc.get("strategy_hint")}, "name": sc.get("name")}] if npc else [],
        "agent_models": [{"model": "gpt-4o-mini", "name": sc.get("name")}] if npc else [],
        "environment": (d / "environment.yaml").read_text(),
        "npcs": 1 if npc else 0,
        "has_workspace": False, "workspace_files": None,
        "has_utils": False, "utils_files": None,
        "evaluator_code": (d / "evaluator.py").read_text(),
        "github_url": None,
        "toolkit": tk,
    }


def main():
    cls = classes()
    good = {t: (g, d) for t, (g, d) in dirs().items() if cls.get(t) == "good"}
    rows = [row(t, d) for t, (g, d) in sorted(good.items())]
    out = ROOT / "arm_hf/out/data"; out.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), out / "train-00000-of-00001.parquet")
    man = {"n": len(rows), "by_toolkit": dict(collections.Counter(r["toolkit"] for r in rows)),
           "by_set": dict(collections.Counter(g for g, _ in good.values())),
           "variants": sum("-v1" in t or "-sal-" in t for t in good), "npc": sum(r["npcs"] for r in rows),
           "tasks": {t: {"set": g, "dir": str(d.relative_to(ROOT))} for t, (g, d) in sorted(good.items())}}
    (ROOT / "arm_hf/out/manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: v for k, v in man.items() if k != "tasks"}, indent=1))


if __name__ == "__main__":
    main()
