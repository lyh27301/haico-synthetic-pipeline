"""Step 26: replay the references of every new row in arm_s26_twins/bank/tasks on the real toolkit (step 22's validate: no tool
error allowed); for twins also the trap version's safe reference (trap_safe_reference).  -> arm_s26_twins/validate26.json"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s26_twins"
sys.path[:0] = [str(ROOT / "arm_s22"), str(ROOT / "arm_s18"), str(ROOT)]
import make_tasks as M22  # noqa: E402
M22.OUT = S / "bank"
out = {}
for f in sorted((S / "bank/tasks").glob("*.json")):
    r = json.loads(f.read_text())
    v = M22.validate(r)
    if r.get("trap_safe_reference") is not None:
        v["trap_safe_reference"] = M22.validate(dict(r, safe_reference=r["trap_safe_reference"], violator_reference=[]))["safe_reference"]
    out[r["instance_id"]] = v
    print(r["instance_id"], {k: (x["steps"], x["errors"]) for k, x in v.items()}, flush=True)
(S / "validate26.json").write_text(json.dumps(out, indent=1))
