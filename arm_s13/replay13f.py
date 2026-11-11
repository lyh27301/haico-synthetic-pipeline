"""Step 13f: re-grade the stored runs with the agent's workspace files visible (harness/workspace_bridge.py). No model
calls and no new rollouts: every action is the one the agent logged.

Scope: every run of a finance or evidence task and of every attachment-carrier task (arm_s13/outcomes.jsonl).
Per run:
  1. workspace: if the run has a terminal command (other than chat_npc) or a file_editor edit, a fresh container of the
     agent image (no network) replays those actions in order (arm_s13/ws_driver.py) and the workspace is snapshotted
     before every env call. Runs with no such action keep an empty workspace (/workspace starts empty in the image).
  2. env: the env calls of calls.jsonl run again on a fresh env three times:
       base       as logged (must reproduce the step-13e verdict and utility: the control);
       ws         workspace overlaid (file arguments and gmail attachment paths resolve to the agent's files);
       ws_dl      ws, plus /downloads/<id> attachment paths read as <id> (the tool-contract fix, a separate switch).
     Framework-rejected calls stay rejected. Grader v2 grades the final state; grader v4 checks utility on it with the
     workspace snapshot under `workspace`.
Caveat: the replay is counterfactual after the first call the overlay changes. The agent saw an error there and its
later actions answered that error (a retry, another path, giving up); the replay keeps those actions as logged.

  .venv/bin/python arm_s13/replay13f.py [--workers 6]  ->  arm_s13/outcomes13f.jsonl, arm_s13/workspaces13f/*.json
  --rest-gmail: the gmail runs outside that scope (the /downloads re-grade covers every send_email), written to
                arm_s13/outcomes13f_rest.jsonl."""
import argparse, collections, json, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(S13)); sys.path.insert(0, str(ROOT / "harness"))
import replay as R  # noqa: E402
import grader_v4, workspace_bridge  # noqa: E402
from replay import grader_v2, profiles  # noqa: E402

IMAGE = "openagentsafety-agentdojo:fac00adba"
MODES = ("base", "ws", "ws_dl")
OUT = S13 / "outcomes13f.jsonl"; WSD = S13 / "workspaces13f"
LOCK = threading.Lock()


def writes(s) -> bool:
    if s["tool"] == "file_editor":
        return isinstance(s["args"], dict) and s["args"].get("command") not in (None, "view")
    if s["tool"] == "terminal":
        c = str(s["args"].get("command") or "")
        return bool(c.strip()) and not re.match(r"\s*chat_npc\b", c) and not s["args"].get("is_input")
    return False


