#!/bin/bash
# Step 26 part 4 launcher (2 workers per agent): 24 tasks (22 safe twins + 2 -v26 repairs) x r1-r3, step-29 layout
# (arm_s26_twins/runs, qwen9b, qwen35).   arm_s26_twins/start26.sh api | 9b | 35b | all
#   api   claude-haiku-5-5 first, all of its runs (Anthropic credit ends 2026-11-27 00:00 UTC), then gpt-6-luna
#   9b / 35b  wait until the endpoint answers (localhost:8000 / 8001), then run with the step-21 guard and watchdog
#   all   api, then 9b and 35b side by side
cd "$(dirname "$0")/.."
PY=.venv/bin/python
case "$1" in
api)
  mkdir -p arm_s26_twins/runs
  $PY arm_s16c/watchdog16c.py arm_s26_twins/runs >> arm_s26_twins/runs/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s26_twins/run_harness26.py --agent haiku --root arm_s26_twins/runs --first 1 --last 3 >> arm_s26_twins/runs/runner_haiku.out 2>&1
  echo "$(date) haiku done"
  WORKERS=2 $PY arm_s26_twins/run_harness26.py --agent luna --root arm_s26_twins/runs --first 1 --last 3 >> arm_s26_twins/runs/runner_luna.out 2>&1
  echo "$(date) luna done"; kill $W
  ;;
9b|35b)
  if [ "$1" = 9b ]; then PORT=8000; AG=qwen; DIR=arm_s26_twins/qwen9b; else PORT=8001; AG=qwen35; DIR=arm_s26_twins/qwen35; fi
  mkdir -p $DIR
  until curl -sf -m 10 localhost:$PORT/v1/models >/dev/null; do sleep 60; done; echo "$(date) $1 up"
  GUARD_DIR=$DIR/harness QWEN_BASE_URL=http://localhost:$PORT/v1 $PY arm_s21/guard21.py $AG >> $DIR/guard.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py $DIR >> $DIR/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s26_twins/run_harness26.py --agent $AG --root $DIR --first 1 --last 3 >> $DIR/runner.out 2>&1
  kill $G $W; echo "$(date) $1 done"
  ;;
all)
  "$0" api; "$0" 9b & "$0" 35b & wait
  ;;
esac
