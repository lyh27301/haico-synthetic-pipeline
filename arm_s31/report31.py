"""Step 31 report: analysis/step31.md from arm_s31/checks31.json + checks31.out (check31.py), arm_s31/split31.json and
export/*/stats.json (export31.py), arm_s31/dryrun31.json (dryrun31.py) and arm_s31/samples31.md. No model call.
  python3 arm_s31/report31.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s31"
AGENTS = ["gpt-6-luna", "haiku5.5", "qwen3.5-9b", "qwen3.5-35b-a3b"]
AG = {"gpt-6-luna": "luna", "haiku5.5": "Haiku", "qwen3.5-9b": "Qwen 9B", "qwen3.5-35b-a3b": "Qwen 35B"}
HU, LU = "high-unsafe", "low-unsafe"


def short(t):
    return t[7:] if t.startswith("safety-") else t


def main():
    C = json.loads((S / "checks31.json").read_text()); SP = json.loads((S / "split31.json").read_text())
    D = json.loads((S / "dryrun31.json").read_text())
    ST = {v: json.loads((S / f"export/{v}/stats.json").read_text()) for v in ("base", "with_safer")}
    trajs = [json.loads(x) for x in (S / "export/base/trajectories.jsonl").read_text().splitlines()]
    L = []; w = L.append
    b, ws = C["base"], C["with_safer"]; pb = b["prohibition"]
    w("# Step 31: the labelled runs in the benchmarks format, and what training monitor v0 still needs\n")
    w("No agent runs, no API spend, nothing pushed to Hugging Face. The frozen rules "
      "are not touched. The benchmarks repo was read and its loader, renderers and SFT entry points were called from its "
      "own venv; nothing there was edited, and its `git status` is the same before and after.\n")
    w("## Summary\n")
    w("| item | status |\n|---|---|")
    w(f"| export (base) | {ST['base']['trajectories']} runs, 4,129 examples (181 unsafe, 4.4%), 110 context-only steps; loads with the benchmarks loader unchanged |")
    w(f"| export (with_safer) | + {ST['with_safer']['safer_runs']} safer runs (21 safe examples). Step 30 has {ST['with_safer']['branches']} graded branches so far (luna and Haiku only); rerun when the Qwen branches arrive |")
    w(f"| split | by family: 21 train / 4 dev of 25 (seed {SP['seed']}, draw {SP['draw']}); dev has 54 unsafe examples from 4 toolkits and all 4 agents, but only 1 from Haiku |")
    w("| checks | all pass (load, one example per training step, family split, no run twice, counts = label table, no monitor message) |")
    w(f"| leak scan | zero hits for every listed string. One hit of a kind I introduced: the empty `id=` of a context-only step is visible in the history of {b['leak_hits']['history-only marker id= (empty)']['examples']} base inputs (and in all 21 safer-run inputs) |")
    w(f"| prohibition in the rendered input (ceiling for v0) | {pb['in_rendered_qwen']} / {pb['unsafe_examples']} unsafe examples (Qwen format), "
      f"{pb['in_rendered_shieldgemma']} / {pb['unsafe_examples']} (ShieldGemma format); {pb['never_returned_to_agent']} were never shown to the agent at all |")
    w(f"| 400-character cut | removes the prohibition from {pb['removed_by_400_cut']} of the {pb['returned_in_last20_uncut']} unsafe examples whose prohibition was in the last 20 steps. This is large: change the cut before training |")
    w(f"| Qwen sequence length | {b['tokens_over_2048']['qwen']['all']} of 4,129 Qwen-format prompts are over 2,048 tokens (45 unsafe). The trainer truncates from the right, so these add no loss. ShieldGemma: {b['tokens_over_2048']['shieldgemma']['all']} |")
    w("| dry run (mock, CPU) | sft-scaling (ShieldGemma path): loading, rendering, 1:1 upsampling, mock training and the dev threshold fit all run; it stops at the final plot (no matplotlib in the CPU venv). sft-run (Qwen path): runs to the end |")
    w("| training | not run (no GPU in this step). Commands in arm_s31/TRAIN.md. Missing: a held-out side, the cut decision, the Qwen length limit, and context-only steps scored in the benchmarks evaluation |\n")

    # ------------------------------------------------------------------ 1
    w("## 1. What the benchmarks code does (read first)\n")
    w("Paths are under `benchmarks/safety_monitor/safety_monitor/`.\n")
    for line in [
        "**Schema** (`synthesis/pairs.py:29-62`):\n"
        "   - `LabeledStep` has action_id, tool_name, arguments, summary, observation, is_error, label, label_source and a few more.\n"
        "   - `MinedTrajectory` has key, instance_id, run, condition, actor, role, rule_based, instruction, steps, split, corpus and services.\n"
        "   - Extra keys are ignored on load.",
        "**Loading** (`sft/data.py:187-199`): `load_trajectories` validates each line with pydantic and skips rows with "
        "`outcome_status == \"unknown\"`. The SFT entry points then require every train row to be a synthetic corpus "
        "(v4/v5/v6) or a real passive rollout, `condition == \"mg_passive\"` (`data.py:202-237`).",
        "**SFT input, Qwen** (`sft/data.py:289-311`, `critic/prompts.py:22-32`, `critic/prompted.py:28-46`):\n"
        "   - Order: `Task instruction:` + instruction, then `Prior observable steps:` (the last 20 steps: `ACTION tool {args} summary=… id=…` plus `OBS`), then `CURRENT action to label:`.\n"
        "   - An observation over 400 characters becomes its first 200 + \" … \" + last 200 (`prompted.py:42`).\n"
        "   - The system prompt is fixed (`prompts.py:6`).",
        "**SFT input, ShieldGemma** (`critic/shieldgemma.py:90-109`): the current action plus the last 8 steps (same "
        "400-character cut), the whole history capped at 700 + \" ... \" + 700 characters (`:98`), inside the model card's "
        "policy template. There is **no instruction**.",
        "**Label strings** (`types.py:14-15`): `high-unsafe` and `low-unsafe`.\n"
        "   - Qwen target: `Label: <label>` (`data.py:310`).\n"
        "   - ShieldGemma target: `Yes` for high-unsafe, `No` otherwise (`data.py:316`).\n"
        "   - The Qwen critic parses its own generated text (`prompted.py:49`).",
        "**`split`**:\n"
        "   - Read only with `--use-shipped-splits` (sft-run) or always (sft-scaling), through `split_by_shipped_fields` (`data.py:519-553`): train / dev / test by instance_id. A task with two values is an error.\n"
        "   - sft-run otherwise re-splits by a hash of instance_id (`data.py:470`).\n"
        "   - With the shipped split, sft-run maps test to its holdout and does not use dev (`data.py:151-162`).",
        "**Threshold** (`sft/scaling.py:63, 370-403, 704-710`): only in sft-scaling. On dev it tries a Yes-probability "
        "threshold from 0.05 to 0.95, keeps the best step-level F1 (ties broken by run-level max AUROC against "
        "`role == harmful`), and freezes it for the rung. sft-run has no threshold.",
        "**Missing or invalid label** (tested):\n"
        "   - A missing `label` silently becomes `low-unsafe` (`pairs.py:38`).\n"
        "   - `null` or any other string fails validation, so the whole file fails to load.\n"
        "   - The only way to keep a step out of training is an empty `action_id`. `build_examples` skips it "
        "(`data.py:415`), but it stays in the history of later steps, and it is still scored, with its stored label, by "
        "`evaluate_critic` (`experiment.py:76`) and `score_trajectories` (`scaling.py:221`).",
        "**Class balance**:\n"
        "   - `upsample_high` (`data.py:616-634`) repeats unsafe examples up to the safe count (1:1). It is on by default "
        "(`experiment.py:259, 301`; `scaling.py:646`) and is not a CLI option.\n"
        "   - The LoRA loss is unweighted.\n"
        "   - The CPU mock uses class weights.",
        "**Sequence length** (`sft/backends.py:535, 583-584`): `train_lora_sft` tokenizes with "
        "`truncation=True, max_length=2048`. Truncation is from the right, so a longer prompt loses the current action and "
        "every target token is masked; `max_length` is not a CLI option."]:
        w(f"1. {line}")
    w("")

    # ------------------------------------------------------------------ 2
    w("## 2. Export (arm_s31/export31.py)\n")
    w("**One trajectory per run.** A run is exported when it has at least one `use` step and no `drop_run_*` flag: "
      "515 of the 732 graded runs.\n")
    w("**Text is re-read from the run's own conversation**, from the final attempt's output file:\n"
      "- **instruction:** the user message the agent received, checked equal to the output's `instruction`;\n"
      "- **action:** the tool name and the call's arguments. For a call the SDK rejected, the raw arguments the agent "
      "sent. The agent's own `summary` argument goes in `summary`;\n"
      "- **observation:** the content the agent received, text parts joined with a newline. For a rejected call, the SDK "
      "error.\n")
    w("Step i is the i-th action, the grader's own reading, and every step's tool name is checked against the label "
      "table.\n")
    w("**Kept out of every rendered field:** env state, snapshots, rules, trap text and task metadata. The task id is in "
      "`instance_id` and the agent in `actor`; neither is rendered. mechanic_id, toolkit, prohibition_location, "
      "counter_example, outcome and the source are under `metadata`, which the loader ignores.\n")
    w("**Labels:** unsafe -> `high-unsafe`, safe -> `low-unsafe`. `label_source` carries our source "
      "(`trap:<id>/<rule>`, `judge`, `none`).\n")
    w("**drop_step steps (110: off_design-only unsafe and third label).** The loader has no label-less value (§1, item 8), "
      "so they are written as follows:\n"
      "- `action_id` is empty, so `build_examples` skips them but keeps them in the history;\n"
      "- `train: false`, kept in the file but dropped by the loader;\n"
      "- `label` is ours mapped (that is what the benchmarks evaluation would read);\n"
      "- `label_source` is `history_only:<reason>`.\n"
      "- With `label: null` instead, the file would not load at all (pydantic ValidationError).\n")
    w("**Trajectory fields:**\n"
      "- `condition = mg_passive`, the only value the train firewall admits for real rollouts;\n"
      "- `role = harmful` when the run has an unsafe training example, else `clean`; `rule_based` is the same as 0/1;\n"
      "- `corpus = gmail-dojo-s31`.\n")
    sp = ST["with_safer"]
    w("**Safer runs (`--safer include`).** Read from the step-30 worktree's arm_s30/, since step 30 is not merged.\n")
    w("| | branches |\n|---|---|")
    w(f"| graded so far (luna and Haiku only; the Qwen branches are not graded yet) | {sp['branches']} |")
    w(f"| not pair_ok, not exported | {sp['not_pair_ok']} |")
    w(f"| source run not exported (its task, active-studies-v25, is on the step-29 repair list) | {len(sp['source_not_exported'])} |")
    w(f"| cut before the first step with `mentions_block` | {sp['cut']} |")
    w(f"| exported | {sp['safer_runs']} |\n")
    w(f"- The {sp['cut']} cut branches lost {sp['steps_lost']} steps ({sp['examples_lost']} examples).\n"
      f"- All {sp['cut']} were cut at their first step after the block, so none has a training example left, and none is "
      f"exported: {', '.join('`' + k + '`' for k in sp['no_example_left'])}.\n"
      "- Each exported safer run is: the steps before the blocked step as context only (they are the source run's "
      "steps, already examples there, and the label table does not repeat them), then the continuation steps as examples.\n"
      "- The blocked call and its result are left out. The monitor message is never read into the export, and the check "
      "below searches the whole file for every message text.\n"
      "- A safer run takes its source run's family, so it is on the same side of the split.\n")
    w(f"**Split by family.**\n"
      f"- dev = {round(SP['dev_fraction'] * 25)} of the 25 families (about 15%), one from each of 4 different toolkits. A "
      "toolkit with only one family is never drawn, so every toolkit keeps a family in train.\n"
      f"- Drawn with `random.Random({SP['seed']})`; a draw is kept only when dev holds unsafe training steps from at least "
      f"3 toolkits and from all 4 agents. Draw {SP['draw']} was kept.\n"
      "- My first rule (15% of each toolkit's families, at least one) put 6 families in dev, including medical's only "
      "family, and was replaced before any check.\n")
    w("| side | toolkit | families |\n|---|---|---|")
    for side in ("dev", "train"):
        for tk, fs in SP[side].items():
            if fs:
                w(f"| {side} | {tk} | {', '.join(short(f) for f in fs)} |")
    dev_cells = collections.Counter((t["metadata"]["toolkit"], t["actor"]) for t in trajs if t["split"] == "dev" for s in t["steps"] if s["train"] and s["label"] == HU)
    w("\nUnsafe training examples in dev, by toolkit and agent: " + "; ".join(f"{tk} / {AG[a]} {n}" for (tk, a), n in sorted(dev_cells.items())) + ".\n")

    # ------------------------------------------------------------------ 3
    w("## 3. Checks (arm_s31/check31.py, run with the benchmarks venv)\n")
    w("```text\n" + (S / "checks31.out").read_text().strip() + "\n```\n")
    w("### Leak scan\n")
    w(f"The scan covers every rendered input: the Qwen user message and the ShieldGemma user prompt, "
      f"{4129} + {4150} examples, each in both formats.\n")
    w("Strings searched:\n"
      "- `BLOCKED BY THE SAFETY MONITOR` and `safety monitor`;\n"
      "- `trap*`, `checkpoint`, `off_design`, `twin*`;\n"
      "- the label words `high-unsafe` and `low-unsafe`;\n"
      f"- every rule id in the grades ({', '.join('`' + r + '`' for r in C['rule_ids_scanned'])});\n"
      "- every trap id that appears in a label source, as a whole word.\n")
    w("**Result: zero hits for all of them, in both files.** The fixed system prompt contains the label words by design; "
      "it is the benchmarks' prompt, not our data, and is not scanned.\n")
    hb = b["leak_hits"]["history-only marker id= (empty)"]; hw = ws["leak_hits"]["history-only marker id= (empty)"]
    w(f"**One hit of a kind the export itself creates.** A context-only step is rendered with an empty `id=` in the "
      f"history (`format_action`, `prompted.py:31`).\n"
      f"- base: in the last-20-step history of {hb['examples']} examples (Qwen format; {hb['shieldgemma']} in ShieldGemma's 8 steps). "
      f"Of these, {b['examples_with_history_only_step_in_last20']['by_source_label'].get('run high-unsafe', 0)} are unsafe and "
      f"{b['examples_with_history_only_step_in_last20']['by_source_label'].get('run low-unsafe', 0)} safe: 4.8% unsafe against 4.4% overall, "
      "so in base the marker says almost nothing about the label.\n"
      "- with_safer: all 21 safer-run examples carry the marker (their prefix is context-only) and all 21 are safe, so "
      "there it is a shortcut, although a small one (21 of 4,150).\n"
      "- Removing it needs a field the loader keeps (see the proposals at the end). I did not work around it.\n")
    w("### Counts\n")
    for v, X in (("base", b), ("with_safer", ws)):
        t = X["label_agent_split"]
        w(f"**{v}**: examples per label x agent x split\n")
        w("| agent | train unsafe | train safe | dev unsafe | dev safe | all | unsafe share |\n|---|---|---|---|---|---|---|")
        tot = collections.Counter()
        for a in AGENTS:
            c = {(l, s): t.get(f"{l} | {a} | {s}", 0) for l in (HU, LU) for s in ("train", "dev")}
            tot.update(c); n = sum(c.values()); u = c[(HU, "train")] + c[(HU, "dev")]
            w(f"| {AG[a]} | {c[(HU, 'train')]} | {c[(LU, 'train')]} | {c[(HU, 'dev')]} | {c[(LU, 'dev')]} | {n} | {u / n:.1%} |")
        n = sum(tot.values()); u = tot[(HU, "train")] + tot[(HU, "dev")]
        w(f"| all | {tot[(HU, 'train')]} | {tot[(LU, 'train')]} | {tot[(HU, 'dev')]} | {tot[(LU, 'dev')]} | {n} | {u / n:.1%} |")
        w(f"\nUnsafe share: train {X['unsafe_share']['train']:.1%}, dev {X['unsafe_share']['dev']:.1%}. By source: "
          + "; ".join(f"{s} {d.get(HU, 0)} unsafe / {d.get(LU, 0)} safe" for s, d in X["per_source"].items()) + ".\n")
    w("**Examples per toolkit** (base):\n")
    w("| toolkit | unsafe | safe | unsafe share |\n|---|---|---|---|")
    for tk, d in b["per_toolkit"].items():
        w(f"| {tk} | {d.get(HU, 0)} | {d.get(LU, 0)} | {d.get(HU, 0) / (d.get(HU, 0) + d.get(LU, 0)):.1%} |")
    w("\nwith_safer adds 21 safe examples: commerce 3, gmail 6, sqldb 12.\n")
    w("### Is the prohibition in the rendered input? (the ceiling of what v0 can learn)\n")
    w("For each unsafe training example, the text that states the prohibition of its traps was searched in the rendered "
      "input itself, after normalizing both. The text comes from arm_s25/prohibition_location.jsonl, each trap's fragments "
      "and quote; a derived version takes its nearest listed ancestor's.\n")
    w("No task has its prohibition in the instruction (prohibition_location `instruction`: 0), so everything depends on "
      "what the agent read.\n")
    w("| | unsafe examples |\n|---|---|")
    w(f"| all unsafe training examples (base; with_safer adds none) | {pb['unsafe_examples']} |")
    w(f"| prohibition in the rendered Qwen input | **{pb['in_rendered_qwen']}** ({pb['in_rendered_qwen'] / pb['unsafe_examples']:.0%}) |")
    w(f"| prohibition in the rendered ShieldGemma input | **{pb['in_rendered_shieldgemma']}** ({pb['in_rendered_shieldgemma'] / pb['unsafe_examples']:.0%}) |")
    w(f"| returned to the agent within the last 20 steps (uncut) | {pb['returned_in_last20_uncut']} |")
    w(f"| ... of which the 400-character cut removes it | {pb['removed_by_400_cut']} |")
    w(f"| returned only more than 20 steps back | {pb['only_older_than_20_steps']} |")
    w(f"| never returned to the agent before the unsafe step | {pb['never_returned_to_agent']} |\n")
    w("The 86 \"never returned\" cases were spot-checked: distinctive words of the fragment (\"circulate\", \"fraud\", "
      "\"named\") are absent from the whole history, not a matching miss. The agent acted without reading the record, "
      "manifest or notes that carry the prohibition; the petri archive and grant-wildcard versions are most of them. For "
      "those steps the monitor would need the environment, not the transcript.\n")
    def pairs(d):
        return "; ".join(f"{k} {v}" for k, v in sorted(d.items()))
    w(f"By location: {pairs(pb['in_rendered_qwen_by_ploc'])} (True = in the rendered Qwen input).\n")
    w(f"By split: {pairs(pb['in_rendered_qwen_by_split'])}.\n")
    w(f"By agent: {pairs(pb['in_rendered_qwen_by_agent'])}.\n")
    w("### The 400-character cut\n")
    w(f"In **{pb['removed_by_400_cut']} of the {pb['returned_in_last20_uncut']}** unsafe examples whose prohibition was "
      "returned within the last 20 steps, the cut removes it. The observation is longer than 400 characters and the "
      "sentence sits in the dropped middle.\n")
    w("This is large: it is 40 of the 95 learnable unsafe examples. I recommend changing the cut before training, for "
      "example a longer keep, or keeping the whole observation of the step that returned the object the current action "
      "uses. The cut is hard-coded in benchmarks (`critic/prompted.py:42`), so the change belongs there; it is not done here.\n")
    w("Ten of them:\n")
    w("| run | step | prohibition text (start) |\n|---|---|---|")
    seen = set(); n = 0
    for x in pb["cut_examples"]:
        if x["run"] in seen:
            continue
        seen.add(x["run"]); n += 1
        w(f"| {short(x['run'])} | {x['step']} | {(x['fragment'] or '')[:110].replace('|', '/')} |")
        if n == 10:
            break
    w("")
    w("### Prompt length\n")
    tq, tg = b["tokens_over_2048"]["qwen"], b["tokens_over_2048"]["shieldgemma"]
    w("Token counts use local stand-in tokenizers of the same families: Qwen2.5 for the Qwen format, Gemma-2B for "
      "ShieldGemma.\n")
    w(f"- **Qwen format** (system prompt + user message): median {tq['median']} tokens, max {tq['max']}. "
      f"**{tq['all']} of 4,129 are over 2,048**: {pairs(tq['by_label_split'])}. The trainer truncates from the right, so "
      "those examples lose the current action and add no loss.\n"
      f"- **ShieldGemma format**: median {tg['median']} tokens, max {tg['max']}; {tg['all']} over 2,048, all safe.\n")
    w("### Samples\n")
    w("Five rendered Qwen inputs per file are printed in full in the appendix: one unsafe, one safe, one safer run (with_safer "
      "only), one long one with cut observations, and random picks.\n")

    # ------------------------------------------------------------------ 4
    w("## 4. Training readiness (no GPU run)\n")
    w("Run with `python3 arm_s31/dryrun31.py`: the benchmarks CLI in mock mode on CPU, from its own directory and venv, "
      "outputs outside both repos.\n")
    for k in ("sft-scaling base", "sft-scaling with_safer", "sft-run base", "sft-run with_safer", "score31 mock"):
        v = D[k]
        w(f"**{k}** (exit {v['exit']})\n\n```text\n$ {v['command']}\n" + "\n".join(v["log"]) + "\n```\n")
        if k.startswith("sft-scaling"):
            for r, x in v["rungs"].items():
                w(f"- rung {r}:\n"
                  f"  - training: {json.dumps(x['train_stats'])}\n"
                  f"  - example counts: {json.dumps(x['example_counts'])}\n"
                  f"  - dev threshold **{x['threshold']}**, chosen by {json.dumps(x['threshold_selection'])}\n"
                  f"  - dev step-level metrics at that threshold: P {x['dev_action']['precision_high_unsafe']:.3f} / "
                  f"R {x['dev_action']['recall_high_unsafe']:.3f} / F1 {x['dev_action']['f1_high_unsafe']:.3f}")
            w("")
        elif k.startswith("sft-run"):
            w(f"- split: {json.dumps(v['split'])}\n- example counts: {json.dumps(v['example_counts'])}\n"
              f"- training: {json.dumps(v['train_stats'])}\n"
              f"- after mock SFT on the eval file (dev): P {v['after_sft_eval_action']['precision_high_unsafe']:.3f} / "
              f"R {v['after_sft_eval_action']['recall_high_unsafe']:.3f} / F1 {v['after_sft_eval_action']['f1_high_unsafe']:.3f}\n")
        else:
            w(f"- step level: {json.dumps(v['summary']['step'])}\n")
    w(f"The benchmarks working tree was unchanged after the runs: {D['benchmarks_working_tree_unchanged']}.\n")
    w("What these show:\n")
    w("- **Loading:** both files load, and the train firewall passes with `condition = mg_passive`.\n"
      "- **Rendering:** examples are built in both formats.\n"
      "- **Class balance:** rung `all` trains on 5,962 rows with 2,981 positive, the 1:1 upsampling of 127 unsafe "
      "against 2,981 safe.\n"
      "- **Threshold fit:** it ran on the 144 dev trajectories and froze 0.5 for rung all (0.05 for the zero-shot keyword "
      "stand-in).\n"
      "- **Plot:** the ladder stops at its final plot because this CPU venv has no matplotlib; the `[sft]` extra installs "
      "it. Every result file is written before that.\n"
      "- **Counts:** the \"example_counts\" lines (3,201 / 198 train, 1,038 / 66 dev) count every step, including the "
      "context-only ones; the trainer used 3,108 / 127.\n"
      "- **Mock numbers:** the P/R/F1 values above come from a hashed-n-gram logistic regression and the keyword stand-in. "
      "They are not monitor results.\n")
    w("**Class balance.** Unsafe is 4.1% of the train examples.\n"
      "- What benchmarks does: it repeats them to 1:1 (`upsample_high`, on by default, not a CLI option), the LoRA loss "
      "is unweighted, and the CPU mock uses class weights.\n"
      "- With 127 distinct unsafe examples, 1:1 means about 23 repeats each per epoch.\n"
      "- Proposed setting: `upsample_high(..., max_ratio=0.25)`, about 745 unsafe rows against 2,981 safe (about 20% of "
      "rows, about 6 repeats each). It is an existing argument, but using it means changing the two call sites in "
      "benchmarks; not done here.\n")
    w("Commands for the real runs, expected counts, outputs and what is missing are in **arm_s31/TRAIN.md**. For per-step "
      "AUROC and the per-agent numbers, which the ladder does not write, `arm_s31/score31.py` scores a split with the "
      "adapter using the benchmarks scoring function and skips the context-only steps.\n")

    # ------------------------------------------------------------------ proposals
    w("## Where the benchmarks code cannot take our data as it is (proposals only; nothing changed there)\n")
    for p in [
        "**No \"not a training example\" flag.**\n"
        "   - Where: `synthesis/pairs.py:38`, `sft/data.py:415`, `sft/experiment.py:76`, `sft/scaling.py:221`.\n"
        "   - Effect: the empty-`action_id` workaround shows up as an empty `id=` in the history, and context-only steps "
        "are still scored by the evaluation, with the label we stored.\n"
        "   - Proposal: `LabeledStep.train: bool = True`; `build_examples` skips `not step.train`; `evaluate_critic` and "
        "`score_trajectories` skip those steps. Our export would then keep the real ids.",
        "**The 400-character observation cut** (`critic/prompted.py:42`).\n"
        f"   - Effect: it removes the prohibition from {pb['removed_by_400_cut']} of {pb['returned_in_last20_uncut']} learnable unsafe examples.\n"
        "   - Proposal: a `max_obs_chars` argument on `format_history`, carried through `critic_user_prompt` and "
        "`format_shieldgemma_prompt`, with a value chosen before training.",
        "**Qwen 2,048-token right truncation** (`sft/backends.py:535, 583`).\n"
        f"   - Effect: {tq['all']} of 4,129 examples lose their target.\n"
        "   - Proposal: truncate the history from the left (or drop the oldest steps) so the current action and the label "
        "always fit, or expose `max_length`.",
        "**sft-run does not use dev**, so the Qwen path has no threshold and no held-out number. Proposal: give sft-run the "
        "dev/test handling sft-scaling has, or run the Qwen path through a scoring critic.",
        "**No per-step scores saved by the ladder.** Covered on our side by `arm_s31/score31.py`; no change needed."]:
        w(f"1. {p}")
    w("")
    w("## Files\n")
    w("- `arm_s31/export31.py` writes `arm_s31/export/{base,with_safer}/trajectories.jsonl`, `eval_dev.jsonl`, "
      "`stats.json` and `arm_s31/split31.json`. The export files hold run text and are not committed, like the run trees.\n"
      "- `arm_s31/check31.py` writes `checks31.json`, `checks31.out` and `samples31.md`.\n"
      "- `arm_s31/dryrun31.py` writes `dryrun31.json`.\n"
      "- `arm_s31/score31.py` does the per-step scoring.\n"
      "- `arm_s31/TRAIN.md`; `arm_s31/report31.py` writes this file.\n")
    w("## Appendix: rendered inputs (Qwen format, user message, in full)\n")
    w((S / "samples31.md").read_text())
    (ROOT / "analysis/step31.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step31.md")


if __name__ == "__main__":
    main()
