"""Step 27 part 2: re-grade every step-14 warned branch (and the original runs they branch from) with engine v4 and the
v4.2 rules of the old task versions (grader/out/v4.2-s27, grader/gen_rules_s27.py). No agent runs.

Branches (19 steps x 4 conditions = 76):
  v1           round 1 specific warning   arm_s14/branches       (bid = v1_bid of arm_s14/r2/jobs_r2.json)
  v2, v2-noalt round 2                    arm_s14/r2/branches    (arm_s14/r2/jobs_r2.json)
  v2-continue  round 2b                   arm_s14/r2b/branches   (arm_s14/r2b/jobs_r2b.json)
  original     the stored run of the step (arm_v08 / arm_v09 harness trees, arm_s12 for the step-13f source)
Loader: the old harness stored no per-step states, so the run's actions (the analysis step file analyze_v09 wrote: tool,
args, the observation the agent saw) are played on the old task row (arm_s16b/play.py with the old staged files) to get
the state before and after every step. A call the run recorded as failed (calls.jsonl "error", or a call the framework
rejected) is not executed in the replay: its step keeps the state unchanged and carries the recorded error. The call
result in each step is the observation the agent saw. Checks of the loader: the recorded start state (pre.json) and
final state (post.json) of the run against the replay's first / last state; a mismatch is listed in the row.
Grading as grader/grade23.py one(): engine4.label_run (rule code makes a step unsafe; the note judge can only clear an
unasked-change finding; the third-label judge only adds "intent"), engine4.completion on the first and last state.
Judges: grade23's caches (copied to grader/out/v4.2-s27 on the first run), spend in grader/out/v4.2-s27/usage.jsonl
(shared with the rule generation; cap $1.9 so the step stays under $2), OpenAI through the key selection.
  .venv/bin/python arm_s27/grade27.py     -> arm_s27/grades27.jsonl"""
import json, shutil, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S14 = ROOT / "arm_s14"; G = ROOT / "grader"
sys.path[:0] = [str(ROOT / "arm_s27"), str(G), str(ROOT / "arm_s16c"), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]
SET = G / "out/v4.2-s27"
FROZEN = ["grader/out/v4.2-set0/rules", "grader/out/v4.2-set0/set.json", "grader/prompts", "grader/gen_rules42.py",
          "grader/toolkit_events42.py", "grader/engine4.py", "grader/judge_note4.py", "grader/engine.py", "grader/grade.py",
          "arm_s16c/judge.py"]
USAGE = SET / "usage.jsonl"; CAP = 1.9
STEPDIR = {"v0.8": ROOT / "arm_v08/analysis/steps", "v0.9": ROOT / "arm_v09/analysis/steps", "step13f": ROOT / "arm_s13/steps"}
ORIG_RESULTS = {"v0.8": ROOT / "arm_v08/harness/results", "v0.9": ROOT / "arm_v09/harness/results",
                "step13f": ROOT / "arm_s12/harness/results"}


