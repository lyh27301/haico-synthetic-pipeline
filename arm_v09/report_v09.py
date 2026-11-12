"""v0.9 aggregate results (no model calls), after arm_v09/analyze_v09.py on the batch tree:
  - per agent on the same tasks: 2x2, unsafe rate, honest_success rate, tool-error rate. 4o-mini / Qwen use the runs of
    record (arm_v09/sonnet_set.py runs_of_record(): v0.8 runs for the re-rolled tasks, step-13f runs otherwise,
    contaminated runs excluded); Haiku 5.5 all 302 tasks x 5; Sonnet 5.5 its task set x 3, so every Sonnet comparison is
    restricted to Sonnet's tasks. Tool-error rate = (env calls whose result is an error + calls the framework rejected
    before execution) / (env calls + rejected calls), from the replay steps of each run;
  - Sonnet diagnostic: unsolved tasks that now have a Sonnet honest success (by toolkit), the control set's
    honest_success rate, and the tasks Sonnet failed 3/3 with a one-line failure description per task;
  - goodness_v2 per agent (>= 1 natural honest_success and >= 1 unsafe run of that agent), good_haiku, good_sonnet,
    good_any_v2 over natural honest successes only, before (4o-mini + Qwen) and after;
  - honest successes of the new agents get agent + safe_source = natural (arm_v09/analysis/honest_successes_v09.jsonl);
  - hidden-state scan, replay fidelity, label stats, spend.
  .venv/bin/python arm_v09/report_v09.py  ->  arm_v09/analysis/v09_results.json"""
import collections, json, sys
from pathlib import Path

import os
ROOT = Path(__file__).resolve().parents[1]; V9 = ROOT / "arm_v09"
TREE = Path(os.environ.get("V09_ROOT", V9)); AN = TREE / "analysis"   # V09_ROOT=arm_v09/smoke for a dry run
sys.path[:0] = [str(V9)]
OUTS = ("honest_success", "unsafe_success", "failed_safe", "unsafe_failed")
AGENTS = ("4omini", "qwen3.5-9b", "haiku5.5", "sonnet5.5")
TKS = ("gmail", "finance", "evidence", "sqldb", "medical", "commerce")


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def js(p):
    return json.loads(Path(p).read_text()) if Path(p).exists() else {}


def steps_path(o):
    key = f"{o['task']}__{o['agent']}__r{o['run']}.json"
    return {"step13f": ROOT / "arm_s13/steps", "v0.8": ROOT / "arm_v08/analysis/steps"}.get(o.get("source"), AN / "steps") / key


def tool_err(o):
    if "_te" not in o:
        env = err = rej = 0
        for s in (json.loads(steps_path(o).read_text()) if steps_path(o).exists() else []):
            if s["kind"] == "env":
                env += 1
                ob = s["observation"]
                try:
                    d = json.loads(ob) if isinstance(ob, str) else ob
                except ValueError:
                    d = ob
                err += isinstance(d, dict) and bool(d.get("error"))
            elif s["kind"] == "rejected":
                rej += 1
        o["_te"] = (env, err, rej)
    return o["_te"]


def block(rs):
    c = collections.Counter(r["outcome"] for r in rs)
    n = len(rs); te = [tool_err(r) for r in rs]; calls = sum(e + j for e, _, j in te)
    return {"runs": n, "tasks": len({r["task"] for r in rs}), **{k: c[k] for k in OUTS},
            "unsafe_rate": round(sum(bool(r["unsafe"]) for r in rs) / n, 3) if n else None,
            "honest_success_rate": round(c["honest_success"] / n, 3) if n else None,
            "failed_safe_rate": round(c["failed_safe"] / n, 3) if n else None,
            "tool_error_rate": round(sum(x + j for _, x, j in te) / calls, 3) if calls else None,
            "env_error_rate": round(sum(x for _, x, _ in te) / max(sum(e for e, _, _ in te), 1), 3),
            "rejected_calls": sum(j for _, _, j in te), "tool_calls": calls,
            "runs_with_tool_error": round(sum((x + j) > 0 for _, x, j in te) / n, 3) if n else None}


def good(rs):
    by = collections.defaultdict(list)
    for r in rs:
        by[r["task"]].append(r)
    return {t: any(r["outcome"] == "honest_success" for r in v) and any(r["unsafe"] for r in v) for t, v in by.items()}


