# Step 13g: toolkit audit for id discoverability

Harness side only: agent mistakes made with an adequate tool stay as they are. No rollouts. The full table, the before/after tool lists and the run classification are in `arm_s13/toolkit_audit.md` (`arm_s13/toolkit_audit.py`).

## Audit

**48 rows**: every write, send or delete tool that takes an id or exact key, across all six toolkits.
- **Lookup tool:** checked against the lookup's real output.
- **Described:** read from the tool and parameter descriptions.
- **Error helps:** measured. Each tool is called on its base environment with a bogus id, and the result is checked for a named lookup or a list of the valid values.
- **The before phase** ran on the code as committed in step 13f, extracted with `git archive`, so it shows what the stored runs saw.

**36 rows were `fix`; 0 remain.** The 12 `ok` rows are unchanged: their errors are byte-identical before and after.

| cause | rows | fix |
|---|---|---|
| lookup exists, but neither the description nor the error mentions it | 26 | the not-found error names the lookup |
| silent on an unknown id: gmail `delete_emails`, `delete_contact`, `add_or_update_contact` (created a new contact), `download_attachment` (accepted any id) | 4 | they now return or raise a not-found error that names the lookup |
| no lookup tool: commerce alerts (38 tasks start with alerts), Teladoc consultations, prescription reminders | 4 | new lookups `inventory_list_alerts`, `teladoc_list_consultations`, `prescription_list_reminders`; the errors name them |
| misleading: `bank_send_statement` promised only downloaded statements, and no tool listed the task's own files | 1 | new lookup `bank_list_files`; the description and error name it (the only description change) |
| misleading contract: `download_attachment` returns `/downloads/<id>`, which `send_email` rejected | 1 | the `--downloads` harness switch (step 13f); the tool is unchanged |

**Contract and scope:**
- The new lookups are read-only and list real state (the same records the write tools act on). Like the toolkit's other list tools, they write no log.
- No fuzzy name matching was added.
- **Exposure:** every medical bank task uses the clinic vantage, so the clinic tool list is unchanged (8). The two new medical lookups and the Teladoc and prescription fixes reach no current task.

**Checks:**
- The six suite smoke tests pass, extended to the new lookups and errors.
- `harness/test_mcp_server.py` passes on all six toolkits.
- The rebuilt image loads all toolkits with the new tool counts.
- **The stored grading still stands.** I re-graded under the new code the 15 stored runs whose calls the gmail behavior changes touch (unknown ids in downloads, contacts and deletes). None changes verdict or outcome.

## Wrong-id and wrong-type runs by cause

A run is **harness-caused** when its failed call hit a row with no lookup path, a misleading description, or a lookup the description never mentions. It is **agent-caused** when the lookup existed and was described.

| | runs | harness-caused | agent-caused | mixed |
|---|---|---|---|---|
| `attempt_wrong_id` | 86 | 11 | **72** | 3 |
| `attempt_wrong_type` | 237 | **208** | 22 | 7 |

By toolkit:

| toolkit | wrong_id: harness / agent / mixed | wrong_type: harness / agent / mixed |
|---|---|---|
| gmail | 7 / 72 / 3 | 167 / 2 / 7 |
| finance | none | 37 / 0 / 0 |
| medical | 4 / 0 / 0 | 4 / 0 / 0 |
| commerce | none | 0 / 20 / 0 |

- **wrong_type is mostly harness.**
  - gmail: 174 attempts are `send_email` with the `/downloads/<id>` path that `download_attachment` handed out.
  - finance: 37 are `bank_send_statement` on the task's own report, which no tool listed.

  The step-13f record already re-graded the `/downloads` part (15 runs moved). The fix of record for both is the re-roll.
- **wrong_id is mostly the agent.** In 72 gmail runs the agent attached a file by its name. The description says ids, and the error lists the known ids.
- **commerce wrong_type is all agent:** a product id passed as an order or item id. The order and item tools already said "search orders / items to find the id".
- **medical, 8 runs, harness by the rule:** the lookup is the same tool's `action='list'`, and nothing said so. The calls themselves pass a patient id or a document title as the document id.

## Re-rolls (folded into the v0.8 plan)

- **41 tasks to re-roll** (gmail 29, medical 7, commerce 5): their stored runs, 101 of them, hit a fixed row. The 55 other tasks with a hit are already among the 89 v0.8 task-file tasks.
- **Batch:** 130 tasks and 1,300 runs. Budget ≈ $9 OpenAI and ≈ 10 GPU-h active (≈ 14 allocated). See `analysis/v08_rollout_plan.md`.
- **Bank:** the 41 rows carry a `task_changes` note in `arm_hf/out_v08/` (local) and keep `task_version` 0.7, because the task itself is unchanged.
