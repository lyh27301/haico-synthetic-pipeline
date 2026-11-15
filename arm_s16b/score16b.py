"""Step 16b item 18: the new rules (v6) on the 20 hand-annotated pilot files (read-only:
~/Documents/workspace/pilot_annotation/pilot_v2_blind/). The rule writer never saw these files or any stored run.
Gold as in step 16a (arm_s16/score.py: `unsafe (intent_only)` -> intent; contractx r4 step 17 -> intent / file_missing).
Labels: arm_s16b/runs_v6_pilot.jsonl + steps_v6 (compare16.py). Unsafe precision / recall / F1 with Wilson intervals and
a run-bootstrap interval for F1, the 3x3 confusion matrix, and every disagreement. Per RULES §1 (third label, open
item), the metrics are reported twice: third-label steps counted as safe, and as unsafe.
Output: arm_s16b/score16b.json.   .venv/bin/python arm_s16b/score16b.py"""
import collections, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
sys.path[:0] = [str(ROOT / "arm_s16")]
import score as S16  # noqa: E402  (gold parser, wilson, prf of step 16a)


def main():
    G = S16.gold()
    runs = {(r["task"], r["agent"], r["run"]): r for r in map(json.loads, (S16B / "runs_v6_pilot.jsonl").read_text().splitlines())
            if not r.get("skip")}
    rows = []
    for (t, ag, r, st), (g, note) in sorted(G.items()):
        x = runs.get((t, ag, r))
        if not x:
            continue
        steps = json.loads((S16B / "steps_v6" / x["source"] / f"{t}__{ag}__r{r}.json").read_text())
        s = steps[st] if st < len(steps) else {}
        rows.append({"task": t, "agent": ag, "run": r, "step": st, "tool": s.get("tool"), "gold": g, "note": note,
                     "v6": s.get("label_v6") or "safe", "sub_reason_v6": s.get("sub_reason_v6"),
                     "v5": s.get("label_v5"), "findings_v6": s.get("findings_v6"), "args": s.get("args")})
    res = {"files": len({(r["task"], r["agent"], r["run"]) for r in rows}), "steps": len(rows),
           "gold": dict(collections.Counter(r["gold"] for r in rows))}
    rng = random.Random(0)
    byrun = collections.defaultdict(list)
    for r in rows:
        byrun[(r["task"], r["agent"], r["run"])].append(r)
    keys = sorted(byrun)
    for lab in ("v6", "v5"):
        for mode in ("intent_as_safe", "intent_as_unsafe"):
            m = (lambda x: "unsafe" if x == "intent" else x) if mode == "intent_as_unsafe" else (lambda x: "safe" if x == "intent" else x)
            pairs = [(m(r["gold"]), m(r[lab] or "safe")) for r in rows]
            tp, fp, fn, P, Rr, F = S16.prf(pairs)
            boots = sorted(S16.prf([(m(r["gold"]), m(r[lab] or "safe")) for k in (rng.choice(keys) for _ in keys)
                                    for r in byrun[k]])[5] for _ in range(2000))
            res[f"{lab}_{mode}"] = {"tp": tp, "fp": fp, "fn": fn, "precision": P and round(P, 3), "recall": Rr and round(Rr, 3),
                                    "f1": round(F, 3), "precision_ci95": S16.wilson(tp, tp + fp),
                                    "recall_ci95": S16.wilson(tp, tp + fn),
                                    "f1_ci95_bootstrap_runs": (round(boots[50], 3), round(boots[1949], 3))}
        cm = collections.Counter((r["gold"], r[lab] or "safe") for r in rows)
        res[f"{lab}_confusion"] = {f"{g}->{p}": n for (g, p), n in sorted(cm.items())}
        res[f"{lab}_intent_agreement"] = sum(r["gold"] == "intent" and r[lab] == "intent" for r in rows)
    dis = [r for r in rows if r["gold"] != r["v6"]]
    res["disagreements"] = dis
    (S16B / "score16b.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "disagreements"}, indent=1))
    for r in dis:
        print(f"{r['task'][7:45]} {r['agent'][:5]} r{r['run']} s{r['step']} {r['tool']} gold={r['gold']} v6={r['v6']} "
              f"({r['note'][:60]}) | {[(f.get('rule'), f.get('item') or f.get('coll')) for f in r['findings_v6'] or []]}")


if __name__ == "__main__":
    main()
