"""Step 16c follow-up: add one blind file to pilot v3 on request, without touching the 24 already there.
One of the Qwen runs r1, r4, r5 of safety-md-maria-lopez-med-update-v2 is drawn at random (random.SystemRandom, no seed;
the draw is recorded in the manifest row), rendered with blind16c.render (the same format as the other files) into
~/Documents/workspace/pilot_annotation/pilot_v3_blind/, and appended to arm_s16c/pilot_v3_manifest.jsonl.
Refuses to run if a file for any of the three runs exists already, and checks that the other files are unchanged.
  .venv/bin/python arm_s16c/add_blind16c.py"""
import hashlib, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; C = ROOT / "arm_s16c"
sys.path[:0] = [str(C)]
import blind16c as B  # noqa: E402
import runs16c  # noqa: E402

TASK = "safety-md-maria-lopez-med-update-v2"
CANDIDATES = [f"{TASK}__qwen3.5-9b__r{r}" for r in (1, 4, 5)]
SELECTION = "added on request: a Qwen run the rule sets grade as a safe completion"


def main():
    if any((B.DEST / f"{k}.md").exists() for k in CANDIDATES):
        sys.exit("a file for one of the candidate runs exists already; nothing written")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in B.DEST.iterdir() if p.is_file()}
    key = random.SystemRandom().choice(CANDIDATES)
    g = {s: {x["key"]: x for x in map(json.loads, (C / "grades" / f"{s}.jsonl").read_text().splitlines())}
         for s in ("16a", "v6", "v7-luna", "v7-sol", "v8-luna", "v8-sol")}
    x16, x6 = g["16a"][key], g["v6"][key]
    r = {x["key"]: x for x in runs16c.results()}[key]
    L = runs16c.load(r)
    f = B.DEST / f"{key}.md"
    n = B.render(f, L["row"] | {"toolkit": "medical"}, json.loads((ROOT / "arm_s16b/bank/agent_context.json").read_text()).get(TASK, ""),
                 r, L["history"])
    assert n == len(x16["labels"]), (n, len(x16["labels"]))
    m = {"file": f.name, "task": TASK, "agent": x16["agent"], "run": x16["run"], "picked_as": "added",
         "selection": SELECTION, "outcome_16a": x16["outcome"], "outcome_v6": x6["outcome"], "labels_16a": x16["labels"],
         "labels_v6": x6["labels"], "exposed_rule": x16.get("exposed"), "tools": x16.get("tools"), "tool_steps": n,
         "outcomes_v7_v8": {s: g[s][key]["outcome"] for s in ("v7-luna", "v7-sol", "v8-luna", "v8-sol")},
         "draw": {"from": CANDIDATES, "picked": key, "method": "random.SystemRandom().choice"}}
    with open(B.MAN, "a") as fh:
        fh.write(json.dumps(m) + "\n")
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in B.DEST.iterdir() if p.is_file() and p.name != f.name}
    assert after == before, "an existing file changed"
    print("picked", key, "steps", n, "outcomes", m["outcome_16a"], m["outcome_v6"], m["outcomes_v7_v8"])


if __name__ == "__main__":
    main()
