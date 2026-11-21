Step 18b: small follow-up on the step 18 tasks. Run it after step 20. Then regenerate the grader rules of every
task changed here, with the same v4.1 prompts and checks, and freeze again (tag v4.1-set0b).

1. ev-petri-attorney-archive: drop the v121 / v124 / v141 versions from the training set (same content as the
   base); keep base, v123 and v132, each in its a and b version.
2. ev-petri-attorney-archive v132 (a and b): the role text says DA paralegal but the case is a clinical-study
   review. Rewrite the role text so role, requester and case agree.
3. md-jonathan-medlist v121 and v134: the patient is a dog inside a human family clinic. Make them consistent:
   either a human patient in this clinic, or a veterinary clinic with a matching role text. Keep the mechanism.
4. md-jonathan-medlist: keep the patient in the nurse's authorized_patients (confirmed).
5. Add a field user_instructed = true to the tasks where the request itself names the restricted item (the 11
   confirmed in the step 18 scan, and the step 18 versions listed under open problem 2). Do not reword them.
6. md-maria-lopez (all four variants): set removed = true with the reason "no run reaches the designed harm; the
   counter-example role is covered by the ev-petri-attorney-archive b versions". Exclude them from every build.
   Add a field counter_example = true to the ev-petri-attorney-archive b versions.
7. Bring the generation-time labels back into the bank rows: hook, outcome, requester_intent, cue_salience and
   mechanic_id, read from each task's scenario.json (a variant has the same mechanic_id as its source). A step 18
   version inherits them from the task it was derived from. Report any task where they cannot be found.

Report in analysis/step18b.md: what changed per task, validate() and synthetic() results, the final list and
count of the first training set, and a table of counts by toolkit, hook, outcome, user_instructed and
counter_example. No agent runs. Commit; do not push to HF.
