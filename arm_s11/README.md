Step 11: the v0.6 bank (103 tasks) on Qwen/Qwen3.5-9B (vLLM on a SLURM GPU cluster, harness on the Mac).
- bank_v06.jsonl / ids_v06.txt: the 103 v0.6 rows (from arm_s10/bank_s10.jsonl).
- run_harness.py --agent qwen: results in harness/results/<task>__qwen3.5-9b__r<k>.json.
- cost_watchdog.py: step-10 caps (token 200k uncached; no cost cap for Qwen; hang 10 min).
- Cluster side (job script, tunnel, health check): see the private serving notes.
