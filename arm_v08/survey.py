"""v0.8: preview recipe/workspace_files.role_files on the scope tasks -> arm_v08/survey.json (+ printed table)."""
import collections, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path[:0] = [str(ROOT / "arm_s13"), str(ROOT)]
import step13e as E
from recipe import workspace_files as W


def scenario(t, b):
    d = ROOT / "arm_s12/tasks" / t if (ROOT / "arm_s12/tasks" / t).exists() else Path(b[t]["dir"])
    return json.loads((d / "scenario.json").read_text())


def main():
    xs, rows = E.replay.bank_runs(); b = E.bank()
    O = {o["task"]: (o["toolkit"], o["carrier"]) for o in map(json.loads, open(ROOT / "arm_s13/outcomes.jsonl"))}
    out = {}
    for t in sorted(O):
        tk, carrier = O[t]
        if not W.applies(tk, carrier):
            continue
        g = E.norm_ref(scenario(t, b)["grader"])
        vis, wh = W.role_files(tk, E.yaml_env(rows[t]), g)
        out[t] = {"toolkit": tk, "grader": g.get("kind"), "payload": W.payload(g), "visible": sorted(vis), "withheld": wh,
                  "bytes": sum(len(v) for v in vis.values())}
    (ROOT / "arm_v08/survey.json").write_text(json.dumps(out, indent=1))
    c = collections.Counter(v["toolkit"] for v in out.values())
    print(len(out), dict(c), "visible files", sum(len(v["visible"]) for v in out.values()),
          "withheld", sum(len(v["withheld"]) for v in out.values()),
          "tasks with nothing withheld", sum(not v["withheld"] for v in out.values()))
    for t, v in out.items():
        print(f'{t[7:52]:46} vis {len(v["visible"]):2} | withheld: ' + "; ".join(
            f'{w["dest"].rsplit("/",1)[-1]} ({w["reason"][:40]})' for w in v["withheld"]))


if __name__ == "__main__":
    main()
