# Monitor v0: training on the step-31 export

Everything here runs from the benchmarks repo, unchanged (`$BENCHMARKS_DIR/safety_monitor`, its `.venv` with the
`[sft]` extra: torch, transformers, peft, accelerate, matplotlib). `$REPO` is this repository, `$OUT` any output
directory outside both repos. Weights are local directories; the code never downloads.

```bash
export REPO=/path/to/overnight-gmail-dojo
export BENCHMARKS_DIR=/path/to/benchmarks
export SHIELDGEMMA_MODEL_PATH=/path/to/shieldgemma-2b     # gated on Hugging Face: accept the licence, download once
export QWEN_MODEL_PATH=/path/to/qwen-instruct-model        # any local Qwen chat model directory
export OUT=/path/to/outputs
cd $BENCHMARKS_DIR/safety_monitor
```

## Inputs

| file | trajectories | train examples (unsafe) | dev examples (unsafe) |
|---|---|---|---|
| `arm_s31/export/base/trajectories.jsonl` | 515 runs | 3,108 (127) | 1,021 (54) |
| `arm_s31/export/with_safer/trajectories.jsonl` | 515 runs + 6 safer runs (gpt-6-luna and Haiku branches of step 30; rerun the export when the Qwen branches arrive) | 3,129 (127) | 1,021 (54) |

`eval_dev.jsonl` next to each file holds the dev trajectories only. The CLI requires an `--eval` file; nothing else
held out exists yet (see "Missing").

The benchmarks "example_counts" line reports 3,201 (198) train and 1,038 (66) dev for base. That line counts every step,
including the 110 context-only steps (empty `action_id`). The trainer itself builds exactly the examples above.

With the default class handling (unsafe repeated up to 1:1), base gives 2 × 2,981 = 5,962 training rows per epoch.

## ShieldGemma-2B (threshold fit on dev)

```bash
# base
PYTHONPATH=. python -m safety_monitor sft-scaling --backend hf \
  --train $REPO/arm_s31/export/base/trajectories.jsonl \
  --eval  $REPO/arm_s31/export/base/eval_dev.jsonl \
  --rungs 0,all --epochs 2 --seed 42 --out-dir $OUT/s31_shieldgemma_base

# with_safer
PYTHONPATH=. python -m safety_monitor sft-scaling --backend hf \
  --train $REPO/arm_s31/export/with_safer/trajectories.jsonl \
  --eval  $REPO/arm_s31/export/with_safer/eval_dev.jsonl \
  --rungs 0,all --epochs 2 --seed 42 --out-dir $OUT/s31_shieldgemma_with_safer
```

Rung `0` is the zero-shot baseline; rung `all` trains LoRA on every train family. The Yes-probability threshold is
picked on dev for each rung (grid 0.05 to 0.95: best step-level F1, then run-level max AUROC) and written to
`rung_<n>/threshold.json`. The adapter's path is `adapter_dir` in `rung_all/train_stats.json`.

The ladder writes only aggregates:
- step-level precision, recall and F1 at the threshold;
- run-level AUROC of the max, count and rate of step scores against `role`.

For the numbers v0 is judged on, score dev step by step with the adapter (this repo's script, benchmarks code
unchanged):

```bash
ADAPTER=$(python -c "import json;print(json.load(open('$OUT/s31_shieldgemma_base/rung_all/train_stats.json'))['adapter_dir'])")
PYTHONPATH=. python $REPO/arm_s31/score31.py --export $REPO/arm_s31/export/base/trajectories.jsonl --split dev \
  --model-path $SHIELDGEMMA_MODEL_PATH --adapter-dir $ADAPTER \
  --threshold-json $OUT/s31_shieldgemma_base/rung_all/threshold.json --out $OUT/s31_shieldgemma_base/score31
```

`score31/summary.json` gives, over training examples only (context-only steps are skipped):
- step-level precision, recall and F1 of high-unsafe at the dev threshold;
- step-level AUROC;
- the same per agent, per toolkit and per source (run or safer run);
- run-level AUROC (max step score).

