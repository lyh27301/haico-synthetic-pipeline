"""Step 7: every toolkit's exemplar through the full Stage-B gate (0/0/1, B1/B3, extra_check, step-7 gates, literal
writer score + blind literal path as data). python arm_step7/check_exemplars.py"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.setdefault("USAGE_LOG", str(ROOT / "arm_step7" / "a_usage.jsonl"))
from recipe import profiles, pipeline as P, gates  # noqa: E402

for name in profiles.NAMES:
    prof = profiles.get(name); P.PROFILE = prof
    task = prof.TASK_SCHEMA.model_validate_json(Path(prof.EXEMPLAR_PATH).read_text())
    dry = prof.dry_run(task)
    b = P._bfix_check(task, prof)
    g = {n: (f(prof, task) or [None])[0] for n, f in (("hygiene", gates.hygiene_errors), ("discover", gates.discover_errors),
                                                     ("equivalence", gates.equivalence_errors))}
    err, lit, blind = P.literal_check(task, prof, gate=False)
    print(f"{name:9s} {task.instance_id:48s} dry={dry} bfix={b} gates={g} literal_writer={lit} blind={(blind or {}).get('score')} err={err}")
