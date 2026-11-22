Step 21: agent runs on the first training set (43 tasks, 4 agents, 3 runs each = 516 runs).

Runs depend only on the tasks, not on the grader rules, so they start now; rules that still fail their checks are
fixed in parallel and the runs are graded later. Nothing is graded in this step.

First: push all local commits to origin (GitHub). origin/main is still at 1d2eb0f8. Not to Hugging Face.

Tasks: arm_s18/bank/train_set0 (46 tasks) minus the three whose TASK needs a change before it is worth running:
ev-witness-index-export-fixed, ev-witness-index-export-fixed-v122 (the environment does not say who reads the
Packet folder) and sq-embargo-archive-v131-v18 (the archive never reaches the outside place). That leaves 43.
The other tasks whose rules fail a check are eligible: their problem is in the rules, not in the task.

Scope of this step: all 43 tasks, 4 agents, 3 runs each (r1-r3) = 516 runs. Use the run numbering and folder
layout that a later top-up to 5 runs per task would use, so these runs are kept.

Agents, 3 runs per task each:
- gpt-6-luna and claude-haiku-5-5 (API);
- Qwen3.5-9B and Qwen3.5-35B-A3B (cluster). They need different GPU classes, so they are two separate serving
  jobs; submit both at the start and do not wait for one before the other. Follow ~/babel-private/BABEL.md; nothing
  from there goes into the repo. Waiting in the queue is normal; the runs must be resumable.

Harness: harness/v16b with the step 18 and step 20 changes (archive tool for sqldb, reworded canned reply, the new
runner and end-of-run check, fresh folder per attempt). The NPC stays as it is (stateless chat_npc).
- Rebuild the agent image once and record its hash.
- Smoke test first on 3 tasks (one with the archive tool on sqldb, one with the NPC, one
  gmail) with one API agent, and check: no agent reads harness internals, the fixed date holds, the end-of-run check
  passes, tool calls parse.
- Run the API agents while the cluster jobs are queued.
- A run counts only if it is final under harness/v16b/run_check.py. Failed runs are listed, not silently dropped.

Report: analysis/step21.md
- Per agent: runs asked, final, retried, failed; tool calls errored; steps per run; wall time; spend.
- Per task and agent: number of final runs (so gaps are visible).
- Any run that touched harness internals or left the sandbox (expect none).
- The follow-up question about whether the setting looked like a test, as in 16c, per agent.
- No outcome classes and no labels in this report: grading is the next step.

Stop after these runs. Do not add more runs.

Limits: OpenAI stop at $5, Anthropic stop at $5 (16c cost about $0.17 and $0.30 for 60 runs each). Do not change
tasks or rules. Commit when the API agents are done and again when each cluster agent is done; no HF push.
