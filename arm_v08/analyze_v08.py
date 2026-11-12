"""v0.8 batch analysis: the 130 re-rolled tasks (arm_v08/ids_v08.txt) on their new runs, against the pre-v0.8 runs of the
same tasks (arm_s13/outcomes_record.jsonl, the step-13f outcomes of record, contaminated runs excluded). No model calls.

Per graded v0.8 run (arm_v08/harness/results/*.json):
  - grader v2 verdict: the runner's host re-grade of the sealed pre / post dumps (stored in the result);
  - grader v4 utility on pre / post with the workspace snapshots (`workspace` key, as in arm_s13/replay13f.py); outcome
    = the 2x2 cell;
  - prefix replay (arm_s13/replay.py method A) for the v2 action labels, and the per-call probes (grader v3, with the
    v0.8 disk-path variants) for the v3 labels. The live MCP server overlaid the agent's workspace on every call and
    read /downloads/<id> as <id>; the replay does the same (harness/workspace_bridge.py, downloads on, workspace-wins
    on rows with has_workspace) with the run's final workspace snapshot (the dumps hold only the first and the last).
    A call whose replayed result differs from the logged one is marked result_mismatch; a run whose replayed final
    verdict differs from the stored one is marked verdict_mismatch (the step labels of such a run are approximate);
  - attempt_wrong_id / attempt_wrong_type (arm_s13/step13e.py wrong_calls).
Slots (single runs replacing contaminated runs of tasks outside the re-roll) are reported separately.

Outputs (arm_v08/analysis/): outcomes_v08.jsonl, replay_runs_v3.jsonl, action_labels_v3.jsonl, steps/<run>.json,
v08_results.json.
  .venv/bin/python arm_v08/analyze_v08.py [--workers 6]"""
import argparse, collections, json, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V = ROOT / "arm_v08"; OUTD = V / "analysis"; S13 = ROOT / "arm_s13"
sys.path[:0] = [str(S13), str(ROOT / "harness"), str(ROOT)]
import replay as R  # noqa: E402
import grader_v3, grader_v4, workspace_bridge  # noqa: E402
from replay import grader_v2, profiles  # noqa: E402

AG = ("4omini", "qwen3.5-9b"); TKS = ("gmail", "finance", "evidence", "sqldb", "medical", "commerce")
OUTS = ("honest_success", "unsafe_success", "failed_safe", "unsafe_failed")
PF = ("probe_read", "probe_write", "probe_send")
ROWS = {json.loads(l)["instance_id"]: json.loads(l) for l in (V / "bank_v08.jsonl").read_text().splitlines()}
CTX = json.loads((ROOT / "harness/agent_context.json").read_text())


def js(p):
    return json.loads(p.read_text()) if p.exists() else {}


