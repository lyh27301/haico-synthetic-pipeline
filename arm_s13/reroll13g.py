"""Step 13g: the tasks to re-roll because their stored runs hit a toolkit row the audit marked `fix` (a call on that
tool returned a not-found error, or silently did nothing on an unknown id), outside the 89 v0.8 task-file tasks.
  .venv/bin/python arm_s13/reroll13g.py  ->  arm_s13/reroll13g.json"""
import collections, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
NOT_FOUND = re.compile(r"NotFound|not found|does not exist|no such", re.I)


def hit(s, fix_tools):
    if s["kind"] != "env" or s["tool"] not in fix_tools:
        return False
    o = str(s["observation"])
    a = s["args"] if isinstance(s["args"], dict) else {}
    if s["tool"] == "send_email":   # only the /downloads/<id> row of send_email was `fix`
        return o.startswith('{"error"') and any(isinstance(x, str) and x.startswith("/downloads/")
                                                for x in a.get("attachments") or [])
    if s["tool"] in ("delete_emails",):
        return '"deleted": []' in o
    if s["tool"] == "delete_contact":
        return '"success": false' in o.lower()
    return bool(NOT_FOUND.search(o)) and (o.startswith('{"error"') or '"success": false' in o.lower())


def main():
    before = json.loads((S13 / "toolkit_audit_before.json").read_text())
    fix_tools = {r["tool"] for r in before if r["verdict"] == "fix"}
    v08 = set(json.loads((ROOT / "arm_hf/out_v08/workspace_manifest.json").read_text()))
    rec = {(o["task"], o["agent"], o["run"]): o for o in map(json.loads, (S13 / "outcomes_record.jsonl").read_text().splitlines())}
    runs = collections.defaultdict(list)
    for f in sorted((S13 / "steps").glob("*.json")):
        t, a, r = f.stem.split("__"); k = (t, a, int(r[1:]))
        if rec[k]["contaminated"]:
            continue
        tools = sorted({s["tool"] for s in json.loads(f.read_text()) if hit(s, fix_tools)})
        if tools:
            runs[t].append({"agent": a, "run": k[2], "tools": tools, "outcome": rec[k]["outcome"]})
    tk = {o["task"]: o["toolkit"] for o in rec.values()}
    extra = {t: v for t, v in runs.items() if t not in v08}
    out = {"fix_tools": sorted(fix_tools),
           "tasks_hit": len(runs), "tasks_hit_in_v08": len(set(runs) & v08), "tasks_extra": len(extra),
           "extra_by_toolkit": dict(collections.Counter(tk[t] for t in extra)),
           "runs_hit_extra": sum(len(v) for v in extra.values()),
           "runs_hit_extra_by_outcome": dict(collections.Counter(x["outcome"] for v in extra.values() for x in v)),
           "tools_hit_extra": dict(collections.Counter(x for v in extra.values() for r in v for x in r["tools"])),
           "extra_tasks": {t: extra[t] for t in sorted(extra)}}
    (S13 / "reroll13g.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "extra_tasks"}, indent=1))


if __name__ == "__main__":
    main()
