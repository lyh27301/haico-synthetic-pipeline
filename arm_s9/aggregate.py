"""Step 9 Parts C/D numbers: harness classes (5 x gpt-4o-mini, then 5 x gpt-5-mini on extremes) beside the driver's,
transitions with a per-flip reason, the discoverability gate's effect, NPC contact, harness-only issues, cost/time.
  .venv/bin/python arm_s9/aggregate.py -> arm_s9/aggregate.json (+ summary on stdout)"""
import collections, glob, json, re, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from bank import A2, S7_ARMS, bank, classify  # noqa: E402
from step7_regression import RESULTS  # noqa: E402
from recipe import profiles  # noqa: E402

S9 = ROOT / "arm_s9"; RES = S9 / "harness" / "results"
MAN = json.loads((ROOT / "arm_hf/out_v04/manifest.json").read_text())["tasks"]
TKS = ["gmail", "sqldb", "evidence", "medical", "finance", "commerce"]
AG = {"4o-mini": "4omini", "4omini": "4omini", "gpt-4o-mini": "4omini", "5-mini": "5mini", "5mini": "5mini",
      "gpt-5-mini": "5mini"}
TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


# ----------------------------------------------------------------------------- driver side

def driver_runs() -> dict:
    """{task: {agent: [unsafe 0/1, ...]}} from the result files that classified the v0.4 version of each task."""
    b = bank()
    pools = {"clean": [ROOT / d / "*.json" for d in RESULTS], "repaired": [A2 / "eval/results/*.json"],
             "new": [ROOT / a / "eval/results/*.json" for a in S7_ARMS]}
    by = {k: collections.defaultdict(lambda: collections.defaultdict(list)) for k in pools}
    for k, globs in pools.items():
        for g in globs:
            for f in glob.glob(str(g)):
                r = json.loads(Path(f).read_text())
                if r.get("unsafe") != "" and r.get("unsafe") is not None:
                    by[k][r["task"]][AG.get(r["agent"], r["agent"])].append(int(r["unsafe"]))
    return {t: dict(by[b[t]["status"]].get(t, {})) for t in MAN}


# ----------------------------------------------------------------------------- harness side

def harness_results() -> dict:
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in glob.glob(str(RES / "*.json")):
        r = json.loads(Path(f).read_text())
        out[r["task"]][r["agent"]].append(r)
    return out


def output_index() -> dict:
    """(task, agent, run, rerun) -> (output dict, run dir)."""
    idx = {}
    for f in glob.glob(str(S9 / "harness/*/*/*/*/output.jsonl")):
        p = Path(f); rd = p.parents[2].name; agent = p.parents[3].name
        m = re.match(r"(?:npc\d*_)?r(\d+)(_rerun)?$", rd)
        if not m or agent not in ("4omini", "5mini"):
            continue
        for ln in p.read_text().splitlines():
            if ln.strip():
                o = json.loads(ln)
                idx[(o["instance_id"], agent, int(m.group(1)), bool(m.group(2)))] = (o, p.parent)
    return idx


def calls_of(state_dir: Path) -> list[dict]:
    f = state_dir / "calls.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def wall_seconds(run_dir: Path, t: str) -> float | None:
    f = run_dir / "logs" / f"instance_{t}.log"
    if not f.exists():
        return None
    lines = [ln for ln in f.read_text(errors="replace").splitlines() if TS.match(ln)]
    if len(lines) < 2:
        return None
    a, b = (datetime.strptime(TS.match(x).group(1), "%Y-%m-%d %H:%M:%S") for x in (lines[0], lines[-1]))
    return (b - a).total_seconds()


def run_detail(r: dict, idx: dict, gate_targets: list[str]) -> dict:
    t, agent, k = r["task"], r["agent"], r["run"]
    o, rd = idx.get((t, agent, k, bool(r.get("rerun"))), (None, None))
    prof = profiles.get(MAN[t]["toolkit"])
    sd = ROOT / r["state_dir"] if r.get("state_dir") else None
    calls = calls_of(sd) if sd else []
    acts = collections.Counter()
    for e in (o or {}).get("history") or []:
        if e.get("kind") == "ActionEvent":
            a = e.get("action") or {}
            name = e.get("tool_name")
            if name == "terminal" and "chat_npc" in json.dumps(a):
                name = "chat_npc"
            acts[name] += 1
    mcp = {c["name"] for c in calls}
    blob = json.dumps([c.get("result") for c in calls] + [c.get("args") for c in calls if not c.get("error")],
                      default=str).lower()   # reached = a target came back in a result or was used in a working call
    reached = None if not gate_targets else any(x.lower() in blob for x in gate_targets if not x.startswith("table:"))
    sc_err = sum(1 for c in calls if c.get("error") and prof.is_state_changing(c["name"], c.get("args") or {}))
    return {"task": t, "agent": agent, "run": k, "unsafe": r.get("unsafe"), "graded": r.get("graded"),
            "stuck": r.get("stuck"), "rerun": r.get("rerun"), "first_error": r.get("first_error"),
            "first_stuck": r.get("first_stuck"), "token_capped": bool(r.get("token_capped")),
            "error": r.get("error"), "n_calls": len(calls), "mcp_errors": sum(bool(c.get("error")) for c in calls),
            "state_changing_errors": sc_err,
            "acted": any(prof.is_state_changing(c["name"], c.get("args") or {}) and not c.get("error") for c in calls),
            "reached_target": reached,
            "non_mcp": {a: n for a, n in acts.items() if a not in mcp | {"finish", "think", "chat_npc", None}},
            "chat_npc": acts.get("chat_npc", 0), "cost": (r.get("usage") or {}).get("accumulated_cost"),
            "wall_s": wall_seconds(rd, t) if rd else None}


