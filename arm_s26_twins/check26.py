"""Step 26 part 3: checks for each twin (and the ten checks of the two -v26 repairs).

For a twin (rules grader/out/v4.2-s26, v4.2 pipeline unchanged; the twin's safe_reference IS the trap version's violator path):
  ten checks           failed / not applicable (violator_flagged is n/a on a twin: counter_example)
  violator path        the trap version's violator reference played on the twin with the twin's rules: labels of its steps
                       (must be all safe) and completion (must pass) = the checks safe_not_flagged / safe_completes
  trap safe path       the trap version's safe reference played on the twin (G42.recheck with that reference as the safe one):
                       completes or not, flagged or not (reported; it may not complete when it left the item out on purpose)
  fired traps gone     the trap version's violator path is flagged by its own rules (trap_violator_labels) and is all safe under
                       the twin's rules (violator_path_labels); the protected items / harm states left in the twin's rules are
                       listed (side traps: other items of the same environment, not on the violator path)
The ten checks re-run here with G42.recheck on the kept rule attempt (no regeneration, no model call for rules; judge notes
come from the rule folder's cache).
  .venv/bin/python arm_s26_twins/check26.py   -> arm_s26_twins/checks26.json"""
import copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s26_twins"; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT), str(ROOT / "arm_s30")]
import s29  # noqa: E402
s29.patch()
import grade23 as G23  # noqa: E402
import gen_rules42 as G42  # noqa: E402
import gen_rules_s26  # noqa: E402,F401  (its staged-file lookup: arm_s26_twins/bank first, as when the rules were made)
import openai_key  # noqa: E402

OUT = G / "out/v4.2-s26"


def rules(f):
    d = json.loads(Path(f).read_text())
    return d


def trap_ids(d):
    R = d["rules"]
    return {x["id"]: x["what"] for x in (R.get("protected") or []) + (R.get("harm_states") or [])}


def violator_items(trap, idx, ctxs):
    """The trap items the trap version's violator path fires under the trap version's own rules (the violator reference
    replayed as the 'safe' path of G42.recheck: its safe_flags are the findings, (step, rule, coll, item))."""
    row = copy.deepcopy(G23.rows()[trap]); row["safe_reference"] = row["violator_reference"]
    g = G42.recheck(trap, row, ctxs[trap], PR, ROOT / idx[trap]["rule_file"])
    return sorted({str(f[3]) for f in g.get("safe_flags") or [] if f[0] != "final" and isinstance(f[3], str)})


PR = None
PETRI_A = ["safety-ev-petri-attorney-archive-v29a", "safety-ev-petri-attorney-archive-v123-v29a",
           "safety-ev-petri-attorney-archive-v132-v29a"]


def main():
    global PR
    openai_key.get("check26")
    G42.setup(OUT, 0.3)
    PR = G42.prompts42()
    idx = G23.rule_index(); ctxs = s29.contexts()
    out = {}
    for f in sorted((S / "bank/tasks").glob("*.json")):
        row = json.loads(f.read_text()); ctx = row.pop("_agent_context"); t = row["instance_id"]
        rf = OUT / "rules" / f"{t}.json"
        d = rules(rf); g = G42.recheck(t, row, ctx, PR, rf)
        res = {"ten_checks_failed": g["failed"], "not_applicable": g["not_applicable"], "passed": g["passed"]}
        if row.get("twin_of"):
            trap = row["twin_of"]
            td = rules(ROOT / idx[trap]["rule_file"])
            tc = td["checks"]
            res |= {"violator_path_labels": g.get("safe_flags") or [], "violator_path_not_flagged": g.get("safe_not_flagged"),
                    "violator_path_completes": g.get("safe_completes"), "violator_path_completion": g.get("safe_completion")}
            r2 = copy.deepcopy(row); r2["safe_reference"] = row["trap_safe_reference"]
            g2 = G42.recheck(t, r2, ctx, PR, rf)
            res |= {"trap_safe_path_completes": g2.get("safe_completes"), "trap_safe_path_completion": g2.get("safe_completion"),
                    "trap_safe_path_flags": g2.get("safe_flags") or []}
            res |= {"trap_rules": trap_ids(td), "trap_violator_labels": tc.get("violator_labels"),
                    "trap_violator_items": violator_items(trap, idx, ctxs), "twin_rules": trap_ids(d)}
        else:
            res |= {"violator_flagged": g.get("violator_flagged"), "safe_completes": g.get("safe_completes"),
                    "safe_not_flagged": g.get("safe_not_flagged")}
        out[t] = res
        print(t, {k: v for k, v in res.items() if k not in ("trap_rules", "twin_rules", "violator_path_completion",
                                                             "trap_safe_path_completion")}, flush=True)
    out["_existing_twins_trap_items"] = {a: violator_items(a, idx, ctxs) for a in PETRI_A}   # the a versions of the ev-petri b twins
    print(out["_existing_twins_trap_items"])
    (S / "checks26.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
