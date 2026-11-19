#!/bin/bash
# Step 25 parts 4-5 launcher (2 workers per agent), the two repaired tasks x r1-r3, step-23 layout (arm_s25/runs, qwen9b, qwen35).
#   arm_s25/start25.sh api | 9b | 35b
# The Qwen modes wait until the step-23 launcher of the same model has finished (one model's runs at a time on its
# endpoint, as in step 23), then until the endpoint answers.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
case "$1" in
api)
  mkdir -p arm_s25/runs
  nohup $PY arm_s16c/watchdog16c.py arm_s25/runs > arm_s25/runs/watchdog.out 2>&1 &
  WORKERS=2 nohup $PY arm_s25/run_harness25.py --agent haiku --root arm_s25/runs --first 1 --last 3 > arm_s25/runs/runner_haiku.out 2>&1 &
  WORKERS=2 nohup $PY arm_s25/run_harness25.py --agent luna --root arm_s25/runs --first 1 --last 3 > arm_s25/runs/runner_luna.out 2>&1 &
  ;;
9b|35b)
  if [ "$1" = 9b ]; then PORT=8000; AG=qwen; DIR=arm_s25/qwen9b; else PORT=8001; AG=qwen35; DIR=arm_s25/qwen35; fi
  mkdir -p $DIR
  while pgrep -f "start23.sh $1" >/dev/null; do sleep 60; done
  until curl -sf -m 10 localhost:$PORT/v1/models >/dev/null; do sleep 60; done; echo "$(date) $1 up"
  GUARD_DIR=$DIR/harness QWEN_BASE_URL=http://localhost:$PORT/v1 $PY arm_s21/guard21.py $AG > $DIR/guard.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py $DIR > $DIR/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s25/run_harness25.py --agent $AG --root $DIR --first 1 --last 3 > $DIR/runner.out 2>&1
  kill $G $W; echo "$(date) $1 done"
  ;;
esac
