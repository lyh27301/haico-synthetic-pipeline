"""Step 13e: re-select the 25-task pilot under the 2x2. Same strata and quotas as step 13b (harm_carrier, toolkit, agent
goodness, now goodness v2; at most one variant per mechanic). Each task gives two trajectories:
  - safe: an honest_success run (safe and the task done), the closest in length to the unsafe one;
  - unsafe: either unsafe kind. UNSAFE_FAILED_TARGET tasks use an unsafe_failed run (attempted but failed is a known
    rule-based blind spot), the others prefer unsafe_success and the hard cases of step 13b.
Same agent for the pair when the task is good for that agent; a cross-agent pair otherwise.

Trajectories already annotated in arm_s13/pilot_blind/ are kept when they still qualify: their tasks are forced into the
selection and their files are not re-rendered. Runs over MAX_STEPS steps are not picked (too long to annotate).

  .venv/bin/python arm_s13/pilot13e.py   ->  arm_s13/pilot_manifest.jsonl (new selection), arm_s13/pilot13e.json
  then .venv/bin/python arm_s13/pilot13c.py (labeled copies) and arm_s13/pilot_blind_full.py (annotation copies)"""
import collections, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(S13))
from pilot13b import CARRIER_Q, TOOLKIT_Q, GOOD_Q, early, hard  # noqa: E402

AG = {"good_4omini": "4omini", "good_qwen": "qwen3.5-9b"}
MAX_STEPS = 60
UNSAFE_FAILED_TARGET = 6


def goodness(g) -> str:
    return "both" if g["good_4omini"] and g["good_qwen"] else "good_4omini_only" if g["good_4omini"] else \
        "good_qwen_only" if g["good_qwen"] else "neither"


def adapt(q, tasks, d) -> dict:
    """The step-13b quota, capped by the distinct mechanics a stratum still has; the shortfall is spread over the strata
    that can take it, in proportion to their quotas (finance and evidence have almost no honest_success run)."""
    sup = {k: len({x["mechanic"] for x in tasks.values() if x[d] == k}) for k in q}
    out = {k: min(v, sup[k]) for k, v in q.items()}
    while sum(out.values()) < sum(q.values()):
        open_ = [k for k in q if sup[k] > out[k]]
        if not open_:
            break
        out[min(open_, key=lambda k: out[k] / q[k])] += 1
    return out


def annotated() -> set:
    out = set()
    for f in (S13 / "pilot_blind").glob("*.md"):
        if re.search(r"^- gold: *\S", f.read_text(), re.M):
            t, a, r = f.stem.split("__")
            out.add((t, a, int(r[1:])))
    return out


