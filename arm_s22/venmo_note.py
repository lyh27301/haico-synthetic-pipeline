"""Step 22 part A: the text the safe_variant_ok check appends to the safe reference's changed records for fn-venmo,
before (v4 / v4.1 trap_mentions) and after (v4.2), and which rule each one fires.
  .venv/bin/python arm_s22/venmo_note.py   -> arm_s22/venmo_note.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "grader")]
import gen_rules42 as G42  # noqa: E402
import gen_rules_set42 as S  # noqa: E402

G4R = G42.G4R
t = "safety-fn-venmo-anonymity-fixed-001-v71-v18"
rows, ctx = S.the_set()
d = json.loads((ROOT / "grader/out/v4.1-set0b/rules/safety-fn-venmo-anonymity-fixed-001-v71-v131-v18.json").read_text())
R = d["rules"]
task = G42.G41.Task41(t, rows[t], ctx[t], G42.prompts42())
last = task.safe_steps[-1]
out = {}   # the v4.1 trap_mentions is taken from gen_rules4.py's source (G4R.trap_mentions is patched by gen_rules42)
src = (ROOT / "grader/gen_rules4.py").read_text()
ns = {}
exec(compile(src[src.index("def trap_mentions"):src.index("def safe_variant")], "gen_rules4.trap_mentions", "exec"), ns)
for name, fn in (("before (v4.1)", ns["trap_mentions"]), ("after (v4.2)", G42.trap_mentions)):
    G4R.trap_mentions = fn
    ok, fires = G4R.safe_variant(R, task, last)
    out[name] = {"note": " [not included / left out: " + ", ".join(fn(R)) + "]", "fires": fires, "safe_variant_ok": ok}
G4R.trap_mentions = G42.trap_mentions
out["protected"] = R.get("protected"); out["harm_states"] = R.get("harm_states")
(ROOT / "arm_s22/venmo_note.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps({k: v for k, v in out.items() if k.startswith(("before", "after"))}, indent=1, ensure_ascii=False))
