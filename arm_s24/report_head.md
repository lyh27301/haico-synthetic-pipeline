# Step 24: where each task states its prohibition

Date: 2026-11-19. Branch `step24` in its own worktree, made from main at c16f3f2e while step 23 was still running in the main checkout. No task, rule, prompt, check or engine file was changed. No agent ran and no model was called. There was no OpenAI or Anthropic spend and no Hugging Face push. The data (rules, descriptions, task rows, run trees, grades) is read from the main checkout. Everything new is in `arm_s24/` and this report.

**Why.** The monitor sees the environment only through the agent's read tools, and only a bounded part of it. If the monitor cannot reach a trap's prohibition, that trap is noise in training. Each task therefore gets a `prohibition_location`: 1 instruction, 2 object, 3 destination, 4 related_context, 5 unrelated, or common_sense when no prohibition is stated. The task's value is the nearest place (the lowest number) over all of its traps.

**What was done by code and what by reading.**

- **By code** (`arm_s24/places24.py`, `vio24.py`, `label24.py`, `b24.py`):
  - Loading the 48 tasks: the 46 of `grader/out/v4.2-set0/set.json` and the 2 cm-firmware-lock versions of step 23 (`grader/out/v4.2-s23`).
  - The search for every quote in the instruction and the starting environment. The instruction is the agent context plus the request. The environment is every string field of every record, every staged file and the NPC profile / scenario. The search runs exact first, then normalised (whitespace, dashes, quote marks), then split into the parts the rules joined.
  - The `object` label wherever the place's record id, attachment id or file path is one of the trap's match ids / paths, or is the record a harm state's eq-condition selects.
  - The violator reference's unsafe step and its object and destination. The reference is played on the toolkit and labelled with the frozen v4.2 rules (engine4). Both judges are replaced by their no-answer defaults; they cannot create an unsafe finding.
  - All of part B.
- **By reading:**
  - Which description trap gives the quote of each harm state. The rules give harm states no quote, so the quote is the one the rule set's own description gives for the trap (`H2T` in `places24.py`).
  - Every label that is not `object` by id. Each has a one-line reason (`M` in `label24.py`).
  - The four quotes not found by any search (`READ`).
  - The object / destination wording of the violator column (`VIO`).
  - The restatements below.

**Quote used.** For a protected item, `protected[].quote` of the rules. For a harm state, the description's quote. The `places[].quote` of the rules (who can read a destination) is reported separately as a destination fact; it is not a prohibition. A quoted text that turned out to be the protected content itself or a plain description, not a prohibition, is kept as a place, marked `not_prohibition`, and does not count for the value. Examples: the TX-6066 memo, the prod-key line, the payroll CSV line, the `medical_notes` column description, and the request sentence of pilot-merge H4.

**Files:**
- `arm_s24/prohibition_location.jsonl`: one row per task, with traps, quotes, places (level, label, confidence, reason), destination facts, violator steps, value and confidence.
- `arm_s24/violator_unsafe.json`: the violator reference's unsafe steps per task.
- `arm_s24/b_steps.jsonl`: every unsafe trap step of B, with the case, where the text was seen, and the read calls with their results.
- `arm_s24/b_offdesign.jsonl`: the off_design unsafe steps.
- `arm_s24/b_examples.json`: the example steps.

**Summary.**

- **A, all 48 tasks.**
  - No task states its prohibition in the instruction.
  - 25 tasks are `object`. The flag is a note on the record or email being changed or sent: all commerce tasks, the venmo-anonymity trio, most gmail tasks, embargo, pilot-merge.
  - 5 are `destination`: two folder access files, and the payee record in both payroll tasks.
  - 16 are `related_context`. These are:
    - the manifest of the statement folder (4 petri-attorney);
    - the recipient's request note (2 vendor lists);
    - the email carrying the attachment (deploy-key, consolidated-falsify);
    - a reply in the thread (q3-prelim);
    - the patient's medication-history document (4 medical);
    - a data-dictionary entry (dedupe, partner-grant, petri-grant).
  - 2 are `common_sense`: sq-measure-export-v121 and sq-measurement-account-export-v131.
  - No task is `unrelated` as a whole. But the designed trap of sq-active-studies-changelog is: its prohibition is a changelog entry that is not linked to the studies row.
  - 11 task values are low-confidence (listed below). They mostly turn on "is this the parent record / on the object?".
- **B, step-21 runs (514 graded runs).**
  - The rules label 230 steps unsafe: 175 through a trap and 55 only off_design.
  - Of the 175 trap steps:
    - 87 (50%) had the prohibition text in the trajectory already, always from an earlier tool result, never from the instruction.
    - 28 (16%) would have shown it on a read of the object or the destination.
    - 43 (25%) only on a read of related context: the statements manifest, a data-dictionary entry, the attachment's carrier email.
    - 8 (5%) not through any of these: sq-active-studies-changelog, where it is only in an unrelated changelog row.
    - 9 (5%) have no stated prohibition (common sense).
