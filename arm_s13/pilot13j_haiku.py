"""Step 13j pilot v2: fill the two pairs left open by the role / requester repairs with Haiku 5.5 runs (two tasks per
mechanic kept; no task from the repair batch, removed, unqualified or pending). New files only (blind copy with the
`exposed:` line + labeled copy, rendered as in arm_s13/pilot13h.py); no existing file is touched.
Manifest (arm_s13/pilot_v2_manifest.jsonl):
  - venmo-anonymity-fixed-001-v71 (not annotated): superseded_by the new pair;
  - ev-witness-index-export-fixed-v121 (annotated by the user, old task version): group "off_record" -- the lines
    still count when scoring the rule-based action labels against gold, not as a contrast pair; superseded_by the new
    pair for the contrast-pair role;
  - new lines: part "13j-haiku", replaces, replace_mode "swap_any_haiku" (no Haiku candidate in the old stratum).
  .venv/bin/python arm_s13/pilot13j_haiku.py [--dry]"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path[:0] = [str(S13), str(ROOT / "arm_v08")]
import pilot13h as P  # noqa: E402

FILL = {"safety-ev-witness-index-export-fixed-v121": "safety-sq-export-config-all-contents-v131",
        "safety-fn-venmo-anonymity-fixed-001-v71": "safety-sq-spring2026-roster-v121"}
OFF_RECORD = {"safety-ev-witness-index-export-fixed-v121"}


def main(dry):
    ox = [json.loads(l) for l in (S13 / "outcomes_v2_13h.jsonl").read_text().splitlines()]
    car = {o["task"]: o["carrier"] for o in P.jl(S13 / "outcomes_record.jsonl")}
    _, var = P.pools()
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_v08/bank_v08.jsonl").read_text().splitlines()}
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    xs9 = {}
    for f in (ROOT / "arm_v09/harness/results").glob("*.json"):
        r = json.loads(f.read_text()); xs9[(r["task"], r["agent"], int(r["run"]))] = r
    man = P.jl(P.PILOTS["v2"][2]); new = []
    P.V8 = ROOT / "arm_v09"   # render() reads non-step-13f steps from <V8>/analysis/steps: the v0.9 (Haiku) steps
    for old_t, t in FILL.items():
        hk = [o for o in ox if o["task"] == t and o["agent"] == "haiku5.5" and o["source"] == "v0.9" and o["of_record"]
              and not o["contaminated"] and o["n_steps"] <= P.A.MAX_STEPS]
        un = sorted((o for o in hk if o["unsafe"] is True), key=lambda o: (o["n_steps"], o["run"]))
        hs = [o for o in hk if o["outcome_v2"] == "honest_success" and o["exposed"]]
        assert un and hs, t
        u = un[0]; s = sorted(hs, key=lambda o: (abs(o["n_steps"] - u["n_steps"]), o["run"]))[0]
        olds = [m for m in man if m["task"] == old_t and not m.get("superseded_by")]
        files = []
        for side, r in (("unsafe", u), ("safe", s)):
            r = r | {"carrier": car.get(t), "tags": []}
            m = {"task": t, "agent": r["agent"], "run": r["run"], "part": "13j-haiku", "label_side": side,
                 "outcome": r["outcome"], "outcome_v2": r["outcome_v2"], "exposed": r["exposed"],
                 "exposure_step": r["exposure_step"], "exposure_rule_valid": True, "unsafe": r["unsafe"],
                 "utility": r["utility"], "toolkit": r["toolkit"], "carrier": r["carrier"],
                 "mechanic": var.get(t, t), "n_steps": r["n_steps"], "source": "v0.9", "hard_tags": [],
                 "replaces": next((f"{x['task']}__{x['agent']}__r{x['run']}" for x in olds if x["label_side"] == side), None),
                 "replace_mode": "swap_any_haiku", "pair_same_agent": True}
            if not dry:
                P.render("v2", t, r, side, m, rows, ctx, {}, xs9)
            new.append(m); files.append(f"{t}__{r['agent']}__r{r['run']}")
        for x in olds:
            x["superseded_by"] = files[0] if x["label_side"] == "unsafe" else files[1]
            x.pop("excluded_13j", None)
            if old_t in OFF_RECORD:
                x["group"] = "off_record"
                x["group_note"] = ("old task version (repaired in step 13j); annotated by the user: counts for scoring the "
                                   "rule-based action labels against gold, not as a contrast pair")
        print(old_t, "->", files)
    if not dry:
        P.PILOTS["v2"][2].write_text("".join(json.dumps(m) + "\n" for m in man + new))


if __name__ == "__main__":
    main("--dry" in sys.argv)
