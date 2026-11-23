"""Read-only: a compact text view of a -v34 task row for the admission review (statement, role, labels, references,
checkpoints, environment).   .venv/bin/python arm_s34/dump34.py <task-substring> [body_chars]"""
import json, sys
from pathlib import Path
import yaml

S = Path(__file__).resolve().parent


def short(x, n):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    s = s.replace("\n", " | ")
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


def main():
    pat = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 350
    for f in sorted((S / "bank/tasks").glob("*.json")):
        if pat not in f.name:
            continue
        r = json.loads(f.read_text()); e = yaml.safe_load(r["environment"])
        print("#####", r["instance_id"], "| date", r.get("current_date"), "| hook", r.get("hook"), "| outcome", r.get("outcome"),
              "| intent", r.get("requester_intent"), "| mech", r.get("mechanic_id"), "| npcs", r.get("npcs"))
        print("STATEMENT:", r["problem_statement"].strip())
        print("ROLE:", short(r["_agent_context"], 600))
        if r.get("agent_scenarios"):
            print("NPC:", short(r["agent_scenarios"], 900))
        print("CHECKPOINTS:", short(r.get("checkpoints"), 700))
        for k in ("safe_reference", "violator_reference"):
            print(k.upper() + ":")
            for s in r.get(k) or []:
                print("   ", s["tool"], short(s["args"], 260))
        print("FILES:", r.get("workspace_files"))
        for k, v in e.items():
            if k in ("inbox", "sent", "trash", "drafts"):
                for m in v or []:
                    print(f"  [{k}] {m.get('id')} {m.get('timestamp')} from={m.get('sender')} to={m.get('recipients')} "
                          f"cc={m.get('cc')} subj={m.get('subject')!r} labels={m.get('labels')} thread={m.get('thread_id')}")
                    print("        body:", short(m.get("body", ""), n))
                    for a in m.get("attachments") or []:
                        print("        att:", a.get("id"), a.get("name") or a.get("filename"), short(a.get("content", ""), n))
            elif k == "databases":
                for db, tabs in v.items():
                    for tn, tb in tabs.items():
                        rows = tb.get("rows") if isinstance(tb, dict) else tb
                        print(f"  [{db}.{tn}] {len(rows or [])} rows; cols {list((rows or [{}])[0].keys()) if rows else tb}")
                        for i, row in enumerate(rows or []):
                            print("       ", i, short(row, n))
            else:
                print(f"  [{k}]", short(v, max(n * 3, 600)))


if __name__ == "__main__":
    main()
