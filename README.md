# haico-synthetic-pipeline

A pipeline that generates synthetic agent-safety tasks on AgentDojo-style stateful environments: Gmail, SQL database,
medical records, commerce, finance and evidence handling. The tasks follow HAICOSYSTEM's risk categories. Each task's
environment is a Pydantic state that real tool functions change. A rule-based grader reads only the environment state
before and after a run, with no LLM judge, so whether a run was unsafe can be checked. Tasks are kept when rollouts on
the OpenAgentSafety harness give both safe and unsafe outcomes. The resulting banks are on Hugging Face as
[`yanhanliu/haico_synthetic`](https://huggingface.co/yanhanliu) (latest: `yanhanliu/haico_synthetic_v0.6`).

For results, see [REPORT.md](REPORT.md), [REPORT_round2.md](REPORT_round2.md) and the per-step reports in
[analysis/](analysis/), for example `analysis/step9.md` and `analysis/step10.md`.

This is research code from a CMU LTI directed study (Agentic Safety Monitor project).
