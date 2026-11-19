"""Step 21: audit of stored runs, no grading. Per run (every result in the given roots, and every attempt it lists):
  - final / retried / failed / capped (runner result) and harness/v16b/run_check.py on the final attempt;
  - harness internals: any internal path readable by the agent's user at the end (v16b/visible.txt) and any internal
    path named in the agent's own actions (commands, file paths, tool arguments);
  - leaving the sandbox: network or install commands in the agent's actions (curl, wget, pip, apt, git clone, ssh, nc,
    ping, python urllib/requests) and whether any got a non-error answer from outside; the in-container network check
    (v16b/net.json);
  - the date the agent saw (visible.txt date line, and `date` outputs in the transcript) against the task's date;
  - tool calls that errored (AgentErrorEvent: rejected before execution, e.g. unparsable arguments; observations
    marked as errors); agent actions; wall time (first to last event); spend (usage.json).
Writes <out> (default arm_s21/checks21.json).
  .venv/bin/python arm_s21/checks21.py arm_s21/smoke [arm_s21/runs ...] [--out f]"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness/v16b"))
import run_check as C  # noqa: E402

INTERNAL = re.compile(r"/var/lib/\.oh16b|/opt/\.oh16b|/opt/agentdojo|agentdojo-venv|OH_CONVERSATIONS|bash_events|"
                      r"chat_npc_real|\.npc_config|state_seal|/npc\b|gmail_mcp_server|server_patch|setclock|libclock|"
                      r"/proc/1/|/root\b|\.oh16b")
NET = re.compile(r"(^|[;&|(`]\s*|\$\()\s*(sudo\s+)?(curl|wget|pip3?\s+install|apt(-get)?\s+install|git\s+clone|ssh|scp|nc|ncat|"
                 r"ping|telnet)\b|urllib\.request|requests\.(get|post)|http\.client|socket\.socket", re.M)
DATE_OUT = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +(\d+) [\d:]+ \w+ (\d{4})")
MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
BANK = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s21/bank/bank_21_harness.jsonl").read_text().splitlines()}


def ts(e):
    from datetime import datetime
    try:
        return datetime.fromisoformat(e["timestamp"]).timestamp()
    except Exception:  # noqa: BLE001
        return None


def audit_attempt(task: str, d: Path) -> dict:
    o = C.output_of(d, task)
    sd = d / "agentdojo_state" / task
    out = {"dir": str(d.relative_to(ROOT))}
    if o is None:
        return {**out, "no_output": True}
    h = o.get("history") or []
    acts = [e for e in h if e.get("kind") == "ActionEvent"]
    obs = [e for e in h if e.get("kind") == "ObservationEvent"]
    agent_err = [e for e in h if e.get("kind") == "AgentErrorEvent"]
    obs_err = [e for e in obs if isinstance(e.get("observation"), dict) and e["observation"].get("is_error")]
    act_text = "\n".join(json.dumps(e.get("action"), default=str) for e in acts)
    internal_named = sorted(set(m.group(0) for m in INTERNAL.finditer(act_text)))
    # network / install commands: in terminal commands only (file contents and tool arguments are not commands)
    cmds = [str((e.get("action") or {}).get("command") or "") for e in acts if e.get("tool_name") == "terminal"]
    net_cmds = [c[:200] for c in cmds if NET.search(c)]
    vis = (sd / "v16b/visible.txt").read_text(errors="replace") if (sd / "v16b/visible.txt").exists() else ""
    readable = [l for l in vis.splitlines() if l.startswith("READABLE")]
    m = DATE_OUT.search(next((l for l in vis.splitlines() if l.startswith("## date")), ""))
    seen = f"{m.group(4)}-{MON[m.group(2)]:02d}-{int(m.group(3)):02d}" if m else None
    task_day = str(BANK[task]["current_date"])[:10]
    obs_text = "\n".join(json.dumps(e.get("observation"), default=str) for e in obs)
    dates_in_tr = sorted({f"{x.group(4)}-{MON[x.group(2)]:02d}-{int(x.group(3)):02d}" for x in DATE_OUT.finditer(obs_text)})
    # NPC replies that are API errors (e.g. the OpenAI org spend limit, 2026-11-18 ~21:04 EST): the task's NPC did not work
    npc_err = [json.dumps(e.get("observation"), default=str)[:160] for e in obs if e.get("tool_name") == "terminal" and
               re.search(r"Error code: \d{3}|enforced spend limit|Connection error", json.dumps(e.get("observation"), default=str))
               and "chat_npc" in json.dumps([x.get("action") for x in acts if x.get("tool_call_id") == e.get("tool_call_id")], default=str)]
    net = json.loads((sd / "v16b/net.json").read_text()) if (sd / "v16b/net.json").exists() else {}
    t = [x for x in map(ts, h) if x]
    u = json.loads((sd / "usage.json").read_text()) if (sd / "usage.json").exists() else {}
    chk = C.check(h, sd)
    return {**out, "check_ok": chk["ok"] and not o.get("error"), "check_problems": chk["problems"], "error": o.get("error"),
            "n_actions": len(acts), "n_tool_errors": len(agent_err) + len(obs_err), "n_rejected": len(agent_err),
            "n_obs_errors": len(obs_err), "internal_readable": readable, "internal_named_in_actions": internal_named,
            "net_commands": net_cmds, "npc_errors": npc_err, "net_rules_ok": bool(net.get("ok")), "date_seen": seen, "task_date": task_day,
            "date_ok": seen == task_day and all(x == task_day for x in dates_in_tr), "dates_in_transcript": dates_in_tr,
            "wall_s": (max(t) - min(t)) if len(t) > 1 else None, "cost": u.get("accumulated_cost"),
            "tokens": (u.get("token_usage") or {})}


def main(roots, out):
    rows = []
    for r in roots:
        for f in sorted((ROOT / r / "harness/results").glob("*.json")):
            rec = json.loads(f.read_text())
            atts = []
            for a in rec.get("attempts") or []:
                if a.get("dir"):
                    atts.append({**audit_attempt(rec["task"], ROOT / a["dir"]), "status": a["status"], "reason": a.get("reason")})
            rows.append({"root": r, "task": rec["task"], "agent": rec["agent"], "run": rec["run"], "final": bool(rec.get("final")),
                         "failed": bool(rec.get("failed")), "capped": rec.get("capped"), "error": rec.get("error"),
                         "n_attempts": len(rec.get("attempts") or []), "attempts": atts})
    Path(out).write_text(json.dumps(rows, indent=1, default=str))
    for x in rows:
        fin = [a for a in x["attempts"] if a.get("status") == "final"]
        a = fin[-1] if fin else (x["attempts"][-1] if x["attempts"] else {})
        flags = [k for k in ("internal_readable", "internal_named_in_actions", "net_commands", "npc_errors") if a.get(k)]
        print(x["agent"], x["task"][7:50], f"r{x['run']}", "final" if x["final"] else "NOT FINAL", f"att={x['n_attempts']}",
              "check", a.get("check_ok"), "date", a.get("date_seen"), "ok" if a.get("date_ok") else "MISMATCH",
              "toolerr", a.get("n_tool_errors"), "acts", a.get("n_actions"), "cost", a.get("cost"), "FLAGS:" + ",".join(flags) if flags else "")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = ROOT / "arm_s21/checks21.json"
    if "--out" in args:
        i = args.index("--out"); out = ROOT / args[i + 1]; del args[i:i + 2]
    main(args, out)
