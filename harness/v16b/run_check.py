"""Step 20: is a stored run a complete run? Used by the harness (oas_agentdojo16b.py marks a run that fails it with an
error), by the runner (harness/v16b/runner.py counts a run as final only if it passes) and on stored runs (CLI below).

A run passes when
  1. it ends properly: its last agent action is the finish tool ("finish"), or it used the whole step cap
     (max_iterations agent actions, "step_cap");
  2. its last step is not cut off: every agent action in the history has its observation (or an agent error event)
     with the same tool_call_id;
  3. the per-step record agrees with the history: as many recorded steps (v16b/steps/NNNN.json) as executed agent actions
     (actions the framework rejected before execution, e.g. for a missing argument, record no step), and
     the end-of-run capture (v16b/steps/final.json, post.json) exists.
Step 19 showed why 3 matters: after a watchdog kill the SDK's REST fallback reported the conversation "finished"
and the stored history held only the system prompt and the request (2 events), while the container had recorded 37
steps. No error was set.

  .venv/bin/python harness/v16b/run_check.py arm_s16c/runs arm_s16c/qwen arm_s19/runs   # result trees
"""
from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_ITER = 500


def _d(e):
    if isinstance(e, dict):
        return e
    try:
        return e.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return {}


def check(history: list, state_dir: Path | None, max_iter: int = MAX_ITER) -> dict:
    """history: the run's events (dicts or SDK events). Returns {"ok", "end", "problems", "n_actions", "n_steps"}."""
    ev = [_d(e) for e in history or []]
    acts = [e for e in ev if e.get("kind") == "ActionEvent" or (e.get("source") == "agent" and e.get("action") is not None
                                                                   and e.get("tool_call_id"))]
    answered = {e.get("tool_call_id") for e in ev if e.get("source") == "environment" or
                e.get("kind") in ("ObservationEvent", "AgentErrorEvent", "UserRejectObservation")}
    # executed = reached the tool server (an observation); an action the framework rejected before execution (AgentErrorEvent,
    # e.g. a missing argument) records no step in the container
    executed = {e.get("tool_call_id") for e in ev if e.get("kind") == "ObservationEvent"}
    n_exec = sum(1 for e in acts if e.get("tool_call_id") in executed)
    problems = []
    last = acts[-1] if acts else None
    if last is not None and last.get("tool_name") == "finish":
        end = "finish"
    elif len(acts) >= max_iter:
        end = "step_cap"
    else:
        end = "no_finish"
        problems.append(f"does not end with the finish tool or the step cap (last agent action: "
                        f"{last.get('tool_name') if last else 'none'}; {len(acts)} actions)")
    open_ = [e.get("tool_name") for e in acts if e.get("tool_call_id") not in answered]
    if open_:
        problems.append(f"last step cut off: {len(open_)} action(s) without an observation ({', '.join(map(str, open_[-3:]))})")
    n_steps = None
    if state_dir is not None:
        sd = Path(state_dir)
        st = sd / "v16b" / "steps"
        n_steps = len([f for f in st.glob("[0-9]*.json")]) if st.exists() else 0
        if n_steps != n_exec:
            problems.append(f"{n_steps} steps recorded in the container but {n_exec} executed agent actions in the history")
        if not (st / "final.json").exists():
            problems.append("no end-of-run capture (v16b/steps/final.json)")
        if not (sd / "post.json").exists():
            problems.append("no post.json")
    return {"ok": not problems, "end": end, "problems": problems, "n_actions": len(acts), "n_steps": n_steps}


def output_of(traj_dir: Path, task: str) -> dict | None:
    """The harness output record of `task` in an output folder (last line wins, as the harness reads it)."""
    o = None
    for f in sorted(Path(traj_dir).glob("output.critic_attempt_*.jsonl")):
        for ln in f.read_text().splitlines():
            if ln.strip() and f'"{task}"' in ln[:300]:
                x = json.loads(ln)
                if x.get("instance_id") == task:
                    o = x
    return o


def check_result(rec: dict) -> dict:
    """A runner result record (arm_v08-style: task, traj_dir, state_dir) -> check(), plus the harness error if any."""
    o = output_of(ROOT / rec["traj_dir"], rec["task"]) if rec.get("traj_dir") else None
    if o is None:
        return {"ok": False, "end": None, "problems": ["no harness output for this task in its folder"], "n_actions": 0,
                "n_steps": None}
    r = check(o.get("history") or [], ROOT / rec["state_dir"] if rec.get("state_dir") else None)
    if o.get("error"):
        r["ok"] = False; r["problems"].insert(0, f"harness error: {str(o['error'])[:200]}")
    return r


def scan(tree: Path) -> list[dict]:
    out = []
    for f in sorted((tree / "harness" / "results").glob("*.json")):
        rec = json.loads(f.read_text())
        counted = rec.get("final", rec.get("graded"))
        r = check_result(rec)
        out.append({"file": str(f.relative_to(ROOT)), "task": rec["task"], "agent": rec["agent"], "run": rec["run"],
                    "counted_final": bool(counted), **r})
    return out


if __name__ == "__main__":
    for t in sys.argv[1:]:
        rows = scan(ROOT / t)
        bad = [r for r in rows if r["counted_final"] and not r["ok"]]
        print(f"{t}: {len(rows)} results, {sum(r['counted_final'] for r in rows)} counted final, {len(bad)} fail the check")
        for r in bad:
            print("  ", r["task"], r["agent"], f"r{r['run']}", "|", "; ".join(r["problems"]))
