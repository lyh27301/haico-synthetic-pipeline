Step 19: try a larger open model as the third agent, on the 12 trial tasks.

Why. In pilot v3, 6 of the 7 hand-labelled unsafe steps come from Qwen3.5-9B, and of its 60 runs in step 16c only 7
are safe completions. An agent that is unsafe almost every time gives no unsafe / safe pair from the same agent.
We want an open model in between: sometimes careless, but able to finish tasks.

What to run
- Model: Qwen3.5-35B-A3B. If it cannot be served (no weights, no fitting GPU, tool calling broken in the server),
  fall back to Qwen3.5-27B and say why. Serving follows ~/babel-private/BABEL.md; nothing from there goes into the
  repo. Waiting in the queue is normal and has no time limit; make the job resumable.
- Tasks: the same 12 tasks and the same harness (harness/v16b) as step 16c, 5 runs each = 60 runs. Tasks are used as
  they are now, although some will be fixed later: this step compares agents, not tasks.
- Smoke test on 2 tasks first; check that tool calls parse.
- Grade with the frozen grader v4 rules (grader/out/v4). Mark verdicts from rule sets that failed their checks, as
  in step 17b.

Report: analysis/step19.md
- One table, Qwen3.5-9B (stored 16c runs, re-graded with v4) next to the new model, per task and in total:
  safe completion, unsafe and succeeded, failed safely, unsafe and failed, third label; share of tool calls that
  errored; steps per run; wall time per run.
- For how many of the 12 tasks does each model give both a safe completion and an unsafe run.
- What the new model said when asked whether the setting looked like a test (same question as step 16c).
- Serving notes that belong in the repo only in general terms (GPU memory class, tokens per second), no host names,
  paths, user names or job ids.
- Recommendation: keep 9B, replace it, or run both.

Limits: no API spend except grading (stop at $2). Do not change tasks, rules or stored runs. Commit; no HF push.
