"""Build haico_synthetic v0.8 locally (not published): v0.7's 302 tasks, unchanged membership (at least one validated
unsafe run; decision after step 13e), plus the goodness v2 flags on the step-13f outcomes of record, contaminated runs excluded
(arm_s13/goodness_v2_record.json; was arm_s13/goodness_v2.json, the step-13e outcomes):
  good_4omini_v2  gpt-4o-mini has at least one honest_success run (safe and the task done, grader v4) and one unsafe run
  good_qwen_v2    Qwen3.5-9B: same
  good_any_v2     either
The v0.7 flags (good_4omini, good_qwen, good_any: at least one safe and one unsafe run) stay. The v2 flags are for
contrast-pair selection and reporting only, not membership.

v0.8 task change (step 13f decision 3): for finance, evidence and attachment-carrier gmail tasks, the files the agent's
role can reach are staged on disk, protected ones included (recipe/workspace_files.py): has_workspace = True, workspace_files = the staged
files as files/<task>/workspace/<path> under this folder (the harness resolves them with OAS_WORKSPACE_ROOT pointing
here, or at the HF snapshot); only files the role could not reach are withheld. Those rows get task_version "0.8"; every other row
keeps "0.7". task_changes lists what changed. arm_hf/out_v08/workspace_manifest.json has staged and withheld files per
task. The goodness flags describe v0.7 runs; the v0.8 rows are re-rolled before their flags are recomputed.
Step 13g: the 41 tasks outside those whose stored runs hit a fixed toolkit row (arm_s13/reroll13g.json) are marked in
task_changes for the same batch; their task content and task_version stay.
  .venv/bin/python arm_s13/record13f.py && .venv/bin/python arm_hf/build_bank_v08.py  ->  arm_hf/out_v08/"""
import json, shutil, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "arm_hf/out_v07/data/train-00000-of-00001.parquet"
OUT = ROOT / "arm_hf/out_v08"
V2 = {"good_4omini_v2": "good_4omini", "good_qwen_v2": "good_qwen", "good_any_v2": "good_any"}
sys.path[:0] = [str(ROOT / "arm_s13"), str(ROOT)]


def stage_files(t):
    """Write the role's files for the v0.8 rows; -> {task: (specs, withheld)}."""
    import step13e as E
    from recipe import workspace_files as W
    rows = {r["instance_id"]: r for r in t.to_pylist()}
    car = {o["task"]: o["carrier"] for o in map(json.loads, (ROOT / "arm_s13/outcomes.jsonl").read_text().splitlines())}
    b = E.bank(); files = OUT / "files"
    shutil.rmtree(files, ignore_errors=True)
    out = {}
    for i, r in rows.items():
        if not W.applies(r["toolkit"], car.get(i)):
            continue
        d = ROOT / "arm_s12/tasks" / i if (ROOT / "arm_s12/tasks" / i).exists() else Path(b[i]["dir"])
        g = E.norm_ref(json.loads((d / "scenario.json").read_text())["grader"])
        vis, wh, pr = W.role_files(r["toolkit"], E.yaml_env(r), g)
        specs = []
        for dest, text in sorted(vis.items()):
            rel = Path("files") / i / dest.lstrip("/")          # files/<task>/workspace/<path>
            (OUT / rel).parent.mkdir(parents=True, exist_ok=True); (OUT / rel).write_text(text)
            specs.append(str(rel))
        out[i] = (specs, wh, pr)
    return out


def main():
    t = pq.read_table(SRC)
    g2 = json.loads((ROOT / "arm_s13/goodness_v2_record.json").read_text())["tasks"]
    ids = t.column("instance_id").to_pylist()
    assert set(ids) == set(g2), "goodness_v2 and the v0.7 bank cover different tasks"
    for col, f in V2.items():
        t = t.append_column(pa.field(col, pa.bool_()), pa.array([bool(g2[i][f]) for i in ids], pa.bool_()))
    staged = stage_files(t)
    hw = [i in staged for i in ids]
    t = t.set_column(t.schema.get_field_index("has_workspace"), "has_workspace", pa.array(hw, pa.bool_()))
    wf = t.schema.field("workspace_files").type
    t = t.set_column(t.schema.get_field_index("workspace_files"), pa.field("workspace_files", wf),
                     pa.array([staged[i][0] if i in staged else None for i in ids], wf))
    t = t.append_column("task_version", pa.array(["0.8" if h else "0.7" for h in hw], pa.string()))
    rr = json.loads((ROOT / "arm_s13/reroll13g.json").read_text())["extra_tasks"]   # step 13g re-rolls
    t = t.append_column("task_changes", pa.array(
        [(["workspace_files: every file the role can reach staged on disk, protected ones included"] if h else [])
         + (["re-roll: its runs hit a toolkit row fixed in step 13g (task unchanged)"] if i in rr else [])
         for i, h in zip(ids, hw)], pa.list_(pa.string())))
    (OUT / "workspace_manifest.json").write_text(json.dumps(
        {i: {"staged": [s.split("/", 2)[2] for s in v[0]], "withheld": v[1], "staged_protected": v[2]}
         for i, v in sorted(staged.items())}, indent=1))
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
           "by_toolkit": by, "published": False,
           "task_version": {"0.8": sum(hw), "0.7": len(hw) - sum(hw)},
           "rollout_batch_v08": {"task_files": sum(hw), "toolkit_13g_rerolls": len(rr), "tasks": sum(hw) + len(rr)},
           "toolkits": "step 13g: not-found errors name their lookup; new lookups bank_list_files, inventory_list_alerts, "
                       "teladoc_list_consultations, prescription_list_reminders (arm_s13/toolkit_audit.md)",
           "workspace": {"tasks": len(staged), "staged_files": sum(len(v[0]) for v in staged.values()),
                         "withheld_files": sum(len(v[1]) for v in staged.values()),
                         "staged_protected_files": sum(len(v[2]) for v in staged.values()),
                         "rule": "withhold only what the role cannot reach; reachable-but-protected files are staged",
                         "root": "OAS_WORKSPACE_ROOT=<this folder>; workspace_files are relative to it"}}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
