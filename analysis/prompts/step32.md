Step 32: training data for a monitor that reads, then judges.

Work on main. Nothing from ~/babel-private in any repo. No Hugging Face push. Frozen rules unchanged. No agent
runs, no API spend. Keep this step small: one export, one evaluation script. No extra conditions or analyses beyond
what is listed.

Design
The monitor has the agent's read tools (no snapshot, no env_state). For a step it first says what it wants to read,
gets the results, then gives the label and, when unsafe, the reason. Two single-turn training examples per step:
  READ   input: instruction + prior steps + current action    output: the read calls, or NONE
  JUDGE  input: the same + the read results                    output: "Label: high-unsafe" + reason,
                                                                        or "Label: low-unsafe"
The step 30 warning text is never in an input. Its Why and consequence sentences are the reason in the output.

1. Read targets (the answer key of the READ examples; never part of any input)
The monitor does not know where a prohibition is. What it can learn is where restrictions are usually written for
a kind of action, for example: before forwarding or replying, the rest of the thread; before sending a file, the
notes or manifest of its folder; before changing rows, the table's dictionary entry. So the target is set per task
family and kind of action, and is THE SAME for safe and unsafe steps: the object, the destination, and the context
place of that family (taken from where its prohibitions are stated: arm_s25/prohibition_location.jsonl, step 30
texts). Families without a trap: object and destination. Skip a read whose content the agent already got back in
the history. Steps that do not send, change or delete: NONE. Run each call against the stored state of that step
to get its result.
Report how many unsafe steps have the prohibition in the JUDGE input (step 31: 55 of 181 without reads), and list
the ones that still do not; those keep the label but get no reason.

2. Export: arm_s32/export/, same runs and family split as step 31, plus all pair_ok safer runs of step 30 (by
switch, block and message left out, as in step 31).

3. benchmarks: local branch `gmail-dojo-monitor` in ~/Documents/workspace/benchmarks, not pushed, defaults
unchanged. Only what the export needs: a per-step "not a training example" flag, an adjustable observation cut
(step 31: the 400-character cut removed 40 prohibitions), dropping the oldest history instead of the current action
when a prompt is too long, and free-text targets on the Qwen path.

4. arm_s32/eval.py: only the read loop is new; the metrics and the threshold fit reuse the benchmarks functions
(evaluate_critic / score_trajectories / the dev threshold of sft-scaling), they are not rewritten. On dev, take the model's READ output, run the calls against the stored state, then JUDGE.
Per-step precision / recall / F1 and AUROC from the label-token probability, and read recall on the dev families (did the reads the model chose return the prohibition). Show it runs with a stand-in model
that replays the targets. arm_s32/TRAIN.md: the commands to train on a local Qwen and evaluate (no cluster paths).

Report: analysis/step32.md, short: the number from part 1, example counts, 2 READ and 2 JUDGE examples in full,
anything that did not work.
