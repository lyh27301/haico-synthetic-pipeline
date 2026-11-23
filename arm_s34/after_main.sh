#!/bin/bash
# Step 34: twin runs of one agent once its main runs are done (luna: after start34.sh api; Qwen: after start34.sh 9b/35b),
# same runner and layout as the main runs (BANK34=arm_s34/twins, OUT34=arm_s34/twins).  arm_s34/after_main.sh luna|9b|35b
cd "$(dirname "$0")/.."
case "$1" in
luna) until grep -q "luna done" arm_s34/logs/start_api.out; do sleep 60; done
      mkdir -p arm_s34/twins/runs
      BANK34=arm_s34/twins WORKERS=2 .venv/bin/python arm_s34/run_harness34.py --agent luna --root arm_s34/twins/runs --first 1 --last 3 >> arm_s34/twins/runs/runner_luna.out 2>&1 ;;
9b|35b) until grep -q "$1 done" arm_s34/logs/start_$1.out; do sleep 60; done
      BANK34=arm_s34/twins OUT34=arm_s34/twins arm_s34/start34.sh $1 ;;
esac
echo "$(date) $1 twins done"
