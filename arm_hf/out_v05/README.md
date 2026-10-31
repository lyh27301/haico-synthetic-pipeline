---
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
- 87 tasks, 6 with an NPC. agent_models: {"gpt-4o-mini": 62, "gpt-4o-mini+gpt-5-mini": 25}.

| toolkit | v0.4 tasks | run on the harness (after the step-9 gates) | **good on the harness** |
|---|---|---|---|
| gmail | 64 | 50 | **46** |
| sqldb | 43 | 42 | **24** |
| medical | 14 | 14 | **4** |
| commerce | 12 | 12 | **6** |
| finance | 6 | 6 | **3** |
| evidence | 4 | 4 | **4** |
| **total** | 143 | 128 | **87** |

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
