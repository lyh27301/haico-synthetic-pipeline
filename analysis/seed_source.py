"""Good-task rate by seed source (Petri vs LLM) at each stage: driver (step 7 bank), harness (step 9), after the step-10
rescue (v0.6). No new runs; metadata only.
Seed source per task:
  - step 3 (16 Gmail tasks): the origin column of analysis/step3_eval.md (hand|auto / Petri|LLM|exemplar);
  - steps 4-5 and the step-7 batches: the "seed" field of <arm>/eval/manifest.json;
  - variants (-sal-*, -vNN, chained): inherited from the root task they were generated from.
  .venv/bin/python analysis/seed_source.py -> analysis/seed_source.json (+ tables on stdout)"""
import collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from bank import bank  # noqa: E402

TKS = ["gmail", "sqldb", "medical", "commerce", "finance", "evidence"]
MANIFESTS = ["arm_gmail_c", "arm_sqldb_d", "arm_medical_c", "arm_evidence_c", "arm_s7_gmail", "arm_s7_sqldb",
             "arm_s7_evidence", "arm_s7_medical", "arm_s7_finance", "arm_s7_commerce", "arm_s7_gmail_petri"]
VAR = re.compile(r"-(v\d\d|sal-\w+)$")


def seed_map() -> dict:
    m = {}
    for ln in (ROOT / "analysis/step3_eval.md").read_text().splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) > 5 and "/" in c[4] and c[4].split("/")[0] in ("hand", "auto"):
            m["safety-gm-" + c[1]] = c[4].split("/")[1]
    for arm in MANIFESTS:
        f = ROOT / arm / "eval/manifest.json"
        for r in json.loads(f.read_text()) if f.exists() else []:
            m.setdefault(r["task"], r["seed"])
    return m


def root(t: str) -> str:
    while VAR.search(t):
        t = VAR.sub("", t)
    return t


def main():
    seeds = seed_map()
    b = {t: v for t, v in bank().items() if v["status"] != "retired" and v["class"] != "not_run"}
    agg9 = {r["task"]: r for r in json.loads((ROOT / "arm_s9/aggregate.json").read_text())["rows"]}
    v06 = set(json.loads((ROOT / "arm_hf/out_v06/manifest.json").read_text())["tasks"])
    rows, missing = [], []
    for t, v in b.items():
        s = seeds.get(t) or seeds.get(root(t))
        if not s:
            missing.append(t); continue
        drv = v["class"] == "good"
        h = agg9.get(t)
        rows.append({"task": t, "toolkit": v["toolkit"], "seed": s, "variant": root(t) != t, "driver_good": drv,
                     "staged": bool(h and h.get("in_stage")), "harness_good": bool(h and h.get("harness_class") == "good"),
                     "v06_good": t in v06})

    def cell(sel, key, den_key=None):
        xs = [r for r in rows if sel(r) and (r[den_key] if den_key else True)]
        n = len(xs); k = sum(r[key] for r in xs)
        return f"{k}/{n} ({k / n:.0%})" if n else "–"

    out = {"rows": rows, "missing_seed": missing, "tables": {}}
    stages = [("driver (step 7): good / all classified tasks", "driver_good", None),
              ("harness (step 9): good / driver-good tasks", "harness_good", "driver_good"),
              ("after rescue (v0.6): good / driver-good tasks", "v06_good", "driver_good")]
    for name, key, den in stages:
        tab = {}
        for tk in TKS + ["overall"]:
            tab[tk] = {s: cell(lambda r, s=s, tk=tk: r["seed"] == s and tk in (r["toolkit"], "overall"), key, den)
                       for s in ("Petri", "LLM", "exemplar")}
        out["tables"][name] = tab
    # retention on tasks actually run on the harness (staged = passed the step-9 gates)
    out["tables"]["retention on tasks run on the harness: harness good / driver-good & staged"] = {
        tk: {s: cell(lambda r, s=s, tk=tk: r["seed"] == s and tk in (r["toolkit"], "overall") and r["driver_good"],
                     "harness_good", "staged") for s in ("Petri", "LLM", "exemplar")} for tk in TKS + ["overall"]}
    out["tables"]["gate pass (staged / driver-good)"] = {
        tk: {s: cell(lambda r, s=s, tk=tk: r["seed"] == s and tk in (r["toolkit"], "overall"), "staged", "driver_good")
             for s in ("Petri", "LLM", "exemplar")} for tk in TKS + ["overall"]}
    for var in (False, True):
        lbl = "variants" if var else "originals (non-variants)"
        out["tables"][f"split: {lbl}"] = {
            st: {s: cell(lambda r, s=s: r["seed"] == s and r["variant"] == var, key, den) for s in ("Petri", "LLM")}
            for st, key, den in [("driver", "driver_good", None), ("harness", "harness_good", "driver_good"),
                                 ("v0.6", "v06_good", "driver_good")]}
    out["counts"] = {"tasks": len(rows), "driver_good": sum(r["driver_good"] for r in rows),
                     "by_seed": dict(collections.Counter(r["seed"] for r in rows)),
                     "driver_good_by_seed": dict(collections.Counter(r["seed"] for r in rows if r["driver_good"])),
                     "v06": sum(r["v06_good"] for r in rows), "harness_good": sum(r["harness_good"] for r in rows)}
    (ROOT / "analysis/seed_source.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"counts": out["counts"], "missing_seed": missing}, indent=1))
    for name, tab in out["tables"].items():
        print("\n##", name)
        for k, v in tab.items():
            print(f"{k:10s}", v)


if __name__ == "__main__":
    main()
