"""Summarise harness runs (step 8): per run the grade, the tools the agent used (MCP vs OpenHands built-ins), the
MCP call sequence, reads before the pivotal action, tokens and cost.
  python harness/summarize_runs.py harness/runs/c_run1 [...]  -> JSON lines on stdout"""
import collections, glob, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
GMAIL_WRITE = {"send_email", "delete_emails", "organize_email", "add_or_update_contact", "delete_contact"}
PRICE = {"gpt-4o-mini": (0.15, 0.60)}   # $ per 1M input / output tokens


def summarize(run_dir):
    rows = []
    for out in glob.glob(str(Path(run_dir) / "*/*/output.jsonl")):
        base = Path(out).parent
        for line in open(out):
            o = json.loads(line)
            iid = o["instance_id"]; sd = base / "agentdojo_state" / iid
            acts = collections.Counter()
            for e in o.get("history") or []:
                if (e.get("kind") or e.get("type")) == "ActionEvent":
                    acts[e.get("tool_name")] += 1
            calls = [json.loads(x) for x in (sd / "calls.jsonl").read_text().splitlines()] if (sd / "calls.jsonl").exists() else []
            piv = next((i for i, c in enumerate(calls) if c["name"] in GMAIL_WRITE and not c["error"]), None)
            u = json.loads((sd / "usage.json").read_text()) if (sd / "usage.json").exists() else {}
            tu = u.get("token_usage") or {}
            pin, pout = PRICE.get("gpt-4o-mini")
            cost = (tu.get("prompt_tokens", 0) * pin + tu.get("completion_tokens", 0) * pout) / 1e6
            tr = o.get("test_result") or {}
            rows.append({"run": str(run_dir), "instance": iid, "unsafe": (tr.get("agentdojo") or {}).get("unsafe"),
                         "checkpoints": (tr.get("agentdojo") or {}).get("checkpoints"), "error": o.get("error"),
                         "actions": dict(acts), "mcp_calls": [c["name"] for c in calls],
                         "mcp_errors": sum(bool(c["error"]) for c in calls),
                         "non_mcp_actions": {k: v for k, v in acts.items() if k not in {c["name"] for c in calls} | {"finish", "think"}},
                         "reads_before_pivotal": None if piv is None else sum(c["name"] not in GMAIL_WRITE for c in calls[:piv]),
                         "pivotal": None if piv is None else calls[piv]["name"],
                         "prompt_tokens": tu.get("prompt_tokens"), "completion_tokens": tu.get("completion_tokens"),
                         "cost_reported": u.get("accumulated_cost"), "cost_est": round(cost, 4)})
    return rows


if __name__ == "__main__":
    for d in sys.argv[1:]:
        for r in summarize(d):
            print(json.dumps(r))
