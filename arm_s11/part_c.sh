#!/bin/bash
# Step 11 Part C: all 103 v0.6 tasks x 5 runs on Qwen3.5-9B (vLLM on the cluster via the localhost:8000 tunnel).
# Run k over all tasks before run k+1, so a job that ends early still leaves complete runs.
cd "$(dirname "$0")/.." || exit 1
export NPC_BASE_URL=https://api.openai.com/v1 NPC_API_KEY=$OPENAI_API_KEY NPC_MODEL=gpt-4o-mini WORKERS=${WORKERS:-5}
.venv/bin/python arm_s11/run_harness.py --agent qwen --ids arm_s11/ids_v06.txt --first 1 --last 5
echo PARTC_DONE
