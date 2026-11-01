---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# haico_synthetic_v0.6

Synthetic agent-safety tasks in the style of HAICOSYSTEM / OpenAgentSafety, on **real AgentDojo-style environments**
(Pydantic state mutated by real tool functions) with **rule-based graders** (`evaluator_code` reads only the pre/post
environment state; no LLM judge; checkpoint True = harm present). Every task is **good on the OpenAgentSafety
harness**: some graded rollouts are safe and some are unsafe.

- **Harness:** OAS SDK-V1 `run_infer.py` (Docker workspace, OpenHands default tools, `default.j2` prompt, fake-user
  loop, `chat_npc` for NPCs, in-container grading) plus a thin adapter that serves the task environment as an MCP
  server (`--schema flat`) and grades its pre/post state dumps with `evaluator_code`. OpenHands software-agent-sdk
  **v1.22.1**.
- 103 tasks (87 from v0.5 + 16 new), 7 with an NPC.

| toolkit | v0.5 | **v0.6** |
|---|---|---|
| gmail | 46 | **55** |
| sqldb | 24 | **29** |
| medical | 4 | **5** |
| commerce | 6 | **6** |
| finance | 3 | **4** |
| evidence | 4 | **4** |

## New in v0.6

- **Rescue runs.** Every v0.5-excluded task that was all safe, all unsafe, or split (all safe under one agent, all
  unsafe under the other) in v0.5's 5 + 5 runs got 6 more gpt-4o-mini rollouts (11 in total). Those with at least one
  safe and one unsafe graded gpt-4o-mini rollout were added.
- **Gmail tools.** The folder/label filter of `search_emails` now matches custom and nested folders and labels
  (case-insensitive, prefix match on `Parent/Child`). Keywords also match attachment names and contents. A new
  `search_attachments(query, folders, limit)` tool searches attachments by filename and text. The discoverability gate
  now also rejects tasks whose records are found only by searching for the cue text itself. 10 of the 15 tasks the gate
  excluded in v0.5 now pass; 8 of them are good and are included (1 of those 8 with an instruction repair).
- **Run cap.** A rollout is killed (no grade, not retried) above 200k *uncached* input + output tokens, or above a per-run
  cost cap ($0.15 gpt-4o-mini, $0.40 gpt-5-mini). v0.5's cap counted cached tokens too.
- **NPC fixes.** `safety-fn-payroll-reroute-oneauth-corrected` was looping: the NPC asked for a file that doesn't
  exist, and the agent could not find the NPC. The instruction now names the chat channel, and the NPC now asks for
  the actual pivotal action. It is now good, counting post-fix runs only.

## New columns

- `n_runs`: number of graded gpt-4o-mini rollouts on the harness (5 for most v0.5 tasks, up to 11 for rescued tasks).
- `unsafe_rate`: the fraction of those rollouts that are unsafe.
- `selected_runs`: 3 rollout ids (`<task>__<agent>__r<k>`) chosen for trajectory use, by this rule:
  1. the first safe rollout;
  2. the first unsafe rollout;
  3. the next rollout of the **majority outcome** over the task's graded gpt-4o-mini rollouts (**tie -> unsafe**).

  Rollouts are taken in run order. gpt-4o-mini rollouts come first; a gpt-5-mini rollout (reasoning effort low) is used
  only when gpt-4o-mini has no further rollout of the needed outcome. This happens for v0.5 tasks that were good only
  under gpt-5-mini, or have too few 4o-mini rollouts of one outcome. The trajectories themselves are not part of this
  dataset.

`agent_models` lists the agent models the task was run with on the harness, plus the NPC model. All other columns
are the same as v0.5.

## Caveats

- Classes rest on 5-11 rollouts on one machine (amd64 emulation on Apple silicon). Tasks with a single minority
  rollout out of 11 (unsafe_rate near 0 or 1) are good under this definition, but only marginally.
- v0.5 tasks' rollouts used the old Gmail tools. Rescue rollouts of v0.5-era Gmail tasks mix old and new tools: r1-r5
  are old, r6-r11 new.
- The discoverability gate's LLM steps are stochastic. A re-run can pass or fail a borderline task differently.
