"""Partial Stage-B rebuild (step 5): keep the arm's emitted tasks that still pass the CURRENT gate (0/0/1, B1/B3,
toolkit extra_check incl. the instruction-anchor check, literal gate), move the others to tasks_dropped_<tag>/,
and rebuild every gated scenario without a kept task, up to --target. The previous funnel is saved as
funnel_<tag>.json.

  python run_stage_b_fill.py --arm arm_medical_c --toolkit medical --target 15 --tag fill1
"""
import argparse, json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe import pipeline, profiles  # noqa: E402
from recipe.graders import dry_run_ok  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--arm", required=True); ap.add_argument("--toolkit", required=True)
ap.add_argument("--target", type=int, required=True); ap.add_argument("--tag", required=True)
a = ap.parse_args()
prof = profiles.get(a.toolkit); pipeline.PROFILE = prof
arm = Path(a.arm)
f = json.loads((arm / "funnel.json").read_text())
shutil.copy(arm / "funnel.json", arm / f"funnel_{a.tag}.json")
gated = [json.loads(x) for x in (arm / "gated_scenarios.jsonl").read_text().splitlines() if x.strip()]
keep, dropped = [], []
for r in f.get("tasks", []):
    if not r.get("dir"):
        continue
    t = prof.TASK_SCHEMA.model_validate_json((Path(r["dir"]) / "scenario.json").read_text())
    why = None
    try:
        if not dry_run_ok(prof.dry_run(t)):
            why = "dry_run"
        why = why or pipeline._bfix_check(t, prof) or pipeline.literal_check(t, prof)[0]
    except Exception as e:  # noqa: BLE001
        why = f"{type(e).__name__}: {e}"
    if why:
        dropped.append({"instance_id": t.instance_id, "idx": r["idx"], "why": str(why)[:200]})
        dd = arm / f"tasks_dropped_{a.tag}"; dd.mkdir(exist_ok=True)
        shutil.move(r["dir"], str(dd / Path(r["dir"]).name))
    else:
        keep.append(r)
print(f"kept {len(keep)}: {[r['instance_id'] for r in keep]}", flush=True)
print(f"dropped {len(dropped)}: {json.dumps(dropped)}", flush=True)
kept_idx = {r["idx"] for r in keep}
todo = [(i + 1, g) for i, g in enumerate(gated) if (i + 1) not in kept_idx]
f.pop("tasks", None); f.pop("task_funnel", None)
f["fill_" + a.tag] = {"kept": [r["instance_id"] for r in keep], "dropped": dropped}
(arm / "funnel.json").write_text(json.dumps(f, indent=2))
print(f"rebuilding {len(todo)} scenarios", flush=True)
out = pipeline.run_stage_b([g for _, g in todo], arm, target=a.target, profile=prof,
                           idx_list=[i for i, _ in todo], keep_rows=keep)
print("TASK FUNNEL", json.dumps(out["task_funnel"]), flush=True)
