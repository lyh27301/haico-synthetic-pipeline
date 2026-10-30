---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# haico_synthetic_v0.4

Synthetic agent-safety tasks in the style of HAICOSYSTEM / OpenAgentSafety. They run on **real AgentDojo-style
environments** (Pydantic state mutated by real tool functions) and use **rule-based graders** (`evaluator_code`
reads only the pre/post environment state; no LLM judge). Polarity: the checkpoint is True when the harm is present.

Every task here is **good**: under at least one agent (gpt-4o-mini at temperature 1.0, or gpt-5-mini with low
reasoning effort), its 5 rollouts had **mixed** outcomes (some safe, some unsafe). Tasks that were safe in every
rollout, or unsafe in every rollout, are excluded.

| toolkit | env | v0.3 tasks | new batch tasks | new variants | **total** |
|---|---|---|---|---|---|
| gmail | Gmail (9 tools) | 30 | 9 | 25 | **64** |
| sqldb | SQLDatabaseToolkit over a research database | 16 | 10 | 17 | **43** |
| medical | EpicFHIR clinic records (HAICOSYSTEM healthcare) | 6 | 2 | 6 | **14** |
| commerce | order / refund / shipping back office | 0 | 6 | 6 | **12** |
| finance | payments, payroll and vendor ledger | 0 | 3 | 3 | **6** |
| evidence | EvidenceManagement (7 tools) | 0 | 2 | 2 | **4** |
| **total** | | **52** | **32** | **59** | **143** |

The 143 tasks cover 61 distinct mechanics. 83 are variants (ids ending in `-vNN` or containing `-sal-`); 10 have an
NPC (`npcs = 1`).

## Changes from v0.3

v0.3 is unchanged and its 52 tasks are all here, byte-identical. v0.4 adds the step-7 tasks:
- **32 batch tasks** from new generation batches on all six toolkits, including the first tasks for `finance` and
  `commerce` and two new `evidence` tasks (v0.3 had none).
- **59 variants**: two one-axis variants (domain, persona, data or wording) were generated for one good task per
  mechanic; the ones that passed every gate and were themselves good are included.

Every new task passed the data-hygiene, discoverability and grader-equivalence gates described below before it was
evaluated, and was classified the same way (5 x gpt-4o-mini, plus 5 x gpt-5-mini when the first five were all safe or
all unsafe). `agent_models` and `dependencies` follow the v0.3 conventions. `manifest.json` gives each task's origin,
toolkit and repair status.

## Changes from v0.2 (in v0.3)

- **`agent_models`** lists every agent model the task was evaluated with, as `{"model": ..., "name": "agent"}`,
  followed for NPC tasks by the simulated NPC's model, `{"model": "gpt-4o-mini", "name": <npc name>}`.
  In v0.4: gpt-4o-mini for all 143 tasks, plus gpt-5-mini for 38.
- **`dependencies`** is `["agentdojo:<toolkit>"]`, so the harness can tell these tasks from OAS ones.
- `agent_scenarios` / `agent_profiles` are filled from `scenarios.json` for NPC tasks and are empty lists otherwise,
  as in v1.1's rows with `npcs = 0`.

## Changes from v0.1 (in v0.2)

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
- The evidence toolkit had no good task left in v0.2; v0.4 adds 4.

`manifest.json` lists which tasks were repaired and why each retired task left.

## Columns

The columns are those of `yanhanliu/openagentsafety_v1.1`, plus `toolkit`.
- `problem_statement` is the task instruction (`task.md`).
- `agent_scenarios` / `agent_profiles` hold the NPC from `scenarios.json` (10 tasks have one). In the other tasks,
  a simulated user delivers the instruction.
- `environment` is the full initial environment state (`environment.yaml`), not a prose description.
- `checkpoints` is the task's one-line harm statement.
- `evaluator_code` is the grader (`grade_checkpoints(pre, post)`).
- `toolkit` names the environment the task runs in.
- `dependencies` is `["agentdojo:<toolkit>"]`.
- Columns we cannot fill are null: `github_url`, the `workspace_files` / `utils_files` lists, and
  the NPC demographics.

## Caveats

- Validated on our local multi-turn driver (an OpenAI tool-calling loop plus an LLM-simulated user), **not yet in
  the OpenAgentSafety harness**. Evaluators take `(pre, post)` env dicts, not an OAS trajectory.
- Classes are based on 5 rollouts per agent.
