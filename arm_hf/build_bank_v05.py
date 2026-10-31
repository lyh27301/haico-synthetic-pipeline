"""Build yanhanliu/haico_synthetic_v0.5 = the tasks that are good ON THE OAS HARNESS (step 9 Part C): run_infer.py +
harness/oas_agentdojo.py + MCP, SDK v1.22.1; 5 x gpt-4o-mini (harness defaults), then 5 x gpt-5-mini (low reasoning
effort) on tasks all_safe / all_unsafe under 4o-mini; good = mixed under either agent (graded runs only).
Rows come from the step-9 task source (arm_s9/bank_s9.jsonl: v0.4 rows with the Part A instruction repairs and the
Part B NPC fixes); same schema as v0.4. agent_models = the agents the task was run with on the harness.
  .venv/bin/python arm_hf/build_bank_v05.py  ->  arm_hf/out_v05/ (data/*.parquet, manifest.json, README.md)"""
import collections, json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "arm_hf")); sys.path.insert(0, str(ROOT / "analysis"))
from build_bank import SCHEMA  # noqa: E402

OUT = ROOT / "arm_hf" / "out_v05"
MODEL = {"4omini": "gpt-4o-mini", "5mini": "gpt-5-mini"}
TKS = ["gmail", "sqldb", "medical", "commerce", "finance", "evidence"]


def main():
    agg = json.loads((ROOT / "arm_s9" / "aggregate.json").read_text())
    rows_by = {r["task"]: r for r in agg["rows"]}
    ran = collections.defaultdict(set)
    for d in agg["details"]:
        ran[d["task"]].add(d["agent"])
    src = [json.loads(x) for x in (ROOT / "arm_s9" / "bank_s9.jsonl").read_text().splitlines()]
    rows = []
    for r in src:
        t = r["instance_id"]
        if rows_by[t]["harness_class"] != "good":
            continue
        npc = [m for m in r["agent_models"] if m["name"] != "agent"]
        r["agent_models"] = [{"model": MODEL[a], "name": "agent"} for a in ("4omini", "5mini") if a in ran[t]] + npc
        rows.append(r)
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), OUT / "data" / "train-00000-of-00001.parquet")
    by = collections.Counter(r["toolkit"] for r in rows)
    man = {"n": len(rows), "by_toolkit": dict(by), "npc": sum(r["npcs"] for r in rows),
           "agent_models": dict(collections.Counter("+".join(m["model"] for m in r["agent_models"] if m["name"] == "agent")
                                                    for r in rows)),
           "harness": "OAS SDK-V1 run_infer.py + harness/oas_agentdojo.py (MCP, --schema flat), SDK v1.22.1",
           "tasks": {r["instance_id"]: {"toolkit": r["toolkit"], "gate": rows_by[r["instance_id"]]["gate"],
                                        "harness_unsafe": rows_by[r["instance_id"]]["harness_unsafe"],
                                        "driver_unsafe": rows_by[r["instance_id"]]["driver_unsafe"]} for r in rows}}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    hb = agg["headline"]["by_toolkit"]
    table = "\n".join(f"| {tk} | {hb[tk]['v04']} | {hb[tk]['staged']} | **{by.get(tk, 0)}** |" for tk in TKS)
    tot = (sum(hb[tk]["v04"] for tk in TKS), sum(hb[tk]["staged"] for tk in TKS), len(rows))
    (OUT / "README.md").write_text(README.format(n=len(rows), table=table, t0=tot[0], t1=tot[1], t2=tot[2],
                                                 npc=man["npc"], am=json.dumps(man["agent_models"])))
    print(json.dumps({k: v for k, v in man.items() if k != "tasks"}, indent=1))


README = """---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# haico_synthetic_v0.5

Synthetic agent-safety tasks in the style of HAICOSYSTEM / OpenAgentSafety, on **real AgentDojo-style environments**
(Pydantic state mutated by real tool functions) with **rule-based graders** (`evaluator_code` reads only the pre/post
environment state; no LLM judge; checkpoint True = harm present).

**New in v0.5: every task here is good on the OpenAgentSafety harness**, not on our local driver.
- **Harness:** the OAS SDK-V1 `run_infer.py` (Docker workspace, OpenHands default tools, `default.j2` prompt, fake-user
  loop, `chat_npc` for NPCs, in-container grading), with a thin adapter that serves the task environment to the agent
  as an MCP server (`--schema flat`) and grades the MCP server's pre/post state dumps with `evaluator_code`.
- **SDK:** OpenHands software-agent-sdk **v1.22.1** (the last tag compatible with `run_infer.py` at HEAD; the group's
  pin 128452b4 is not reachable yet).
- **Agents:** 5 rollouts with **gpt-4o-mini** (harness defaults); tasks that were all safe or all unsafe under it got 5
  more with **gpt-5-mini** (reasoning effort low). **Good = mixed (some safe, some unsafe graded runs) under either
  agent.** Runs that the harness's stuck detection aborted were rerun once; runs that ended without a grade (stuck
  twice, or killed for exceeding a 200k-token per-run cap) are not counted.
- {n} tasks, {npc} with an NPC. agent_models: {am}.

| toolkit | v0.4 tasks | run on the harness (after the step-9 gates) | **good on the harness** |
|---|---|---|---|
{table}
| **total** | {t0} | {t1} | **{t2}** |

## Changes from v0.4

- **Discoverability gate (literal search).** An LLM extracts the searches a literal agent would run from the
  instruction (names, labels, folders, dates, subjects, ids), they are run against the initial environment with the
  real tools, and the records the violator path touches must come back. Failing tasks got one instruction rewrite
  (records named the way the data names them, no hint of the harm); tasks failing twice were excluded. These tasks'
  `problem_statement` differs from v0.4.
- **NPC placement.** In NPC tasks the NPC's request now lives only in `agent_scenarios` (it was also staged in the
  mailbox or the instruction); the instruction makes contacting the colleague a required step, and for Gmail says the
  colleague is reachable only on chat (`chat_npc`).
- Same schema and column conventions as v0.4 (the full env YAML is still in `environment`; the harness adapter replaces
  it with the agent's role text in the prompt). `manifest.json` has each task's gate status and per-agent unsafe counts
  on the harness and on the driver.

## Caveats

- Classes are based on 5 rollouts per agent on one machine (amd64 emulation on Apple silicon).
- gpt-5-mini ran with reasoning effort low (the harness default is high) to stay within budget.
"""

if __name__ == "__main__":
    main()
