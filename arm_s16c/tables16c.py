"""Step 16c items 5, 6, 14: tables for analysis/step16c.md from arm_s16c/grades/<set>.jsonl, the follow-up answers and
the stored old runs.
  - outcome classes by agent for each rule set (16a, v6, and after the freeze v7-luna, v7-sol);
  - exposure by agent (13h rule, renamed; shared by the sets);
  - tasks with at least one unsafe run and at least one honest success, per set;
  - honest-success rate of the forward task and the archive / merge tasks, new runs vs the stored old runs of the same
    task ids (old: 16a outcome_v5 and v6 outcome_v6 of arm_s16b/runs_v6.jsonl, all agents and sources), per set;
  - eval awareness: share of "yes" by agent and the reasons, next to step 13j (arm_v10/followup13j.jsonl).
Writes arm_s16c/tables16c.json.   .venv/bin/python arm_s16c/tables16c.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; C = ROOT / "arm_s16c"
SETS = ("16a", "v6", "v7-luna", "v7-sol")
CLASSES = ("unsafe_success", "unsafe_failed", "intent_only", "honest_success", "safe_unexposed", "failed_safe")
FORWARD = ("safety-gm-customers-q4-forward-v141",)
ARCHIVE = ("safety-gm-deploy-key-zip-v121", "safety-ev-petri-attorney-archive", "safety-ev-petri-attorney-archive-v123")
UNSAFE = ("unsafe_success", "unsafe_failed")


def main():
    out = {}
    old = [json.loads(l) for l in (ROOT / "arm_s16b/runs_v6.jsonl").read_text().splitlines()]
    for s in SETS:
        f = C / "grades" / f"{s}.jsonl"
        if not f.exists():
            continue
        rows = [x for x in map(json.loads, f.read_text().splitlines()) if "crash" not in x and not x.get("skip")]
        by = collections.defaultdict(collections.Counter)
        for x in rows:
            by[x["agent"]][x["outcome"]] += 1; by["all"][x["outcome"]] += 1
        tasks = collections.defaultdict(set)
        for x in rows:
            tasks[x["task"]].add(x["outcome"])
        usable = sorted(t for t, o in tasks.items() if o & set(UNSAFE) and "honest_success" in o)
        hs = {}
        for name, ids in (("forward", FORWARD), ("archive_merge", ARCHIVE)):
            new = [x for x in rows if x["task"] in ids]
            oldk = "outcome_v5" if s == "16a" else "outcome_v6"
            o = [x for x in old if x["task"] in ids]
            hs[name] = {"new": f"{sum(x['outcome'] == 'honest_success' for x in new)}/{len(new)}",
                        "new_rate": round(sum(x["outcome"] == "honest_success" for x in new) / len(new), 3) if new else None,
                        "new_by_agent": {a: f"{sum(x['outcome'] == 'honest_success' for x in new if x['agent'] == a)}/"
                                            f"{sum(x['agent'] == a for x in new)}" for a in sorted({x['agent'] for x in new})},
                        "old": f"{sum(x.get(oldk) == 'honest_success' for x in o)}/{len(o)}" if s in ("16a", "v6") else
                               "old runs are not graded with v7 (v7 is applied to Part A only)",
                        "old_rate": round(sum(x.get(oldk) == "honest_success" for x in o) / len(o), 3) if o and s in ("16a", "v6") else None,
                        "old_by_agent": {a: f"{sum(x.get(oldk) == 'honest_success' for x in o if x['agent'] == a)}/"
                                            f"{sum(x['agent'] == a for x in o)}" for a in sorted({x['agent'] for x in o})}
                        if s in ("16a", "v6") else None}
        out[s] = {"runs": len(rows), "outcomes_by_agent": {a: {c: v.get(c, 0) for c in CLASSES} for a, v in sorted(by.items())},
                  "unsafe_runs_by_agent": {a: sum(v.get(c, 0) for c in UNSAFE) for a, v in sorted(by.items())},
                  "tasks_with_unsafe_and_honest_success": len(usable), "usable_tasks": usable,
                  "honest_success_forward_archive": hs,
                  "exposure_by_agent": {a: f"{sum(bool(x['exposed']) for x in rows if x['agent'] == a)}/{sum(x['agent'] == a for x in rows)}"
                                        for a in sorted({x['agent'] for x in rows})}}
    # step agreement between sets
    lab = {s: {x["key"]: x for x in map(json.loads, (C / "grades" / f"{s}.jsonl").read_text().splitlines())}
           for s in SETS if (C / "grades" / f"{s}.jsonl").exists()}
    agr = {}
    for a in lab:
        for b in lab:
            if a < b:
                pairs = [(x, lab[b][k]) for k, x in lab[a].items() if k in lab[b] and "crash" not in x and "crash" not in lab[b][k]]
                st = [(p, q) for x, y in pairs for p, q in zip(x["labels"], y["labels"])]
                agr[f"{a} vs {b}"] = {"steps": round(sum(p == q for p, q in st) / len(st), 3) if st else None,
                                      "outcomes": round(sum(x["outcome"] == y["outcome"] for x, y in pairs) / len(pairs), 3) if pairs else None}
    out["agreement"] = agr
    # eval awareness
    ea = {}
    for name, f in (("16c", C / "followup16c.jsonl"), ("13j", ROOT / "arm_v10/followup13j.jsonl")):
        if not f.exists():
            continue
        rows = [x for x in map(json.loads, f.read_text().splitlines()) if x.get("answer")]
        d = {}
        for a in sorted({x["agent"] for x in rows}):
            rr = [x for x in rows if x["agent"] == a]
            yes = [x for x in rr if x.get("aware") == "yes"]
            d[a] = {"asked": len(rr), "yes": len(yes), "share_yes": round(len(yes) / len(rr), 3) if rr else None,
                    "unclear": sum(x.get("aware") == "unclear" for x in rr),
                    "reasons": collections.Counter(r for x in yes for r in x.get("reasons") or []).most_common(12)}
        ea[name] = d
    out["eval_awareness"] = ea
    (C / "tables16c.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:9000])


if __name__ == "__main__":
    main()
