"""Step 12a: re-grade every stored rollout of the 103 v0.6 tasks with harness/grader_v2.py (no model calls) ->
arm_s12/regrade.jsonl, one line per run: task, agent, run, v1 grade (the stored result), harm_realized,
attempted_leak (+ rule), side_effect (+ the out-of-scope changes), v2 unsafe.
Calls the framework rejected (agentdojo_state/<task>/rejected_calls.jsonl, arm_s12/backfill_rejected.py) count in the
leak check. Runs: Qwen3.5-9B r1-r5 (arm_s11), gpt-4o-mini and gpt-5-mini (arm_s9 + arm_s10 via arm_s10/aggregate.load, the two
NPC-fixed tasks r6+ only). Ungraded runs (no post.json) are carried with unsafe=None.
  .venv/bin/python arm_s12/regrade.py"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"
sys.path.insert(0, str(ROOT / "harness")); sys.path.insert(0, str(ROOT / "arm_s10"))
from grader_v2 import grade  # noqa: E402
from aggregate import load  # noqa: E402


def runs(ids):
    for t in ids:
        for k in range(1, 6):
            yield json.loads((ROOT / f"arm_s11/harness/results/{t}__qwen3.5-9b__r{k}.json").read_text())
    for (t, a, k), x in sorted(load().items()):
        if t in ids:
            yield x


def main():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s11/bank_v06.jsonl").read_text().splitlines()}
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    out = []
    for x in runs(set(rows)):
        sd = ROOT / x["state_dir"]
        rec = {"task": x["task"], "agent": x["agent"], "run": x["run"], "v1_graded": x["graded"], "v1_unsafe": x["unsafe"]}
        if not (x["graded"] and (sd / "post.json").exists()):
            out.append({**rec, "unsafe": None}); continue
        pre, post = json.loads((sd / "pre.json").read_text()), json.loads((sd / "post.json").read_text())
        calls = [json.loads(l) for l in (sd / "calls.jsonl").read_text().splitlines() if l.strip()] \
            if (sd / "calls.jsonl").exists() else []
        rej = [json.loads(l) for l in (sd / "rejected_calls.jsonl").read_text().splitlines() if l.strip()] \
            if (sd / "rejected_calls.jsonl").exists() else []
        out.append({**rec, **grade(rows[x["task"]], pre, post, calls, ctx.get(x["task"], ""), rej)})
    (S12 / "regrade.jsonl").write_text("".join(json.dumps(o) + "\n" for o in out))
    g = [o for o in out if o.get("unsafe") is not None]
    print(len(out), "runs,", len(g), "graded; v1 mismatch:", sum(o["harm_realized"] != bool(o["v1_unsafe"]) for o in g))
    print(collections.Counter((o["agent"], o["harm_realized"], o["attempted_leak"], o["side_effect"]) for o in g))


if __name__ == "__main__":
    main()
