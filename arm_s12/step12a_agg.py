"""Step 12a aggregation of arm_s12/regrade.jsonl -> arm_s12/step12a.json: per-agent task classes under the v1 grade
(stored, = harm_realized) and the v2 grade (harm_realized or attempted_leak or side_effect), class transitions,
flipped runs by reason / carrier / toolkit, and the Jaccard of the good sets.
Windows as in step 11: Qwen r1-r5; gpt-4o-mini its first 5 graded runs (and all runs); gpt-5-mini all runs; the bank
label (4o-mini U 5-mini, all runs).
  .venv/bin/python arm_s12/step12a_agg.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"


def klass(xs):
    n, u = len(xs), sum(xs)
    return "no_grade" if not n else "good" if 0 < u < n else "all_unsafe" if u else "all_safe"


def main():
    R = [json.loads(l) for l in (S12 / "regrade.jsonl").read_text().splitlines()]
    hc = json.loads((ROOT / "arm_s11/harm_carrier.json").read_text())
    ids = sorted(hc)
    g = [o for o in R if o.get("unsafe") is not None]
    by = collections.defaultdict(list)
    for o in sorted(g, key=lambda o: o["run"]):
        by[(o["task"], o["agent"])].append(o)
    win = {"qwen3.5-9b": lambda t: by[(t, "qwen3.5-9b")],
           "4omini_first5": lambda t: by[(t, "4omini")][:5],
           "4omini_all": lambda t: by[(t, "4omini")],
           "5mini_all": lambda t: by[(t, "5mini")],
           "bank_4o_or_5": None}
    cls = {}
    for w, f in win.items():
        for v in ("v1", "v2"):
            key = "harm_realized" if v == "v1" else "unsafe"
            if f:
                cls[(w, v)] = {t: klass([bool(o[key]) for o in f(t)]) for t in ids}
            else:   # bank label: good if good under either OpenAI agent (all runs)
                a, b = cls[("4omini_all", v)], cls[("5mini_all", v)]
                cls[(w, v)] = {t: "good" if "good" in (a[t], b[t]) else a[t] if a[t] == b[t] or b[t] == "no_grade"
                               else b[t] if a[t] == "no_grade" else "split" for t in ids}
    out = {"classes": {}, "transitions": {}, "flips": {}, "jaccard": {}, "per_carrier": {}, "per_toolkit": {}}
    for w in win:
        out["classes"][w] = {v: dict(collections.Counter(cls[(w, v)].values())) for v in ("v1", "v2")}
        out["transitions"][w] = {f"{a}->{b}": n for (a, b), n in sorted(collections.Counter(
            (cls[(w, "v1")][t], cls[(w, "v2")][t]) for t in ids).items()) if a != b}
    for agent in ("qwen3.5-9b", "4omini", "5mini"):
        rs = [o for o in g if o["agent"] == agent]
        fl = [o for o in rs if o["unsafe"] and not o["harm_realized"]]
        out["flips"][agent] = {
            "graded_runs": len(rs), "unsafe_v1": sum(o["harm_realized"] for o in rs), "unsafe_v2": sum(o["unsafe"] for o in rs),
            "flipped_safe_to_unsafe": len(fl),
            "by_reason": dict(collections.Counter("attempted_leak+side_effect" if o["attempted_leak"] and o["side_effect"]
                                                  else "attempted_leak" if o["attempted_leak"] else "side_effect" for o in fl)),
            "by_leak_rule": dict(collections.Counter(o["leak_rule"] for o in fl if o["attempted_leak"])),
            "by_carrier": dict(collections.Counter(hc[o["task"]]["harm_carrier"] for o in fl)),
            "flags_on_already_unsafe_runs": {"attempted_leak": sum(o["attempted_leak"] for o in rs if o["harm_realized"]),
                                             "side_effect": sum(o["side_effect"] for o in rs if o["harm_realized"])},
            "tasks_with_a_flip": len({o["task"] for o in fl})}
    for a, b in (("4omini_first5", "qwen3.5-9b"), ("4omini_all", "qwen3.5-9b"), ("bank_4o_or_5", "qwen3.5-9b")):
        for v in ("v1", "v2"):
            ga = {t for t in ids if cls[(a, v)][t] == "good"}; gb = {t for t in ids if cls[(b, v)][t] == "good"}
            out["jaccard"][f"{a} vs {b} {v}"] = {"good_a": len(ga), "good_b": len(gb), "both": len(ga & gb),
                                                  "either": len(ga | gb), "jaccard": round(len(ga & gb) / len(ga | gb), 3)}
    for dim, fn in (("per_carrier", lambda t: hc[t]["harm_carrier"]), ("per_toolkit", lambda t: hc[t]["toolkit"])):
        for k in sorted({fn(t) for t in ids}):
            s = [t for t in ids if fn(t) == k]
            out[dim][k] = {"n": len(s), **{f"good_{w}_{v}": sum(cls[(w, v)][t] == "good" for t in s)
                                           for w in ("qwen3.5-9b", "4omini_first5") for v in ("v1", "v2")},
                           **{f"both_good_{v}": sum(cls[("qwen3.5-9b", v)][t] == "good" == cls[("4omini_first5", v)][t]
                                                    for t in s) for v in ("v1", "v2")}}
    out["task_changes"] = {t: {w: [cls[(w, "v1")][t], cls[(w, "v2")][t]] for w in ("qwen3.5-9b", "4omini_first5", "bank_4o_or_5")
                               if cls[(w, "v1")][t] != cls[(w, "v2")][t]} for t in ids}
    out["task_changes"] = {t: v for t, v in out["task_changes"].items() if v}
    out["side_effect_runs"] = [{"task": o["task"], "agent": o["agent"], "run": o["run"], "harm_realized": o["harm_realized"],
                                "effects": o["side_effects"][:4]} for o in g if o["side_effect"]]
    (S12 / "step12a.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("task_changes", "side_effect_runs")}, indent=1))
    print(len(out["task_changes"]), "tasks change class somewhere")


if __name__ == "__main__":
    main()
