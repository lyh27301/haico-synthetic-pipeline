"""Step 13a: action-level labels by prefix replay (method A). No model calls.

For every graded run behind the v0.7 flags, the replay works like this:
  - v0.6 tasks: gpt-4o-mini's first 5 graded step-10 runs and Qwen r1-r5 (arm_s12/regrade.jsonl, as in
    arm_hf/build_bank_v07.py);
  - 12b member tasks: every graded run;
  - it rebuilds the task's env from the bank row's `environment` and walks the conversation history's tool calls in
    order;
  - executed MCP calls run again through the real tool function, with arguments from calls.jsonl;
  - framework-rejected calls (harness/rejected_calls.py) and non-env tools (chat_npc, terminal, finish, ...) leave
    the env unchanged; their observations / NPC replies come from the log;
  - after every step, grader v2 grades (pre, env now, calls so far, rejected calls so far).

The definition of the labels is in analysis/step13.md: steps before the pivotal step are safe, the pivotal step is
unsafe, and later steps are post_harm. A run whose final verdict is safe has no pivotal step.

  .venv/bin/python arm_s13/replay.py  ->  arm_s13/action_labels.jsonl(.gz) (one row per step), arm_s13/replay_runs.jsonl
                                          (one row per run: first step per flag, consistency checks)"""
import collections, gzip, json, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "harness")); sys.path.insert(0, str(ROOT / "arm_s10"))
import grader_v2, rejected_calls  # noqa: E402
from recipe import profiles  # noqa: E402

FLAGS = ("harm_realized", "attempted_leak", "side_effect")
NPC_TOOLS = {"chat_npc", "chat_with_npc", "npc_chat"}


def jl(p: Path) -> list:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def rt(x):
    return json.loads(json.dumps(x, default=str))


def toolkit(row) -> str:
    for d in row.get("dependencies") or []:
        if str(d).startswith("agentdojo:"):
            return str(d).split(":", 1)[1]
    return row["toolkit"]


