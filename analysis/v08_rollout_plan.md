# v0.8 rollout plan (not run)

Nothing here has been rolled out. The user starts the Qwen serving job when ready.

## What changes for the re-rolled tasks

1. **Task files on disk** (step 13f decision 3, `recipe/workspace_files.py`): 89 tasks (finance 23, evidence 15, attachment-carrier gmail 51).
   - The role's files are staged under `/workspace` and the protected files are withheld.
   - The rows have `task_version` "0.8" in `arm_hf/out_v08/`.
2. **Harness** (applies to every agentdojo rollout from now on):
   - the workspace overlay (`--workspace`), plus `--workspace-wins` on v0.8 rows;
   - `--downloads` on;
   - hidden task and grader state (`--task-file`, sealed state dumps);
   - the trimmed image.
3. **Toolkit fixes from step 13g:** see the section below. The tasks whose runs failed on a toolkit the audit marked `fix` are re-rolled in the same batch.

## Batch

| | tasks | runs (×5 per agent) |
|---|---|---|
| v0.8 task-file change | 89 | 890 |
| step 13g toolkit fixes, not already above | see below | see below |

**Agents:** gpt-4o-mini ×5 and Qwen3.5-9B ×5 at temperature 1.0, set explicitly, with the same run caps, endpoint guard, cost watchdog and budget guard as step 12.

## Cost estimate (v0.8 task-file part)

The estimate comes from the stored runs of these same 89 tasks (`usage.json`). They run about twice as long as the bank average.

| | per run | runs | estimate |
|---|---|---|---|
| gpt-4o-mini rollouts | $0.012 (147k tokens; bank average $0.006) | 445 | **$5.3** |
| NPC (gpt-4o-mini) | step-12 rate, $0.41 per 100 tasks | 89 tasks | $0.4 |
| Qwen3.5-9B, active GPU | 0.016 GPU-h | 445 | **≈ 7.1 GPU-h** |
| Qwen3.5-9B, allocated | step-12 ratio of allocated to active, 1.4 | | ≈ 10 GPU-h |

- **How the Qwen figure is derived:** 0.0109 GPU-h per run in step 12 (12.0 GPU-h over 1,102 runs), scaled by token use. These tasks average 334k tokens per run against the bank's 229k.
- **Margin:** staged files give the agent more to read. Budget for **≈ $7 and ≈ 9 GPU-h active (≈ 13 GPU-h allocated)** for this part.

## Before the batch

1. **One smoke rollout per toolkit** (finance, evidence, gmail; gpt-4o-mini, one run each) with `OAS_WORKSPACE_ROOT` pointing at the bank folder. It checks the adapter path that this step tested only in pieces:
   - the task file is uploaded and consumed;
   - the evaluator shim grades from sealed state;
   - the dumps are unsealed on download;
   - the role's files sit in `/workspace` and the withheld ones do not.
2. **Rollouts write to a new output dir** per agent, keyed by `instance_id` and with `task_version` 0.8 recorded, so the v0.7 runs of the same ids stay as they are.

## After the batch

- **Grading:** grader v2, the v3 probes, and v4 utility with the workspace snapshot. The utility specs and probes are unchanged.
- **Goodness:** goodness v2 is recomputed for the v0.8 rows. The 2×2 is reported separately for v0.7 and v0.8 runs of the re-rolled tasks, because the task changed.
- **Exclusions:** contaminated runs are excluded as before. The scan (`arm_s13/contamination.py`) runs on the new runs too. Hits should drop to zero.
