"""Step 12a addendum: write agentdojo_state/<task>/rejected_calls.jsonl (harness/rejected_calls.py) for every stored
rollout of the v0.6 tasks (Qwen r1-r5, gpt-4o-mini / gpt-5-mini via arm_s10/aggregate.load), from the conversation
history in the run's output.critic_attempt_1.jsonl, so grader v2's leak check sees calls the framework rejected.
  .venv/bin/python arm_s12/backfill_rejected.py"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness")); sys.path.insert(0, str(ROOT / "arm_s12"))
import rejected_calls  # noqa: E402
from regrade import runs  # noqa: E402

H = {}


def history(out_dir: Path, t: str):
    if out_dir not in H:
        H[out_dir] = {}
        for f in out_dir.rglob("output.critic_attempt_1.jsonl"):
            for ln in f.read_text().splitlines():
                if ln.strip():
                    o = json.loads(ln); H[out_dir][o["instance_id"]] = o.get("history") or []
    return H[out_dir].get(t)


def main():
    ids = {json.loads(l)["instance_id"] for l in (ROOT / "arm_s11/bank_v06.jsonl").read_text().splitlines()}
    n = collections.Counter(); kinds = collections.Counter()
    for x in runs(ids):
        sd = ROOT / x["state_dir"]
        h = history(sd.parents[1], x["task"])
        if h is None:
            n[(x["agent"], "no_history")] += 1; continue
        k = rejected_calls.write(h, sd)
        n[(x["agent"], "runs")] += 1; n[(x["agent"], "runs_with_rejected")] += bool(k); n[(x["agent"], "rejected")] += k
        for r in rejected_calls.extract(h):
            kinds[(x["agent"], r["kind"], "send_email" if "send_email" in str(r["name"]) else "other")] += 1
    print(sorted(n.items())); print(sorted(kinds.items()))


if __name__ == "__main__":
    main()
