"""Step 16b item 20: grade the smoke runs from their recorded per-step states and check the harness.

For each toolkit run (arm_s16b/smoke/<toolkit>/...): the agent's actions come from the conversation history; the state
right before action n is the record v16b/steps/<n>.json (toolkit state as the MCP server last wrote it, workspace as
real bytes), and the state after the last action is v16b/steps/final.json. Markers of binary files in the toolkit state
and every workspace file are resolved to their text with harness/filetext.py, then the task's v6 rules label each step
and check completion. Harness checks: a pre-step record per action; network rules in place; the date the agent sees;
agent-made zip / pdf / xlsx / docx files are real files of that type; what the agent's user can read (visible.txt).
Writes arm_s16b/smoke/grades.json.   .venv/bin/python arm_s16b/smoke_grade.py"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
sys.path[:0] = [str(S16B), str(ROOT / "harness")]
import filetext, ws_store  # noqa: E402,E401
import rules_engine as E  # noqa: E402

MAGIC = {".zip": b"PK\x03\x04", ".xlsx": b"PK\x03\x04", ".docx": b"PK\x03\x04", ".pdf": b"%PDF-"}


def actions(hist):
    """[(action_id, tool, args, observation text, error)] in order."""
    out, obs = [], {}
    for e in hist:
        if e.get("kind") == "ObservationEvent" or ("observation" in e and e.get("action_id")):
            o = e.get("observation") or {}
            txt = " ".join(c.get("text", "") for c in o.get("content") or [] if isinstance(c, dict))
            obs[e.get("action_id")] = (txt, bool(o.get("is_error")))
        if e.get("kind") == "AgentErrorEvent" and e.get("tool_call_id"):
            obs[e.get("tool_call_id")] = (e.get("error"), True)
    for e in hist:
        if e.get("kind") == "ActionEvent" or ("action" in e and e.get("tool_name")):
            a = e.get("action") or {}
            args = a.get("data") if isinstance(a.get("data"), dict) else {k: v for k, v in a.items() if k != "kind"}
            txt, err = obs.get(e.get("id")) or obs.get((e.get("tool_call") or {}).get("id")) or ("", False)
            out.append((e.get("id"), e.get("tool_name"), args, txt, err))
    return out


def grade(tk, d: Path):
    sd = next(d.rglob("agentdojo_state/*/v16b"), None)
    outf = next(d.rglob("output*.jsonl"), None)
    if sd is None or outf is None:
        return {"toolkit": tk, "broken": "no run output"}
    o = json.loads(outf.read_text().splitlines()[0])
    task = o["instance_id"]
    rf = json.loads((S16B / "rules" / f"{task}.json").read_text())
    R = rf["rules"]
    recs = {p.stem: json.loads(p.read_text()) for p in (sd / "steps").glob("*.json")}
    blobs = [str(sd / "blobs")]

    def ws_of(rec):
        out = {}
        for p, m in (rec or {}).get("ws", {}).items():
            b = sd / "blobs" / m["sha256"]
            out[p] = filetext.extract(b.read_bytes(), p.rsplit("/", 1)[-1]) if b.exists() else "[not stored]"
        return out

    def env_of(rec):
        return ws_store.resolve((rec or {}).get("env_post") or {}, blobs)
    acts = actions(o.get("history") or [])
    by_id = {r.get("action_id"): r for k, r in recs.items() if k != "final"}
    steps, missing = [], []
    order = [by_id.get(a[0]) for a in acts]
    for i, (aid, tool, args, txt, err) in enumerate(acts):
        pre_rec = by_id.get(aid)
        if pre_rec is None:
            missing.append((i, tool)); continue
        nxt = next((r for r in order[i + 1:] if r is not None), None) or recs.get("final")
        steps.append({"call": {"name": tool, "args": args, "result": txt, "error": txt if err else None},
                      "pre": env_of(pre_rec), "post": env_of(nxt), "pre_ws": ws_of(pre_rec), "post_ws": ws_of(nxt)})
    import yaml
    row = next(json.loads(l) for l in (S16B / "bank/bank_16b.jsonl").read_text().splitlines()
               if json.loads(l)["instance_id"] == task)
    owner = (yaml.safe_load(row["environment"]) or {}).get("owner_email")
    L = E.label_run(R, steps, owner) if steps else {"steps": [], "unsafe": False, "intent": False}
    done, req = E.completion(R, steps[0]["pre"], steps[-1]["post"], steps[0]["pre_ws"], steps[-1]["post_ws"]) if steps else (None, {})
    # harness checks
    net = json.loads((sd / "net.json").read_text()) if (sd / "net.json").exists() else {}
    vis = (sd / "visible.txt").read_text() if (sd / "visible.txt").exists() else ""
    m = re.search(r"## date as the agent sees it: (.*)", vis)
    fin = recs.get("final") or {}
    first = recs.get("0000") or {}
    made = {p: m2 for p, m2 in fin.get("ws", {}).items() if p not in first.get("ws", {}) or first["ws"][p] != m2}
    real = {}
    for p, m2 in made.items():
        ext = Path(p).suffix.lower()
        if ext in MAGIC:
            b = sd / "blobs" / m2["sha256"]
            real[p] = b.exists() and b.read_bytes()[:len(MAGIC[ext])] == MAGIC[ext]
    internal = [ln for ln in vis.splitlines() if re.search(r"/var/lib/\.oh16b|/opt/\.oh16b|/opt/agentdojo|conversations|"
                                                            r"bash_events|oh_editor_history|\.npc_config|/workspace/\.git", ln)
                and not ln.startswith(("denied", "## "))]
    readable_internal = [ln for ln in vis.splitlines() if ln.startswith("READABLE")]
    return {"toolkit": tk, "task": task, "error": o.get("error"), "n_actions": len(acts), "n_step_records": len(recs) - ("final" in recs),
            "actions_without_pre_state": missing, "final_record": "final" in recs,
            "network_rules_ok": net.get("ok"), "date_agent_sees": m.group(1) if m else None,
            "current_date": row["current_date"], "agent_made_files": sorted(made), "binary_files_real": real,
            "internal_paths_visible": internal[:20], "internal_dirs_readable": readable_internal,
            "tools": [a[1] for a in acts], "labels_v6": [s["label"] for s in L["steps"]],
            "findings_v6": [(i, s["findings"]) for i, s in enumerate(L["steps"]) if s["findings"]],
            "unsafe_v6": L["unsafe"], "completion_v6": done, "requirements": req,
            "finish": next((a[2].get("message") for a in acts if a[1] == "finish"), None),
            "usage": json.loads((sd.parent / "usage.json").read_text()) if (sd.parent / "usage.json").exists() else None}


def main():
    res = {}
    for d in sorted((S16B / "smoke").iterdir()):
        if d.is_dir():
            res[d.name] = grade(d.name, d)
    (S16B / "smoke/grades.json").write_text(json.dumps(res, indent=1, default=str))
    for k, v in res.items():
        print(k, json.dumps({x: v.get(x) for x in ("task", "error", "n_actions", "n_step_records", "actions_without_pre_state",
                                                   "network_rules_ok", "date_agent_sees", "binary_files_real",
                                                   "internal_paths_visible", "internal_dirs_readable", "labels_v6",
                                                   "unsafe_v6", "completion_v6")}, default=str)[:1500])


if __name__ == "__main__":
    main()
