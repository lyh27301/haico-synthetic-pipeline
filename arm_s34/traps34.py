"""Step 34: per -v34 task (and twin), the traps of its v4.2-s34 rules (protected items and harm states, with their quotes)
and the trap items its violator path fires under those rules (the violator reference replayed as the 'safe' path of
G42.recheck, as arm_s26_twins/check26.py does). No model call (judge notes from the rule folder's cache).
  .venv/bin/python arm_s34/traps34.py   -> arm_s34/traps34.json"""
import copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT)]
import gen_rules_s34  # noqa: E402,F401  (staged-file lookup in arm_s34 first)
import gen_rules42 as G42  # noqa: E402
import openai_key  # noqa: E402

OUT = G / "out/v4.2-s34"


def main():
    openai_key.get("traps34")
    G42.setup(OUT, 0.3); PR = G42.prompts42()
    res = {}
    for b in ("bank", "twins"):
        for f in sorted((S / b / "tasks").glob("*.json")):
            row = json.loads(f.read_text()); ctx = row.pop("_agent_context"); t = row["instance_id"]
            rf = OUT / "rules" / f"{t}.json"
            if not rf.exists():
                continue
            d = json.loads(rf.read_text()); R = d["rules"]
            traps = [{"id": x["id"], "kind": k, "what": x.get("what"), "quote": x.get("quote"), "collection": x.get("collection")}
                     for k, xs in (("protected", R.get("protected") or []), ("harm_state", R.get("harm_states") or []))
                     for x in xs]
            r2 = copy.deepcopy(row); r2["safe_reference"] = row["violator_reference"]
            g = G42.recheck(t, r2, ctx, PR, rf)
            fired = sorted({str(x[3]) for x in g.get("safe_flags") or [] if x[0] != "final" and isinstance(x[3], str)})
            res[t] = {"traps": traps, "violator_fires": fired, "checks_failed": d["checks"].get("failed"),
                      "not_applicable": d["checks"].get("not_applicable")}
            print(t, "fires", fired, "| traps", [(x["id"], (x["what"] or "")[:60]) for x in traps], flush=True)
    (S / "traps34.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
