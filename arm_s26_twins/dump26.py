"""Helper (read only): print the chosen trap version's request, traps, prohibition places and violator reference."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "grader"), str(ROOT / "arm_s30")]
import s29  # noqa
s29.patch()
import grade23 as G23  # noqa
rows = G23.rows(); loc = s29.loc()
sel = json.loads((ROOT / "arm_s26_twins/selected.json").read_text())
for m, v in sel.items():
    if sys.argv[1:] and not any(a in m for a in sys.argv[1:]):
        continue
    t = v["chosen"]; r = rows[t]; L = loc.get(t) or {}
    print("=" * 30, t, "| inherited", L.get("inherited_from"))
    print("REQUEST:", r["problem_statement"][-700:])
    for tr in L.get("traps") or []:
        print(" TRAP", tr["trap"], tr["kind"], "|", tr["what"][:200])
        for p in tr.get("places") or []:
            print("    place", p.get("label"), p.get("kind"), p.get("where"), p.get("field"), "|", (p.get("fragment") or "")[:160])
    print(" VIOLATOR:", json.dumps([(s["tool"], s["args"]) for s in r.get("violator_reference") or []])[:900])
    print(" files:", r.get("workspace_files"))
