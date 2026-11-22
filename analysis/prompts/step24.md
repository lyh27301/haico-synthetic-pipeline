Step 24: record where each task states its prohibition (trial labelling, read-only on tasks).

Run in a separate git worktree on branch `step24` if step 23 is still running in the main checkout. Change no task,
rule, prompt, check or engine file. No agent runs. No model call is needed for the labels: do them by code where
possible and by reading where not, and say which. No OpenAI or Anthropic spend. No Hugging Face push.

Why: the monitor reads the environment only through the agent's read interface, and only a bounded part of it.
A trap whose prohibition the monitor cannot reach is noise in training. Each task therefore gets a
`prohibition_location`. Definitions:
  1. instruction      in the task instruction
  2. object           on or in the thing the unsafe action sends or changes (content, label, metadata field)
  3. destination      where it goes: the recipient's record, the target folder's description or access list
  4. related_context  directly linked to the object or the destination: the thread the email is in, the parent
                      folder's README, the case / project / parent record, the data dictionary entry or access
                      policy of the table
  5. unrelated        anywhere else
  common_sense        no stated prohibition; the harm is common sense
A prohibition stated in several places gets all of them; the task's value is the nearest (lowest number).

Tasks: the 46 tasks of the v4.2 set (grader/out/v4.2-set0/set.json), plus the new cm-firmware-lock versions of
step 23 if they exist.

A. Per task (arm_s24/prohibition_location.jsonl and a table in the report)
For every trap (protected item / harm state) of the task's rules:
- the quote the rules give for the prohibition, and every place in the instruction and the starting environment
  (records and staged files) where that text, or the sentence it comes from, is found: collection + record id +
  field, or file path. Exact search first; if the quote is not found verbatim, say so and locate it by reading.
- the object and the destination of the violator reference's unsafe action (from the reference and the rules).
- the location label for each place, with one line of reason, and the task's value.
- `confidence`: high when exact search and the object / destination ids decide it; low when it needed judgment
  (for example: is this record "the parent" of the object?). List every low one separately; they are what a person
  will check first.
For controls (counter_example) record the marker that is present and why it does not apply.

B. Per unsafe step, on the graded step 21 runs (only if grades21.jsonl of step 23 exists; otherwise skip B and
say so)
For each step the rules label unsafe through a trap (not off_design):
- was the prohibition text already in the trajectory before this step (in the instruction or in any earlier tool
  result, untruncated)? yes / no.
- if no: would reading the object and the destination with the agent's read tools at that point have returned
  it? And reading related_context?
Report per task and per agent: unsafe trap steps; share with the prohibition already in the trajectory; share
reachable only by reading object or destination; only by related context; not reachable.
Report off_design unsafe steps as their own count (they need no prohibition).

Report: analysis/step24.md
- The table of A, grouped by location; the count per location; the list of `unrelated` tasks with what would have
  to move where to repair them (do not repair).
- The low-confidence list.
- B's tables, and three example steps for each of the four cases, with the text that was or was not visible.
- Anything that does not fit the five labels, described rather than forced into one.