def replay_ws(x, row):
    """arm_s13/replay.py replay() with the workspace bridge on every env call; returns steps (with probe), issues, fin."""
    tk = R.toolkit(row); prof = profiles.get(tk)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(row["environment"])
    env = prof.load_environment(fh.name); Path(fh.name).unlink()
    runtime = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    sd = x["state_dir"]
    pre_stored, post_stored = js(sd / "pre.json"), js(sd / "post.json")
    ws = {k: v for k, v in (js(sd / "workspace_pre.json") | js(sd / "workspace_post.json")).items()
          if not k.startswith("/workspace/.git/")}
    calls_stored = R.jl(sd / "calls.jsonl")
    pre = R.rt(prof.env_to_dict(env)); issues = [] if pre == pre_stored else ["pre_mismatch"]
    hist = R.history(x["traj_dir"], x["task"])
    if hist is None:
        return None, ["no_history"], {}
    steps = R.steps_of(hist, set(runtime.functions))
    if [s["tool"] for s in steps if s["kind"] == "env"] != [c["name"] for c in calls_stored]:
        issues.append("call_alignment")
    spec = js(S13 / "probes" / f"{x['task']}.json")
    ci = iter(calls_stored); calls, rej, out = [], [], []
    prev = {"unsafe": False, **{f: False for f in R.FLAGS}, "leak_rule": None, "side_effects": []}
    for i, s in enumerate(steps):
        changed = False
        if s["kind"] == "env":
            c = next(ci, None)
            if c is None:
                issues.append("extra_env_call"); c = {"name": s["tool"], "args": {k: v for k, v in s["args"].items() if k != "summary"}}
            res, err, _ = workspace_bridge.call(prof, env, runtime, c["name"], c["args"], ws, downloads=True,
                                                wins=bool(row.get("has_workspace")))
            result = R.rt({"error": err} if err else res)
            if "result" in c and result != R.rt(c["result"]):
                s["result_mismatch"] = True
            calls.append({"name": c["name"], "args": c["args"], "result": result, "error": err})
            s["args"] = c["args"]; s["observation"] = json.dumps(c.get("result", result), default=str); changed = True
        elif s["kind"] == "rejected":
            rej.append(s["rec"]); changed = True
        v = grader_v2.grade(row, pre, R.rt(prof.env_to_dict(env)), calls, CTX.get(x["task"], ""), rej) if changed else prev
        pc = {"name": s["tool"], "args": s["args"], "result": s["observation"]}
        if s["kind"] == "rejected":
            pc |= {"rejected": True, "rec": s["rec"]}
        probe = grader_v3.probe(spec, pc, row, pre) if spec else {f: [] for f in PF}
        out.append({"probe": probe, "step": i, "tool": s["tool"], "kind": s["kind"], "args": s["args"],
                    "observation": s["observation"], "flags": {f: bool(v[f]) for f in R.FLAGS}, "unsafe": bool(v["unsafe"]),
                    "leak_rule": v["leak_rule"], "side_effects": v["side_effects"],
                    "result_mismatch": s.get("result_mismatch", False)})
        prev = v
    if not out:
        prev = grader_v2.grade(row, pre, pre, [], CTX.get(x["task"], ""), [])
    if R.rt(prof.env_to_dict(env)) != post_stored:
        issues.append("post_mismatch")
    if any(o["result_mismatch"] for o in out):
        issues.append("result_mismatch")
    return out, issues, {"final": bool(prev["unsafe"]), "final_flags": {f: bool(prev[f]) for f in R.FLAGS}}


def one(x):
    import step13e as E
    t = x["task"]; row = ROWS[t]; sd = x["state_dir"]; key = f"{t}__{x['agent']}__r{x['run']}"
    try:
        steps, issues, fin = replay_ws(x, row)
    except Exception as e:  # noqa: BLE001
        return {"task": t, "agent": x["agent"], "run": x["run"], "crash": f"{type(e).__name__}: {e}"[:300]}, []
    stored = bool(x["stored"]["unsafe"])
    if steps is None:
        return {"task": t, "agent": x["agent"], "run": x["run"], "issues": issues}, []
    if fin["final"] != stored:
        issues.append("verdict_mismatch")
    piv2, _, transient = R.label(steps, fin["final"])
    for s in steps:
        s["probe_flags"] = {f: bool(s["probe"][f]) for f in PF}
        s["label_v3"] = "unsafe" if s["new_harm"] or any(s["probe_flags"].values()) else "safe"
    piv3 = next((s["step"] for s in steps if s["label_v3"] == "unsafe"), None)
    (OUTD / "steps" / f"{key}.json").write_text(json.dumps(steps, default=str))
    # utility (grader v4) with the workspace snapshots
    sp = js(S13 / "utility" / f"{t}.json")
    pre, post = js(sd / "pre.json"), js(sd / "post.json")
    wpre, wpost = js(sd / "workspace_pre.json"), js(sd / "workspace_post.json")
    u, req = grader_v4.utility(sp, pre | {"workspace": wpre}, post | {"workspace": wpost}) \
        if sp and sp["gate"]["passed"] else (None, {})
    sc = json.loads((x["scen_dir"] / "scenario.json").read_text())
    by_title, by_type = E.wrong_calls(steps, E.protected(row, sc, E.yaml_env(row)))
    rec = {"task": t, "agent": x["agent"], "run": x["run"], "slot": x["slot"], "toolkit": R.toolkit(row),
           "unsafe": stored, "utility": u, "requirements": req,
           "outcome": grader_v4.outcome(stored, u) if u is not None else None,
           "n_steps": len(steps), "replay_unsafe": fin["final"], "ever_flagged": any(s["unsafe"] for s in steps),
           "pivotal_v2": piv2, "pivotal_v3": piv3, "pivotal_v3_rules": sorted({r for f in PF for r in steps[piv3]["probe"][f]}) if piv3 is not None else [],
           "n_unsafe_v2": sum(s["label"] == "unsafe" for s in steps),
           "n_unsafe_v3": sum(s["label_v3"] == "unsafe" for s in steps),
           "v2_v3_disagree_steps": [s["step"] for s in steps if s["label"] != s["label_v3"]],
           "attempt_wrong_id": bool(by_title), "attempt_wrong_id_steps": by_title,
           "attempt_wrong_type": bool(by_type), "attempt_wrong_type_steps": by_type,
           "transient": transient, "issues": issues}
    labs = [{"task_id": t, "agent": x["agent"], "run": x["run"], "step": s["step"], "tool": s["tool"], "kind": s["kind"],
             "args": json.dumps(s["args"], default=str)[:300], "label_v2": s["label"], "label_v3": s["label_v3"],
             "new_harm": s["new_harm"], "flags": s["flags"], **s["probe_flags"], "probe_rules": s["probe"],
             "episode_unsafe": stored, "issue": issues or None} for s in steps]
    return rec, labs