class Box:
    """One container running ws_driver.py."""
    def __init__(self):
        self.cid = subprocess.run(["docker", "run", "-d", "--rm", "--platform", "linux/amd64", "--network", "none",
                                   "--entrypoint", "sleep", IMAGE, "infinity"], capture_output=True, text=True,
                                  check=True).stdout.strip()
        subprocess.run(["docker", "exec", self.cid, "mkdir", "-p", "/tmp/.wsb"], check=True)
        for f in (ROOT / "harness/workspace_bridge.py", S13 / "ws_driver.py"):
            subprocess.run(["docker", "cp", str(f), f"{self.cid}:/tmp/.wsb/{f.name}"], check=True, capture_output=True)
        self.p = subprocess.Popen(["docker", "exec", "-i", self.cid, "python3", "/tmp/.wsb/ws_driver.py"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def ask(self, req):
        self.p.stdin.write(json.dumps(req) + "\n"); self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.p.kill()
        subprocess.run(["docker", "kill", self.cid], capture_output=True)


def workspaces(steps):
    """Snapshot before each step (index -> ws), the actions' return codes, and the final snapshot."""
    if not any(writes(s) for s in steps):
        return {}, [], {}
    box = Box(); snaps, rcs, ws, dirty = {}, [], {}, False
    try:
        for i, s in enumerate(steps):
            if s["kind"] in ("env", "rejected"):
                if dirty:
                    ws = box.ask({"op": "snap"})["ws"]; dirty = False
                snaps[i] = ws
            elif writes(s):
                r = box.ask({"op": "terminal", "command": s["args"]["command"]} if s["tool"] == "terminal"
                            else {"op": "file_editor", "args": s["args"]})
                rcs.append({"step": i, "rc": r.get("rc"), "tail": r.get("tail", "")[-300:]}); dirty = True
        final = box.ask({"op": "snap"})["ws"]
    finally:
        box.close()
    return snaps, rcs, final


def env_replay(x, row, ctx, steps, snaps, mode, calls_stored):
    prof = profiles.get(R.toolkit(row))
    _, env, rt = __import__("gen_utility").fresh(row)
    pre = R.rt(prof.env_to_dict(env))
    ci = iter(calls_stored); calls, rej, notes = [], [], []
    for i, s in enumerate(steps):
        if s["kind"] == "env":
            c = next(ci, None) or {"name": s["tool"], "args": {k: v for k, v in s["args"].items() if k != "summary"}}
            if mode == "base":
                res, err = rt.run_function(env, c["name"], c["args"]); note = None
            else:
                res, err, note = workspace_bridge.call(prof, env, rt, c["name"], c["args"], snaps.get(i, {}),
                                                       downloads=mode == "ws_dl")
            if note:
                notes.append({"step": i, "tool": c["name"], "via": note, "error_now": bool(err),
                              "error_logged": bool(c.get("error"))})
            calls.append({"name": c["name"], "args": c["args"], "result": R.rt({"error": err} if err else res), "error": err})
        elif s["kind"] == "rejected":
            rej.append(s["rec"])
    post = R.rt(prof.env_to_dict(env))
    v = grader_v2.grade(row, pre, post, calls, ctx, rej)
    return pre, post, v, notes


def one(x, row, ctx, spec):
    hist = R.history(x["traj_dir"], x["task"])
    prof = profiles.get(R.toolkit(row))
    rt_fns = set(__import__("gen_utility").fresh(row)[2].functions)
    steps = R.steps_of(hist, rt_fns)
    calls_stored = R.jl(x["state_dir"] / "calls.jsonl")
    snaps, rcs, final_ws = workspaces(steps)
    rec = {"task": x["task"], "agent": x["agent"], "run": x["run"], "replayed_actions": len(rcs),
           "action_failures": sum(r["rc"] != 0 for r in rcs), "workspace_files": sorted(final_ws)}
    for m in MODES:
        pre, post, v, notes = env_replay(x, row, ctx, steps, snaps, m, calls_stored)
        done, req = grader_v4.utility(spec, pre | {"workspace": {}}, post | {"workspace": final_ws}) if spec else (None, {})
        rec[m] = {"unsafe": bool(v["unsafe"]), "flags": {f: bool(v[f]) for f in R.FLAGS}, "utility": done if spec else None,
                  "requirements": req, "outcome": grader_v4.outcome(bool(v["unsafe"]), done) if spec else None,
                  "overlay": notes}
    WSD.mkdir(exist_ok=True)
    (WSD / f"{x['task']}__{x['agent']}__r{x['run']}.json").write_text(json.dumps({"workspace": final_ws, "actions": rcs}))
    return rec


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--limit", type=int)
    ap.add_argument("--tasks"); ap.add_argument("--rest-gmail", action="store_true"); a = ap.parse_args()
    global OUT
    if a.rest_gmail:
        OUT = S13 / "outcomes13f_rest.jsonl"
    O = {(o["task"], o["agent"], o["run"]): o for o in map(json.loads, (S13 / "outcomes.jsonl").read_text().splitlines())}
    xs, rows = R.bank_runs()
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    def in_scope(o):
        return o["toolkit"] in ("finance", "evidence") or o["carrier"] == "attachment"
    todo = [x for x in xs if (k := (x["task"], x["agent"], x["run"])) in O and
            (in_scope(O[k]) if not a.rest_gmail else (O[k]["toolkit"] == "gmail" and not in_scope(O[k])))]
    if a.tasks:
        todo = [x for x in todo if x["task"] in a.tasks.split(",")]
    done = set()
    if OUT.exists() and not a.tasks:
        done = {(r["task"], r["agent"], r["run"]) for r in map(json.loads, OUT.read_text().splitlines())}
    todo = [x for x in todo if (x["task"], x["agent"], x["run"]) not in done][:a.limit]
    specs = {}
    for f in (S13 / "utility").glob("*.json"):
        s = json.loads(f.read_text())
        if s["gate"]["passed"]:
            specs[s["task"]] = s
    print(len(todo), "runs to do,", len(done), "done", flush=True)
    n = collections.Counter()

    def go(x):
        try:
            r = one(x, rows[x["task"]], ctx.get(x["task"], ""), specs.get(x["task"]))
        except Exception as e:  # noqa: BLE001
            r = {"task": x["task"], "agent": x["agent"], "run": x["run"], "crash": f"{type(e).__name__}: {e}"[:300]}
        o = O[(x["task"], x["agent"], x["run"])]
        r |= {"toolkit": o["toolkit"], "carrier": o["carrier"], "stored": {k: o[k] for k in ("unsafe", "utility", "outcome")}}
        with LOCK:
            with open(OUT, "a") as fh:
                fh.write(json.dumps(r) + "\n")
            n["done"] += 1; n["crash"] += "crash" in r
            if n["done"] % 25 == 0:
                print(n["done"], dict(n), flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(go, todo))
    print("finished", dict(n), flush=True)


if __name__ == "__main__":
    main()
