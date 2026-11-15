"""Step 16c item 5: the step-13j eval-awareness follow-up (arm_s13/followup13j.py, unchanged: same question, same
conversation rebuild with tool results over 2,000 characters cut, same gpt-5-mini classifier) on the Part A runs.
Agents: gpt-6-luna (API defaults), Claude Haiku 5.5 (adaptive thinking, display summarized, drop_block for the bound
thinking blocks, as in 13j), Qwen3.5-9B on the cluster endpoint. Runs only after Part A is complete; never part of a
trajectory, of grading or of the blind files.
Output arm_s16c/followup16c.jsonl.   harness/.venv-oas/bin/python arm_s16c/followup16c.py [--workers 4]"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arm_s13"))
import followup13j as F  # noqa: E402

F.OUT = ROOT / "arm_s16c/followup16c.jsonl"
F.CAPS = {"anthropic": 1.0, "openai": 1.0}
F.SPENT.update({"anthropic": 0.0, "openai": 0.0})
_llm = F.llm_for


def llm_for(agent):
    from openhands.sdk.llm import LLM
    if agent == "gpt-6-luna":
        return LLM(model="gpt-6-luna", api_key=F.env_key("OPENAI_API_KEY"), usage_id="followup"), "openai"
    return _llm(agent)


def classify(rows):
    """followup13j.classify with its usage log in arm_s16c (the 13j one writes to arm_v10, an old result)."""
    import json
    sys.path[:0] = [str(ROOT)]
    os.environ["USAGE_LOG"] = str(ROOT / "arm_s16c/followup_usage.jsonl")
    os.environ.setdefault("OPENAI_API_KEY", F.env_key("OPENAI_API_KEY"))
    from recipe import llm
    for r in rows:
        if r.get("aware") is not None or not r.get("answer"):
            continue
        msg, err = llm.chat("gpt-5-mini", [{"role": "system", "content": F.CLS}, {"role": "user", "content": r["answer"][:4000]}],
                            True, reasoning_effort="low")
        try:
            j = json.loads(msg.content) if not err else {}
        except ValueError:
            j = {}
        r["aware"], r["reasons"] = j.get("aware"), j.get("reasons") or []


F.llm_for = llm_for
F.classify = classify

if __name__ == "__main__":
    if "--trees" not in sys.argv:
        sys.argv += ["--trees", "arm_s16c/runs,arm_s16c/qwen"]
    F.main()
