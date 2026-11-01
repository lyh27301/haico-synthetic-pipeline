"""Step 10 Part D: compact transcripts of the two looping NPC tasks, rebuilt from run_infer's conversation_event
stream in the run logs (errored runs have empty traj_*.json). One line per action / observation / message.
  .venv/bin/python arm_s10/npc_transcripts.py <log> <instance> [run_dir_substring]"""
import json, sys


def short(x, n=260):
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s.replace("\\n", " ").replace("\n", " ")[:n]


def main(log, inst, sub=""):
    for ln in open(log, errors="replace"):
        if not ln.startswith("{") or f'"instance_id": "{inst}"' not in ln:
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if sub and sub not in o.get("run_id", ""):
            continue
        et = o.get("event_type")
        try:
            e = json.loads(o.get("event", "{}"))
        except ValueError:
            continue
        tag = o.get("run_id", "").split("/")[-3][-12:]
        if et == "ActionEvent":
            a = e.get("action") or {}
            print(f"[{tag}] ACT {e.get('tool_name')}: {short({k: v for k, v in a.items() if k != 'kind'})}")
        elif et == "ObservationEvent":
            ob = e.get("observation") or {}
            txt = ob.get("content") or ob
            print(f"[{tag}]   OBS {short(txt, 300)}")
        elif et == "MessageEvent":
            m = e.get("llm_message") or {}
            print(f"[{tag}] MSG {e.get('source')}: {short(m.get('content'), 500)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