def runs():
    import gen_utility as G
    b = G.bank()
    slots = {(s["task"], s["run"]) for s in json.loads((V / "batch_v08.json").read_text())["slots"]}
    ids = set((V / "ids_v08.txt").read_text().split())
    out, final = [], collections.Counter()
    for f in sorted((V / "harness/results").glob("*.json")):
        r = json.loads(f.read_text())
        if r.get("endpoint_lost"):
            continue
        final["final"] += 1; final["graded"] += bool(r.get("graded")); final["capped"] += bool(r.get("capped"))
        final["error"] += not r.get("graded") and not r.get("capped")
        slot = r["task"] not in ids
        if slot and (r["task"], int(r["run"])) not in slots:
            continue
        if r.get("graded"):
            t = r["task"]
            out.append({"task": t, "agent": r["agent"], "run": int(r["run"]), "slot": slot, "stored": r,
                        "state_dir": ROOT / r["state_dir"], "traj_dir": ROOT / r["traj_dir"],
                        "scen_dir": ROOT / "arm_s12/tasks" / t if (ROOT / "arm_s12/tasks" / t).exists() else Path(b[t]["dir"])})
    return out, dict(final)


def tab(rs):
    c = collections.Counter(r["outcome"] for r in rs if r["outcome"])
    return {k: c[k] for k in OUTS} | {"n": sum(c.values()), "no_outcome": sum(r["outcome"] is None for r in rs)}


def rate(rs, k):
    n = len([r for r in rs if r["outcome"]])
    return round(sum(r["outcome"] == k for r in rs) / n, 3) if n else None


def compare(new, old):
    def block(rs):
        return {"runs": len(rs), "2x2": tab(rs), "honest_success": rate(rs, "honest_success"),
                "failed_safe": rate(rs, "failed_safe"), "unsafe": round(sum(r["unsafe"] for r in rs) / max(len(rs), 1), 3),
                "attempt_wrong_id": sum(r["attempt_wrong_id"] for r in rs),
                "attempt_wrong_type": sum(r["attempt_wrong_type"] for r in rs)}
    res = {"all": {"v08": block(new), "pre": block(old)}}
    for tk in TKS:
        res[tk] = {"v08": block([r for r in new if r["toolkit"] == tk]), "pre": block([r for r in old if r["toolkit"] == tk])}
    for a in AG:
        res[a] = {"v08": block([r for r in new if r["agent"] == a]), "pre": block([r for r in old if r["agent"] == a])}
    return res


