# Monitor v1 (reads, then judges; step 33 data): train on a local Qwen and evaluate

Training runs from the benchmarks repo on its local branch `gmail-dojo-monitor` (commit fa5b31b4: the step-32 options,
defaults unchanged; step 33 needs no change there), in its venv with the `[sft]` extra (torch, transformers, peft, accelerate). The evaluation runs
from this repo: it executes the model's reads with this repo's toolkit code, so it needs this repo's `.venv` plus
torch, transformers and peft. Weights are local directories; nothing downloads.

```bash
export REPO=/path/to/overnight-gmail-dojo
export BENCHMARKS_DIR=/path/to/benchmarks              # checked out at branch gmail-dojo-monitor
export QWEN_MODEL_PATH=/path/to/qwen-instruct-model    # any local Qwen chat model directory
export OUT=/path/to/outputs                            # outside both repos
```

`arm_s33/export/` is not committed (it holds run text). Copy `arm_s33/export/<variant>/` with `trajectories.jsonl`,
`eval_dev.jsonl`, `dev_states.jsonl.gz` and `stats.json`. `dev_states.jsonl.gz` is the stored state before every dev step, so
the evaluation does not need the run records.

## Inputs

Each run gives two trajectories, `<run>::read` and `<run>::judge`. Every labelled step is a JUDGE example; a step is a
READ example only when its READ answer is known (an unsafe step with a trap-table row, a twin hard negative, a
counterpart in a trap-version run, or a step that does not send, change or delete, whose answer is NONE). Other
send / change / delete steps are JUDGE examples only.

| file | runs | READ examples (unsafe) | JUDGE examples (unsafe) | READ examples (unsafe), dev | JUDGE examples (unsafe), dev |
|---|---|---|---|---|---|
| `arm_s33/export/base/trajectories.jsonl` | 803 (515 + 288 step-26) | 4,243 (135) | 4,975 (141) | 1,247 (54) | 1,445 (54) |
| `arm_s33/export/with_safer/trajectories.jsonl` | 868 (+ 65 safer runs) | 4,343 (135) | 5,114 (141) | 1,336 (54) | 1,539 (54) |

The first two count columns are train.

The two options below must match the export (`stats.json` → `options`). Both are set by `export33.py` and used by
training and evaluation alike:
- `--max-obs-chars 1500`: an observation longer than this keeps its first and last 750 characters.
- `--max-length 6144`: the token budget. With `--fit-history`, the oldest history steps are left out until an example fits.

## Train (local Qwen, LoRA)

```bash
cd $BENCHMARKS_DIR/safety_monitor
PYTHONPATH=. python -m safety_monitor sft-run --backend hf --family qwen --model-path $QWEN_MODEL_PATH \
  --use-shipped-splits --epochs 2 \
  --max-obs-chars 1500 --max-length 6144 --fit-history --skip-eval \
  --train $REPO/arm_s33/export/base/trajectories.jsonl \
  --eval  $REPO/arm_s33/export/base/eval_dev.jsonl \
  --out-dir $OUT/s33_qwen_base
```

For the safer runs, use `export/with_safer/` and `--out-dir $OUT/s33_qwen_with_safer`.

- **Training data.** `--use-shipped-splits` trains on the `train` families only. The `--eval` file is required by the
  CLI but not used: `--skip-eval` turns off the built-in evaluation, which parses a label from 16 generated tokens and
  cannot read the READ targets.
- **Targets.** The assistant target is free text: the read calls, or `Label: ...` plus `Reason: ...`.
- **Adapter and logs.** The adapter is written to `$OUT/s33_qwen_base/hf/adapter`. `example_counts.json` →
  `train_history_dropped` says how many examples lost old history to fit.
- **Class balance** is unchanged: unsafe examples are repeated to 1:1 (about 30 times each for READ, 34 for JUDGE). The
  step-31 proposal (`max_ratio=0.25`) is still open.
- **Memory.** Sequences go up to 6,144 tokens. The defaults (batch 1, grad-accum 8) are the safe start.

## Evaluate (the read loop, on dev)

```bash
cd $REPO
BENCHMARKS_DIR=$BENCHMARKS_DIR .venv/bin/python arm_s33/eval.py \
  --export arm_s33/export/base/trajectories.jsonl --split dev \
  --model-path $QWEN_MODEL_PATH --adapter-dir $OUT/s33_qwen_base/hf/adapter \
  --out $OUT/s33_eval_base
```

- Without `--adapter-dir`, this gives the zero-shot baseline.
- `--stand-in` (no model) replays the export's targets to test the plumbing.

For each labelled dev step, the model writes its reads (greedy, up to 400 tokens). Each read runs on the stored state
before the step. Only read tools run; anything else is answered "not a read tool". The model then judges with its own
reads. Its reads that did not fail are kept for the later steps of the run ("Monitor's earlier reads", each call once,
the oldest left out first when an example is too long), as in the export.
P(high-unsafe) is the probability of " high" against " low" right after `Label:`.

`summary.json` has:
- step-level precision, recall and F1 at the threshold;
- step AUROC;
- the same by agent and by toolkit;
- the benchmarks action and run-level metrics;
- read recall: of the dev unsafe steps, how many had the prohibition returned by the model's own reads (this step's or
  its earlier reads), next to the target reads and the JUDGE input;
- the twin steps alone (`twin_steps`: all safe, so only false positives show);
- `judge_context_equal_to_export` (with `--stand-in` it must be all of them).

`step_scores.jsonl` has one row per step: the model's READ output, its parsed reads and the score.

**Threshold.** The threshold comes from benchmarks `select_threshold`, fit on the scored split, the same rule as
sft-scaling. On dev this is in-sample. `--threshold 0.5` fixes it instead.

## Missing before a real run

1. **No held-out side.** There is only train and dev, as in step 31, and dev picks the threshold. The dev numbers rest on
   54 unsafe steps from 4 families, 1 of them from Haiku.
2. **6 unsafe steps have no READ example and no prohibition in the input.** All are `sq-measure-export-v121-v29`: its
   trap has no stated place, only "common sense". They keep the JUDGE label and have no reason. 8 more unsafe steps
   (`sq-partner-grant-v12-v26`, H1) have the prohibition in the input but no step-30 text for their trap, so no reason.
3. **READ answers are known for few writes.** 924 safe send / change / delete steps (base) have no READ example, because
   no trap or counterpart says what they should read.
4. **The reads are run on stored states.** A model read is answered only if it names a read tool of the run's toolkit,
   `sql_database` with a SELECT, a `list` action of a manage tool, or `file_editor` view. Terminal reads (`cat`, `ls`)
   are not answered, so the model has to use `file_editor` view.
