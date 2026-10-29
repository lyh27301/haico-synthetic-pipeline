"""Run Petri (inspect_petri.audit) on this arm's seeds, OpenAI model roles, save transcripts."""
import json, os, sys
from pathlib import Path
from inspect_ai import eval as inspect_eval
from inspect_ai.model import get_model
from inspect_petri import audit

ROOT = Path(__file__).resolve().parent
TARGET = os.environ.get("AGENT_MODEL", "gpt-5-mini")
AUX = os.environ.get("GEN_MODEL", "gpt-4o-mini")

def main():
    seeds = [s.strip() for s in (ROOT/"seeds.txt").read_text().splitlines() if s.strip()]
    n = int(os.environ.get("PETRI_N", "6"))
    seeds = seeds[:n]
    task = audit(seed_instructions=seeds, max_turns=int(os.environ.get("PETRI_TURNS","15")),
                 target_tools="synthetic", realism_filter=False)
    logs = inspect_eval(
        task,
        model=f"openai/{TARGET}",                 # target under test
        model_roles={
            "target": get_model(f"openai/{TARGET}"),
            "auditor": get_model(f"openai/{AUX}"),
            "judge": get_model(f"openai/{AUX}"),
            "realism": get_model(f"openai/{AUX}"),
        },
        log_dir=str(ROOT/"petri_logs"),
        max_connections=4,
        fail_on_error=False,
    )
    print("PETRI_EVAL_DONE logs:", ROOT/"petri_logs")

if __name__ == "__main__":
    main()
