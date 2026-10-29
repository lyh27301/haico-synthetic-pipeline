"""Aggregate a step-4 batch (Gmail or SQL): per-task buckets, good / all_safe / all_unsafe, salience vs unsafe,
seed-origin lift, cue-read x unsafe 2x2, funnel + task-writer pass rate, cost (list prices) and wall time.

  python analysis/aggregate_step4.py arm_gmail_c [arm_sqldb_d]   -> <arm>/eval/agg.json + markdown on stdout
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# $ per 1M tokens (input, output), OpenAI list prices used for estimates
PRICE = {"gpt-4o-mini": (0.15, 0.60), "gpt-5-mini": (0.25, 2.00)}


def bucket(us):
    if not us:
        return None
    return "all_unsafe" if all(us) else "all_safe" if not any(us) else "mixed"


def cost(path: Path) -> dict:
    out = defaultdict(float)
    if not path.exists():
        return {}
    for ln in path.read_text().splitlines():
        r = json.loads(ln)
        pi, po = PRICE.get(r["model"], (0, 0))
        out[r.get("tag") or "untagged"] += (r["in"] * pi + r["out"] * po) / 1e6
    return {k: round(v, 3) for k, v in out.items()}


def rate(xs):
    return round(sum(xs) / len(xs), 2) if xs else None


def agg(arm: Path) -> dict:
    ev = arm / "eval"
    man = {m["task"]: m for m in json.loads((ev / "manifest.json").read_text())}
    res = [json.loads(p.read_text()) for p in sorted((ev / "results").glob("*.json"))]
    res = [r for r in res if r["unsafe"] != ""]
    per = {}
    for t, m in man.items():
        rs = {a: [r for r in res if r["task"] == t and r["agent"] == a] for a in ("4omini", "5mini")}
        b = {a: bucket([r["unsafe"] for r in rs[a]]) for a in rs}
        per[t] = {**{k: m[k] for k in ("seed", "seed_id", "hook", "outcome", "cue_salience", "grader_kind",
                                       "pivotal_tool", "instruction")},
                  "rate_4o": rate([r["unsafe"] for r in rs["4omini"]]), "rate_5m": rate([r["unsafe"] for r in rs["5mini"]]),
                  "b_4o": b["4omini"], "b_5m": b["5mini"],
                  "cue_read": sum(r["cue_read_before_pivotal"] for r in rs["4omini"] + rs["5mini"]),
                  "n": len(rs["4omini"] + rs["5mini"]),
                  "turns_4o": [r["n_user_turns"] for r in rs["4omini"]]}
        bs = [x for x in b.values() if x]
        per[t]["good"] = "mixed" in bs
        per[t]["all_safe_both"] = bool(bs) and all(x == "all_safe" for x in bs) and len(bs) == 2
        per[t]["all_unsafe_both"] = bool(bs) and all(x == "all_unsafe" for x in bs) and len(bs) == 2
        per[t]["cue_4o"] = sum(r["cue_read_before_pivotal"] for r in rs["4omini"])
    n = len(per)
    out = {"n_tasks": n,
           "good": sum(p["good"] for p in per.values()),
           "all_safe_both": sum(p["all_safe_both"] for p in per.values()),
           "all_unsafe_both": sum(p["all_unsafe_both"] for p in per.values()),
           "all_safe_4o": sum(p["b_4o"] == "all_safe" for p in per.values()),
           "all_unsafe_4o": sum(p["b_4o"] == "all_unsafe" for p in per.values()),
           "mixed_4o": sum(p["b_4o"] == "mixed" for p in per.values())}
    # salience x unsafe (pooled rollouts, per agent)
    sal = defaultdict(lambda: defaultdict(list))
    for r in res:
        sal[r["agent"]][man[r["task"]]["cue_salience"]].append(r["unsafe"])
    out["salience_unsafe"] = {a: {s: [rate(v), len(v)] for s, v in d.items()} for a, d in sal.items()}
    out["salience_good"] = {s: [sum(p["good"] for p in per.values() if p["cue_salience"] == s),
                                sum(1 for p in per.values() if p["cue_salience"] == s)]
                            for s in sorted({p["cue_salience"] for p in per.values()})}
    # seed origin
    out["origin"] = {o: {"tasks": sum(1 for p in per.values() if p["seed"] == o),
                         "good": sum(p["good"] for p in per.values() if p["seed"] == o),
                         "all_safe_both": sum(p["all_safe_both"] for p in per.values() if p["seed"] == o),
                         "unsafe_4o": rate([r["unsafe"] for r in res if r["agent"] == "4omini" and man[r["task"]]["seed"] == o])}
                     for o in sorted({p["seed"] for p in per.values()})}
    # cue-read x unsafe 2x2 per agent
    out["cue2x2"] = {}
    for a in ("4omini", "5mini"):
        rs = [r for r in res if r["agent"] == a]
        cell = lambda c, u: sum(1 for r in rs if r["cue_read_before_pivotal"] == c and r["unsafe"] == u)
        out["cue2x2"][a] = {"read_unsafe": cell(True, 1), "read_safe": cell(True, 0),
                            "noread_unsafe": cell(False, 1), "noread_safe": cell(False, 0)}
    # turns
    t4 = [r["n_user_turns"] for r in res if r["agent"] == "4omini"]
    out["turns_4o"] = {"mean": rate(t4), "le2": sum(1 for x in t4 if x <= 2), "n": len(t4)}
    # funnel / generation
    f = json.loads((arm / "funnel.json").read_text())
    rows = f.get("tasks", [])
    out["scenario_funnel"] = f.get("scenario_funnel")
    out["task_funnel"] = f.get("task_funnel")
    tried = len(rows)
    out["taskwriter_auto_pass"] = [sum(1 for r in rows if r.get("status") != "failed"), tried]
    out["first_attempt_pass"] = [sum(1 for r in rows if r.get("attempts") == 1), sum(1 for r in rows if r.get("attempts"))]
    stages = defaultdict(int)
    for r in rows:
        for e in (r.get("trail") or []):
            stages[str(e).split(":")[0].split(" ")[0]] += 1
    out["failure_stages"] = dict(stages)
    out["review_accepted"] = sum(1 for r in rows if r.get("accepted"))
    out["cost_usd"] = {**cost(arm / "gen_usage.jsonl"), **cost(ev / "usage.jsonl")}
    tm = ev / "timing.json"
    out["eval_timing_s"] = json.loads(tm.read_text()) if tm.exists() else None
    out["per_task"] = per
    (ev / "agg.json").write_text(json.dumps(out, indent=1))
    return out


def md(name, o):
    n = o["n_tasks"]
    print(f"\n### {name}: {n} tasks")
    print(f"good {o['good']}/{n} = {o['good']/n:.2f}; all_safe(both) {o['all_safe_both']}/{n} = {o['all_safe_both']/n:.2f}; "
          f"all_unsafe(both) {o['all_unsafe_both']}/{n}; 4o buckets: mixed {o['mixed_4o']} / all_safe {o['all_safe_4o']} / all_unsafe {o['all_unsafe_4o']}")
    print("salience unsafe:", json.dumps(o["salience_unsafe"]), "| salience good:", json.dumps(o["salience_good"]))
    print("origin:", json.dumps(o["origin"]))
    print("cue2x2:", json.dumps(o["cue2x2"]))
    print("turns_4o:", o["turns_4o"], "| funnel:", o["scenario_funnel"], o["task_funnel"])
    print("auto pass:", o["taskwriter_auto_pass"], "first-attempt:", o["first_attempt_pass"], "fail stages:", o["failure_stages"])
    print("cost:", o["cost_usd"], "timing:", o["eval_timing_s"])
    print("| task | seed | hook | outcome | sal | pivotal | 4o | 5m | buckets | cue-read |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for t, p in o["per_task"].items():
        print(f"| {t} | {p['seed']} | {p['hook']} | {p['outcome']} | {p['cue_salience']} | {p['pivotal_tool']} | "
              f"{p['rate_4o']} | {p['rate_5m'] if p['rate_5m'] is not None else '-'} | {p['b_4o']}/{p['b_5m'] or '-'}"
              f"{' **good**' if p['good'] else ''} | {p['cue_read']}/{p['n']} |")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        md(a, agg(ROOT / a))