# ---------- which runs ---------------------------------------------------------------------------------------------
def bank_runs():
    from aggregate import load
    man = json.loads((ROOT / "arm_hf/out_v07/manifest.json").read_text())["tasks"]
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s11/bank_v06.jsonl").read_text().splitlines()}
    rows |= {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s12/bank_12b.jsonl").read_text().splitlines()}
    old = {(t, a, str(k)): x for (t, a, k), x in load().items()}
    win = collections.defaultdict(list)
    for o in sorted(jl(ROOT / "arm_s12/regrade.jsonl"), key=lambda o: o["run"]):
        if o.get("unsafe") is not None and o["agent"] in ("4omini", "qwen3.5-9b"):
            win[(o["task"], o["agent"])].append(o)
    out = []
    for (t, a), os_ in sorted(win.items()):
        for o in os_[:5] if a == "4omini" else os_:
            if a == "4omini":
                x = old[(t, a, str(o["run"]))]; sd = ROOT / x["state_dir"]
            else:
                x = json.loads((ROOT / f"arm_s11/harness/results/{t}__qwen3.5-9b__r{o['run']}.json").read_text())
                sd = ROOT / x["state_dir"]
            out.append({"task": t, "agent": a, "run": int(o["run"]), "source": "v0.6", "state_dir": sd,
                        "traj_dir": sd.parents[1], "stored": o})
    for f in sorted((ROOT / "arm_s12/harness/results").glob("*.json")):
        r = json.loads(f.read_text())
        if r.get("graded") and man.get(r["task"], {}).get("source") == "step12b":
            out.append({"task": r["task"], "agent": r["agent"], "run": int(r["run"]), "source": "12b",
                        "state_dir": ROOT / r["state_dir"], "traj_dir": ROOT / r["traj_dir"], "stored": r})
    return out, rows


H = {}


def history(d: Path, t: str):
    if d not in H:
        H[d] = {}
        for name in ("output.jsonl", "output.critic_attempt_1.jsonl"):   # the attempt file wins where both exist
            for f in d.rglob(name):
                for ln in f.read_text().splitlines():
                    if ln.strip():
                        o = json.loads(ln)
                        if o.get("history"):
                            H[d][o["instance_id"]] = o["history"]
    return H[d].get(t)


# ---------- one run ----------------------------------------------------------------------------------------------
def steps_of(hist, env_tools):
    """Agent tool calls in history order: ("env", ActionEvent) / ("rejected", rejected record) / ("other", ActionEvent),
    with the observation text of each ActionEvent."""
    rej_ids = {e.get("tool_call_id") for e in hist if e.get("kind") == "AgentErrorEvent"}
    obs = {}
    for e in hist:
        if e.get("kind") in ("ObservationEvent", "UserRejectObservation", "AgentErrorEvent") and e.get("tool_call_id"):
            o = e.get("observation") or {}
            txt = " ".join(c.get("text", "") for c in o.get("content") or [] if isinstance(c, dict)) if isinstance(o, dict) \
                else str(o)
            obs[e["tool_call_id"]] = txt or str(e.get("error") or "")
    rej = iter(rejected_calls.extract(hist))
    out = []
    for e in hist:
        k = e.get("kind")
        if k == "ActionEvent":
            c = e.get("tool_call") or {}
            if c.get("id") in rej_ids:
                continue   # emitted at its AgentErrorEvent
            name = c.get("name") or e.get("tool_name")
            try:
                args = json.loads(c.get("arguments") or "{}")
            except ValueError:
                args = {"_raw": c.get("arguments")}
            out.append({"kind": "env" if name in env_tools else "npc" if name in NPC_TOOLS else "other", "tool": name,
                        "args": args, "observation": obs.get(c.get("id"), "")})
        elif k == "AgentErrorEvent":
            r = next(rej)
            out.append({"kind": "rejected", "tool": r["name"], "args": r["args"] if r["args"] is not None else {"_raw": r["raw"]},
                        "observation": r["error"], "rec": r})
        elif k == "MessageEvent" and e.get("source") == "agent":
            for r in rejected_calls.extract([e]):
                assert next(rej) == r
                out.append({"kind": "rejected", "tool": r["name"], "args": r["args"] if r["args"] is not None else
                            {"_raw": r["raw"]}, "observation": r["error"], "rec": r})
    return out


def replay(x, row, ctx, probe=None):
    """probe: optional f(call, pre) -> dict, evaluated on every step (step 13c, grader v3); its output is the step's
    "probe" field."""
    tk = toolkit(row); prof = profiles.get(tk)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(row["environment"])
    env = prof.load_environment(fh.name); Path(fh.name).unlink()
    runtime = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    sd = x["state_dir"]
    pre_stored = json.loads((sd / "pre.json").read_text()); post_stored = json.loads((sd / "post.json").read_text())
    calls_stored = jl(sd / "calls.jsonl"); rej_stored = jl(sd / "rejected_calls.jsonl")
    pre = rt(prof.env_to_dict(env))
    issues = []
    if pre != pre_stored:
        issues.append("pre_mismatch")
    hist = history(x["traj_dir"], x["task"])
    if hist is None:
        return None, ["no_history"], {}
    steps = steps_of(hist, set(runtime.functions))
    # executed env calls must line up with calls.jsonl
    env_steps = [s for s in steps if s["kind"] == "env"]
    if [s["tool"] for s in env_steps] != [c["name"] for c in calls_stored]:
        issues.append("call_alignment")
    if len([s for s in steps if s["kind"] == "rejected"]) != len(rej_stored):
        issues.append("rejected_count")
    ci = iter(calls_stored)
    calls, rej, out = [], [], []
    prev = {"unsafe": False, **{f: False for f in FLAGS}, "leak_rule": None, "side_effects": []}
    for i, s in enumerate(steps):
        changed = False
        if s["kind"] == "env":
            c = next(ci, None)
            if c is None:
                issues.append("extra_env_call"); args = {k: v for k, v in s["args"].items() if k != "summary"}
                c = {"name": s["tool"], "args": args}
            res, err = runtime.run_function(env, c["name"], c["args"])
            result = rt({"error": err} if err else res)
            if "result" in c and result != rt(c["result"]):
                s["result_mismatch"] = True   # e.g. a read tool whose matching changed since the run; the log's result is shown
            calls.append({"name": c["name"], "args": c["args"], "result": result, "error": err})
            s["args"] = c["args"]; s["observation"] = json.dumps(c.get("result", result), default=str); changed = True
        elif s["kind"] == "rejected":
            rej.append(s["rec"]); changed = True
        v = grader_v2.grade(row, pre, rt(prof.env_to_dict(env)), calls, ctx, rej) if changed else prev
        if probe is not None:   # the call as the agent made it, with the logged result (as the probe gate saw it)
            pc = {"name": s["tool"], "args": s["args"], "result": s["observation"]}
            if s["kind"] == "rejected":
                pc |= {"rejected": True, "rec": s["rec"]}
            s["probe"] = probe(pc, pre)
        out.append({**({"probe": s["probe"]} if probe is not None else {}), "step": i, "tool": s["tool"], "kind": s["kind"], "args": s["args"], "observation": s["observation"],
                    "flags": {f: bool(v[f]) for f in FLAGS}, "unsafe": bool(v["unsafe"]), "leak_rule": v["leak_rule"],
                    "side_effects": v["side_effects"], "result_mismatch": s.get("result_mismatch", False)})
        prev = v
    if not out:   # no tool call at all: the grade of the untouched env
        prev = grader_v2.grade(row, pre, pre, [], ctx, [])
    final = bool(prev["unsafe"])
    if rt(prof.env_to_dict(env)) != post_stored:
        issues.append("post_mismatch")
    if any(o["result_mismatch"] for o in out):
        issues.append("result_mismatch")
    return out, issues, {"final": final, "final_flags": {f: bool(prev[f]) for f in FLAGS}}


def label(steps, final_unsafe):
    piv = next((s["step"] for s in steps if s["unsafe"]), None) if final_unsafe else None
    for s in steps:
        s["label"] = "safe" if piv is None or s["step"] < piv else "unsafe" if s["step"] == piv else "post_harm"
    first = {f: next((s["step"] for s in steps if s["flags"][f]), None) for f in FLAGS}
    # a flag that fires and later clears, or an unsafe prefix in a run that ends safe
    transient = [f for f in FLAGS if first[f] is not None and not steps[-1]["flags"][f]]
    return piv, first, transient


def main():
    (S13 / "steps").mkdir(parents=True, exist_ok=True)
    runs, rows = bank_runs()
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    n_steps = 0; mism = []; summary = []
    with open(S13 / "action_labels.jsonl", "w") as fa, open(S13 / "replay_runs.jsonl", "w") as fr:
        for j, x in enumerate(runs):
            row = rows[x["task"]]; stored = bool(x["stored"]["unsafe"])
            steps, issues, fin = replay(x, row, ctx.get(x["task"], ""))
            if steps is None:
                mism.append((x["task"], x["agent"], x["run"], "no_history"))
                fr.write(json.dumps({"task": x["task"], "agent": x["agent"], "run": x["run"], "issues": issues}) + "\n")
                continue
            if fin["final"] != stored:
                mism.append((x["task"], x["agent"], x["run"], f"stored {stored} replay {fin['final']}"))
                issues.append("verdict_mismatch")
            piv, first, transient = label(steps, fin["final"])
            if transient:
                issues.append("transient_flag")   # a flag fired and cleared: the end-state grader misses reverted harm
            prof = profiles.get(toolkit(row))
            if piv is not None and steps[piv]["kind"] == "env" and not prof.is_state_changing(steps[piv]["tool"], steps[piv]["args"]):
                issues.append("pivot_on_read")    # harm_realized is a proxy on a read (e.g. a download)
            fired = sorted({v for v in first.values() if v is not None})
            stored_flags = {f: bool(x["stored"].get(f)) for f in FLAGS}
            rec = {"task": x["task"], "agent": x["agent"], "run": x["run"], "source": x["source"],
                   "toolkit": toolkit(row), "n_steps": len(steps), "n_env_calls": sum(s["kind"] == "env" for s in steps),
                   "episode_unsafe": stored, "replay_unsafe": fin["final"], "stored_flags": stored_flags,
                   "replay_flags": fin["final_flags"], "pivotal_step": piv,
                   "pivotal_tool": steps[piv]["tool"] if piv is not None else None,
                   "pivotal_kind": steps[piv]["kind"] if piv is not None else None,
                   "pivotal_is_last": piv is not None and piv == len(steps) - 1,
                   "pivotal_is_last_env": piv is not None and piv == max((s["step"] for s in steps if s["kind"] in ("env", "rejected")), default=-1),
                   "first_step": first, "first_flag": [f for f in FLAGS if first[f] is not None and first[f] == min(fired)] if fired else [],
                   "multi_step_flags": len(fired) > 1, "transient": transient,
                   # diagnostic, not a verdict: some prefix was unsafe. ever_flagged and not replay_unsafe = harm the
                   # agent later undid, which the final-state grader cannot see by design (step 14: method A's misses)
                   "ever_flagged": any(s["unsafe"] for s in steps), "issues": issues}
            fr.write(json.dumps(rec) + "\n"); summary.append(rec)
            with open(S13 / "steps" / f"{x['task']}__{x['agent']}__r{x['run']}.json", "w") as fs:
                json.dump(steps, fs, default=str)
            for s in steps:
                a = json.dumps(s["args"], default=str)
                fa.write(json.dumps({"task_id": x["task"], "agent": x["agent"], "run": x["run"], "step": s["step"],
                                     "tool": s["tool"], "kind": s["kind"], "args": a[:300], "label": s["label"],
                                     "flags": s["flags"], "unsafe_prefix": s["unsafe"], "leak_rule": s["leak_rule"],
                                     "episode_unsafe": stored, "issue": issues or None,
                                     "result_mismatch": s["result_mismatch"]}) + "\n")
            n_steps += len(steps)
            if j % 200 == 0:
                print(j, len(runs), n_steps, len(mism), flush=True)
    # the tracked copy is the .gz (deterministic: no name / mtime in the header); the .jsonl is ignored
    with open(S13 / "action_labels.jsonl", "rb") as fi, open(S13 / "action_labels.jsonl.gz", "wb") as fo, \
            gzip.GzipFile(filename="", mode="wb", fileobj=fo, mtime=0) as gz:
        shutil.copyfileobj(fi, gz)
    print(f"{len(runs)} runs, {n_steps} steps; verdict mismatches: {len(mism)} ({100 * len(mism) / len(runs):.2f}%)")
    for m in mism:
        print("  MISMATCH", *m)
    print("issues:", collections.Counter(i for r in summary for i in r["issues"]))


if __name__ == "__main__":
    main()
