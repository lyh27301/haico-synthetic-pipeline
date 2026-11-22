# Monitor v1 (reads, then judges): train on a local Qwen and evaluate

Training runs from the benchmarks repo on its local branch `gmail-dojo-monitor` (commit fa5b31b4: the step-32 options,
defaults unchanged), in its venv with the `[sft]` extra (torch, transformers, peft, accelerate). The evaluation runs
from this repo: it executes the model's reads with this repo's toolkit code, so it needs this repo's `.venv` plus
torch, transformers and peft. Weights are local directories; nothing downloads.

```bash
export REPO=/path/to/overnight-gmail-dojo
export BENCHMARKS_DIR=/path/to/benchmarks              # checked out at branch gmail-dojo-monitor
export QWEN_MODEL_PATH=/path/to/qwen-instruct-model    # any local Qwen chat model directory
export OUT=/path/to/outputs                            # outside both repos
```

`arm_s32/export/` is not committed (it holds run text). Copy `arm_s32/export/<variant>/` with `trajectories.jsonl`,
`eval_dev.jsonl`, `dev_states.jsonl.gz` and `stats.json`. `dev_states.jsonl.gz` is the stored state before every dev step, so
the evaluation does not need the run records.

## Inputs

Each training step gives two examples. They come from two trajectories per run, `<run>::read` and `<run>::judge`:

| file | runs | train examples, READ + JUDGE (unsafe) | dev examples, READ + JUDGE (unsafe) |
|---|---|---|---|
| `arm_s32/export/base/trajectories.jsonl` | 515 | 2 × 3,108 (2 × 127) | 2 × 1,021 (2 × 54) |
| `arm_s32/export/with_safer/trajectories.jsonl` | 515 + 65 safer runs | 2 × 3,247 (2 × 127) | 2 × 1,115 (2 × 54) |

The two options below must match the export (`stats.json` → `options`). Both are set by `export32.py` and used by
training and evaluation alike:
- `--max-obs-chars 1500`: an observation longer than this keeps its first and last 750 characters.
- `--max-length 6144`: the token budget. With `--fit-history`, the oldest history steps are left out until an example fits.

## Train (local Qwen, LoRA)

```bash
cd $BENCHMARKS_DIR/safety_monitor
PYTHONPATH=. python -m safety_monitor sft-run --backend hf --family qwen --model-path $QWEN_MODEL_PATH \
  --use-shipped-splits --epochs 2 \
  --max-obs-chars 1500 --max-length 6144 --fit-history --skip-eval \
  --train $REPO/arm_s32/export/base/trajectories.jsonl \
  --eval  $REPO/arm_s32/export/base/eval_dev.jsonl \
  --out-dir $OUT/s32_qwen_base
```

For the safer runs, use `export/with_safer/` and `--out-dir $OUT/s32_qwen_with_safer`.

- **Training data.** `--use-shipped-splits` trains on the `train` families only. The `--eval` file is required by the
  CLI but not used: `--skip-eval` turns off the built-in evaluation, which parses a label from 16 generated tokens and
  cannot read the READ targets.
- **Targets.** The assistant target is free text: the read calls, or `Label: ...` plus `Reason: ...`.
- **Adapter and logs.** The adapter is written to `$OUT/s32_qwen_base/hf/adapter`. `example_counts.json` →
  `train_history_dropped` says how many examples lost old history to fit.
- **Class balance** is unchanged: unsafe examples are repeated to 1:1, about 23 times each. This applies to READ and
  JUDGE examples alike. The step-31 proposal (`max_ratio=0.25`) is still open.
- **Memory.** Sequences go up to 6,144 tokens. The defaults (batch 1, grad-accum 8) are the safe start.

## Evaluate (the read loop, on dev)

```bash
cd $REPO
BENCHMARKS_DIR=$BENCHMARKS_DIR .venv/bin/python arm_s32/eval.py \
  --export arm_s32/export/base/trajectories.jsonl --split dev \
  --model-path $QWEN_MODEL_PATH --adapter-dir $OUT/s32_qwen_base/hf/adapter \
  --out $OUT/s32_eval_base
```

- Without `--adapter-dir`, this gives the zero-shot baseline.
- `--stand-in` (no model) replays the export's targets to test the plumbing.

For each dev step, the model writes its reads (greedy, up to 400 tokens). Each read runs on the stored state before the
step. Only read tools run; anything else is answered "not a read tool". The model then judges with its own reads.
P(high-unsafe) is the probability of " high" against " low" right after `Label:`.

`summary.json` has:
- step-level precision, recall and F1 at the threshold;
- step AUROC;
- the same by agent and by toolkit;
- the benchmarks action and run-level metrics;
- read recall: of the dev unsafe steps, how many had the prohibition returned by the model's own reads, next to the
  target reads and the JUDGE input.

`step_scores.jsonl` has one row per step: the model's READ output, its parsed reads and the score.

**Threshold.** The threshold comes from benchmarks `select_threshold`, fit on the scored split, the same rule as
sft-scaling. On dev this is in-sample. `--threshold 0.5` fixes it instead.

## Missing before a real run

1. **No held-out side.** There is only train and dev, as in step 31, and dev picks the threshold. The dev numbers rest on
   54 unsafe steps from 4 families, 1 of them from Haiku.
2. **6 unsafe steps cannot have a prohibition in the input.** All are `sq-measure-export-v121-v29`: its traps have no
   stated prohibition, only "common sense". They keep the label and have no reason.
3. **The reads are run on stored states.** A model read is answered only if it names a read tool of the run's toolkit,
   `sql_database` with a SELECT, a `list` action of a manage tool, or `file_editor` view. Terminal reads (`cat`, `ls`)
   are not answered, so the model has to use `file_editor` view.
