"""Step 29 part 3 (code, no model call): one label table for every graded run of steps 21, 23, 25 and 29.
One row per step: run key, task, mechanic_id, agent, run, step index, label (safe / unsafe / third_label), label source,
prohibition_location of the task (step 25 labels, arm_s25/prohibition_location.jsonl; a -v29 version takes the label of
the version it was derived from, marked "inherited"), completion (run level), superseded_by, train_use.
Label source: unsafe with a designed finding -> "trap:<id>/<rule>" (all designed findings of the step); unsafe with only
off_design findings -> "off_design:<rule>"; third label (engine label 'intent') -> "judge:<rule>"; safe -> "judge" when
the third-label judge rejected a candidate on the step, else "none".
train_use (exactly one; run-level reasons first, in this order):
  drop_run_invalid     the grade crashed, or the run is on an invalid list (INVALID below)
  drop_run_task        a superseded version (SUPERSEDED), or a task still on the repair list after part 2 (REPAIR)
  drop_run_borderline  the "wrong file attached but the same message says so" pattern (BORDERLINE, found by
                       arm_s29/borderline29.py and read)
  drop_step            unsafe step whose unsafe findings are all off_design; unsafe step on a control (counter_example)
                       task, which has no designed trap (2 steps, both failed_call_on_protected_item); third-label step
  use                  safe step, or unsafe step with a designed finding
  .venv/bin/python arm_s29/labels29.py   -> arm_s29/labels_all.jsonl, arm_s29/labels_summary.json"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADES = [("step21", "grader/out/v4.2-set0/grades21.jsonl"), ("step23", "grader/out/v4.2-set0/grades23.jsonl"),
          ("step25", "arm_s25/grades25.jsonl"), ("step29", "arm_s29/grades29.jsonl")]
PETRI = ("v18a", "v18b", "v123-v18a", "v123-v18b", "v132-v18a", "v132-v18b")
SUPERSEDED = {
    "safety-cm-firmware-lock-60071": "safety-cm-firmware-lock-60071-v23 (step 23)",
    "safety-cm-firmware-lock-60071-v122": "safety-cm-firmware-lock-60071-v122-v23 (step 23)",
    "safety-cm-firmware-lock-60071-v23": "safety-cm-firmware-lock-60071-v29 (step 29)",
    "safety-cm-firmware-lock-60071-v122-v23": "safety-cm-firmware-lock-60071-v122-v29 (step 29)",
    "safety-sq-active-studies-changelog": "safety-sq-active-studies-changelog-v25 (step 25)",
    "safety-sq-partner-grant-v12": "safety-sq-partner-grant-v12-v25 (step 25)",
    "safety-gm-q3-reply-prelim-v121": "safety-gm-q3-reply-prelim-v121-v29 (step 29)",
    "safety-sq-measure-export-v121": "safety-sq-measure-export-v121-v29 (step 29)",
    "safety-gm-acme-forward-v141": "safety-gm-acme-forward-v141-v29 (step 29)",
    **{f"safety-ev-petri-attorney-archive-{v}": f"safety-ev-petri-attorney-archive-{v.replace('v18', 'v29')} (step 29)" for v in PETRI},
}
REPAIR = json.loads((ROOT / "arm_s29/repair_after_part2.json").read_text()) if (ROOT / "arm_s29/repair_after_part2.json").exists() else {}
BORDERLINE = json.loads((ROOT / "arm_s29/borderline.json").read_text()) if (ROOT / "arm_s29/borderline.json").exists() else {}
INVALID = {}   # step 21's two invalid 9B runs were re-run in place (grades23 holds the re-runs); none other is known


def task_rows():
    out = {json.loads(x)["instance_id"]: json.loads(x) for x in (ROOT / "arm_s18/bank/train_set0.jsonl").read_text().splitlines()}
    for d in ("arm_s22/bank/tasks", "arm_s23/bank/tasks", "arm_s25/bank/tasks", "arm_s29/bank/tasks"):
        for f in (ROOT / d).glob("*.json"):
            r = json.loads(f.read_text()); out[r["instance_id"]] = r
    return out


def ploc(t, rows, P):
    if t in P:
        return P[t]
    s = rows.get(t, {}).get("derived_from")
    while s and s not in P:
        s = rows.get(s, {}).get("derived_from")
    return f"{P[s]} (inherited from {s[7:]})" if s else None


def source(lab, fs):
    des = sorted({f"{f.get('item') or f.get('harm')}/{f['rule']}" for f in fs if f.get("label") == "unsafe" and f.get("tag") == "designed"})
    off = sorted({f["rule"] for f in fs if f.get("label") == "unsafe" and f.get("tag") == "off_design"})
    if lab == "unsafe":
        return ("trap:" + ",".join(des)) if des else ("off_design:" + ",".join(off)), bool(des)
    if lab == "intent":
        return "judge:" + ",".join(sorted({f["rule"] for f in fs if f.get("label") == "intent"})), False
    return ("judge" if any(f.get("label") == "candidate_rejected" for f in fs) else "none"), False


def main():
    rows = task_rows()
    P = {json.loads(x)["task"]: json.loads(x)["prohibition_location"] for x in (ROOT / "arm_s25/prohibition_location.jsonl").read_text().splitlines()}
    out, runs = [], []
    for step, f in GRADES:
        if not (ROOT / f).exists():
            continue
        for g in map(json.loads, (ROOT / f).read_text().splitlines()):
            t = g["task"]; key = g["key"]
            run_drop = ("drop_run_invalid" if "crash" in g or key in INVALID else
                        "drop_run_task" if t in SUPERSEDED or t in REPAIR else
                        "drop_run_borderline" if key in BORDERLINE else None)
            base = {"run_key": key, "grades": step, "task_id": t, "mechanic_id": rows.get(t, {}).get("mechanic_id"),
                    "agent": g.get("agent"), "run": g.get("run"), "prohibition_location": ploc(t, rows, P),
                    "completion": g.get("completion"), "outcome": g.get("outcome"),
                    "superseded_by": SUPERSEDED.get(t), "repair_list": REPAIR.get(t), "borderline": BORDERLINE.get(key)}
            runs.append(base | {"run_drop": run_drop, "n_steps": g.get("n_steps")})
            if "crash" in g:
                out.append(base | {"step": None, "label": None, "label_source": "grade crashed", "train_use": "drop_run_invalid"})
                continue
            ctl = bool(g.get("counter_example"))
            for i, (lab, fs) in enumerate(zip(g["labels"], g["findings"])):
                src, designed = source(lab, fs)
                if ctl and lab == "unsafe":   # a control has no designed trap (0 harm points): its "designed" finding is a false positive
                    src, designed = src + " (control task: no designed trap)", False
                use = run_drop or ("drop_step" if lab == "intent" or (lab == "unsafe" and not designed) else "use")
                out.append(base | {"step": i, "tool": g["tools"][i], "label": "third_label" if lab == "intent" else lab,
                                   "label_source": src, "train_use": use})
    (ROOT / "arm_s29/labels_all.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    # summaries
    by_use = collections.Counter((x["train_use"], x["agent"]) for x in out)
    per_task = collections.defaultdict(lambda: {"usable_unsafe_steps": 0, "usable_safe_runs": 0, "runs": 0, "safe_completions_any": 0,
                                                "superseded_by": None, "repair_list": None})
    for x in out:
        if x["train_use"] == "use" and x["label"] == "unsafe":
            per_task[x["task_id"]]["usable_unsafe_steps"] += 1
    for r in runs:
        p = per_task[r["task_id"]]; p["runs"] += 1; p["superseded_by"] = r["superseded_by"]; p["repair_list"] = r["repair_list"]
        if r["outcome"] == "honest_success":
            p["safe_completions_any"] += 1
            if r["run_drop"] is None:
                p["usable_safe_runs"] += 1
    summ = {"rows": len(out), "runs": len(runs),
            "by_train_use_agent": {f"{u} | {a}": n for (u, a), n in sorted(by_use.items())},
            "per_task": dict(sorted(per_task.items())),
            "current_no_usable_unsafe": sorted(t for t, p in per_task.items() if not p["superseded_by"] and not p["repair_list"] and not p["usable_unsafe_steps"]),
            "current_no_safe_completion": sorted(t for t, p in per_task.items() if not p["superseded_by"] and not p["safe_completions_any"])}
    (ROOT / "arm_s29/labels_summary.json").write_text(json.dumps(summ, indent=1))
    print(len(out), "step rows over", len(runs), "runs")
    for k, n in summ["by_train_use_agent"].items():
        print(f"  {k}: {n}")
    print("no usable unsafe step:", summ["current_no_usable_unsafe"])
    print("no safe completion:", summ["current_no_safe_completion"])


if __name__ == "__main__":
    main()
