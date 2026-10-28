# Gmail safety-task pipeline on AgentDojo (+ Petri ablation)

_Overnight run. Project: agentic safety-monitor; need per-action unsafe labels from real, checkable env state. AgentDojo used as the middle ground: real Python tools over a diffable Pydantic Gmail env._

## Models & keys
- `OPENAI_API_KEY`: not in env; used the key from `~/Documents/workspace/benchmarks/.llm_config/openai.json`.
- `ANTHROPIC_API_KEY`: not set.
- **Agent under test: `gpt-5-mini`** (available on the key; preferred).
- **Generation + simulated-user model: `gpt-4o-mini`** (no Anthropic key; chosen over gpt-5-mini for cost/latency across ~60 rollouts — recorded deviation from "same OpenAI model").

## Headline (filled at end)
_pending — Phases 2–5_

## Phase 1 — Gmail suite (DONE)
- `gmail_suite/environment.py`: `GmailEnvironment(TaskEnvironment)` with `inbox, sent, trash, contacts, downloads` (Pydantic, mutated in place); models `Email, Contact, Attachment` follow ToolEmu field names.
- `gmail_suite/tools.py`: all 9 ToolEmu Gmail tools as `Depends(...)` functions with `:param:` docstrings; each state-changing tool mutates state. `build_runtime()` registers them. `TOOLEMU_NAME_MAP` maps ToolEmu names 1:1.
- `gmail_suite/base_environment.yaml`: 15 emails (incl. HR comp notes, password-reset code, draft contract attachment, customer-list CSV attachment, phishing-awareness reminder) + 10 contacts (incl. an external personal address `owner.personal@gmail.com`).
- `gmail_suite/smoke_test.py`: **PASS** — all 9 tools mutate state as expected.
- Phase 1b `driver.py`: multi-turn OpenAI agent + LLM-simulated user over `FunctionsRuntime`; JSONL transcript; returns pre/post env dicts. Trivial end-to-end check **PASS** (agent deleted the newsletter; env changed; loop terminated; 2 tool calls).

## Decisions
- No env API keys; reused the workspace OpenAI key. No Anthropic key → generation falls back to OpenAI.
- Agent gpt-5-mini; generation+user gpt-4o-mini (cost/latency; deviation noted above).
- Skipped AgentDojo's native `TaskSuite`/benchmark-runner registration — the deliverable is OAS-format tasks run by `driver.py`, not AgentDojo `BaseUserTask`; verification done via the driver.
- `GmailEnvironment` keeps the five collections as top-level fields; tools declare exactly the slices they need as multiple `Depends` params (clean multi-collection mutation). Owner account = `me@company.com`.
- Base mailbox loaded from one shared YAML via `model_validate`; Phase-2 tasks get their own `environment.yaml` (base + scenario-specific).

## Blockers
_(none in Phase 1)_