def goodness(rs, tasks):
    by = collections.defaultdict(list)
    for r in rs:
        by[(r["task"], r["agent"])].append(r)
    g = {}
    for t in tasks:
        g[t] = {f"good_{'4omini' if a == '4omini' else 'qwen'}": any(o["outcome"] == "honest_success" for o in by[(t, a)])
                and any(o["unsafe"] for o in by[(t, a)]) for a in AG}
        g[t]["good_any"] = g[t]["good_4omini"] or g[t]["good_qwen"]
    return g


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); a = ap.parse_args()
    (OUTD / "steps").mkdir(parents=True, exist_ok=True)
    xs, final = runs()
    print(len(xs), "graded runs to analyse", final, flush=True)
    recs, labs = [], []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (r, l) in enumerate(ex.map(one, xs, chunksize=4)):
            recs.append(r); labs += l
            if i % 100 == 0:
                print(i, flush=True)
    recs.sort(key=lambda r: (r["task"], r["agent"], r["run"]))
    (OUTD / "outcomes_v08.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    (OUTD / "action_labels_v3.jsonl").write_text("".join(json.dumps(l) + "\n" for l in labs))
    ok = [r for r in recs if "crash" not in r and "outcome" in r]
    ids = sorted(set((V / "ids_v08.txt").read_text().split()))
    new = [r for r in ok if not r["slot"]]
    rec_old = [json.loads(l) for l in (S13 / "outcomes_record.jsonl").read_text().splitlines()]
    car = {o["task"]: o["carrier"] for o in rec_old}
    old = [o for o in rec_old if o["task"] in ids and not o["contaminated"]]
    for r in new:
        r["carrier"] = car.get(r["task"])
    g_new, g_old = goodness(new, ids), goodness(old, ids)
    gd = {f: {"pre": sum(g_old[t][f] for t in ids), "v08": sum(g_new[t][f] for t in ids),
              "gained": sum(g_new[t][f] and not g_old[t][f] for t in ids), "lost": sum(g_old[t][f] and not g_new[t][f] for t in ids)}
          for f in ("good_4omini", "good_qwen", "good_any")}
    gd["good_any_by_toolkit"] = {tk: {"pre": sum(g_old[t]["good_any"] for t in ids if R.toolkit(ROWS[t]) == tk),
                                      "v08": sum(g_new[t]["good_any"] for t in ids if R.toolkit(ROWS[t]) == tk),
                                      "tasks": sum(R.toolkit(ROWS[t]) == tk for t in ids)} for tk in TKS}
    iss = collections.Counter(i for r in recs for i in r.get("issues", []))
    res = {"batch": final, "analysed": len(recs), "crashed": [f"{r['task']}__{r['agent']}__r{r['run']}: {r['crash']}" for r in recs if "crash" in r],
           "replay_issues": dict(iss),
           "verdict_mismatch_runs": [f"{r['task']}__{r['agent']}__r{r['run']}" for r in recs if "verdict_mismatch" in r.get("issues", [])],
           "compare": compare(new, old), "goodness_v2": gd,
           "by_carrier": {c: {"v08": tab([r for r in new if r["carrier"] == c]), "pre": tab([o for o in old if o["carrier"] == c])}
                          for c in ("action", "body", "attachment")},
           "labels": {"steps": len(labs), "v2_unsafe": sum(l["label_v2"] == "unsafe" for l in labs),
                      "v3_unsafe": sum(l["label_v3"] == "unsafe" for l in labs),
                      "disagree_steps": sum(l["label_v2"] != l["label_v3"] for l in labs),
                      "runs_with_disagreement": sum(bool(r.get("v2_v3_disagree_steps")) for r in ok),
                      "v2_safe_runs_with_v3_unsafe_step": sum((not r["unsafe"]) and r["pivotal_v3"] is not None for r in ok),
                      "honest_success_with_attempted_or_reverted_harm": sum(
                          r["outcome"] == "honest_success" and (r["attempt_wrong_id"] or r["attempt_wrong_type"]
                                                                or r["n_unsafe_v2"] or r["n_unsafe_v3"]) for r in new),
                      "honest_success": sum(r["outcome"] == "honest_success" for r in new)},
           "slots": [{k: r.get(k) for k in ("task", "agent", "run", "unsafe", "utility", "outcome", "issues")} for r in recs if r.get("slot")],
           "goodness_tasks": {"v08": g_new, "pre": g_old}}
    (OUTD / "v08_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "goodness_tasks"}, indent=1))


if __name__ == "__main__":
    main()
