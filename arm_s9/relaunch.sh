#!/usr/bin/env bash
# Relaunch run_harness.py parents (new token-cap logic) once the orphaned run_infer children of the old parents exit.
cd ~/overnight-gmail-dojo
export NPC_API_KEY="$OPENAI_API_KEY" NPC_MODEL=gpt-4o-mini
( while kill -0 66101 2>/dev/null; do sleep 20; done
  WORKERS=5 .venv/bin/python arm_s9/run_harness.py --agent 4omini --ids arm_s9/ids_nonnpc.txt --runs 5 >> arm_s9/harness/c_4omini_nonnpc.log 2>&1 ) &
( while kill -0 67994 2>/dev/null; do sleep 20; done
  WORKERS=2 .venv/bin/python arm_s9/run_harness.py --agent 4omini --ids arm_s9/ids_npc.txt --runs 3 --tag npc_ >> arm_s9/harness/b_npc.log 2>&1 ) &
wait
