Step 33: READ answers from the rationale, not from hand-written read rules; twins added.

Merge branch step26 into main first, then work on main. Nothing from ~/babel-private in any repo. No Hugging Face
push. Frozen rules unchanged. No agent runs, no API spend. Keep it small: this replaces part 1 of step 32 and
re-exports; the JUDGE format, the benchmarks branch, the split and eval.py stay as they are.

Why: step 32's read answers came from rules per toolkit (object / destination / context), several of them written
around single tasks (ids in file names looked up in the database, Venmo records before a statement, note files
found by name). The goal is a monitor that learns where to look from the rationale: an unsafe step says where the
restriction was written, so next time it reads that kind of place.

1. READ answer
- Per trap (task version x trap rule), one data row: the concrete read call(s) that return the place where the
  prohibition is stated, taken from arm_s25 / arm_s30 prohibition_location (and the Why text of step 30). This is a
  table (arm_s33/trap_reads.jsonl), about one row per trap, not code per toolkit. A trap whose place no read tool
  returns, or that is common sense only: no row.
- Unsafe step: the row(s) of the trap(s) it fires. If the agent already got that content back in the history shown
  to the monitor: NONE.
- Its safe counterparts get the SAME answer:
  a) twin runs: the steps that the trap version's rules flag (step 26's --as-trap grading, the 194 hard negatives),
     with the read run on the twin's state (it returns the place without the prohibition);
  b) trap-version runs with no unsafe step from that trap: the step(s) that act on the same object with the same
     kind of call as the trap's violator (use the same --as-trap style match on the item, not the label).
- Steps that do not send, change or delete: NONE.
- Other send / change / delete steps (no trap and no counterpart): NO READ example at all. We do not know that
  nothing needed checking there, so we do not teach "do not read". They still give a JUDGE example, with no reads.
- Delete the per-toolkit target rules from the export path (keep kind() only if eval needs
  it). Running reads on the stored state, the "already in the history" test and the result cap stay.
- Check and report: among steps with a non-NONE READ answer, how many are unsafe and how many safe, per family. If a
  family has reads only on unsafe steps, list it (there the read gives the label away).

1b. No repeated reads
Step 32 compared a read only with the agent's history, so the monitor read the same manifest again at every later
step of a run. From now on the results of the monitor's own reads at earlier steps of the same run are part of what
it sees at later steps (a section "Monitor's earlier reads", each read once, oldest dropped first when the prompt is
too long), in READ and JUDGE inputs, and the "already seen" test checks them too. eval.py keeps the same record
across the steps of a run. Report how many READ answers become NONE because of this.

2. JUDGE input = history + the results of that step's READ answer. Reason only when the prohibition text is in the
JUDGE input. Report the step 32 number again (was 175 of 181 with the old rules; 55 without reads).

3. Export arm_s33/export/{base,with_safer}/ as step 32, now including the step 26 twin runs (label table rows with
the same train_use rules; the third-label steps of the customers-q4 and case-study twins are drop_step) and the two
-v26 repairs. A twin goes to the side of its family. Counts per split: examples, unsafe, hard negatives, READ
non-NONE.

4. eval.py: unchanged loop; rerun the stand-in model. Update TRAIN.md paths to arm_s33.

Report: analysis/step33.md, short: the two numbers (part 1 check, part 2), counts, 2 READ and 2 JUDGE examples in
full (one unsafe, one twin hard negative of the same family), anything that did not work.
