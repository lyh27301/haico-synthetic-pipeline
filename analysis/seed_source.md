# Good-task rate by seed source (Petri vs LLM)

Metadata only; no new runs. Script: `analysis/seed_source.py`, output: `analysis/seed_source.json`.

**Seed source per task:**

| tasks | where the source comes from |
|---|---|
| step 3 (16 Gmail tasks) | the origin column of `analysis/step3_eval.md` |
| steps 4–5 and the step-7 batches | the `seed` field of `<arm>/eval/manifest.json` |
| variants (`-sal-*`, `-vNN`, chained) | inherited from their root task |

All 241 classified, non-retired tasks have a source:
- **Petri:** 145 tasks.
- **LLM:** 95 tasks.
- **Exemplar:** 1 task, `exemplar-campaign-forward`, hand-written from an exemplar. It is good at every stage and is
  left out of the tables below.

**What each stage counts:**
- **Driver (step 7):** the denominator is every task classified on the local driver (steps 3–7). Good = mixed under
  either agent. The good ones form the v0.4 bank of 143 tasks.
- **Harness (step 9):** the denominator is the driver-good tasks. Good = harness-good in step 9. Tasks the step-9
  discoverability gate excluded count as not good. So this column is also the **driver → harness retention rate**.
- **After the step-10 rescue (v0.6):** same denominator; good = in v0.6. This includes 10 gate-excluded tasks that
  were rescued in step 10.

## Good rate by stage, toolkit and seed source

Each cell is good / n (rate).

| toolkit | driver Petri | driver LLM | harness Petri | harness LLM | v0.6 Petri | v0.6 LLM |
|---|---|---|---|---|---|---|
| gmail | 39/58 (67%) | 24/45 (53%) | 27/39 (69%) | 18/24 (75%) | 32/39 (82%) | 22/24 (92%) |
| sqldb | 28/36 (78%) | 15/21 (71%) | 15/28 (54%) | 9/15 (60%) | 18/28 (64%) | 11/15 (73%) |
| medical | 12/23 (52%) | 2/10 (20%) | 3/12 (25%) | 1/2 (50%) | 3/12 (25%) | 2/2 (100%) |
| commerce | 6/7 (86%) | 6/8 (75%) | 4/6 (67%) | 2/6 (33%) | 4/6 (67%) | 2/6 (33%) |
| finance | 5/11 (45%) | 1/3 (33%) | 3/5 (60%) | 0/1 (0%) | 3/5 (60%) | 1/1 (100%) |
| evidence | 3/10 (30%) | 1/8 (12%) | 3/3 (100%) | 1/1 (100%) | 3/3 (100%) | 1/1 (100%) |
| **overall** | **93/145 (64%)** | **49/95 (52%)** | **55/93 (59%)** | **31/49 (63%)** | **63/93 (68%)** | **39/49 (80%)** |

**Fisher exact tests, Petri vs LLM overall (two-sided):** driver p = 0.061, harness p = 0.72, v0.6 p = 0.17.

## Driver → harness retention (good stays good)

| toolkit | all driver-good, Petri | all driver-good, LLM | run on the harness only, Petri | run on the harness only, LLM |
|---|---|---|---|---|
| gmail | 27/39 (69%) | 18/24 (75%) | 27/30 (90%) | 18/19 (95%) |
| sqldb | 15/28 (54%) | 9/15 (60%) | 15/27 (56%) | 9/15 (60%) |
| medical | 3/12 (25%) | 1/2 (50%) | 3/12 (25%) | 1/2 (50%) |
| commerce | 4/6 (67%) | 2/6 (33%) | 4/6 (67%) | 2/6 (33%) |
| finance | 3/5 (60%) | 0/1 (0%) | 3/5 (60%) | 0/1 (0%) |
| evidence | 3/3 (100%) | 1/1 (100%) | 3/3 (100%) | 1/1 (100%) |
| **overall** | **55/93 (59%)** | **31/49 (63%)** | **55/83 (66%)** | **31/44 (70%)** |

"Run on the harness only" leaves out the 15 tasks the step-9 gate excluded: Petri 10 (9 Gmail, 1 sqldb) and LLM 5 (all
Gmail). The gate pass rate is the same for both sources: Petri 83/93 (89%), LLM 44/49 (90%). Retention on the run
tasks has p = 0.69.

## Originals vs variants

| | driver Petri | driver LLM | harness Petri | harness LLM | v0.6 Petri | v0.6 LLM |
|---|---|---|---|---|---|---|
| originals | 36/64 (56%) | 23/54 (43%) | 23/36 (64%) | 14/23 (61%) | 26/36 (72%) | 17/23 (74%) |
| variants | 57/81 (70%) | 26/41 (63%) | 32/57 (56%) | 17/26 (65%) | 37/57 (65%) | 22/26 (85%) |

## Reading

- **Petri's edge on the driver is modest (64% vs 52%, p = 0.06), and it doesn't carry over.** Petri seeds give more
  driver-good tasks in every toolkit, and the biggest gaps are in medical and evidence.
  - On the harness, Petri tasks are retained slightly *less* often than LLM tasks (59% vs 63%).
  - After the rescue, LLM tasks are ahead (80% vs 68%). Neither difference is significant at these n.
- **The gap after the rescue comes mostly from variants.** LLM-seeded variants end at 22/26 good vs Petri variants at
  37/57 (p = 0.075). The step-10 rescue added the same number of tasks for each source (variants +5 each, originals +3 each), but the LLM base is half the size, so its rate moves further.
- **Medical is where Petri seeds lose most on the harness:** 12 driver-good, 3 harness-good. This matches step 7's
  "all_safe cause 2", where the planted fact sits off the agent's path. The medical LLM cells have n = 2 and can't be
  compared.
- **Gmail retains best for both sources** once the gate is passed (90% and 95%). sqldb and medical drop most.

## Caveats

- **Seed source is confounded with batch.**
  - Steps 4–5 were mostly Petri-seeded.
  - The step-7 Gmail batch was almost all LLM-seeded, because of a seed-writer bug (1 Petri seed out of 25).
  - Variants were generated only from good sources, and inherit the root's label.
  - So a difference by seed source also carries generation step, writer version and toolkit mix.
- **Driver classes come from different steps.** Steps 3–7 used slightly different protocols (step 3 ran 5 + 5 runs
  on every task; later steps ran 5 gpt-4o-mini runs, then 5 gpt-5-mini runs on extremes) and some driver tasks were
  repaired. The driver denominator includes every classified, non-retired task.
- **Small cells.** Several toolkit cells have n ≤ 3; read only the overall row and Gmail/sqldb as meaningful.
