---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# haico_synthetic_v0.1

Synthetic agent-safety tasks in the style of HAICOSYSTEM / OpenAgentSafety. They run on **real AgentDojo-style
environments** (Pydantic state mutated by real tool functions) and use **rule-based graders** (`evaluator_code`
reads only the pre/post environment state; no LLM judge). Polarity: the checkpoint is True when the harm is present.

Every task here is **good**: under at least one agent (gpt-4o-mini at temperature 1.0, or gpt-5-mini with low
reasoning effort), its 5 rollouts had **mixed** outcomes (some safe, some unsafe). Tasks that were safe in every
rollout, or unsafe in every rollout, are excluded.

| toolkit | env | tasks |
|---|---|---|
| gmail | Gmail (9 tools) | 32 |
| sqldb | SQLDatabaseToolkit over a research database | 16 |
| medical | EpicFHIR clinic records (HAICOSYSTEM healthcare) | 7 |
| evidence | EvidenceManagement (HAICOSYSTEM trial evidence) | 2 |
| **total** | | **57** |

Of these, 25 are variants: 15 surface variants of good tasks (step 6) and 10 cue-salience variants (step 5).
Their ids contain `-v1` or `-sal-`.

## Columns

The columns are those of `yanhanliu/openagentsafety_v1.1`, plus `toolkit`.
- `problem_statement` is the task instruction (`task.md`).
- `agent_scenarios` / `agent_profiles` hold the NPC from `scenarios.json` (only 3 tasks have one). In the other tasks,
  a simulated user delivers the instruction.
- `environment` is the full initial environment state (`environment.yaml`), not a prose description.
- `checkpoints` is the task's one-line harm statement.
- `evaluator_code` is the grader (`grade_checkpoints(pre, post)`).
- `toolkit` names the environment the task runs in.
- Columns we cannot fill are null: `dependencies`, `github_url`, the `workspace_files` / `utils_files` lists, and
  the NPC demographics.

## Caveats

- Validated on our local multi-turn driver (an OpenAI tool-calling loop plus an LLM-simulated user), **not yet in
  the OpenAgentSafety harness**. Evaluators take `(pre, post)` env dicts, not an OAS trajectory.
- Classes are based on 5 rollouts per agent.
