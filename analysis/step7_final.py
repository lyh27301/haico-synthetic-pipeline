"""Step 7 Part F numbers: batches (Parts C/D), bank headline, Part A gate effects, new toolkits, variants (Part E),
Petri vs LLM. Classes as defined: good = mixed under either agent (5 x 4o-mini, then 5 x 5-mini on extremes).

  python analysis/step7_final.py -> analysis/step7_final.json (+ summary on stdout)
"""
import collections, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from aggregate_step4 import cost  # noqa: E402
from bank import bank, buckets_from, classify, good  # noqa: E402

TKS = ["gmail", "sqldb", "evidence", "medical", "finance", "commerce"]
VAR = re.compile(r"-(v\d\d|sal-\w+)$")


def rate(n, d):
    return f"{n}/{d} = {n / d:.2f}" if d else f"{n}/0"


def batch(tk):
    arm = ROOT / f"arm_s7_{tk}"
    if not (arm / "funnel.json").exists():
        return None
    f = json.loads((arm / "funnel.json").read_text())
    man = json.loads((arm / "eval" / "manifest.json").read_text()) if (arm / "eval" / "manifest.json").exists() else []
    res = buckets_from(arm / "eval" / "results" / "*.json")
    rows = []
    allres = [json.loads(Path(p).read_text()) for p in glob.glob(str(arm / "eval" / "results" / "*.json"))]
    for m in man:
        c, b = classify(res[m["task"]]) if m["task"] in res else ("not_run", {})
        sc = json.loads((Path(m["dir"]) / "scenario.json").read_text())
        rr = [r for r in allres if r["task"] == m["task"]]
        rows.append({"task": m["task"], "seed": m["seed"], "hook": m["hook"], "class": c, "buckets": b,
                     "literal_doubtful": sc.get("axes", {}).get("literal_doubtful"),
                     "cue_read": sum(bool(r.get("cue_read_before_pivotal")) for r in rr), "n": len(rr),
                     "acted": sum(bool(r.get("acted")) for r in rr), "instruction": m.get("instruction", "")[:200]})
    tf = f.get("task_funnel", {}); sf = f.get("scenario_funnel", {})
    attempted = tf.get("emitted", 0) + tf.get("failed", 0)
    seeds = list((arm / "seeds").glob("*.toml"))
    gen, ev = cost(arm / "gen_usage.jsonl"), cost(arm / "eval" / "usage.jsonl")
    petri_mined = json.loads((arm / "petri" / "mined.json").read_text()) if (arm / "petri" / "mined.json").exists() else []
    comp = collections.Counter(str(m.get("compliance")) for m in petri_mined)
    return {"seeds": len(seeds), "seeds_petri": sum("_petri_" in p.name for p in seeds),
            "seeds_llm": sum("_llm_" in p.name for p in seeds), "petri_audits": len(petri_mined),
            "petri_compliance": dict(comp), "scenario_funnel": sf, "task_funnel": tf,
            "writer_pass": rate(tf.get("emitted", 0), attempted), "writer_pass_x": (tf.get("emitted", 0) / attempted) if attempted else None,
            "classes": dict(collections.Counter(r["class"] for r in rows)), "rows": rows,
            "cost_gen": round(sum(gen.values()), 3), "cost_eval": round(sum(ev.values()), 3),
            "start": (arm / "start.txt").read_text().strip() if (arm / "start.txt").exists() else None,
            "done": (arm / "done.txt").read_text().strip() if (arm / "done.txt").exists() else None}