def main():
    g2 = json.loads((S13 / "goodness_v2.json").read_text())["tasks"]
    var = {json.loads(l)["variant"]: json.loads(l) for l in (ROOT / "arm_s12/variants.jsonl").read_text().splitlines()}
    old = {(r["task"], r["agent"], r["run"]): r for r in map(json.loads, (S13 / "replay_runs.jsonl").read_text().splitlines())}
    runs = collections.defaultdict(list)
    for o in map(json.loads, (S13 / "outcomes.jsonl").read_text().splitlines()):
        r = old[(o["task"], o["agent"], o["run"])]
        if o["outcome"] and o["n_steps"] <= MAX_STEPS and "verdict_mismatch" not in r["issues"] and "call_alignment" not in r["issues"]:
            runs[o["task"]].append(o | {"old": r})
    tasks = {}
    for t, rs in runs.items():
        good = [AG[f] for f in AG if g2[t][f]]
        pairs = [(a, a) for a in good] or [(a, b) for a in AG.values() for b in AG.values() if a != b]
        ok = [(a, b) for a, b in pairs if any(r["agent"] == a and r["unsafe"] for r in rs)
              and any(r["agent"] == b and r["outcome"] == "honest_success" for r in rs)]
        if not ok:
            continue
        us = [r for r in rs if r["unsafe"] and r["agent"] in {a for a, _ in ok}]
        tasks[t] = {"carrier": rs[0]["carrier"], "toolkit": rs[0]["toolkit"], "good": goodness(g2[t]), "pairs": ok,
                    "mechanic": var[t]["mechanic"] if t in var else t,
                    "hard": max(hard(r["old"]) if r["old"].get("pivotal_step") is not None else 0 for r in us),
                    "can_fail": any(r["outcome"] == "unsafe_failed" for r in us)}
    ann = annotated()
    forced = sorted({t for t, a, k in ann if t in tasks and any(
        r["agent"] == a and r["run"] == k and (r["unsafe"] or r["outcome"] == "honest_success") for r in runs[t])})
    rng = random.Random(13); best = None
    Q = {"carrier": adapt(CARRIER_Q, tasks, "carrier"), "toolkit": adapt(TOOLKIT_Q, tasks, "toolkit"), "good": adapt(GOOD_Q, tasks, "good")}
    for _ in range(3000):
        cnt = {d: collections.Counter() for d in Q}; mech, sel = set(), []
        for t in forced:
            sel.append(t); mech.add(tasks[t]["mechanic"])
            for d in Q:
                cnt[d][tasks[t][d]] += 1
        while len(sel) < 25:
            ok = [t for t in tasks if t not in sel and tasks[t]["mechanic"] not in mech
                  and all(cnt[d][tasks[t][d]] < Q[d][tasks[t][d]] for d in Q)]
            if not ok:
                break
            sup = {d: collections.Counter(tasks[t][d] for t in ok) for d in Q}
            w = lambda t: sum((Q[d][tasks[t][d]] - cnt[d][tasks[t][d]]) / sup[d][tasks[t][d]] for d in Q) * rng.uniform(0.5, 1.5)
            t = max(ok, key=w); x = tasks[t]
            sel.append(t); mech.add(x["mechanic"])
            for d in Q:
                cnt[d][x[d]] += 1
        if len(sel) == 25:
            score = sum(tasks[t]["hard"] for t in sel) + 3 * min(UNSAFE_FAILED_TARGET, sum(tasks[t]["can_fail"] for t in sel))
            if best is None or score > best[0]:
                best = (score, sorted(sel))
    assert best, "no selection meets the quotas"
    sel = best[1]
    fail_left = UNSAFE_FAILED_TARGET
    manifest, kept = [], []
    for i, t in enumerate(sorted(sel, key=lambda t: (t not in forced, not tasks[t]["can_fail"], -tasks[t]["hard"], t))):
        x = tasks[t]; rs = runs[t]; want_early = i % 2 == 0
        cands = [(a, b, r) for a, b in x["pairs"] for r in rs if r["agent"] == a and r["unsafe"]]
        cands = [c for c in cands if any(s["agent"] == c[1] and s["outcome"] == "honest_success" for s in rs)]
        mine = [c for c in cands if (t, c[2]["agent"], c[2]["run"]) in ann]
        if mine:
            a, b, u = mine[0]
        else:
            fails = [c for c in cands if c[2]["outcome"] == "unsafe_failed"]
            if fails and fail_left > 0:
                cands, fail_left = fails, fail_left - 1
            a, b, u = max(cands, key=lambda c: (c[2]["outcome"] == "unsafe_success",
                                                hard(c[2]["old"]) if c[2]["old"].get("pivotal_step") is not None else 0,
                                                c[2]["old"].get("pivotal_step") is not None and early(c[2]["old"]) == want_early,
                                                -c[2]["run"]))
        safes = [r for r in rs if r["agent"] == b and r["outcome"] == "honest_success"]
        s = next((r for r in safes if (t, r["agent"], r["run"]) in ann), None) or \
            min(safes, key=lambda r: (abs(r["n_steps"] - u["n_steps"]), r["run"]))
        for r, side in ((u, "unsafe"), (s, "safe")):
            k = (t, r["agent"], r["run"])
            if k in ann:
                kept.append(k)
            why = f"{r['outcome']}; {r['n_steps']} steps" + ("; kept: annotated before step 13e" if k in ann else "")
            manifest.append({"task": t, "agent": r["agent"], "run": r["run"], "label_side": side, "carrier": x["carrier"],
                             "toolkit": x["toolkit"], "goodness": x["good"], "mechanic": x["mechanic"], "n_steps": r["n_steps"],
                             "pivotal_step": r["old"].get("pivotal_step"), "why": why, "outcome": r["outcome"],
                             "utility": r["utility"], "attempt_wrong_id": r["attempt_wrong_id"],
                             "attempt_wrong_type": r["attempt_wrong_type"], "annotated_kept": k in ann})
    (S13 / "pilot_manifest.jsonl").write_text("".join(json.dumps(m) + "\n" for m in manifest))
    summ = {"quotas": Q, "tasks": len(sel), "trajectories": len(manifest), "eligible_tasks": len(tasks),
            "eligible_by": {d: dict(collections.Counter(tasks[t][d] for t in tasks)) for d in Q},
            "selected_by": {d: dict(collections.Counter(tasks[t][d] for t in sel)) for d in Q},
            "outcomes": dict(collections.Counter(m["outcome"] for m in manifest)),
            "steps": sum(m["n_steps"] for m in manifest),
            "annotated_before": sorted("__".join(map(str, k)) for k in ann),
            "annotated_kept": sorted("__".join(map(str, k)) for k in kept),
            "annotated_not_kept": sorted("__".join(map(str, k)) for k in ann - set(kept))}
    (S13 / "pilot13e.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
