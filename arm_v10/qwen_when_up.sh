#!/bin/bash
# Waits for the Babel Qwen endpoint (tunnel on localhost:8000), checks tool calling, then starts the Qwen guard and the
# 145 queued step-13j runs (arm_v10/queue_qwen.json) under arm_v10/qwen. Writes arm_v10/qwen/STARTED / FAILED_CHECK.
cd "$(dirname "$0")/.." || exit 1
until curl -s -m 10 localhost:8000/v1/models | grep -q Qwen; do sleep 30; done
echo "$(date) endpoint up" >> arm_v10/qwen/when_up.log
tc=$(curl -s -m 120 localhost:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"Qwen/Qwen3.5-9B","messages":[{"role":"user","content":"What is the weather in Paris? Use the tool."}],"tools":[{"type":"function","function":{"name":"get_weather","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],"tool_choice":"auto"}')
if ! grep -q tool_calls <<<"$tc"; then echo "$(date) tool-call check failed: ${tc:0:300}" > arm_v10/qwen/FAILED_CHECK; exit 1; fi
echo "$(date) tool-call check ok" >> arm_v10/qwen/when_up.log
GUARD_DIR=arm_v10/qwen/harness nohup .venv/bin/python arm_v10/endpoint_guard.py >> arm_v10/qwen/guard.out 2>&1 &
QWEN_BASE_URL=http://localhost:8000/v1 WORKERS=3 nohup .venv/bin/python arm_v09/run_harness.py --agent qwen --ids arm_v10/ids_13j.txt --first 1 --last 5 --root arm_v10/qwen >> arm_v10/qwen/run_qwen.out 2>&1 &
echo "$(date) runner pid $!" > arm_v10/qwen/STARTED