def rows():
    return {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s27/bank/bank_27.jsonl").read_text().splitlines()}


def jobs():
    """One entry per run to grade: the 76 branches and the 14 distinct original runs."""
    r2 = json.loads((S14 / "r2/jobs_r2.json").read_text())
    r2b = json.loads((S14 / "r2b/jobs_r2b.json").read_text())
    out = []

    def add(cond, bid, j, tree):
        res = tree / "harness/results" / f"{j['task']}__{j['agent']}__r{bid}.json"
        out.append({"condition": cond, "bid": bid, "key": j["key"], "task": j["task"], "agent": j["agent"], "run": j["run"],
                    "source": j["source"], "branch_step": j["step"], "result": str(res.relative_to(ROOT)),
                    "steps_file": str((tree / "analysis/steps" / res.name).relative_to(ROOT))})
    for j in r2:
        add(j["condition"], j["bid"], j, S14 / "r2/branches")
    for j in r2b:
        add("v2-continue", j["bid"], j, S14 / "r2b/branches")
    seen = set()
    for j in sorted(r2, key=lambda j: j["v1_bid"]):
        if j["v1_bid"] not in seen:
            seen.add(j["v1_bid"]); add("v1", j["v1_bid"], j, S14 / "branches")
    seen = set()
    for j in r2:
        k = (j["source"], j["task"], j["agent"], j["run"])
        if k in seen:
            continue
        seen.add(k)
        name = f"{j['task']}__{j['agent']}__r{j['run']}.json"
        out.append({"condition": "original", "bid": None, "key": f"{j['task']}__{j['agent']}__r{j['run']}", "task": j["task"],
                    "agent": j["agent"], "run": j["run"], "source": j["source"], "branch_step": None,
                    "result": str((ORIG_RESULTS[j["source"]] / name).relative_to(ROOT)),
                    "steps_file": str((STEPDIR[j["source"]] / name).relative_to(ROOT))})
    return out


def _jl(p: Path) -> list:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def load(job: dict) -> dict:
    import play as P, bank27, replay27 as R27
    P.staged = bank27.staged
    row = rows()[job["task"]]
    res = json.loads((ROOT / job["result"]).read_text())
    sd = ROOT / res["state_dir"]
    st = json.loads((ROOT / job["steps_file"]).read_text())
    calls = _jl(sd / "calls.jsonl")
    env = [s for s in st if s["kind"] == "env"]
    if [s["tool"] for s in env] != [c["name"] for c in calls]:
        raise ValueError("step file and calls.jsonl do not align")
    err = {}
    for s, c in zip(env, calls):
        if c.get("error"):
            err[s["step"]] = c["error"]
    for s in st:
        if s["kind"] == "rejected":
            err[s["step"]] = str(s.get("observation") or "rejected")
    ws_end = json.loads((sd / "workspace_post.json").read_text()) if (sd / "workspace_post.json").exists() else {}
    known_att = {a.get("id") for e in (json.loads((sd / "pre.json").read_text()).get("inbox") or [])
                 for a in e.get("attachments") or []} if (sd / "pre.json").exists() else set()
    ws0 = P.ws_text(bank27.staged(row))
    made = {p: v for p, v in ws_end.items() if p.startswith("/workspace/") and (v or "").strip() != (ws0.get(p) or "").strip()}
    put_at = {}   # terminal step -> files it made or changed (first terminal command naming the file; final recorded text)
    for p, v in made.items():
        i = next((s["step"] for s in st if s["tool"] in ("terminal", "execute_bash")
                  and (p in str((s.get("args") or {}).get("command")) or p.rsplit("/", 1)[-1] in str((s.get("args") or {}).get("command")))), None)
        if i is not None:
            put_at.setdefault(i, {})[p] = v
    fixes = []

    def planned(s):
        if s["step"] in err:
            return {"tool": "think", "args": {}}
        if s["step"] in put_at:
            return {"tool": "_put", "args": {"files": put_at[s["step"]]}}
        a = dict(s.get("args") or {})
        if s["tool"] == "send_email" and a.get("attachments"):
            new = [x.rsplit("/", 1)[-1] if str(x).startswith("/downloads/") and x.rsplit("/", 1)[-1] in known_att else x
                   for x in a["attachments"]]
            if new != a["attachments"]:
                fixes.append(s["step"]); a["attachments"] = new
        return {"tool": s["tool"], "args": a}
    plan = [planned(s) for s in st]
    played = R27.play(row, plan)
    steps = []
    for s, p in zip(st, played):
        c = dict(p["call"])
        if s["step"] in err:
            c = {"name": s["tool"], "args": s.get("args") or {}, "result": s.get("observation"), "error": err[s["step"]]}
            steps.append({**p, "call": c, "rejected": s["kind"] == "rejected", "post": p["pre"], "post_ws": p["pre_ws"]})
            continue
        replay_err = c.get("error")
        c["name"] = s["tool"] if s["kind"] != "env" else c["name"]
        if s["kind"] == "env":
            c["args"] = s.get("args") or {}   # the arguments as the agent sent them (the replay may have mapped a path)
        c["result"] = s.get("observation")
        c["error"] = None
        steps.append({**p, "call": c, "replay_error": str(replay_err)[:200] if replay_err else None})
    pre_rec, post_rec = sd / "pre.json", sd / "post.json"
    import ws_store
    check = {}
    if pre_rec.exists():
        check["pre_match"] = json.loads(pre_rec.read_text()) == (P.initial(row)[0] if not steps else steps[0]["pre"])
    if post_rec.exists() and steps:
        import re
        hdr = lambda x: json.loads(re.sub(r'\[file [^\]\\]+\]\\n', "", json.dumps(x)))   # the current bridge's "[file <name>]" line
        rec = hdr(json.loads(post_rec.read_text())); got = hdr(steps[-1]["post"])
        check["post_match"] = rec == got
        if not check["post_match"]:
            check["post_diff"] = sorted(k for k in set(rec) | set(got) if rec.get(k) != got.get(k))
    check["replay_errors"] = [i for i, s in enumerate(steps) if s.get("replay_error")]
    check["terminal_files"] = {i: sorted(v) for i, v in put_at.items()}
    check["download_paths_mapped"] = fixes
    if ws_end and steps:
        got = steps[-1]["post_ws"]
        check["ws_diff"] = sorted(p for p in set(ws_end) | set(got) if (ws_end.get(p) or "").strip() != (got.get(p) or "").strip())
    return {"row": row, "steps": steps, "check": check, "result": res}


def init():
    import engine4 as E, judge_note4, judge as J, budget
    budget.USAGE = USAGE; budget.CAP = CAP
    judge_note4.CACHE = SET / "judge_note_cache.jsonl"; judge_note4._cache = None
    J.CACHE = SET / "judge_intent_cache.jsonl"; J.USAGE = USAGE; J._cache = None
    import grade23 as G23
    E.JUDGE = G23._pending_wrap(J.judge, "third_label", {"claims": False})
    E.NOTE_JUDGE = G23._pending_wrap(judge_note4.judge, "note", {"only_actions_or_known": False})


def one(job):
    import yaml, engine4 as E, play as P, bank27
    import grade as G3
    P.staged = bank27.staged
    try:
        L = load(job)
        ix = json.loads((SET / "set.json").read_text())["tasks"][job["task"]]
        d = json.loads((ROOT / ix["rule_file"]).read_text())
        files = "\n".join(f"## {p}\n{v[:3000]}" for p, v in P.initial(L["row"])[1].items()) or "(none)"
        R = {**d["rules"], "_note_env": L["row"]["environment"] + "\n\n# Files on disk at the start\n" + files}
        owner = (yaml.safe_load(L["row"]["environment"]) or {}).get("owner_email")
        st = L["steps"]
        Lr = E.label_run(R, st, owner)
        done, req = E.completion(R, st[0]["pre"], st[-1]["post"], st[0]["pre_ws"], st[-1]["post_ws"]) if st else (False, {})
        pend = [i for i, s in enumerate(Lr["steps"]) if any(
            (f.get("note_judge") or {}).get("judge_pending") or (f.get("judge") or {}).get("judge_pending") for f in s["findings"])]
        ck = d["checks"]
        return {**job, "rule_file": ix["rule_file"], "rules_failed_checks": ck.get("failed") or [],
                "labels": [s["label"] for s in Lr["steps"]], "sub_reasons": [s["sub_reason"] for s in Lr["steps"]],
                "findings": [s["findings"] for s in Lr["steps"]], "tools": [s["call"]["name"] for s in st],
                "args": [s["call"]["args"] for s in st], "errors": [bool(s["call"].get("error")) for s in st],
                "unsafe": Lr["unsafe"], "intent": Lr["intent"], "completion": done, "requirements": req,
                "outcome": G3.outcome(Lr["unsafe"], Lr["intent"], done), "judge_pending_steps": pend, "n_steps": len(st),
                "loader_check": L["check"], "final_message": next((s["call"]["args"].get("message") for s in reversed(st)
                                                                   if s["call"]["name"] == "finish"), None)}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {**job, "crash": f"{type(e).__name__}: {e}"[:300], "tb": traceback.format_exc()[-1500:]}


def main():
    if subprocess.run(["git", "diff", "--quiet", "v4.2-set0", "--", *FROZEN], cwd=ROOT).returncode:
        sys.exit("v4.2 rules / prompts / checks / engine differ from v4.2-set0: refusing to grade")
    for f in ("judge_note_cache.jsonl", "judge_intent_cache.jsonl"):
        if not (SET / f).exists() and (G / "out/v4.2-set0" / f).exists():
            shutil.copy(G / "out/v4.2-set0" / f, SET / f)
    import openai_key
    try:
        openai_key.get("grade27")
    except Exception as e:  # noqa: BLE001
        print("OpenAI not available:", str(e)[:200], file=sys.stderr)
    todo = jobs()
    if "--only" in sys.argv:
        todo = todo[: int(sys.argv[sys.argv.index("--only") + 1])]
    with ProcessPoolExecutor(4, initializer=init) as ex:
        out = list(ex.map(one, todo, chunksize=1))
    f = ROOT / "arm_s27/grades27.jsonl"
    f.write_text("".join(json.dumps(x, default=str) + "\n" for x in out))
    import budget
    budget.USAGE = USAGE
    print(len(out), "runs ->", f.relative_to(ROOT), "; crashed", sum("crash" in x for x in out), "; judge pending steps",
          sum(len(x.get("judge_pending_steps") or []) for x in out), f"; spend ${budget.spent():.2f}", "(key:", openai_key.which(), ")")
    print("loader: pre mismatch", sum(x.get("loader_check", {}).get("pre_match") is False for x in out),
          "; post mismatch", sum(x.get("loader_check", {}).get("post_match") is False for x in out))
    for x in out:
        if "crash" in x:
            print(x["key"], x["condition"], x["crash"], x["tb"]); break


if __name__ == "__main__":
    main()
