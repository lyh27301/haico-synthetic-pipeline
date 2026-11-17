"""Step 19: the step-16c eval-awareness follow-up (arm_s16c/followup16c.py -> arm_s13/followup13j.py: same question,
same conversation rebuild, same gpt-5-mini classifier) on the step-19 runs of Qwen3.5-35B-A3B, asked on the cluster
endpoint. Output arm_s19/followup19.jsonl; classifier spend arm_s19/followup_usage.jsonl (counts toward step 19's $2).
  harness/.venv-oas/bin/python arm_s19/followup19.py [--workers 4]"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16c"), str(ROOT / "arm_s13")]
import followup16c as F16  # noqa: E402  (sets up followup13j as F16.F)

F = F16.F
F.OUT = ROOT / "arm_s19/followup19.jsonl"
MODEL = os.environ.get("S19_MODEL", "Qwen/Qwen3.5-35B-A3B")


def llm_for(agent):
    from openhands.sdk.llm import LLM
    if agent.startswith("qwen3.5-35b") or agent.startswith("qwen3.5-27b"):
        return LLM(model=f"openai/{MODEL}", base_url=os.environ.get("QWEN_BASE_URL", "http://localhost:8000/v1"),
                   api_key="EMPTY", temperature=1.0, usage_id="followup"), "qwen"
    return F16.llm_for(agent)


def classify(rows):
    os.environ["USAGE_LOG"] = str(ROOT / "arm_s19/followup_usage.jsonl")
    sys.path[:0] = [str(ROOT)]
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
        sys.argv += ["--trees", "arm_s19/runs"]
    F.main()
