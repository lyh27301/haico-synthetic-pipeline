"""Step 10 aggregation -> arm_s10/aggregate.json (Part A rescue, run selection, no-grade, cost, Part D).
  - runs: every result file in arm_s9/harness/results and arm_s10/harness/results (step 10 never rewrites a step-9 run);
  - the two NPC tasks fixed in Part D (arm_s10/npc_tasks) count only their post-fix runs (r6+): r1-r5 ran the old task;
  - Part A class = on the task's graded gpt-4o-mini harness runs (r1-r11): good = >=1 safe and >=1 unsafe;
  - v0.6 bank = step-9 good tasks (step-9 rule: mixed under either agent) + Part A tasks now good;
  - selection: 3 runs per good task = first safe run, first unsafe run, and the next run of the majority outcome over
    the task's 4o-mini graded runs (tie -> unsafe); runs are taken in run order, 4o-mini first, gpt-5-mini runs only
    when 4o-mini has no (further) run of the needed outcome; fewer than 3 if no agent has one.
  .venv/bin/python arm_s10/aggregate.py"""
import collections, glob, json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S10 = ROOT / "arm_s10"
FIXED = {p.name for p in (S10 / "npc_tasks").iterdir() if p.is_dir()}
PART_A = [x.strip() for x in (S10 / "ids_partA.txt").read_text().splitlines() if x.strip()]
RESCUED = [x.strip() for x in (S10 / "ids_rescued_c.txt").read_text().splitlines() if x.strip()]
CLASS9 = json.loads((S10 / "extreme_class_s9.json").read_text())
CAPPED_S10 = {(o["run"], o["instance"]): o for o in map(json.loads, (S10 / "harness/capped.jsonl").read_text().splitlines())}


def load():
    runs = {}
    for src in ("arm_s9", "arm_s10"):
        for f in glob.glob(str(ROOT / src / "harness/results/*.json")):
            x = json.loads(Path(f).read_text()); x["src"] = src
            if x["task"] in FIXED and x["run"] < 6:
                continue
            runs[(x["task"], x["agent"], x["run"])] = x
    return runs


def rid(x):
    return f"{x['task']}__{x['agent']}__r{x['run']}"


def counts(rs):
    g = [x for x in rs if x["graded"]]
    return len(g), sum(bool(x["unsafe"]) for x in g)


def select(rs):
    g4 = sorted((x for x in rs if x["graded"] and x["agent"] == "4omini"), key=lambda x: x["run"])
    g5 = sorted((x for x in rs if x["graded"] and x["agent"] == "5mini"), key=lambda x: x["run"])
    n, u = len(g4), sum(bool(x["unsafe"]) for x in g4)
    maj = u >= n - u  # tie -> unsafe
    pick = []
    for want in (False, True, maj):
        x = next((x for x in g4 + g5 if bool(x["unsafe"]) == want and x not in pick), None)
        if x:
            pick.append(x)
    return pick, maj


