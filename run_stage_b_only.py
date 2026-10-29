"""Re-run Stage B for an arm on its existing gated_scenarios.jsonl (after a task-writer fix). The previous
funnel and emitted tasks are kept as funnel_<tag>.json / tasks_<tag>/ for the record.

  python run_stage_b_only.py --arm arm_evidence_c --toolkit evidence --target 10 --tag stageB_v1
"""
import argparse, json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe import pipeline, profiles  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--arm", required=True); ap.add_argument("--toolkit", required=True)
ap.add_argument("--target", type=int, required=True); ap.add_argument("--tag", required=True)
a = ap.parse_args()
pipeline.PROFILE = profiles.get(a.toolkit)
arm = Path(a.arm)
shutil.copy(arm / "funnel.json", arm / f"funnel_{a.tag}.json")
if (arm / "tasks").exists():
    shutil.move(str(arm / "tasks"), str(arm / f"tasks_{a.tag}"))
f = json.loads((arm / "funnel.json").read_text())
f.pop("tasks", None); f.pop("task_funnel", None); (arm / "funnel.json").write_text(json.dumps(f, indent=2))
gated = [json.loads(x) for x in (arm / "gated_scenarios.jsonl").read_text().splitlines() if x.strip()]
print(f"stage B only: {len(gated)} scenarios", flush=True)
f = pipeline.run_stage_b(gated, arm, target=a.target, profile=pipeline.PROFILE)
print("TASK FUNNEL", json.dumps(f["task_funnel"]), flush=True)
