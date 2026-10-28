"""GmailTask -> our 5-file OAS task dir. task.md = problem_statement ONLY."""
from __future__ import annotations
import json, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recipe.gmail_task import GmailTask
from recipe.graders import synthesize_evaluator, _san_email, _san_contact

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "gmail_suite" / "base_environment.yaml"

def emit(task: GmailTask, arm_dir: Path) -> str:
    d = arm_dir / "tasks" / task.instance_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text(task.problem_statement.strip() + "\n")
    npc = task.npc.model_dump() if task.npc else {}
    (d / "scenarios.json").write_text(json.dumps(npc, indent=2))
    (d / "evaluator.py").write_text(synthesize_evaluator(task).strip() + "\n")
    base = yaml.safe_load(BASE.read_text())
    base.setdefault("inbox", []).extend(_san_email(x) for x in task.mailbox.emails if isinstance(x, dict))
    base.setdefault("contacts", []).extend(_san_contact(x) for x in task.mailbox.contacts if isinstance(x, dict))
    (d / "environment.yaml").write_text(yaml.safe_dump(base, sort_keys=False))
    (d / "scenario.json").write_text(task.model_dump_json(indent=2))
    return str(d)
