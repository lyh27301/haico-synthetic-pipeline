---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# haico_synthetic_v0.2

Synthetic agent-safety tasks in the style of HAICOSYSTEM / OpenAgentSafety. They run on **real AgentDojo-style
environments** (Pydantic state mutated by real tool functions) and use **rule-based graders** (`evaluator_code`
reads only the pre/post environment state; no LLM judge). Polarity: the checkpoint is True when the harm is present.

Every task here is **good**: under at least one agent (gpt-4o-mini at temperature 1.0, or gpt-5-mini with low
reasoning effort), its 5 rollouts had **mixed** outcomes (some safe, some unsafe). Tasks that were safe in every
rollout, or unsafe in every rollout, are excluded.

| toolkit | env | tasks |
|---|---|---|
| gmail | Gmail (9 tools) | 30 |
| sqldb | SQLDatabaseToolkit over a research database | 16 |
| medical | EpicFHIR clinic records (HAICOSYSTEM healthcare) | 6 |
| **total** | | **52** |

Of these, 24 are variants: 14 surface variants of good tasks (step 6) and 10 cue-salience variants (step 5).
Their ids contain `-v1` or `-sal-`.

## Changes from v0.1

v0.1 is unchanged. v0.2 is the same bank after a data-hygiene repair.

Every v0.1 task was checked by three deterministic gates:
- **Data hygiene:** a task record must not reuse a base record's id, and must not re-create a base entity under a
  new id.
- **Discoverability:** every id on the reference path must be findable by the agent.
- **Grader equivalence:** the grader must not require a value that the instruction does not fix.

17 of the 57 tasks were flagged and repaired mechanically. The mechanic was never changed.
- A duplicate of a base record was dropped, and references point at the base record.
- A different record that reused a base id got a fresh id. Before the fix, the base record shadowed it, so the
  agent could not open the task's record by id.
- A missing list or search step was added to the reference path.

Every repaired task passes the dry run and all gates. It was then re-run (5 rollouts gpt-4o-mini, plus 5 rollouts
gpt-5-mini if the first five were all safe or all unsafe):
- **12 stayed good** and are included here, from their repaired version.
- **5 left the bank** because they were no longer mixed: `gm-leads-master-send`, `gm-priya-reset-v11`,
  `ev-altered-image-falsify`, `ev-depo-integrator-privacy` and `md-knee-addendum-falsify`. Their files are kept in
  the source repo, tagged `retired`.
- The evidence toolkit has no good task left.

`manifest.json` lists which tasks were repaired and why each retired task left.

## Columns

The columns are those of `yanhanliu/openagentsafety_v1.1`, plus `toolkit`.
- `problem_statement` is the task instruction (`task.md`).
- `agent_scenarios` / `agent_profiles` hold the NPC from `scenarios.json` (only 2 tasks have one). In the other tasks,
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
