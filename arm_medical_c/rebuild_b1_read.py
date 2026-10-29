"""One-off (step 5 Part C): rebuild the medical scenarios whose last failure was the B1 read-pivotal bug
(an unauthorized-access scenario whose harmful step is a per-patient read; fixed in medical_profile.pivotal_tool).
Only those scenarios are rebuilt; their old failed rows are replaced, every other row is kept as is."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from recipe import pipeline, profiles  # noqa: E402

prof = profiles.get("medical"); pipeline.PROFILE = prof
arm = ROOT / "arm_medical_c"
f = json.loads((arm / "funnel.json").read_text())
(arm / "funnel_b1fix.json").write_text(json.dumps(f, indent=2))
gated = [json.loads(x) for x in (arm / "gated_scenarios.jsonl").read_text().splitlines() if x.strip()]
redo = [r["idx"] for r in f["tasks"] if not r.get("dir") and str(r.get("err", "")).startswith("B1") and ":read" in str(r.get("err"))]
print("rebuilding", redo, flush=True)
rows = []
for i in redo:
    r = pipeline.build_task(gated[i - 1], i, arm, pipeline.load_exemplars(prof), profile=prof)
    if r["task"] is None:
        rows.append({"idx": i, "status": "failed", "err": r["err"], "trail": r.get("trail"), "rebuild": "b1fix"})
        print(f"  task {i}: FAILED {str(r['err'])[:200]}", flush=True)
        continue
    d = prof.emit(r["task"], arm)
    t = r["task"]
    rows.append({"idx": i, "instance_id": t.instance_id, "dir": d, "hook": t.axes["hook"], "outcome": t.axes["outcome"],
                 "requester_intent": t.axes.get("requester_intent"), "accepted": r["accepted"], "dry": r["dry"],
                 "review_err": r["err"], "attempts": r.get("attempts"), "trail": r.get("trail"), "rebuild": "b1fix"})
    print(f"  task {i}: {t.instance_id} dry={r['dry']}", flush=True)
f["tasks"] = [r for r in f["tasks"] if r["idx"] not in redo] + rows
tf = f["task_funnel"]
built = sum(1 for r in rows if r.get("dir"))
tf["built_sound"] += built; tf["emitted"] += built; tf["failed"] -= built
tf["literal_rejections"] += sum(str(t).startswith("harm_not_on_literal_path") for r in rows for t in (r.get("trail") or []))
f["b1fix_rebuild"] = {"idx": redo, "built": built}
(arm / "funnel.json").write_text(json.dumps(f, indent=2))
print("done", json.dumps(tf), flush=True)
