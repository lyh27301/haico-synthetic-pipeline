"""Step 34 parts 3-4 (code, no model call): which -v34 tasks are kept for training, and the step-29 label table rows of
every graded -v34 run and twin run.

Keep (part 3): a task is kept when at least one run of any agent is a safe completion (outcome honest_success) and at least
one run has a trap-based unsafe step (an unsafe step with a designed finding). Otherwise it is listed with the reason:
  all_safe      no run has a trap-based unsafe step (safe completions exist)
  all_unsafe    no run is a safe completion (trap-based unsafe steps exist)
  stumble       neither: no safe completion and no trap-based unsafe step (the agents fail on something that is not the trap)
Crashed grades do not count either way.

Label rows: arm_s29/labels29.py's columns and rules (label source, train_use), with prohibition_location from
arm_s34/prohibition_location34.jsonl (a twin: 'none (safe twin of <trap>)'). Run-level drop: drop_run_invalid (crashed grade),
drop_run_task (task not kept, with its reason; twins of tasks not kept). On a twin (control, counter_example) an unsafe step
is drop_step, as on step 29's controls.
  .venv/bin/python arm_s34/labels34.py   -> arm_s34/keep34.json, arm_s34/labels34.jsonl, arm_s34/labels34_summary.json"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"
sys.path.insert(0, str(ROOT / "arm_s29"))
import labels29 as L29  # noqa: E402


def jl(f):
    return [json.loads(l) for l in Path(f).read_text().splitlines() if l.strip()] if Path(f).exists() else []


def designed_step(g):
    return any(lab == "unsafe" and any(f.get("label") == "unsafe" and f.get("tag") == "designed" for f in fs)
               for lab, fs in zip(g.get("labels") or [], g.get("findings") or []))


def main():
    G = [g for g in jl(S / "grades34.jsonl")]
    GT = [g for g in jl(S / "twins/grades34t.jsonl")]
    tasks = sorted(json.loads(f.read_text())["instance_id"] for f in (S / "bank/tasks").glob("*.json"))
    P = {r["task"]: r["prohibition_location"] for r in jl(S / "prohibition_location34.jsonl")}
    rows = {json.loads(f.read_text())["instance_id"]: json.loads(f.read_text()) for b in ("bank", "twins")
            for f in (S / b / "tasks").glob("*.json")}
    per = {t: {"runs": 0, "safe_completions": 0, "trap_unsafe_runs": 0, "by_agent": collections.defaultdict(lambda: [0, 0, 0])}
           for t in tasks}
    for g in G:
        if "crash" in g or g["task"] not in per:
            continue
        p = per[g["task"]]; p["runs"] += 1; a = p["by_agent"][g["agent"]]; a[0] += 1
        if g.get("outcome") == "honest_success":
            p["safe_completions"] += 1; a[1] += 1
        if designed_step(g):
            p["trap_unsafe_runs"] += 1; a[2] += 1
    kept, dropped = [], {}
    for t, p in per.items():
        if p["safe_completions"] and p["trap_unsafe_runs"]:
            kept.append(t)
        else:
            dropped[t] = ("all_safe" if p["safe_completions"] else "all_unsafe" if p["trap_unsafe_runs"] else "stumble")
    keep = {"kept": kept, "not_kept": dropped,
            "per_task": {t: {**{k: v for k, v in p.items() if k != "by_agent"},
                             "by_agent (runs, safe completions, runs with a trap-based unsafe step)": dict(p["by_agent"])}
                         for t, p in per.items()}}
    (S / "keep34.json").write_text(json.dumps(keep, indent=1))
    out = []
    for step, gs in (("step34", G), ("step34_twins", GT)):
        for g in gs:
            t = g["task"]; key = g["key"]; r = rows.get(t, {})
            twin_of = r.get("twin_of")
            trap = twin_of or t
            run_drop = ("drop_run_invalid" if "crash" in g else
                        f"drop_run_task" if trap in dropped else None)
            base = {"run_key": key, "grades": step, "task_id": t, "mechanic_id": r.get("mechanic_id"), "agent": g.get("agent"),
                    "run": g.get("run"), "prohibition_location": (f"none (safe twin of {twin_of})" if twin_of else P.get(t)),
                    "completion": g.get("completion"), "outcome": g.get("outcome"), "superseded_by": None, "repair_list": None,
                    "borderline": None, "not_kept": dropped.get(trap), "twin_of": twin_of}
            if "crash" in g:
                out.append(base | {"step": None, "label": None, "label_source": "grade crashed", "train_use": "drop_run_invalid"})
                continue
            ctl = bool(twin_of)
            for i, (lab, fs) in enumerate(zip(g["labels"], g["findings"])):
                src, des = L29.source(lab, fs)
                if ctl and lab == "unsafe":
                    src, des = src + " (control task: no designed trap)", False
                use = run_drop or ("drop_step" if lab == "intent" or (lab == "unsafe" and not des) else "use")
                out.append(base | {"step": i, "tool": g["tools"][i], "label": "third_label" if lab == "intent" else lab,
                                   "label_source": src, "train_use": use})
    (S / "labels34.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    summ = {"rows": len(out), "by_train_use_label": dict(collections.Counter(f"{x['grades']} | {x['train_use']} | {x['label']}" for x in out))}
    (S / "labels34_summary.json").write_text(json.dumps(summ, indent=1))
    print(len(kept), "kept;", "not kept:", dropped)
    print(len(out), "label rows;", summ["by_train_use_label"])


if __name__ == "__main__":
    main()
