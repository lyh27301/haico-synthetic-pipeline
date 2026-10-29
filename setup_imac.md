# Setup on iMac (2026-10-29)

Unpacked `~/Downloads/overnight-gmail-dojo.tar.gz`; HEAD = `3ef43b7 step4c(wip)` (one WIP commit past `step4b`).
`.env` written from shell `OPENAI_API_KEY` (164 chars). venv: `uv venv --python 3.13` (uv-managed CPython 3.13; no system 3.13).

Package diffs vs `install.log` / `petri_install.log` (everything else identical):

| package | original | iMac |
|---|---|---|
| openai | 3.40.0 | 3.41.0 |
| inspect-ai | 0.3.285 | 0.3.286 |
| inspect-petri | git@128f61d | git@128f61d (same commit) |

Patch-level only; not pinned back. Note: Petri imports as `inspect_petri`, not `petri`
(the original `import petri` check in petri_install.log failed the same way, so this is not a regression).

Verification: `tests/test_taskwriter.py` ALL PASS; the 7 step-2 tasks (incl. the 3-scenario set) re-dry-run
7/7 at 0/0/1 with B1/B3 checks clean; live `python driver.py` trivial rollout OK (2 tool calls, env changed).
caffeinate: running on behalf of `claude` (`caffeinate -dims`), no extra one started.
