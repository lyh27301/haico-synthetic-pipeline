"""Step 7 Part A smoke: the Stage-A blind literal check (+ one regen) on step-5 medical gated scenarios, joined with
what the step-5 Stage-B blind check said about each scenario's task (funnel trail). python arm_step7/smoke_stage_a_literal.py"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.setdefault("USAGE_LOG", str(ROOT / "arm_step7" / "a_usage.jsonl"))
from recipe import profiles, pipeline as P  # noqa: E402

P.PROFILE = profiles.get("medical")
arm = ROOT / "arm_medical_c"
gated = [json.loads(x) for x in (arm / "gated_scenarios.jsonl").read_text().splitlines() if x.strip()]
rows = {}
for f in [arm / "funnel.json"] + sorted(arm.glob("ext_*/funnel.json")):
    for r in json.loads(f.read_text()).get("tasks", []):
        rows.setdefault(r["idx"], r)
out = []
for i, sc in enumerate(gated[:12], 1):
    r = P.scenario_literal_check(sc)
    stb = rows.get(i, {})
    blind_b = any("[independent" in str(t) for t in (stb.get("trail") or []))
    out.append({"idx": i, "stage_a_ok": r["ok"], "why": r["why"], "stage_b_blind_rejected": blind_b,
                "stage_b_status": "emitted" if stb.get("dir") else stb.get("status")})
    print(i, "A-ok" if r["ok"] else "A-FAIL", "| B blind-rejected" if blind_b else "| B ok", stb.get("status") or ("emitted" if stb.get("dir") else "?"), "|", r["why"][:110], flush=True)
# regen path on the first failure
fail = next((g for g, o in zip(gated, out) if not o["stage_a_ok"]), None)
if fail:
    funnel = {}
    c = json.loads(json.dumps(fail))
    P._literal_stage_a(c, c["_seed"], funnel)
    print("REGEN TEST:", funnel, "doubtful=", c["_literal_doubtful"], "| new request:", c.get("request", "")[:160])
(ROOT / "arm_step7" / "smoke_stage_a_literal.json").write_text(json.dumps(out, indent=1))