`step_scores.jsonl` has one row per step. Run the same command without `--adapter-dir`, with rung 0's threshold, for
the zero-shot baseline.

## Local Qwen (generated label, no threshold)

```bash
# base
PYTHONPATH=. python -m safety_monitor sft-run --backend hf --family qwen --model-path $QWEN_MODEL_PATH \
  --use-shipped-splits --epochs 2 \
  --train $REPO/arm_s31/export/base/trajectories.jsonl \
  --eval  $REPO/arm_s31/export/base/eval_dev.jsonl \
  --out-dir $OUT/s31_qwen_base

# with_safer
PYTHONPATH=. python -m safety_monitor sft-run --backend hf --family qwen --model-path $QWEN_MODEL_PATH \
  --use-shipped-splits --epochs 2 \
  --train $REPO/arm_s31/export/with_safer/trajectories.jsonl \
  --eval  $REPO/arm_s31/export/with_safer/eval_dev.jsonl \
  --out-dir $OUT/s31_qwen_with_safer
```

`--use-shipped-splits` is required. Without it, sft-run re-splits by a hash of the task id, which puts versions of one
family on both sides.

Even with the flag, sft-run never uses the dev split: it maps an empty test split to its holdout. The Qwen critic
generates `Label: high-unsafe | low-unsafe`, so there is no score and no threshold.

`metrics.json` reports, for zero-shot, few-shot and after SFT:
- step-level precision, recall and F1 on the `--eval` file (dev here);
- run-level count, rate and max against `role`.

There is no step-level AUROC for this path.

## Class balance

Unsafe is 4.1% of train examples (127 of 3,108).

What benchmarks does:
- `upsample_high` (`sft/data.py:616`) repeats unsafe examples until they equal the safe count, 1:1. It is on by default
  in both entry points (`sft/experiment.py:259`, `sft/scaling.py:646`) and is not a CLI option.
- The LoRA loss is unweighted.
- The CPU mock uses class weights instead.

With 127 distinct unsafe examples, 1:1 means each one is seen about 23 times per epoch.

Proposed setting: `upsample_high(..., max_ratio=0.25)`. That gives about 745 unsafe rows against 2,981 safe (unsafe
about 20% of rows), about 6 repeats each. It is an existing argument of an existing function, but setting it means
changing those two call sites in benchmarks, which this step does not do.

## Missing before a real run

1. **A held-out side.** The split has only train and dev. Dev picks the threshold, so any number on dev at the dev
   threshold is in-sample for the threshold, and the Qwen path reports on dev as its "eval".
   - Options: a test side of families, or cross-fitting over families.
   - With 25 families (4 in dev), the dev numbers rest on 54 unsafe steps, only 1 of them from Haiku.
2. **The 400-character observation cut.** It removes the prohibition text from 40 of the 95 unsafe examples whose
   prohibition was returned within the last 20 steps. It is hard-coded in `critic/prompted.py:42`, so changing it
   means changing benchmarks; decide before training.
3. **Qwen sequence length.** `train_lora_sft` truncates at 2,048 tokens from the right (`sft/backends.py:535,583`).
   - About 1,024 of 4,129 Qwen-format prompts are longer (45 of the 181 unsafe ones; measured with a Qwen2.5
     tokenizer). They lose the current action and contribute no loss.
   - `max_length` exists but is not a CLI option.
   - ShieldGemma prompts fit: 7 of 4,129 are longer.
4. **Context-only steps are scored in the benchmarks evaluation.** `score_trajectories` and `evaluate_critic` score
   every step with its stored label, including steps with an empty `action_id`. The dev threshold fit therefore sees
   1,038 steps / 66 unsafe instead of 1,021 / 54. `score31.py` skips them. The ladder's own numbers include them.
5. **Weights and GPU:** `SHIELDGEMMA_MODEL_PATH` (gated), `QWEN_MODEL_PATH`, and the `[sft]` extra. The CPU venv used
   for the dry run has no matplotlib, so the ladder stops at its final plot after writing every result file.