def fail_line(t, runs, spec, res):
    """One line on how Sonnet's 3 runs of a task failed (heuristic; for manual review)."""
    what = {q["id"]: q.get("what", "").strip() for q in spec.get("requirements", [])}
    kinds, failed = [], collections.Counter()
    for r in runs:
        sd = ROOT / res[(r["task"], r["agent"], r["run"])]["state_dir"]
        pre, post = js(sd / "pre.json"), js(sd / "post.json")
        wpre, wpost = ({k: v for k, v in js(sd / f).items() if not k.startswith("/workspace/.git/")}
                       for f in ("workspace_pre.json", "workspace_post.json"))
        acted = pre != post or wpre != wpost
        miss = [k for k, v in (r.get("requirements") or {}).items() if not v]
        failed.update(miss)
        kinds.append("harm" if r["unsafe"] else "wrong deliverable" if acted else "gave up (no state change)")
    n = len(runs); top = failed.most_common(1)
    spec_mismatch = top and top[0][1] == n and all(k == "wrong deliverable" for k in kinds) \
        and len(set(tuple(sorted(k for k, v in (r.get("requirements") or {}).items() if not v)) for r in runs)) == 1
    cat = "utility spec mismatch?" if spec_mismatch else collections.Counter(kinds).most_common(1)[0][0]
    req = f"; failed `{top[0][0]}` in {top[0][1]}/{n}: {what.get(top[0][0], '')[:120]}" if top else ""
    return {"task": t, "category": cat, "runs": dict(collections.Counter(kinds)),
            "outcomes": [r["outcome"] for r in runs], "line": f"{cat} ({', '.join(f'{k} {v}' for k, v in collections.Counter(kinds).items())}){req}"}


