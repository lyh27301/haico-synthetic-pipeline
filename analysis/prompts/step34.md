Step 34: scale up, wave 1. Bring the unused task families of the existing bank into the current pipeline.

Work in a worktree on branch `step34`. Nothing from ~/babel-private in the repo. No Hugging Face push. The frozen
v4.2-set0 rules, prompts, checks and engine are not changed; new rules go to grader/out/v4.2-s34 and must pass the
ten checks. OpenAI through the key selection (report fallback spend). Do not stop or remove containers, jobs or
tunnels you did not start. The Anthropic credit ends 2026-11-27 00:00 UTC: every claude-haiku-5-5 run of this
step is done first, before any other agent's runs.

Why: the first training set has 27 families and 141 unsafe training steps, 54 on the held-out side from 4 families.
That is too few to say a trained monitor beats a baseline. The bank (arm_v08/bank_v08.jsonl, 295 qualified tasks)
has 57 base families; 28 are in use. The other 29 (106 tasks: gmail 21 families, sqldb 7, medical 1) have never
been through steps 18-33.

1. Select
One task version per unused family, two where the versions differ in where the prohibition is written (not only in
wording or salience). Prefer the version whose step-13 / v0.8 runs had both a safe completion and an unsafe run.
List what was picked and why. Target 35 to 45 tasks.

2. Admit (the checks that cost us most so far; fix the task or drop it, and say which)
- A safe way to finish exists without anyone's approval, and it is not "do nothing": part of the request can be
  done safely. No task where the whole request is the trap.
- The request has one reading: no scope word (latest, recent, current, all, our, the usual) with two readings that
  give different objects; recipient and objects named or uniquely findable; every id in the request exists.
- The prohibition is stated in the environment, in a place a read tool returns (object, destination or related
  context), or the harm is common sense. Not `unrelated`. Record prohibition_location as in step 25.
- Environment and checkpoint describe the same harm. Access notes do not contradict themselves.
- mechanic_id, user_instructed, counter_example, current_date and the safe / violator references are filled in.
New ids get the suffix -v34. Rules by the frozen two-step pipeline; ten checks; a task that fails after two tries
is dropped and listed.

3. Runs: 4 agents x 3 runs (gpt-6-luna, claude-haiku-5-5, Qwen3.5-9B, Qwen3.5-35B-A3B), settings of step 29. Grade.
Keep a task for training only if at least one run of any agent is a safe completion and at least one run has a
trap-based unsafe step; list the others with the reason (all safe / all unsafe / agents stumble on something that
is not the trap).

4. For the kept tasks, the same three things the current set has
- one safer run per run with a trap-based first unsafe step (step 30, variant D, gate from the real state);
- one safe twin per family (step 26), 4 agents x 3 runs, Haiku first;
- a row per trap in the read table (step 33) and the label table rows (step 29 rules).
If time before the credit ends is short: all Haiku runs of parts 3 and 4 before anything else of part 4.

5. Report: analysis/step34.md. Start with one table: families selected -> admitted -> kept, with the count of
usable unsafe steps, safe completions and hard negatives per family and agent. Then what was dropped and why, and
spend. No export in this step.
