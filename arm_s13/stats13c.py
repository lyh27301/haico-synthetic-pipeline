"""Step 13c numbers for analysis/step13c.md, from arm_s13/replay_runs_v3.jsonl, action_labels_v3.jsonl and the probe
specs -> arm_s13/step13c.json:
  - label counts v2 / v3 / v3_nohint, and the check that the v2 labels and episode verdicts equal step 13a's;
  - pivotal steps that moved earlier (v3 before v2), by how much, by what;
  - runs graded safe that now have an unsafe action (reverted harm vs probe-only), listed;
  - probe firing counts (steps, runs) by type, toolkit, harm_carrier, agent;
  - rule counts (before / after the dedupe), v2_blind_spot, manual and hinted rules and what they change;
  - 20 probe-firing false-positive candidates (seeded sample of pivots that only a probe sets).
  .venv/bin/python arm_s13/stats13c.py"""
import collections, json, random, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(S13))
from stats13a import carriers  # noqa: E402

PF = ("probe_read", "probe_write", "probe_send")


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def rules_summary():
    out = {"rounds_r9": collections.Counter(), "before_dedupe": collections.Counter(), "after_dedupe": collections.Counter(),
           "tasks_with_rules": collections.Counter(), "deduped": 0, "manual": [], "hinted": [], "split": [],
           "blind_spot": {"rules": 0, "tasks": set(), "steps": set(), "runs": set()}, "probe_coverage_false": [],
           "no_rules": []}
    specs = {}
    for f in sorted((S13 / "probes").glob("*.json")):
        s = json.loads(f.read_text()); t = s["task"]; specs[t] = s
        r9 = json.loads((S13 / "probes_rounds/r9" / f.name).read_text())
        for typ, v in r9["probes"].items():
            out["rounds_r9"][typ] += sum(not r.get("builtin") for r in v)
        for typ, k in s["gate"]["rules_before_dedupe"].items():
            out["before_dedupe"][typ] += k
        out["deduped"] += len(s["gate"]["deduped"])
        if not s["probe_coverage"]:
            out["probe_coverage_false"].append(t)
        n = 0
        for typ, v in s["probes"].items():
            own = [r for r in v if not r.get("builtin")]
            out["after_dedupe"][typ] += len(own); n += len(own)
            out["tasks_with_rules"][typ] += bool(own)
            for r in own:
                if r.get("manual"):
                    out["manual"].append({"task": t, "type": typ, "id": r["id"], "match": r["match"]})
                if r.get("hinted"):
                    out["hinted"].append({"task": t, "type": typ, "id": r["id"], "fitted_on": r["hinted"],
                                          "v2_blind_spot_steps": len(r.get("v2_blind_spot", []))})
                if r.get("split_from"):
                    out["split"].append({"task": t, "type": typ, "id": r["id"], "from": r["split_from"]})
                if r.get("v2_blind_spot"):
                    b = out["blind_spot"]; b["rules"] += 1; b["tasks"].add(t)
                    for x in r["v2_blind_spot"]:
                        b["steps"].add((t, x["agent"], x["run"], x["step"])); b["runs"].add((t, x["agent"], x["run"]))
        if not n:
            out["no_rules"].append(t)
    b = out["blind_spot"]
    out["blind_spot"] = {"rules": b["rules"], "tasks": len(b["tasks"]), "steps": len(b["steps"]), "runs": len(b["runs"])}
    for k in ("rounds_r9", "before_dedupe", "after_dedupe", "tasks_with_rules"):
        out[k] = dict(out[k])
    out["split_dropped"] = [{"task": t, "id": k, "why": v[0][:120]} for t, s in specs.items()
                            for k, v in s["gate"]["dropped"].items() if s["gate"]["dropped_rules"][k].get("split_from")]
    return out, specs


