#!/bin/bash
# Step 21: wait until the 9B endpoint answers on localhost:8000, then start its guard, watchdog and runner (once).
cd "$(dirname "$0")/.."
until curl -sf -m 10 localhost:8000/v1/models >/dev/null; do sleep 60; done
echo "$(date) 9B endpoint up"
GUARD_DIR=arm_s21/qwen9b/harness QWEN_BASE_URL=http://localhost:8000/v1 nohup .venv/bin/python arm_s21/guard21.py qwen > arm_s21/qwen9b/guard.out 2>&1 &
nohup .venv/bin/python arm_s16c/watchdog16c.py arm_s21/qwen9b > arm_s21/qwen9b/watchdog.out 2>&1 &
WORKERS=3 nohup .venv/bin/python arm_s21/run_harness21.py --agent qwen --root arm_s21/qwen9b --first 1 --last 3 > arm_s21/qwen9b/runner.out 2>&1 &
echo "$(date) started"
