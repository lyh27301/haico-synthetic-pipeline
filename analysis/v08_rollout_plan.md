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
3. **Toolkit fixes from step 13g** (`arm_s13/toolkit_audit.md`):
   - every not-found error names its lookup;
   - the gmail silent no-ops now raise;
   - four lookup tools were added: `bank_list_files`, `inventory_list_alerts`, `teladoc_list_consultations` and `prescription_list_reminders`.

   These apply to every task of those toolkits. The tasks whose stored runs hit a fixed row are re-rolled in the same batch.

## Batch

| | tasks | runs (×5 per agent) |
|---|---|---|
| v0.8 task-file change (`task_version` 0.8) | 89 | 890 |
| step 13g re-rolls not already above (`arm_s13/reroll13g.json`: gmail 29, medical 7, commerce 5) | 41 | 410 |
| **batch** | **130** | **1,300** (650 per agent) |

- **Why these 41:** each has at least one stored run (101 in all) where a call on a tool the audit marked `fix` returned a not-found error or did nothing on an unknown id.
  - The calls: `send_email` with `/downloads/<id>` 75, `delete_emails` 13, `epic_manage_clinical_documents` 8, `organize_email` 6, `shopify_draft_order` 4, `epic_download_files` 1 and `inventory_setup_alert` 1.
  - Their tasks are unchanged, so they keep `task_version` 0.7 with a `task_changes` note.
- **Not re-rolled:** the 55 other tasks whose runs hit a fixed row are already in the 89. sqldb has no fixed row. The remaining tasks never hit one.

**Agents:** gpt-4o-mini ×5 and Qwen3.5-9B ×5 at temperature 1.0, set explicitly, with the same run caps, endpoint guard, cost watchdog and budget guard as step 12.

## Cost estimate

The estimate comes from the stored runs of these same 130 tasks (`usage.json`). The 89 task-file tasks run about twice as long as the bank average.

| | per run | runs | estimate |
|---|---|---|---|
| gpt-4o-mini, 89 task-file tasks | $0.012 (147k tokens; bank average $0.006) | 445 | $5.3 |
| gpt-4o-mini, 41 re-roll tasks | $0.0069 (82k tokens) | 205 | $1.4 |
| NPC (gpt-4o-mini) | step-12 rate, $0.41 per 100 tasks | 130 tasks | $0.5 |
| **OpenAI total** | | | **≈ $7.2** |
| Qwen3.5-9B, 89 task-file tasks | 0.016 GPU-h (334k tokens) | 445 | 7.1 GPU-h |
| Qwen3.5-9B, 41 re-roll tasks | 0.0068 GPU-h (144k tokens) | 205 | 1.4 GPU-h |
| **Qwen active GPU** | | | **≈ 8.5 GPU-h** |
| Qwen allocated | step-12 ratio of allocated to active, 1.4 | | ≈ 12 GPU-h |

- **How the Qwen figure is derived:** 0.0109 GPU-h per run in step 12 (12.0 GPU-h over 1,102 runs), scaled by token use. These tasks average 334k tokens per run against the bank's 229k.
- **Margin:** staged files give the agent more to read. Budget for **≈ $9 and ≈ 10 GPU-h active (≈ 14 GPU-h allocated)** for the whole batch. That is about half of step 12, which cost $17.60 and 12.0 GPU-h.

## Before the batch

1. **One smoke rollout per toolkit** (finance, evidence, gmail, medical, commerce; gpt-4o-mini, one run each) with `OAS_WORKSPACE_ROOT` pointing at the bank folder. It checks the adapter path that this step tested only in pieces:
   - the task file is uploaded and consumed;
   - the evaluator shim grades from sealed state;
   - the dumps are unsealed on download;
   - the role's files sit in `/workspace` and the withheld ones do not.
2. **Rollouts write to a new output dir** per agent, keyed by `instance_id` and with `task_version` 0.8 recorded, so the v0.7 runs of the same ids stay as they are.

## After the batch

- **Grading:** grader v2, the v3 probes, and v4 utility with the workspace snapshot. The utility specs and probes are unchanged.
- **Mechanics check:** the step-13g question is answered by comparing `attempt_wrong_id` / `attempt_wrong_type` and failed_safe / unsafe_failed rates on the re-rolled tasks before and after, per toolkit.
- **Goodness:** goodness v2 is recomputed for the v0.8 rows. The 2×2 is reported separately for v0.7 and v0.8 runs of the re-rolled tasks, because the task changed.
- **Exclusions:** contaminated runs are excluded as before. The scan (`arm_s13/contamination.py`) runs on the new runs too. Hits should drop to zero.