def main():
    runs = load()
    by = collections.defaultdict(list)
    for x in runs.values():
        by[x["task"]].append(x)
    bank = {json.loads(l)["instance_id"]: json.loads(l) for l in (S10 / "bank_s10.jsonl").read_text().splitlines()}
    agg9 = {r["task"]: r for r in json.loads((ROOT / "arm_s9/aggregate.json").read_text())["rows"]}
    good9 = [t for t, r in agg9.items() if r.get("harness_class") == "good"]

    part_a = {}
    for t in PART_A:
        rs4 = [x for x in by[t] if x["agent"] == "4omini"]
        n, u = counts(rs4); n5, u5 = counts([x for x in by[t] if x["agent"] == "5mini"])
        part_a[t] = {"toolkit": bank[t]["toolkit"], "class9": CLASS9.get(t, "excluded_gate"), "rescued_c": t in RESCUED,
                     "fixed_npc": t in FIXED, "n4": n, "u4": u, "n5": n5, "u5": u5, "no_grade4": len(rs4) - n,
                     "good": 0 < u < n,
                     "good_either": (0 < u < n) or (0 < u5 < n5) or (n and n5 and (u + u5) not in (0, n + n5)),
                     "class": "good" if 0 < u < n else ("all_unsafe" if n and u == n else
                                                       ("all_safe" if n else "no_grade"))}
    good = good9 + [t for t, v in part_a.items() if v["good"]]

    sel = {}
    for t in good:
        pick, maj = select(by[t])
        rs4 = [x for x in by[t] if x["agent"] == "4omini"]; n, u = counts(rs4)
        sel[t] = {"selected_runs": [rid(x) for x in pick], "majority": "unsafe" if maj else "safe",
                  "n_runs": n, "unsafe_rate": round(u / n, 4) if n else None,
                  "uses_5mini": any(x["agent"] == "5mini" for x in pick), "n_selected": len(pick)}

    # rescue tables
    tab = collections.defaultdict(lambda: collections.Counter())
    for t, v in part_a.items():
        tab["class9:" + v["class9"]][v["class"]] += 1
        tab["toolkit:" + v["toolkit"]][v["class"]] += 1

    # no-grade before/after (gpt-4o-mini + gpt-5-mini, all runs)
    def ng(src):
        xs = [x for x in runs.values() if x["src"] == src]
        cap = [x for x in xs if not x["graded"] and (x.get("token_capped") or x.get("capped"))]
        return {"runs": len(xs), "no_grade": sum(not x["graded"] for x in xs), "capped": len(cap),
                "capped_kind": dict(collections.Counter(x.get("capped") or "token_cap" for x in cap)),
                "stuck_or_other": sum(not x["graded"] for x in xs) - len(cap),
                "by_agent": {a: {"runs": sum(x["agent"] == a for x in xs),
                                 "no_grade": sum(x["agent"] == a and not x["graded"] for x in xs)}
                             for a in ("4omini", "5mini")}}
    nog = {"step9": ng("arm_s9"), "step10": ng("arm_s10")}
    capped10 = [{"task": o["instance"], "kind": o["kind"], "cost": round(o["cost"], 3), "uncached_tokens": o["tokens"]}
                for o in CAPPED_S10.values()]

    # cost per rollout (step-10 runs, final usage.json)
    cost = {}
    for a in ("4omini", "5mini"):
        cs = [x["usage"].get("accumulated_cost") or 0 for x in runs.values()
              if x["src"] == "arm_s10" and x["agent"] == a and x.get("usage")]
        gr = [x["usage"].get("accumulated_cost") or 0 for x in runs.values()
              if x["src"] == "arm_s10" and x["agent"] == a and x.get("usage") and x["graded"]]
        if cs:
            cost[a] = {"n": len(cs), "mean": round(statistics.mean(cs), 4), "median": round(statistics.median(cs), 4),
                       "p95": round(sorted(cs)[int(0.95 * (len(cs) - 1))], 4), "max": round(max(cs), 4),
                       "mean_graded": round(statistics.mean(gr), 4) if gr else None}

    # Part D
    part_d = {t: [{"run": x["run"], "graded": x["graded"], "unsafe": x["unsafe"], "error": (x["error"] or "")[:120],
                   "checkpoints": x.get("checkpoints"), "cost": round((x.get("usage") or {}).get("accumulated_cost") or 0, 4)}
                  for x in sorted(by[t], key=lambda x: (x["agent"], x["run"]))] for t in sorted(FIXED)}

    out = {"part_a": part_a, "tables": {k: dict(v) for k, v in sorted(tab.items())},
           "n_good9": len(good9), "n_good_a": sum(v["good"] for v in part_a.values()), "n_v06": len(good),
           "n_good_either_a": sum(bool(v["good_either"]) for v in part_a.values()),
           "selection": sel, "selection_stats": {
               "n3": sum(v["n_selected"] == 3 for v in sel.values()),
               "uses_5mini": sum(v["uses_5mini"] for v in sel.values()),
               "short": {t: v["selected_runs"] for t, v in sel.items() if v["n_selected"] < 3}},
           "no_grade": nog, "capped_s10": capped10, "cost": cost, "part_d": part_d}
    (S10 / "aggregate.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("tables", "n_good9", "n_good_a", "n_v06", "n_good_either_a",
                                          "selection_stats", "no_grade", "cost")}, indent=1))


if __name__ == "__main__":
    main()
