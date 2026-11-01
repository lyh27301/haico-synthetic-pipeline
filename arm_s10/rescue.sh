#!/usr/bin/env bash
# Step 10 Part A: rescue runs. Part-C-rescued tasks first get step 9's full protocol (4o-mini r1-5, gpt-5-mini r1-5,
# low effort as in step 9), then every task in the set gets gpt-4o-mini r6-r11 (11 in total). Results skip existing.
cd "$(dirname "$0")/.."
export NPC_API_KEY="$OPENAI_API_KEY" NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=4
cat arm_s10/ids_extreme.txt arm_s10/ids_rescued_c.txt > arm_s10/ids_partA.txt
( .venv/bin/python arm_s10/run_harness.py --agent 4omini --ids arm_s10/ids_rescued_c.txt --first 1 --last 5 --tag c_ &&
  .venv/bin/python arm_s10/run_harness.py --agent 5mini --ids arm_s10/ids_rescued_c.txt --first 1 --last 5 --tag c_ ) &
awk "NR%2==1" arm_s10/ids_partA.txt > arm_s10/ids_partA_aa; awk "NR%2==0" arm_s10/ids_partA.txt > arm_s10/ids_partA_ab
.venv/bin/python arm_s10/run_harness.py --agent 4omini --ids arm_s10/ids_partA_aa --first 6 --last 11 --tag a1_ &
.venv/bin/python arm_s10/run_harness.py --agent 4omini --ids arm_s10/ids_partA_ab --first 6 --last 11 --tag a2_ &
wait
echo RESCUE_DONE