# ----------------------------------------------------------------------------- reasons

def flip_reason(dr: str, hr: str, runs: list[dict]) -> str:
    """Main reason a task's 4o-mini bucket moved between driver and harness."""
    g = [r for r in runs if r["graded"]]
    if not g:
        return "stuck"
    if hr == "all_safe":
        safe = [r for r in g if not r["unsafe"]]
        if sum(r["reached_target"] is False for r in safe) > len(safe) / 2:
            return "search_failure"
        if sum(r["state_changing_errors"] > 0 for r in safe) > len(safe) / 2:
            return "tool_rejection"
        if sum(bool(r["non_mcp"]) for r in safe) > len(safe) / 2:
            return "file_deliverable"
        if sum(not r["acted"] for r in safe) > len(safe) / 2:
            return "did_not_act"
        return "genuine_behaviour"
    if sum(r["stuck"] for r in runs) >= 2:
        return "stuck"
    return "genuine_behaviour"


def bucket(us: list[int]) -> str | None:
    return None if not us else "all_unsafe" if all(us) else "all_safe" if not any(us) else "mixed"


# ----------------------------------------------------------------------------- main

def main():
    drv = driver_runs(); har = harness_results(); idx = output_index()
    gates = {Path(f).stem: json.loads(Path(f).read_text()) for f in glob.glob(str(S9 / "gate/*.json"))}
    gnpc = {Path(f).stem: json.loads(Path(f).read_text()) for f in glob.glob(str(S9 / "gate_npc/*.json"))}
    stage = [json.loads(x)["instance_id"] for x in (S9 / "bank_s9.jsonl").read_text().splitlines()]
    rows, details = [], []
    for t in sorted(MAN):
        tk = MAN[t]["toolkit"]
        g = gates.get(t, {}); st = g.get("status", "pass")
        if t in gnpc:
            st = "npc_fix" if gnpc[t]["status"] == "pass" else "undiscoverable"
        tg = (gnpc.get(t, {}).get("check") or {}).get("targets") or (g.get("first") or {}).get("targets") or []
        d_cls, d_b = classify({a: u for a, u in drv[t].items() if u}) if drv[t] else ("not_run", {})
        hd = {a: [run_detail(r, idx, tg) for r in sorted(v, key=lambda r: r["run"])] for a, v in har.get(t, {}).items()}
        for v in hd.values():
            details += v
        h_u = {a: [int(bool(r["unsafe"])) for r in v if r["graded"]] for a, v in hd.items()}
        h_cls, h_b = classify({a: u for a, u in h_u.items() if u}) if any(h_u.values()) else (
            "no_grade" if hd else "not_run", {})
        dr4, hr4 = bucket(drv[t].get("4omini", [])), bucket(h_u.get("4omini", []))
        rows.append({"task": t, "toolkit": tk, "gate": st, "in_stage": t in stage,
                     "driver_class": d_cls, "driver_buckets": d_b,
                     "driver_unsafe": {a: f"{sum(u)}/{len(u)}" for a, u in drv[t].items()},
                     "harness_class": h_cls, "harness_buckets": h_b,
                     "harness_unsafe": {a: f"{sum(u)}/{len(u)}" for a, u in h_u.items()},
                     "harness_no_grade": {a: sum(not r["graded"] for r in v) for a, v in hd.items()},
                     "harness_stuck_first": {a: sum(bool(r["stuck"]) or bool(r.get("first_error")) for r in v) for a, v in hd.items()},
                     "driver_4o": dr4, "harness_4o": hr4,
                     "flip_reason": flip_reason(dr4, hr4, hd.get("4omini", [])) if dr4 and hr4 and dr4 != hr4 else None})
    ran = [r for r in rows if r["in_stage"]]
    out = {"n_bank_v04": len(rows), "n_stage": len(ran)}
    out["headline"] = {
        "driver_good": sum(r["driver_class"] == "good" for r in rows),
        "harness_good": sum(r["harness_class"] == "good" for r in ran),
        "by_toolkit": {tk: {"v04": sum(r["toolkit"] == tk for r in rows),
                            "staged": sum(r["toolkit"] == tk for r in ran),
                            "harness_good": sum(r["toolkit"] == tk and r["harness_class"] == "good" for r in ran),
                            "harness_classes": dict(collections.Counter(r["harness_class"] for r in ran if r["toolkit"] == tk))}
                       for tk in TKS}}
    out["transition_overall"] = dict(collections.Counter(f"{r['driver_class']}->{r['harness_class']}" for r in ran))
    out["transition_4o"] = dict(collections.Counter(f"{r['driver_4o']}->{r['harness_4o']}" for r in ran))
    fl = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in ran:
        if r["flip_reason"]:
            fl[f"{r['driver_4o']}->{r['harness_4o']}"][r["flip_reason"]].append(r["task"])
    out["flip_reasons_4o"] = {k: {rr: {"n": len(v), "examples": v[:3]} for rr, v in d.items()} for k, d in fl.items()}
    # gate effect (4o-mini harness unsafe rate)
    def rate(sel, agent="4omini"):
        us = [int(bool(d["unsafe"])) for d in details if d["task"] in sel and d["agent"] == agent and d["graded"]]
        return {"unsafe": sum(us), "graded": len(us), "rate": round(sum(us) / len(us), 3) if us else None}
    rep = {r["task"] for r in ran if r["gate"] == "repaired"}
    unt = {r["task"] for r in ran if r["gate"] == "pass"}
    unt_gm = {t for t in unt if MAN[t]["toolkit"] == "gmail"}
    out["gate"] = {"by_toolkit": {tk: dict(collections.Counter(r["gate"] for r in rows if r["toolkit"] == tk)) for tk in TKS},
                   "harness_unsafe_repaired": rate(rep), "harness_unsafe_untouched": rate(unt),
                   "harness_unsafe_untouched_gmail": rate(unt_gm),
                   "driver_unsafe_repaired_4o": _drate(drv, rep), "driver_unsafe_untouched_4o": _drate(drv, unt),
                   "repaired_reached_target": _reach(details, rep), "untouched_reached_target": _reach(details, unt)}
    # harness-only issues
    ag = collections.defaultdict(collections.Counter)
    for d in details:
        c = ag[d["agent"]]
        c["runs"] += 1; c["graded"] += bool(d["graded"]); c["first_attempt_failed"] += bool(d["rerun"])
        c["first_attempt_stuck"] += bool(d["first_stuck"]); c["token_capped"] += d["token_capped"]
        c["stuck_rerun_still_failed"] += bool(d["first_stuck"]) and not d["graded"]
        c["stuck_final"] += (not d["graded"]) and bool(d["stuck"]); c["no_grade_final"] += not d["graded"]
        c["runs_with_mcp_error"] += d["mcp_errors"] > 0; c["mcp_errors"] += d["mcp_errors"]
        c["runs_with_non_mcp_tool"] += bool(d["non_mcp"])
        c["runs_no_mcp_call"] += d["n_calls"] == 0
    out["issues"] = {a: dict(c) for a, c in ag.items()}
    out["non_mcp_tasks"] = sorted({d["task"] for d in details if d["non_mcp"]})
    out["non_mcp_tools"] = dict(collections.Counter(k for d in details for k in d["non_mcp"]))
    # cost / time
    ct = {}
    for a in {d["agent"] for d in details}:
        cs = [d["cost"] for d in details if d["agent"] == a and d["cost"] is not None]
        ws = [d["wall_s"] for d in details if d["agent"] == a and d["wall_s"]]
        ct[a] = {"runs": len(cs), "cost_total": round(sum(cs), 3), "cost_per_run": round(sum(cs) / len(cs), 4) if cs else None,
                 "wall_per_run_s": round(sum(ws) / len(ws), 1) if ws else None}
    inv = []
    for f in glob.glob(str(S9 / "harness/*/*/invocations.jsonl")):
        inv += [json.loads(x) for x in Path(f).read_text().splitlines()]
    out["cost_time"] = ct
    out["invocations"] = {"n": len(inv), "instances": sum(i["n"] for i in inv),
                          "wall_h_sum": round(sum(i["end"] - i["start"] for i in inv) / 3600, 2)}
    out["npc"] = json.loads((S9 / "npc_contact.json").read_text()) if (S9 / "npc_contact.json").exists() else None
    if out["npc"]:
        out["npc"] = {k: v for k, v in out["npc"].items() if k != "rows"}
    (S9 / "aggregate.json").write_text(json.dumps({**out, "rows": rows, "details": details}, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


def _drate(drv, sel):
    us = [u for t in sel for u in drv[t].get("4omini", [])]
    return {"unsafe": sum(us), "runs": len(us), "rate": round(sum(us) / len(us), 3) if us else None}


def _reach(details, sel):
    rs = [d for d in details if d["task"] in sel and d["agent"] == "4omini" and d["reached_target"] is not None]
    return f"{sum(bool(d['reached_target']) for d in rs)}/{len(rs)}"


if __name__ == "__main__":
    main()
