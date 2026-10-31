"""Step 9 Part B: discoverability gate on the repaired NPC tasks (arm_s9/npc_tasks). The agent learns the request from
the NPC, so the extraction sees the instruction + role text + the NPC's scripted reply (scenarios.json strategy_hint).
  .venv/bin/python arm_s9/gate_npc.py -> arm_s9/gate_npc/<id>.json"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402
from recipe import discover_gate as D  # noqa: E402

CTX = json.loads((ROOT / "harness/agent_context.json").read_text())
OUT = ROOT / "arm_s9/gate_npc"; OUT.mkdir(exist_ok=True)
for d in sorted((ROOT / "arm_s9/npc_tasks").iterdir()):
    prof = driver.profile_for(d); t = d.name
    task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
    npc = json.loads((d / "scenarios.json").read_text())
    role = CTX.get(t, "") + f"\n\n(Reply from {npc['name']} when messaged: {npc.get('strategy_hint')})"
    # the "only reachable on chat ... chat_npc" sentence names the channel, not a record: leave it out of the search
    # extraction (with it, the extractor tries to call chat_npc and returns no usable search)
    instr = re.sub(r"\s*\w+ is only reachable on chat.*?chat_npc\.", "", task.problem_statement)
    r = D.check(prof, task, str(d / "environment.yaml"), role, instruction=instr)
    rec = {"task": t, "toolkit": prof.NAME, "status": "pass" if r["ok"] else "undiscoverable", "check": r}
    (OUT / f"{t}.json").write_text(json.dumps(rec, indent=1, default=str))
    print(rec["status"], r["reason"], t)
