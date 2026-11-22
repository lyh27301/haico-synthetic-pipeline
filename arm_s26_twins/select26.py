"""Step 26 part 1: which trap version of each family gets a twin.
Current trap versions = the tasks of arm_s29/labels_all.jsonl that are neither superseded nor on the repair list
(step 29's run-level columns). Per mechanic_id the version with the most runs with a usable unsafe step (train_use use)
wins; ties go to the version with more usable unsafe steps, then to the lexicographically first id.
  .venv/bin/python arm_s26_twins/select26.py   -> arm_s26_twins/selected.json"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s26_twins"


def main():
    runs = {}
    for r in map(json.loads, (ROOT / "arm_s29/labels_all.jsonl").read_text().splitlines()):
        k = (r["grades"], r["run_key"])
        x = runs.setdefault(k, {"task": r["task_id"], "mech": r["mechanic_id"], "cur": not (r["superseded_by"] or r["repair_list"]),
                                "unsafe_steps": 0})
        x["unsafe_steps"] += r["label"] == "unsafe" and r["train_use"] == "use"
    per = collections.defaultdict(lambda: {"runs": 0, "unsafe_runs": 0, "unsafe_steps": 0})
    for x in runs.values():
        if x["cur"]:
            c = per[(x["mech"], x["task"])]
            c["runs"] += 1; c["unsafe_runs"] += x["unsafe_steps"] > 0; c["unsafe_steps"] += x["unsafe_steps"]
    fam = collections.defaultdict(list)
    for (m, t), c in per.items():
        fam[m].append({"task": t, **c})
    out = {}
    for m, vs in sorted(fam.items()):
        vs.sort(key=lambda v: (-v["unsafe_runs"], -v["unsafe_steps"], v["task"]))
        out[m] = {"chosen": vs[0]["task"], "versions": vs}
    (S / "selected.json").write_text(json.dumps(out, indent=1))
    for m, v in out.items():
        print(m, "->", v["chosen"], [(x["task"][len(m):], x["unsafe_runs"], x["unsafe_steps"]) for x in v["versions"]])


if __name__ == "__main__":
    main()
