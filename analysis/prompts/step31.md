Step 31: export the labelled runs in the benchmarks format and prepare the first training run (monitor v0).

Work on main (step 29 is merged). Nothing from ~/babel-private in the repo. No Hugging Face push. Frozen rules
unchanged. No agent runs and no API spend in this step. The benchmarks repo (~/Documents/workspace/benchmarks,
safety_monitor/) is read and its loader is called, but NOT edited and nothing is committed there; if its code
cannot take our data as it is, say exactly where and stop at a proposal.

1. Read first
In benchmarks/safety_monitor: the MinedTrajectory / LabeledStep schema, how trajectories.jsonl is loaded, how the
SFT input is rendered (instruction + last 20 steps, observations cut to 400 characters, current action), the label
strings (high-unsafe / low-unsafe), how `split` is used, how thresholds are fit on dev, and what happens to a step
whose label is missing or not one of the two. Write these down in the report in ten lines, with file and line.

2. Export script arm_s31/export31.py, input arm_s29/labels_all.jsonl (+ arm_s30/labels_safer.jsonl by switch)
- One MinedTrajectory per run with train_use = use on at least one step and no drop_run_* flag.
- unsafe -> high-unsafe, safe -> low-unsafe. label_source carries our source (trap rule id / judge).
- drop_step steps (off_design-only unsafe, third label): they stay in the trajectory as history, because they
  happened, but must not become a training example. Use whatever the loader offers for "no label"; if it offers
  nothing, write them with label null plus a field train=false and report what the loader does with that.
- instruction = the user request exactly as the agent received it. Observations exactly as the agent received
  them. No env_state, no snapshot, no rule text, no trap description, no task metadata in any field the SFT input
  is rendered from. Task id, mechanic_id, agent, prohibition_location, counter_example go to metadata fields only.
- Split by mechanic_id, never by run: every version of a family is on one side. dev = about 15% of families,
  chosen with a fixed seed, stratified so that dev has unsafe steps from at least 3 toolkits and from all 4 agents.
  dev is used only to fit the threshold. Write the family list of each side to the report.
- Switch --safer {none,include}. With include, each warned safer run of arm_s30 with flag pair_ok is added as its
  own trajectory: the steps before the blocked step, then the continuation steps. The blocked call and its result
  are left out of this trajectory (the blocked step is already an unsafe example in the original run). The message
  text never appears anywhere in the export. If a continuation step has mentions_block, the trajectory is cut
  before the first such step; report how many trajectories were cut and how many steps were lost. A safer run goes
  to the same side of the split as its source run. Branches that are not pair_ok are not exported.
- Outputs: arm_s31/export/base/trajectories.jsonl and arm_s31/export/with_safer/trajectories.jsonl (with whatever
  arm_s30 holds at the time; rerunnable when the Qwen branches arrive).

3. Checks (all must pass, print each)
- Both files load with the benchmarks loader without change, and the rendered SFT input of 5 random steps per file
  is printed in the report in full (one unsafe, one safe, one from a safer run, one long one that gets cut).
- Leak scan over every rendered input: the strings "BLOCKED BY THE SAFETY MONITOR", "safety monitor", "trap",
  "checkpoint", "off_design", rule ids, "twin", and the label words. Zero hits, or each hit explained.
- No family on both sides of the split. No run twice. Step counts equal the label table counts for train_use.
- Table: examples per label x agent x split, for base and with_safer; unsafe share; examples per toolkit; how many
  unsafe examples have the prohibition already in the rendered input (prohibition_location = instruction, or the
  text was returned within the last 20 steps and survives the 400-character cut) - this last number is the ceiling
  of what v0 can learn, so compute it from the rendered text, not from the task label.
- The 400-character cut: for how many unsafe examples does the cut remove the sentence that states the prohibition?
  List ten. (If this is large we change the cut before training, not after.)

4. Training readiness (no GPU run here)
- Run the benchmarks SFT entry point in its mock / dry mode on base, on CPU, far enough to show that data loading,
  prompt rendering, the class balance handling and the threshold fit on dev all work with our file. Report the
  command and the output.
- Write arm_s31/TRAIN.md: the exact commands for sft-run on base and on with_safer, for ShieldGemma-2B and for a
  local Qwen (QWEN_MODEL_PATH as a placeholder, no cluster paths, no node names), expected example counts, what
  number comes out (per-step precision / recall / F1 at the dev threshold, AUROC, by agent), and what is still
  missing to run it. Nothing cluster-specific in this file.
- Class balance: unsafe is about 4% of the steps. Say what the benchmarks code does about it (weights, sampling,
  nothing) and propose one setting; do not implement a new one in benchmarks.

Report: analysis/step31.md.