def main():
    car = carriers()
    v2runs = {(r["task"], r["agent"], r["run"]): r for r in jl(S13 / "replay_runs.jsonl")}
    rs = [r for r in jl(S13 / "replay_runs_v3.jsonl") if "pivotal_v3" in r]
    for r in rs:
        r["carrier"] = car[r["task"]]
    steps = jl(S13 / "action_labels_v3.jsonl")
    rsum, specs = rules_summary()
    out = {"runs": len(rs), "steps": len(steps),
           "labels": {k: dict(collections.Counter(s[k] for s in steps)) for k in ("label_v2", "label_v3", "label_v3_nohint")},
           "episode_verdict_changed": sum(r["episode_unsafe"] != v2runs[(r["task"], r["agent"], r["run"])]["episode_unsafe"]
                                          for r in rs),
           "replay_verdict_mismatch": sum(r["episode_unsafe"] != r["replay_unsafe"] for r in rs),
           "rules": rsum}
    # pivots moved earlier
    mv = [r for r in rs if r["moved_earlier_by"] and r["episode_unsafe"]]
    unsafe = [r for r in rs if r["episode_unsafe"]]
    by = [r["moved_earlier_by"] for r in mv]
    out["moved_earlier"] = {
        "n": len(mv), "of_unsafe_runs": len(unsafe),
        "by_steps": {"median": statistics.median(by) if by else None, "max": max(by, default=None),
                     "hist": dict(sorted(collections.Counter(min(b, 10) for b in by).items()))},
        "frac_of_traj_median": round(statistics.median(r["moved_earlier_by"] / r["n_steps"] for r in mv), 3) if mv else None,
        "by_source": dict(collections.Counter("+".join(r["pivotal_v3_source"]) for r in mv)),
        "by_toolkit": dict(collections.Counter(r["toolkit"] for r in mv)),
        "by_carrier": dict(collections.Counter(r["carrier"] for r in mv)),
        "by_agent": dict(collections.Counter(r["agent"] for r in mv)),
        "by_task_family": dict(collections.Counter(r["task"].split("-v")[0] for r in mv).most_common(15)),
        "nohint_moved": sum(1 for r in mv if r["pivotal_v3_nohint"] != r["pivotal_v3"]),
        "runs": [{k: r[k] for k in ("task", "agent", "run", "n_steps", "pivotal_v2", "pivotal_v3", "pivotal_v3_tool",
                                    "pivotal_v3_rules")} for r in mv]}
    # step 13d: unsafe steps per run (each step labeled on its own)
    out["unsafe_steps_per_run"] = {}
    for k in ("n_unsafe_v2", "n_unsafe_v3", "n_unsafe_v3_nohint"):
        u = [r[k] for r in rs if r[k]]
        out["unsafe_steps_per_run"][k] = {
            "runs_with_unsafe": len(u), "runs_with_more_than_one": sum(x > 1 for x in u),
            "hist": dict(sorted(collections.Counter(min(x, 10) for x in u).items())),
            "median": statistics.median(u) if u else None, "max": max(u, default=None),
            "more_than_one_by_toolkit": dict(collections.Counter(r["toolkit"] for r in rs if r[k] > 1)),
            "more_than_one_by_carrier": dict(collections.Counter(r["carrier"] for r in rs if r[k] > 1)),
            "more_than_one_by_agent": dict(collections.Counter(r["agent"] for r in rs if r[k] > 1))}
    # step 13d-final: looped runs (>= 5 consecutive near-identical tool calls); not a label
    lp = [r for r in rs if r.get("looped")]
    out["looped"] = {"n": len(lp), "of_runs": len(rs),
                     "by_agent": dict(collections.Counter(r["agent"] for r in lp)),
                     "by_toolkit": dict(collections.Counter(r["toolkit"] for r in lp)),
                     "by_episode_verdict": dict(collections.Counter("unsafe" if r["episode_unsafe"] else "safe" for r in lp)),
                     "loop_max_hist": dict(sorted(collections.Counter(min(r["loop_max"], 20) for r in lp).items())),
                     "with_more_than_one_unsafe_v3": sum(r["n_unsafe_v3"] > 1 for r in lp),
                     "unsafe_steps_v3_in_looped_runs": sum(r["n_unsafe_v3"] for r in lp),
                     "runs": [{k: r[k] for k in ("task", "agent", "run", "n_steps", "loop_max", "n_unsafe_v2", "n_unsafe_v3")}
                              for r in sorted(lp, key=lambda r: -r["loop_max"])]}
    # previously-safe runs with an unsafe action
    ns = [r for r in rs if not r["episode_unsafe"] and r["v3_unsafe_action"]]
    out["newly_unsafe_action"] = {
        "n": len(ns), "of_safe_runs": sum(not r["episode_unsafe"] for r in rs),
        "reverted_harm": sum(r["ever_flagged"] for r in ns), "probe_only": sum(not r["ever_flagged"] for r in ns),
        "ever_flagged_safe_runs": sum(r["ever_flagged"] and not r["episode_unsafe"] for r in rs),
        "all_ever_flagged_included": all(r["v3_unsafe_action"] for r in rs if r["ever_flagged"]),
        "by_source": dict(collections.Counter("+".join(r["pivotal_v3_source"]) for r in ns)),
        "by_toolkit": dict(collections.Counter(r["toolkit"] for r in ns)),
        "by_carrier": dict(collections.Counter(r["carrier"] for r in ns)),
        "by_agent": dict(collections.Counter(r["agent"] for r in ns)),
        "nohint": sum(r["pivotal_v3_nohint"] is not None for r in ns),
        "runs": [{k: r[k] for k in ("task", "agent", "run", "n_steps", "ever_flagged", "pivotal_v3", "pivotal_v3_tool",
                                    "pivotal_v3_source", "pivotal_v3_rules", "hinted_rules_fitted_here")} for r in ns]}
    # firing counts
    key = lambda s: (s["task_id"], s["agent"], s["run"])
    rmeta = {(r["task"], r["agent"], r["run"]): r for r in rs}
    fire = {"steps": {}, "runs": {}}
    for f in PF + ("any",):
        hit = [s for s in steps if (s[f] if f != "any" else any(s[g] for g in PF))]
        runs_hit = {key(s) for s in hit}
        fire["steps"][f] = len(hit); fire["runs"][f] = len(runs_hit)
        for dim in ("toolkit", "carrier", "agent"):
            fire.setdefault(f"runs_by_{dim}", {})[f] = dict(collections.Counter(rmeta[k][dim] for k in runs_hit))
    for dim in ("toolkit", "carrier", "agent"):
        fire[f"runs_total_by_{dim}"] = dict(collections.Counter(r[dim] for r in rs))
    fire["builtin_send_0_steps"] = sum("send_0" in s["probe_rules"]["probe_send"] for s in steps)
    fire["custom_send_steps"] = sum(bool(set(s["probe_rules"]["probe_send"]) - {"send_0"}) for s in steps)
    fire["steps_by_label_v2"] = {f: dict(collections.Counter(s["label_v2"] for s in steps if s[f])) for f in PF}
    out["firing"] = fire
    # manual / hinted
    out["manual_firings"] = [{k: r[k] for k in ("task", "agent", "run", "pivotal_v2", "pivotal_v3", "manual_rules_fired")}
                             for r in rs if r["manual_rules_fired"]]
    out["hinted_effect"] = {
        "runs_where_hinted_rules_were_fitted": sum(bool(r["hinted_rules_fitted_here"]) for r in rs),
        "pivot_differs_without_them": [{k: r[k] for k in ("task", "agent", "run", "episode_unsafe", "pivotal_v2",
                                                          "pivotal_v3", "pivotal_v3_nohint")}
                                       for r in rs if r["pivotal_v3"] != r["pivotal_v3_nohint"]],
        "hinted_rules_fire_on_other_runs": sorted({(r["task"], r["agent"], r["run"]) for r in rs
                                                   for rid in r["rules_fired"]
                                                   if any(h["task"] == r["task"] and h["id"] == rid for h in rsum["hinted"])
                                                   and rid not in r["hinted_rules_fitted_here"]})}
    # false-positive candidates: pivots that only a probe sets (a v3 pivot before the v2 pivot, or in a run graded safe
    # and never flagged)
    cand = [r for r in rs if r["pivotal_v3"] is not None and "v2" not in r["pivotal_v3_source"]]
    rng = random.Random(13)
    pick = rng.sample(cand, min(20, len(cand)))
    sidx = {(key(s), s["step"]): s for s in steps}
    fpc = []
    for r in sorted(pick, key=lambda r: (r["task"], r["agent"], r["run"])):
        s = sidx[((r["task"], r["agent"], r["run"]), r["pivotal_v3"])]
        rules = {x["id"]: x for v in specs[r["task"]]["probes"].values() for x in v}
        full = json.loads((S13 / "steps" / f"{r['task']}__{r['agent']}__r{r['run']}.json").read_text())[r["pivotal_v3"]]
        fpc.append({"task": r["task"], "agent": r["agent"], "run": r["run"], "step": r["pivotal_v3"], "n_steps": r["n_steps"],
                    "episode_unsafe": r["episode_unsafe"], "pivotal_v2": r["pivotal_v2"], "tool": s["tool"],
                    "rules": {f: s["probe_rules"][f] for f in PF if s["probe_rules"][f]},
                    "rule_bodies": {rid: ("built-in attempted_leak" if rules[rid].get("builtin") else rules[rid]["match"])
                                    for f in PF for rid in s["probe_rules"][f]},
                    "tags": {rid: [g for g in ("v2_blind_spot", "hinted", "manual", "split_from") if rules[rid].get(g)]
                             for f in PF for rid in s["probe_rules"][f]},
                    "args": json.dumps(full["args"], default=str)[:600]})
    out["fp_candidates"] = {"pool": len(cand), "sample": fpc}
    (S13 / "step13c.json").write_text(json.dumps(out, indent=1, default=list))
    print(json.dumps({k: v for k, v in out.items() if k not in ("fp_candidates",)}, indent=1, default=list)[:12000])


if __name__ == "__main__":
    main()
