"""Step 21: the step-16c eval-awareness follow-up (arm_s16c/followup16c.py -> arm_s13/followup13j.py: same question, same
conversation rebuild, same gpt-5-mini classifier) on the step-21 final runs. Qwen3.5-9B is asked on its cluster endpoint
(localhost:8000), Qwen3.5-35B-A3B on its own (localhost:8001); ask each Qwen agent while its serving job is still up.
Never part of a trajectory or of grading. Output arm_s21/followup21.jsonl; classifier spend arm_s21/followup_usage.jsonl.
  harness/.venv-oas/bin/python arm_s21/followup21.py --trees arm_s21/runs [--agents gpt-6-luna,haiku5.5] [--workers 4]"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16c"), str(ROOT / "arm_s13")]
import followup16c as F16  # noqa: E402

F = F16.F
F.OUT = ROOT / "arm_s21/followup21.jsonl"
F.CAPS = {"anthropic": 1.0, "openai": 1.0}


def llm_for(agent):
    from openhands.sdk.llm import LLM
    if agent == "qwen3.5-35b-a3b":
        return LLM(model="openai/Qwen/Qwen3.5-35B-A3B", base_url="http://localhost:8001/v1", api_key="EMPTY",
                   temperature=1.0, usage_id="followup"), "qwen"
    if agent == "qwen3.5-9b":
        return LLM(model="openai/Qwen/Qwen3.5-9B", base_url="http://localhost:8000/v1", api_key="EMPTY",
                   temperature=1.0, usage_id="followup"), "qwen"
    return F16.llm_for(agent)


_cls = F16.classify


def classify(rows):
    os.environ["USAGE_LOG"] = str(ROOT / "arm_s21/followup_usage.jsonl")
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
    F.main()
