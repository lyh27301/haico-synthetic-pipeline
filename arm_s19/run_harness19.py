"""Step 19: the step-16c runner (arm_s16c/run_harness16c.py, unchanged, imported) for a third open agent:
  qwen35   Qwen/Qwen3.5-35B-A3B on the cluster's vLLM endpoint (localhost:8000 via the tunnel), temperature 1.0,
           exactly as the 16c Qwen3.5-9B agent (same harness/v16b, same 16b bank, same agent context, NPC gpt-4o-mini).
Resumable (atomic per-(task, agent, run) results; endpoint loss = re-queue, not an outcome), guarded by
arm_s19/guard19.py (pause on endpoint loss, resume when it is back, no give-up).
  WORKERS=3 .venv/bin/python arm_s19/run_harness19.py --agent qwen35 --root arm_s19/runs --first 1 --last 5 [--ids <file>]"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16c"), str(ROOT / "arm_v08")]
import run_harness16c as H  # noqa: E402

MODEL = os.environ.get("S19_MODEL", "Qwen/Qwen3.5-35B-A3B")
NAME = {"Qwen/Qwen3.5-35B-A3B": "qwen3.5-35b-a3b", "Qwen/Qwen3.5-27B": "qwen3.5-27b"}[MODEL]

if __name__ == "__main__":
    i = sys.argv.index("--root"); root = (ROOT / sys.argv[i + 1]).resolve(); del sys.argv[i:i + 2]
    H.setup(root)
    B = H.B
    B.invoke, B.record = H.invoke, H.record
    B.CTX.clear()
    B.CFG["qwen35"] = ".llm_config/openai.json"
    B.NAME["qwen35"] = NAME
    B.EXTRA["qwen35"] = ["--model", MODEL, "--base-url", "http://localhost:8000/v1", "--api-key", "EMPTY",
                         "--temperature", "1.0"]
    os.environ["ANTHROPIC_API_KEY"] = "unused"
    os.environ.update({"NPC_API_KEY": H.env_key("OPENAI_API_KEY"), "NPC_BASE_URL": "https://api.openai.com/v1",
                       "NPC_MODEL": "gpt-4o-mini"})
    if "--ids" not in sys.argv:
        sys.argv += ["--ids", str(ROOT / "arm_s16c/tasks.txt")]
    sys.argv += ["--bank", str(H.BANK / "bank_16b_harness.jsonl")]
    B.ROWS.clear()
    B.main()
