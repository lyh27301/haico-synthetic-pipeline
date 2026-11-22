"""Step 33 part 3: label-table rows for the step-26 runs (the 22 safe twins and the two -v26 repairs), in the format of
arm_s29/labels_all.jsonl and with the same rules (arm_s29/labels29.py: label, label_source, train_use; imported, not
copied). A twin is a control (counter_example), so as in step 29 an unsafe step on it is drop_step (the twin has no
designed trap of the trap version; a side trap it still has is kept as the label but not used) and a third-label step
(the customers-q4 and case-study twins' forwards) is drop_step. No twin or repair is superseded or on the repair list.
prohibition_location: a -v26 repair inherits its source version's (as labels29.ploc); a twin has none ("twin of <id>").
  .venv/bin/python arm_s33/labels33.py   -> arm_s33/labels26.jsonl"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arm_s29"))
import labels29 as L29  # noqa: E402

GRADES26 = ROOT / "arm_s26_twins/grades26.jsonl"


def main():
    rows = L29.task_rows()
    for f in (ROOT / "arm_s26_twins/bank/tasks").glob("*.json"):
        r = json.loads(f.read_text()); rows[r["instance_id"]] = r
    P = {json.loads(x)["task"]: json.loads(x)["prohibition_location"]
         for x in (ROOT / "arm_s25/prohibition_location.jsonl").read_text().splitlines()}
    out = []
    for g in map(json.loads, GRADES26.read_text().splitlines()):
        t = g["task"]; key = g["key"]; r = rows[t]
        run_drop = ("drop_run_invalid" if "crash" in g else
                    "drop_run_task" if t in L29.SUPERSEDED or t in L29.REPAIR else None)
        base = {"run_key": key, "grades": "step26", "task_id": t, "mechanic_id": r.get("mechanic_id"), "agent": g.get("agent"),
                "run": g.get("run"),
                "prohibition_location": f"none (twin of {r['twin_of']})" if r.get("twin_of") else L29.ploc(t, rows, P),
                "completion": g.get("completion"), "outcome": g.get("outcome"), "superseded_by": L29.SUPERSEDED.get(t),
                "repair_list": L29.REPAIR.get(t), "borderline": None, "twin_of": r.get("twin_of")}
        if "crash" in g:
            out.append(base | {"step": None, "label": None, "label_source": "grade crashed", "train_use": "drop_run_invalid"})
            continue
        ctl = bool(g.get("counter_example"))
        for i, (lab, fs) in enumerate(zip(g["labels"], g["findings"])):
            src, designed = L29.source(lab, fs)
            if ctl and lab == "unsafe":
                src, designed = src + " (control task: no designed trap)", False
            use = run_drop or ("drop_step" if lab == "intent" or (lab == "unsafe" and not designed) else "use")
            out.append(base | {"step": i, "tool": g["tools"][i], "label": "third_label" if lab == "intent" else lab,
                               "label_source": src, "train_use": use})
    (ROOT / "arm_s33/labels26.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    c = collections.Counter((x["twin_of"] is not None, x["label"], x["train_use"]) for x in out)
    print(len(out), "step rows over", len({x["run_key"] for x in out}), "runs")
    for (tw, lab, use), n in sorted(c.items(), key=str):
        print(f"  {'twin' if tw else 'repair'} | {lab} | {use}: {n}")


if __name__ == "__main__":
    main()
