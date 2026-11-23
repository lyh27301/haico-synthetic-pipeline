"""Step 34 part 4: step 26's checks for each safe twin (arm_s26_twins/check26.py on the v4.2-s34 rules):
  ten checks           failed / not applicable (violator_flagged is n/a on a twin: counter_example)
  violator path        the trap version's violator reference played on the twin with the twin's rules: must be all safe
                       and complete (= the twin's safe_not_flagged / safe_completes)
  trap safe path       the trap version's safe reference played on the twin: completes or not (reported)
  fired traps gone     the trap items the trap version's violator path fires (arm_s34/traps34.json) and the twin's own
                       rule items (side traps left in the twin)
  .venv/bin/python arm_s34/check34.py   -> arm_s34/twins/checks34.json"""
import copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT)]
import gen_rules_s34  # noqa: E402,F401
import gen_rules42 as G42  # noqa: E402
import openai_key  # noqa: E402

OUT = G / "out/v4.2-s34"


def items(d):
    R = d["rules"]
    return {x["id"]: x.get("what") for x in (R.get("protected") or []) + (R.get("harm_states") or [])}


def main():
    openai_key.get("check34")
    G42.setup(OUT, 0.3); PR = G42.prompts42()
    T = json.loads((S / "traps34.json").read_text())
    out = {}
    for f in sorted((S / "twins/tasks").glob("*.json")):
        row = json.loads(f.read_text()); ctx = row.pop("_agent_context"); t = row["instance_id"]; trap = row["twin_of"]
        rf = OUT / "rules" / f"{t}.json"; d = json.loads(rf.read_text())
        g = G42.recheck(t, row, ctx, PR, rf)
        r2 = copy.deepcopy(row); r2["safe_reference"] = row["trap_safe_reference"]
        g2 = G42.recheck(t, r2, ctx, PR, rf)
        out[t] = {"trap": trap, "ten_checks_failed": g["failed"], "not_applicable": g["not_applicable"],
                  "violator_path_flags": g.get("safe_flags") or [], "violator_path_not_flagged": g.get("safe_not_flagged"),
                  "violator_path_completes": g.get("safe_completes"),
                  "trap_safe_path_completes": g2.get("safe_completes"), "trap_safe_path_flags": g2.get("safe_flags") or [],
                  "trap_violator_items": T[trap]["violator_fires"],
                  "trap_items": {x["id"]: x["what"] for x in T[trap]["traps"]}, "twin_items": items(d)}
        o = out[t]
        print(t, "failed", o["ten_checks_failed"], "| vio safe", o["violator_path_not_flagged"], "completes",
              o["violator_path_completes"], "| trap-safe completes", o["trap_safe_path_completes"], flush=True)
    (S / "twins/checks34.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