def variants():
    arm = ROOT / "arm_s7_variants"
    if not (arm / "variants.jsonl").exists():
        return None
    recs = [json.loads(x) for x in (arm / "variants.jsonl").read_text().splitlines()]
    res = buckets_from(arm / "eval" / "results" / "*.json")
    src = json.loads((arm / "sources.json").read_text())
    per_axis = collections.defaultdict(lambda: collections.Counter())
    rows = []
    for r in recs:
        ax = r.get("axis")
        per_axis[ax]["tried"] += 1
        if r["status"] != "passed":
            per_axis[ax]["failed"] += 1
            per_axis[ax]["fail_" + str(r.get("err", "")).split(":")[0].split(" ")[0]] += 1
            continue
        per_axis[ax]["passed"] += 1
        c, b = classify(res[r["variant"]]) if r["variant"] in res else ("not_run", {})
        per_axis[ax][c] += 1
        rows.append({"variant": r["variant"], "source": r["source"], "toolkit": r.get("toolkit"), "axis": ax,
                     "class": c, "buckets": b, "source_buckets": src.get(r["source"], {}).get("buckets")})
    gen, ev = cost(arm / "gen_usage.jsonl"), cost(arm / "eval" / "usage.jsonl")
    tot = sum(gen.values()) + sum(ev.values())
    ngood = sum(r["class"] == "good" for r in rows)
    return {"sources": len(src), "by_toolkit_sources": dict(collections.Counter(v["toolkit"] for v in src.values())),
            "tried": len(recs), "passed": sum(r["status"] == "passed" for r in recs),
            "per_axis": {a: dict(c) for a, c in per_axis.items()}, "rows": rows,
            "per_toolkit": {tk: dict(collections.Counter(r["class"] for r in rows if r["toolkit"] == tk)) for tk in TKS},
            "cost_gen": round(sum(gen.values()), 3), "cost_eval": round(sum(ev.values()), 3),
            "cost_per_good": round(tot / ngood, 3) if ngood else None, "good": ngood}


def main():
    out = {"batches": {tk: batch(tk) for tk in TKS}, "variants": variants()}
    b = bank(); g = good()
    mech = collections.defaultdict(set)
    for t, v in g.items():
        sc = json.loads((Path(v["dir"]) / "scenario.json").read_text())
        mech[v["toolkit"]].add(sc.get("axes", {}).get("mechanic_id") or VAR.sub("", t))
    out["bank"] = {"good_total": len(g), "by_toolkit": {tk: sum(v["toolkit"] == tk for v in g.values()) for tk in TKS},
                   "by_origin": dict(collections.Counter("step7_variant" if v["set"] == "arm_s7_variants" else
                                                         "step7_batch" if v["set"].startswith("arm_s7_") else
                                                         "steps3-6" for v in g.values())),
                   "mechanics": {tk: len(mech[tk]) for tk in TKS}, "mechanics_total": sum(len(m) for m in mech.values()),
                   "stable_unsafe": sum(v["class"] == "all_unsafe" and v["status"] != "retired" for v in b.values()),
                   "retired": sum(v["status"] == "retired" for v in b.values())}
    # literal_doubtful calibration over step-7 batch tasks
    ld = collections.defaultdict(lambda: [0, 0])
    for tk in TKS:
        bt = out["batches"][tk]
        for r in (bt or {}).get("rows", []):
            if r["class"] == "not_run":
                continue
            k = "doubtful" if r["literal_doubtful"] else "rest"
            ld[k][0] += r["class"] == "good"; ld[k][1] += 1
    out["literal_doubtful"] = {k: rate(*v) for k, v in ld.items()}
    # Petri vs LLM good rate
    pl = {}
    for tk in TKS:
        bt = out["batches"][tk]
        if not bt:
            continue
        pl[tk] = {}
        for s in ("Petri", "LLM"):
            rr = [r for r in bt["rows"] if r["seed"] == s and r["class"] != "not_run"]
            pl[tk][s] = rate(sum(r["class"] == "good" for r in rr), len(rr))
    out["petri_vs_llm"] = pl
    (ROOT / "analysis" / "step7_final.json").write_text(json.dumps(out, indent=1, default=str))
    slim = {k: v for k, v in out.items() if k not in ("batches", "variants")}
    slim["batches"] = {tk: (None if not v else {k: v[k] for k in v if k != "rows"}) for tk, v in out["batches"].items()}
    slim["variants"] = None if not out["variants"] else {k: v for k, v in out["variants"].items() if k != "rows"}
    print(json.dumps(slim, indent=1, default=str))


if __name__ == "__main__":
    main()
