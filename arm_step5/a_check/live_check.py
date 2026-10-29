"""Part A: emit both re-ported exemplars and run 3 live gpt-4o-mini rollouts each (driver per-env runtime)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import driver, run_batch
from recipe import profiles
OUT = Path(__file__).parent
os.environ.setdefault("USAGE_LOG", str(OUT / "usage.jsonl"))
for tk in ("evidence", "medical"):
    prof = profiles.get(tk)
    task = prof.TASK_SCHEMA.model_validate(json.loads(Path(prof.EXEMPLAR_PATH).read_text()))
    d = Path(prof.emit(task, OUT))
    for a in range(1, 4):
        r = driver.run_rollout(task_dir=d, agent_model="gpt-4o-mini", user_model="gpt-4o-mini", out_jsonl=None,
                               agent_kw={"temperature": 1.0}, seed=1000 + a)
        safe, g, err = run_batch.grade(d, r["pre"], r["post"])
        tools = [s["name"] for s in r["rich"]["tool_steps"]]
        extra = {"evidence": lambda: [(t["recipient"], t["recipient_category"]) for t in r["post"]["sent"]],
                 "medical": lambda: {"access_log": [(x["patient_id"], x["authorized"]) for x in r["post"]["access_log"]],
                             "n_search": len(r["post"]["search_log"]),
                             "new_docs": [x["patient_id"] for x in r["post"]["clinical_documents"] if x not in r["pre"]["clinical_documents"]]}}[tk]()
        print(json.dumps({"tk": tk, "a": a, "unsafe": None if safe is None else 1 - safe, "err": err,
                          "n_tools_exposed": len(getattr(prof, "runtime_for_env", lambda e: prof.build_runtime())(prof.load_environment(d / "environment.yaml")).functions),
                          "tools": tools, "state": extra}), flush=True)
