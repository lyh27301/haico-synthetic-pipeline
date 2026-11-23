"""Step 34: replay both references of every -v34 row (arm_s34/bank/tasks) on the real toolkit (step 22's validate: no tool
error allowed) and list the state changes each makes, plus step 18's synthetic() check.  -> arm_s34/validate34.json"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"
sys.path[:0] = [str(ROOT / "arm_s22"), str(ROOT / "arm_s18"), str(ROOT)]
import make_tasks as M22  # noqa: E402
import lib as L  # noqa: E402
M22.OUT = S / "bank"
out = {}
for f in sorted((S / "bank/tasks").glob("*.json")):
    r = json.loads(f.read_text())
    if len(sys.argv) > 1 and not any(a in r["instance_id"] for a in sys.argv[1:]):
        continue
    v = M22.validate(r)
    v["synthetic"] = L.synthetic(r)
    out[r["instance_id"]] = v
    print(r["instance_id"], {k: (x["steps"], x["errors"], x["changes"][:6]) for k, x in v.items() if k != "synthetic"},
          flush=True)
if len(sys.argv) == 1:
    (S / "validate34.json").write_text(json.dumps(out, indent=1))
