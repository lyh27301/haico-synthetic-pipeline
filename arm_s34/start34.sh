#!/bin/bash
# Step 34 launcher (2 workers per agent), x r1-r3, step-29 layout; BANK34 (default arm_s34/bank) picks the bank, OUT34 (default arm_s34) the run trees
# ($OUT34/runs, qwen9b, qwen35).   arm_s34/start34.sh api | 9b | 35b | all
#   api   claude-haiku-5-5 first, all of its runs (Anthropic credit ends 2026-11-27 00:00 UTC), then gpt-6-luna
#   9b / 35b  wait until the endpoint answers (localhost:8000 / 8001), then run with the step-21 guard and watchdog
#   all   api, then 9b and 35b side by side
cd "$(dirname "$0")/.."
PY=.venv/bin/python; OUT34=${OUT34:-arm_s34}; export BANK34=${BANK34:-arm_s34/bank}
case "$1" in
api)
  mkdir -p $OUT34/runs
  $PY arm_s16c/watchdog16c.py $OUT34/runs >> $OUT34/runs/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s34/run_harness34.py --agent haiku --root $OUT34/runs --first 1 --last 3 >> $OUT34/runs/runner_haiku.out 2>&1
  echo "$(date) haiku done"
  WORKERS=2 $PY arm_s34/run_harness34.py --agent luna --root $OUT34/runs --first 1 --last 3 >> $OUT34/runs/runner_luna.out 2>&1
  echo "$(date) luna done"; kill $W
  ;;
9b|35b)
  if [ "$1" = 9b ]; then PORT=8000; AG=qwen; DIR=$OUT34/qwen9b; else PORT=8001; AG=qwen35; DIR=$OUT34/qwen35; fi
  mkdir -p $DIR
  until curl -sf -m 10 localhost:$PORT/v1/models >/dev/null; do sleep 60; done; echo "$(date) $1 up"
  GUARD_DIR=$DIR/harness QWEN_BASE_URL=http://localhost:$PORT/v1 $PY arm_s21/guard21.py $AG >> $DIR/guard.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py $DIR >> $DIR/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s34/run_harness34.py --agent $AG --root $DIR --first 1 --last 3 >> $DIR/runner.out 2>&1
  kill $G $W; echo "$(date) $1 done"
  ;;
all)
  "$0" api; "$0" 9b & "$0" 35b & wait
  ;;
esac
