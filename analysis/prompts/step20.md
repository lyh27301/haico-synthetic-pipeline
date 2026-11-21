Step 20: two things that can run while the step 18 task changes are being reviewed.

First commit the four uncommitted files in arm_s14 and analysis/step14_pilot_r2.md (the fix to the "repeated" check in
arm_s14/r2/outcomes_r2.py: it now compares every unsafe step after the branch point with the original action; the
regenerated outcomes; the correction section in the report).

Part A. Harness: a killed run must not be recorded as a finished run

Found in step 19: when the watchdog kills a run during an endpoint outage, the runner records it as final with no
error, cut mid-run. Also: a re-run into an existing output folder silently re-records the old result.
- Fix both in harness/v16b and the runner: a run killed by the watchdog, or one whose endpoint went away, is recorded
  with an error and is not counted as final; it is retried (fresh output folder) up to 2 times, then listed as failed.
- Add a check that every run counted as final ends with the agent's finish call or with its own step cap, and that
  its last recorded step is not cut off.
- Go back over the stored runs of 16c (all three agents) and step 19 with that check and list any run that fails it.
  Do not delete or change stored runs; report the list.
- Smoke test: kill one run by hand in the middle and show that it is recorded as an error and retried.

Part B. Grader rules (v4.1 prompts, unchanged) for the first training set

The first training set is the 50-task pilot bank with the step 18 versions in place of the tasks they were derived
from: the 30 new rows of arm_s18/bank plus every row of bank_16b that has no step 18 version. Report the exact list
and count.
- ev-petri-attorney-archive: v121 / v124 / v141 have the same content as the base task. Generate rules once per
  distinct task content and say which ids share a rule set.
- Tasks among these whose content is unchanged since v4 / v4.1 keep their frozen rules byte for byte. All others get
  new rules with the v4.1 prompts and the same automatic checks. Do not change the prompts or the checks in this step.
- The step 18 tasks are still under review and may change; that is accepted. Rules for a task that changes later are
  regenerated then.
- Freeze (commit and tag v4.1-set0) when done. Do not grade anything: there are no runs on these task versions yet.

Report: analysis/step20.md
- Part A: what was wrong, what changed, the smoke test, the list of stored runs that fail the new check.
- Part B: per task: passes all checks or which check fails, number of regenerations at each level, and the step 1
  description in full (a person will review these next to the task changes).
- A short list of the tasks that are ready to run (rules pass all checks) and of those that are not, with the reason
  in one line each.
- Spend.

Limits: OpenAI key from .env; stop and report at $5. No agent runs except the Part A smoke test. Nothing about the
cluster in the repo. Do not touch arm_s16c/pilot_v3_gold/. Commit at the end; do not push to HF.