def main():
    import sonnet_set as S
    import budget_guard as BG
    old = S.runs_of_record()
    new_all = jl(AN / "outcomes_v09.jsonl")
    crashed = [r for r in new_all if "crash" in r]
    new = [r for r in new_all if "crash" not in r and r.get("outcome")]
    hidden = [r for r in new if r["hidden"]["contaminated"]]
    new_clean = [r for r in new if not r["hidden"]["contaminated"]]
    for r in new_clean:
        r["source"] = "v0.9"
    runs = old + new_clean
    tk = {json.loads(l)["instance_id"]: next(d.split(":")[1] for d in json.loads(l)["dependencies"] if d.startswith("agentdojo:"))
          for l in (ROOT / "arm_v08/bank_v08.jsonl").read_text().splitlines()}
    sel = js(V9 / "sonnet_set.json")
    son_tasks = set(sel.get("unsolved_tasks", [])) | set(sel.get("control_tasks", []))
    by_agent = {a: [r for r in runs if r["agent"] == a] for a in AGENTS}
    side = {"all_302_tasks": {a: block(by_agent[a]) for a in AGENTS[:3]},
            "sonnet_tasks": {a: block([r for r in by_agent[a] if r["task"] in son_tasks]) for a in AGENTS},
            "sonnet_unsolved_tasks": {a: block([r for r in by_agent[a] if r["task"] in set(sel.get("unsolved_tasks", []))]) for a in AGENTS},
            "sonnet_control_tasks": {a: block([r for r in by_agent[a] if r["task"] in set(sel.get("control_tasks", []))]) for a in AGENTS},
            "by_toolkit": {t: {a: block([r for r in by_agent[a] if tk[r["task"]] == t]) for a in AGENTS[:3]} for t in TKS}}
    # Sonnet diagnostic
    res = {}
    for f in (TREE / "harness/results").glob("*.json"):
        x = json.loads(f.read_text()); res[(x["task"], x["agent"], int(x["run"]))] = x
    son = collections.defaultdict(list)
    for r in by_agent["sonnet5.5"]:
        son[r["task"]].append(r)
    uns = sel.get("unsolved_tasks", []); ctl = sel.get("control_tasks", [])
    solved = [t for t in uns if any(r["outcome"] == "honest_success" for r in son[t])]
    fails = [fail_line(t, son[t], js(ROOT / "arm_s13/utility" / f"{t}.json"), res)
             for t in uns if son[t] and not any(r["outcome"] == "honest_success" for r in son[t])]
    ctl_runs = [r for t in ctl for r in son[t]]
    diag = {"unsolved_tasks": len(uns), "unsolved_with_sonnet_runs": sum(bool(son[t]) for t in uns),
            "now_solved": len(solved),
            "now_solved_by_toolkit": {t: [sum(tk[x] == t for x in solved), sum(tk[x] == t for x in uns)] for t in TKS},
            "unsolved_hs_run_rate": round(sum(r["outcome"] == "honest_success" for t in uns for r in son[t])
                                          / max(sum(len(son[t]) for t in uns), 1), 3),
            "control_tasks": len(ctl), "control_hs_run_rate": round(sum(r["outcome"] == "honest_success" for r in ctl_runs)
                                                                  / max(len(ctl_runs), 1), 3),
            "control_tasks_with_hs": sum(any(r["outcome"] == "honest_success" for r in son[t]) for t in ctl),
            "failed_3of3": len(fails), "failed_3of3_by_category": dict(collections.Counter(f["category"] for f in fails)),
            "failed_3of3_tasks": sorted(fails, key=lambda f: (tk[f["task"]], f["task"])), "now_solved_tasks": solved}
    # goodness_v2 (natural honest successes only)
    g = {a: good(by_agent[a]) for a in AGENTS}
    tasks = sorted(tk)
    before = {t: g["4omini"].get(t, False) or g["qwen3.5-9b"].get(t, False) for t in tasks}
    after = {t: before[t] or g["haiku5.5"].get(t, False) or g["sonnet5.5"].get(t, False) for t in tasks}
    hs_any_before = {t for t in tasks if any(r["outcome"] == "honest_success" for r in old if r["task"] == t)}
    gd = {"good_4omini": sum(g["4omini"].values()), "good_qwen": sum(g["qwen3.5-9b"].values()),
          "good_haiku": sum(g["haiku5.5"].values()), "good_sonnet": sum(g["sonnet5.5"].values()),
          "good_sonnet_of_tasks_run": len(g["sonnet5.5"]),
          "good_any_v2_before": sum(before.values()), "good_any_v2_after": sum(after.values()),
          "gained": sorted(t for t in tasks if after[t] and not before[t]),
          "gained_by": {a: sum(g[a].get(t, False) and not before[t] for t in tasks) for a in ("haiku5.5", "sonnet5.5")},
          "by_toolkit": {t: {"before": sum(before[x] for x in tasks if tk[x] == t), "after": sum(after[x] for x in tasks if tk[x] == t),
                             "tasks": sum(tk[x] == t for x in tasks)} for t in TKS},
          "tasks_with_natural_hs_before": len(hs_any_before),
          "tasks_with_natural_hs_after": len(hs_any_before | {r["task"] for r in new_clean if r["outcome"] == "honest_success"})}
    hsl = [{"task": r["task"], "agent": r["agent"], "run": r["run"], "safe_source": "natural", "toolkit": r["toolkit"]}
           for r in new_clean if r["outcome"] == "honest_success"]
    (AN / "honest_successes_v09.jsonl").write_text("".join(json.dumps(h) + "\n" for h in hsl))
    labs = jl(AN / "action_labels_v09.jsonl")
    iss = collections.Counter(i for r in new_all for i in r.get("issues", []))
    cache = [r["cache"] for r in new if r.get("cache")]
    out = {"batch": js(AN / "batch_counts.json"), "analysed": len(new_all), "crashed": len(crashed),
           "per_agent_counts": {a: {"final": sum(1 for x in res.values() if x["agent"] == a and not x.get("endpoint_lost")),
                                    "graded": sum(1 for x in res.values() if x["agent"] == a and x.get("graded")),
                                    "capped": sum(1 for x in res.values() if x["agent"] == a and x.get("capped")),
                                    "errors": sum(1 for x in res.values() if x["agent"] == a and not x.get("graded")
                                                  and not x.get("capped") and not x.get("endpoint_lost"))}
                                for a in ("haiku5.5", "sonnet5.5")},
           "hidden_state": {"contaminated_runs": [f"{r['task']}__{r['agent']}__r{r['run']}" for r in hidden],
                            "read_content": sum(r["hidden"]["read_content"] for r in new),
                            "path_exposed": sum(r["hidden"]["path_exposed"] for r in new),
                            "harness_src": sum(r["hidden"]["harness_src"] for r in new),
                            "seal_path_runs": sum(bool(r["hidden"]["seal_path_steps"]) for r in new)},
           "replay_issues": dict(iss), "verdict_mismatch_runs": [f"{r['task']}__{r['agent']}__r{r['run']}" for r in new_all
                                                                 if "verdict_mismatch" in r.get("issues", [])],
           "labels": {a: {"steps": sum(l["agent"] == a for l in labs), "v2_unsafe": sum(l["agent"] == a and l["label_v2"] == "unsafe" for l in labs),
                          "v3_unsafe": sum(l["agent"] == a and l["label_v3"] == "unsafe" for l in labs),
                          "disagree": sum(l["agent"] == a and l["label_v2"] != l["label_v3"] for l in labs)} for a in ("haiku5.5", "sonnet5.5")},
           "cache": {"runs": len(cache), "runs_with_uncached_call_after_first": sum(c["calls_after_first_without_cache_read"] > 0 for c in cache),
                     "uncached_calls_after_first": sum(c["calls_after_first_without_cache_read"] for c in cache),
                     "calls_seen": sum(c["calls_seen"] for c in cache)},
           "cost_per_run": {a: (lambda c: {"mean": round(sum(c) / len(c), 4), "p90": round(sorted(c)[int(0.9 * (len(c) - 1))], 4),
                                           "max": round(max(c), 4)} if c else None)([r["cost"] for r in new if r["agent"] == a and r.get("cost") is not None])
                            for a in ("haiku5.5", "sonnet5.5")},
           "spend": {"batch": BG.spend(TREE), "smoke": BG.spend(V9 / "smoke")},
           "side_by_side": side, "sonnet_diagnostic": diag, "goodness_v2": gd, "new_honest_successes": len(hsl)}
    (AN / "v09_results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("side_by_side", "sonnet_diagnostic")}, indent=1)[:4000])


if __name__ == "__main__":
    main()
