"""Part D eval: 15 salience variants x 5 gpt-4o-mini (temp 1.0) rollouts, via run_batch.run_task (resumable).
Cue-read is recomputed post hoc from the rich records as a TEXT test (a distinctive cue snippet appears in any
tool result before the first state change), so it is comparable across loud/medium/quiet placements."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent; sys.path.insert(0, str(ROOT))
import run_batch  # noqa: E402

OUT = HERE / "eval"


def main():
    os.environ.setdefault("USAGE_LOG", str(OUT / "usage.jsonl")); os.environ["USAGE_TAG"] = "rollout_4omini"
    rows = json.loads((HERE / "variants.json").read_text())
    man = [{"task": r["task"], "dir": r["dir"], "toolkit": "gmail", "seed": "variant", "seed_id": r["scenario"],
            "hook": "", "outcome": "", "cue_salience": r["salience"], "cue_ids": []} for r in rows]
    OUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda m: run_batch.run_task(m, "4omini", OUT, 3600), man))
    print("D EVAL DONE", flush=True)


if __name__ == "__main__":
    main()
