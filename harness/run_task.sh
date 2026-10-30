#!/usr/bin/env bash
# Run v0.4 rows on the OAS SDK-V1 harness through harness/oas_agentdojo.py, once.
#   harness/run_task.sh <ids.txt> <out_dir> [llm_config]
set -euo pipefail
H="$(cd "$(dirname "$0")" && pwd)"
IDS="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="$2"; CFG="${3:-.llm_config/openai.json}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
cd "$HOME/Documents/workspace/benchmarks"
OPENHANDS_SUPPRESS_BANNER=1 "$H/.venv-oas/bin/python" "$H/oas_agentdojo.py" "$CFG" \
  --dataset yanhanliu/haico_synthetic_v0.4 --split train --select "$IDS" --output-dir "$OUT" \
  --num-workers "${WORKERS:-1}" --critic pass --max-attempts 1
