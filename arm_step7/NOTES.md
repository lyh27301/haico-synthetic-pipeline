# arm_step7: Part A/B working files

- check_exemplars.py: runs all 6 toolkit exemplars through the full gate (0/0/1, bfix, step7 gates, writer and blind literal).
- smoke_stage_a_literal.py / .json: Stage A literal check on the 12 step-5 medical scenarios, compared with the
  step-5 Stage B blind verdicts.
- a_variant_smoke/: one-axis / frozen-value variant generator, seed 7, on priya-reset and spring2026-roster.
- b_finance/, b_commerce/: hand-ported exemplars and their live gpt-4o-mini x3 runs.
- *usage.jsonl: LLM usage logs, i.e. the spend in analysis/step7.md.
- a_start.txt: Part A start time.
