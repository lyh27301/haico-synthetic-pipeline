#!/bin/bash
# Step 23 part 4 launcher (2 workers per agent). API agents now; each Qwen agent once its endpoint answers.
#   arm_s23/start23.sh api | 9b | 35b
cd "$(dirname "$0")/.."
PY=.venv/bin/python
case "$1" in
api)
  nohup $PY arm_s16c/watchdog16c.py arm_s23/runs > arm_s23/runs/watchdog.out 2>&1 &
  WORKERS=2 nohup $PY arm_s23/run_harness23.py --agent haiku --root arm_s23/runs --first 1 --last 3 > arm_s23/runs/runner_haiku.out 2>&1 &
  WORKERS=2 nohup $PY arm_s23/run_harness23.py --agent luna --root arm_s23/runs --first 1 --last 3 > arm_s23/runs/runner_luna.out 2>&1 &
  ;;
9b)   # the two invalid step-21 payroll r2 runs first (in arm_s21/qwen9b), then the 15 new runs (arm_s23/qwen9b)
  until curl -sf -m 10 localhost:8000/v1/models >/dev/null; do sleep 60; done; echo "$(date) 9B up"
  GUARD_DIR=arm_s21/qwen9b/harness QWEN_BASE_URL=http://localhost:8000/v1 $PY arm_s21/guard21.py qwen >> arm_s21/qwen9b/guard23.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py arm_s21/qwen9b >> arm_s21/qwen9b/watchdog23.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s21/run_harness21.py --agent qwen --root arm_s21/qwen9b --first 2 --last 2 --ids arm_s23/rerun9b_ids.txt > arm_s21/qwen9b/runner23.out 2>&1
  kill $G $W
  GUARD_DIR=arm_s23/qwen9b/harness QWEN_BASE_URL=http://localhost:8000/v1 $PY arm_s21/guard21.py qwen > arm_s23/qwen9b/guard.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py arm_s23/qwen9b > arm_s23/qwen9b/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s23/run_harness23.py --agent qwen --root arm_s23/qwen9b --first 1 --last 3 > arm_s23/qwen9b/runner.out 2>&1
  kill $G $W; echo "$(date) 9B done"
  ;;
35b)
  until curl -sf -m 10 localhost:8001/v1/models >/dev/null; do sleep 60; done; echo "$(date) 35B up"
  GUARD_DIR=arm_s23/qwen35/harness QWEN_BASE_URL=http://localhost:8001/v1 $PY arm_s21/guard21.py qwen35 > arm_s23/qwen35/guard.out 2>&1 & G=$!
  $PY arm_s16c/watchdog16c.py arm_s23/qwen35 > arm_s23/qwen35/watchdog.out 2>&1 & W=$!
  WORKERS=2 $PY arm_s23/run_harness23.py --agent qwen35 --root arm_s23/qwen35 --first 1 --last 3 > arm_s23/qwen35/runner.out 2>&1
  kill $G $W; echo "$(date) 35B done"
  ;;
esac
