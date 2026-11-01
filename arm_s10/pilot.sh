#!/usr/bin/env bash
# Step 10 Part C2 pilot: 5 step-9-good Gmail tasks (runs 6-10) + 5 Part-C-rescued tasks (runs 1-5), gpt-4o-mini.
cd "$(dirname "$0")/.."
export NPC_API_KEY="$OPENAI_API_KEY" NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=5
cat arm_s10/ids_pilot_good.txt arm_s10/ids_pilot_rescued.txt > arm_s10/ids_pilot.txt
.venv/bin/python arm_s10/run_harness.py --agent 4omini --ids arm_s10/ids_pilot_good.txt --first 6 --last 10 --tag pilot_ &
.venv/bin/python arm_s10/run_harness.py --agent 4omini --ids arm_s10/ids_pilot_rescued.txt --first 1 --last 5 --tag pilotc_ &
wait
