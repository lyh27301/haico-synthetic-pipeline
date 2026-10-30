"""Step 7 Part A regression: every existing task set re-dry-runs at 0/0/1 after the Part A changes (medical base
dates, Teladoc view list, evidence list tools, '*' in record graders), and - for information only, nothing is
dropped - which existing tasks the new deterministic gates (recipe/gates.py) would have flagged, joined with their
rollout class (good = mixed under either agent).

  python analysis/step7_regression.py  ->  analysis/step7_regression.json
"""
import collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402
from recipe import gates  # noqa: E402
from recipe.graders import dry_run_ok  # noqa: E402

SETS = {"step2": "arm_step2/tasks", "gmail_step4": "arm_gmail_c/tasks", "sqldb_step4": "arm_sqldb_d/tasks",
        "evidence_step5": "arm_evidence_c/tasks", "medical_step5": "arm_medical_c/tasks",
        "salience_step5": "arm_salience_d/tasks", "variants_step6": "arm_variants/tasks"}
RESULTS = ["arm_eval3/results", "arm_gmail_c/eval/results", "arm_sqldb_d/eval/results", "arm_evidence_c/eval/results",
           "arm_medical_c/eval/results", "arm_salience_d/eval/results", "arm_variants/eval/results"]


def classes():
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for d in RESULTS:
        for f in glob.glob(str(ROOT / d / "*.json")):
            r = json.loads(Path(f).read_text())
            if r.get("unsafe") != "":
                by[r["task"]][r["agent"]].append(int(r["unsafe"]))
    out = {}
    for t, ag in by.items():
        b = {a: ("all_unsafe" if all(u) else "all_safe" if not any(u) else "mixed") for a, u in ag.items()}
        out[t] = ("good" if "mixed" in b.values() else "all_unsafe" if set(b.values()) == {"all_unsafe"}
                  else "all_safe" if set(b.values()) == {"all_safe"} else "split")
    return out


def dirs():
    out = {}
    for m in json.loads((ROOT / "analysis/step3_manifest.json").read_text()):
        out[m["task"]] = ("step3", ROOT / m["dir"])
    for name, rel in SETS.items():
        for d in sorted((ROOT / rel).iterdir()):
            if (d / "scenario.json").exists():
                out.setdefault(d.name, (name, d))
    return out


def main():
    cls = classes()
    rows = []
    for t, (grp, d) in sorted(dirs().items()):
        prof = driver.profile_for(d)
        task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
        try:
            res = prof.dry_run(task); ok = dry_run_ok(res)
        except Exception as e:  # noqa: BLE001
            res, ok = f"{type(e).__name__}: {str(e)[:200]}", False
        g = {}
        for name, fn in (("hygiene", gates.hygiene_errors), ("discover", gates.discover_errors),
                         ("equivalence", gates.equivalence_errors)):
            try:
                e = fn(prof, task)
            except Exception as ex:  # noqa: BLE001
                e = [f"crash {type(ex).__name__}: {ex}"]
            g[name] = e[0][:300] if e else None
        rows.append({"task": t, "set": grp, "toolkit": prof.NAME, "dry": res, "ok": ok, "class": cls.get(t, "not_run"),
                     "has_literal": bool(getattr(task, "literal_reference", None)), **g})
    summ = {"by_set": {}, "flags": {}}
    for grp in sorted({r["set"] for r in rows}):
        sel = [r for r in rows if r["set"] == grp]
        summ["by_set"][grp] = f"{sum(r['ok'] for r in sel)}/{len(sel)}"
    for name in ("hygiene", "discover", "equivalence"):
        fl = [r for r in rows if r[name]]
        summ["flags"][name] = {"n": len(fl), "by_class": dict(collections.Counter(r["class"] for r in fl)),
                               "tasks": [r["task"] for r in fl]}
    summ["classes_all"] = dict(collections.Counter(r["class"] for r in rows))
    summ["discover_note"] = "only tasks with a literal_reference can be checked: %d/%d" % (
        sum(r["has_literal"] for r in rows), len(rows))
    (ROOT / "analysis" / "step7_regression.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))
    print(json.dumps(summ, indent=1))
    for r in rows:
        if not r["ok"]:
            print("FAIL", r["task"], r["dry"])


if __name__ == "__main__":
    main()
