#!/bin/bash
# Step 30 launcher.  arm_s30/start30.sh api | 9b | 35b
#   api  Haiku branches first (Anthropic credit ends 2026-11-27 00:00 UTC), then gpt-6-luna.
#   9b / 35b  the Qwen branches; branch30.py waits per job until the endpoint answers (localhost:8000 / 8001), so a
#             queued job never fails on a down endpoint. One proxy port per launcher.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
case "$1" in
api) S30_PROXY_PORT=18830 $PY arm_s30/branch30.py --agents haiku5.5 --workers 3 >> arm_s30/runs/runner_haiku.out 2>&1
     S30_PROXY_PORT=18830 $PY arm_s30/branch30.py --agents gpt-6-luna --workers 3 >> arm_s30/runs/runner_luna.out 2>&1 ;;
9b)  S30_PROXY_PORT=18831 $PY arm_s30/branch30.py --agents qwen3.5-9b --workers 2 >> arm_s30/runs/runner_9b.out 2>&1 ;;
35b) S30_PROXY_PORT=18832 $PY arm_s30/branch30.py --agents qwen3.5-35b-a3b --workers 2 >> arm_s30/runs/runner_35b.out 2>&1 ;;
esac
