"""Step 7 Part A2: re-evaluate the repaired tasks only - 5 x gpt-4o-mini (temp 1.0), then 5 x gpt-5-mini (reasoning
low) on those all_safe / all_unsafe under 4o-mini (the standard step-7 evaluation, so a task that was good only via
5-mini is judged the same way). Results -> arm_step7/a2/eval/results (atomic, resumable).

  python arm_step7/a2/eval.py
"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT))
os.environ.setdefault("USAGE_LOG", str(HERE / "eval" / "usage.jsonl"))
(HERE / "eval").mkdir(exist_ok=True)
import driver, run_batch  # noqa: E402

OUT = HERE / "eval"


def manifest():
    rows = []
    for r in json.loads((HERE / "repairs.json").read_text()):
        if r["status"] != "repaired":
            continue
        tdir = Path(r["dir"]); prof = driver.profile_for(tdir)
        task = prof.TASK_SCHEMA.model_validate_json((tdir / "scenario.json").read_text())
        rows.append({"task": task.instance_id, "dir": str(tdir), "toolkit": prof.NAME, "seed": "repair",
                     "seed_id": r["set"], "hook": task.axes.get("hook"), "outcome": task.axes.get("outcome"),
                     "cue_salience": task.axes.get("cue_salience"), "cue_ids": prof.cue_ids(task)})
    return rows


def bucket(task, label):
    us = [json.loads(f.read_text())["unsafe"] for f in (OUT / "results").glob(f"{task}__{label}__a*.json")]
    us = [int(u) for u in us if u != ""]
    return None if not us else "all_unsafe" if all(us) else "all_safe" if not any(us) else "mixed"


def main():
    rows = manifest()
    os.environ["USAGE_TAG"] = "rollout_4omini"
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda m: run_batch.run_task(m, "4omini", OUT, 1800), rows))
    extreme = [m for m in rows if bucket(m["task"], "4omini") in ("all_safe", "all_unsafe")]
    print(f"5-mini pass on {len(extreme)} extremes", flush=True)
    os.environ["USAGE_TAG"] = "rollout_5mini"
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda m: run_batch.run_task(m, "5mini", OUT, 1800), extreme))
    print("EVAL DONE", flush=True)


if __name__ == "__main__":
    main()
