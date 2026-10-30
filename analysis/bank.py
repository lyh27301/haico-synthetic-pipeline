"""The task bank after step 7 Part A2: one place that says which tasks are good and where their (possibly
repaired) task dir is. Used by the Part A2 report, the HF builds, Part E (source set) and the Part F headline.

- steps 3-6: classes from the original results (analysis/step7_regression.classes); a task repaired in Part A2 is
  reclassified from its re-run (arm_step7/a2/eval) and points at its repaired dir; a task tagged retired
  (retired.json in its dir) is out.
- step 7: the arm_s7_<toolkit> batches (Parts C/D) and the arm_s7_variants batch (Part E), once evaluated.

  python analysis/bank.py   -> prints counts
"""
import collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from step7_regression import classes as old_classes, dirs as old_dirs  # noqa: E402

A2 = ROOT / "arm_step7" / "a2"
S7_ARMS = ["arm_s7_gmail", "arm_s7_sqldb", "arm_s7_evidence", "arm_s7_medical", "arm_s7_finance", "arm_s7_commerce",
           "arm_s7_variants"]


def buckets_from(results_glob):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in glob.glob(str(results_glob)):
        r = json.loads(Path(f).read_text())
        if r.get("unsafe") != "":
            by[r["task"]][r["agent"]].append(int(r["unsafe"]))
    return by


def classify(ag):
    b = {a: ("all_unsafe" if all(u) else "all_safe" if not any(u) else "mixed") for a, u in ag.items()}
    return ("good" if "mixed" in b.values() else "all_unsafe" if set(b.values()) == {"all_unsafe"}
            else "all_safe" if set(b.values()) == {"all_safe"} else "split"), b


def toolkit_of(d):
    p = Path(d) / "toolkit.txt"
    return p.read_text().strip() if p.exists() else "gmail"


def bank(include_s7=True):
    """{task: {"class", "dir", "set", "toolkit", "status": clean|repaired|retired|new, "reason"?}} for every task."""
    cls, D = old_classes(), old_dirs()
    out = {t: {"class": cls.get(t, "not_run"), "dir": str(d), "set": g, "toolkit": toolkit_of(d), "status": "clean"}
           for t, (g, d) in D.items()}
    rep = json.loads((A2 / "repairs.json").read_text()) if (A2 / "repairs.json").exists() else []
    re_b = buckets_from(A2 / "eval" / "results" / "*.json")
    for r in rep:
        if r["status"] == "repaired":
            c, b = classify(re_b[r["task"]]) if r["task"] in re_b else ("not_run", {})
            out[r["task"]].update({"class": c, "dir": r["dir"], "status": "repaired", "buckets": b,
                                   "old_class": out[r["task"]]["class"]})
    if include_s7:
        for arm in S7_ARMS:
            res = buckets_from(ROOT / arm / "eval" / "results" / "*.json")
            for tdir in sorted((ROOT / arm / "tasks").glob("*")) if (ROOT / arm / "tasks").exists() else []:
                if not (tdir / "scenario.json").exists():
                    continue
                t = tdir.name
                c, b = classify(res[t]) if t in res else ("not_run", {})
                out.setdefault(t, {"class": c, "dir": str(tdir), "set": arm, "toolkit": toolkit_of(tdir),
                                   "status": "new", "buckets": b})
    for t, v in out.items():
        rf = Path(v["dir"]) / "retired.json"
        if rf.exists():
            v["status"] = "retired"; v["reason"] = json.loads(rf.read_text())["reason"]
    return out


def good(include_s7=True):
    return {t: v for t, v in bank(include_s7).items() if v["class"] == "good" and v["status"] != "retired"}


if __name__ == "__main__":
    b = bank()
    g = good()
    print("good:", len(g), dict(collections.Counter(v["toolkit"] for v in g.values())))
    print("status:", dict(collections.Counter(v["status"] for v in b.values())))
