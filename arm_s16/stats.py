"""Step 16a: bank-wide step-label statistics for the report (after base). Writes arm_s16/step_stats.json.
  .venv/bin/python arm_s16/stats.py"""
import collections, json
from pathlib import Path

S16 = Path(__file__).resolve().parent


def pairs(to):
    for x in to or []:
        if isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[1], str):
            yield x
        elif isinstance(x, (list, tuple)):
            for y in x:
                if isinstance(y, (list, tuple)) and len(y) == 2:
                    yield y


def main():
    rs = [json.loads(l) for l in (S16 / "outcomes_v5.jsonl").read_text().splitlines()]
    after = [r for r in rs if r["of_record"] and r["qualified"] and not r["contaminated_old"] and not r["contaminated_h1"]]
    T = collections.Counter(); byfix = collections.Counter(); sub = collections.Counter(); g4r = collections.Counter()
    offc = collections.Counter(); offr = collections.defaultdict(set); border = []; rules = collections.Counter()
    uts = []; off_runs = set(); n = 0
    for r in after:
        p = S16 / "steps" / r["source"] / f"{r['task']}__{r['agent']}__r{r['run']}.json"
        if not p.exists():
            continue
        for s in json.loads(p.read_text()):
            n += 1; old = s.get("label_v2") or "safe"; new = s["label_v5"]
            T[(old, new)] += 1
            if old != new:
                fx = s.get("fixes") or ["N6_repeat_send" if any(f["rule"].startswith(("must_terms", "names_sens"))
                                                                for f in s["findings"]) else "(none)"]
                for f in fx:
                    byfix[(old, new, f)] += 1
            if old == "unsafe" and new == "safe":
                uts.append([r["task"], r["agent"], r["run"], r["source"], s["step"], s.get("old_side_effects"), s["fixes"]])
            if new == "intent":
                sub[s.get("sub_reason")] += 1
                for f in s["findings"]:
                    if f["label"] == "intent":
                        rules[f["rule"]] += 1
            for f in s["findings"]:
                if f["label"] == "unsafe" and f.get("tag") == "leak":
                    for a, why in pairs(f.get("to")):
                        g4r[why] += 1
                if f["label"] == "unsafe" and f.get("tag") == "off_design":
                    k = (r["toolkit"], f["rule"]); offc[k] += 1; offr[k].add((r["task"], r["agent"], r["run"]))
                    off_runs.add((r["task"], r["agent"], r["run"]))
            if s.get("g4_borderline"):
                border.append([r["task"], r["agent"], r["run"], s["step"], s["g4_borderline"].get("rule"),
                               [a for a, _ in s["g4_borderline"].get("to")]])
    causes = collections.Counter(); only = collections.Counter()
    for r in after:
        if r["outcome_v2"] == r["outcome_v5"]:
            continue
        w = set(); ou, nu = bool(r.get("unsafe_v2")), bool(r["unsafe_v5"]); fx = set(r.get("fixes_v5") or [])
        if nu and not ou:
            w |= (fx & {"G3", "G4", "N1", "N2"}) or {"N6_step_level"}
        if ou and not nu:
            w |= (fx & {"G2", "G3"}) or {"other"}
        if r["intent_v5"] and not nu:
            w.add("G2")
        if r.get("utility_v5") != r.get("utility_v4_recomputed"):
            w.add("G1" if r["spec_v5"] in ("G1", "old") else r["spec_v5"])
        w = w or {"exposure_or_other"}
        for x in w:
            causes[x] += 1
        if len(w) == 1:
            only[next(iter(w))] += 1
    res = {"steps": n, "transitions": {f"{a}->{b}": v for (a, b), v in T.items()},
           "byfix": {f"{a}->{b} {c}": v for (a, b, c), v in sorted(byfix.items(), key=lambda x: -x[1])},
           "intent_sub": dict(sub), "intent_rules": dict(rules), "leak_recipient_reasons": dict(g4r),
           "off_design": {f"{a}|{b}": [v, len(offr[(a, b)])] for (a, b), v in sorted(offc.items(), key=lambda x: -x[1])},
           "off_design_runs": len(off_runs), "unsafe_to_safe": uts, "borderline": border,
           "run_causes": dict(causes), "run_only_cause": dict(only),
           "runs_changed": sum(r["outcome_v2"] != r["outcome_v5"] for r in after)}
    (S16 / "step_stats.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("borderline", "unsafe_to_safe")}, indent=0))


if __name__ == "__main__":
    main()
