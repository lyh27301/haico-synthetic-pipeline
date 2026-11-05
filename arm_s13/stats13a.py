"""Step 13a numbers for analysis/step13.md, from arm_s13/replay_runs.jsonl and action_labels.jsonl -> arm_s13/step13a.json:
  - label counts;
  - pivotal-step position (absolute step index; fraction = (index + 1) / trajectory length), overall and per
    harm_carrier / toolkit / agent;
  - pivotal tools;
  - pivotal step at the last call vs earlier: the last tool call of any kind, and the last env-touching call
    (executed or rejected; finish / think / terminal come after it);
  - which flag fires first, and runs where flags fire at different steps (multi_step_flags);
  - transient flags (fire, then clear by the end) and the other replay issues.
  .venv/bin/python arm_s13/stats13a.py"""
import collections, json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"


def carriers() -> dict:
    hc = json.loads((ROOT / "arm_s11/harm_carrier.json").read_text())
    out = {t: v["harm_carrier"] for t, v in hc.items()}
    for l in (ROOT / "arm_s12/variants.jsonl").read_text().splitlines():
        v = json.loads(l); out.setdefault(v["variant"], v["carrier"])
    return out


def pos(rs) -> dict:
    if not rs:
        return {"n": 0}
    idx = [r["pivotal_step"] for r in rs]; frac = [(r["pivotal_step"] + 1) / r["n_steps"] for r in rs]
    q = lambda xs: [round(x, 2) for x in statistics.quantiles(xs, n=4)] if len(xs) > 1 else xs
    bins = collections.Counter(min(int(f * 5), 4) for f in frac)
    return {"n": len(rs), "index_median": statistics.median(idx), "index_quartiles": q(idx), "index_max": max(idx),
            "frac_median": round(statistics.median(frac), 2), "frac_quartiles": q(frac),
            "frac_quintiles": {f"{20 * b}-{20 * b + 20}%": bins[b] for b in range(5)},
            "at_last_call": sum(r["pivotal_is_last"] for r in rs),
            "at_last_env_call": sum(r["pivotal_is_last_env"] for r in rs),
            "earlier_than_last_env_call": sum(not r["pivotal_is_last_env"] for r in rs),
            "multi_step_flags": sum(r["multi_step_flags"] for r in rs)}


def main():
    rs = [json.loads(l) for l in (S13 / "replay_runs.jsonl").read_text().splitlines()]
    car = carriers()
    for r in rs:
        r["carrier"] = car[r["task"]]
    lab = collections.Counter(); by_kind = collections.Counter()
    for l in (S13 / "action_labels.jsonl").open():
        o = json.loads(l); lab[o["label"]] += 1; by_kind[(o["kind"], o["label"])] += 1
    u = [r for r in rs if r["replay_unsafe"]]
    out = {"runs": len(rs), "unsafe_runs": len(u), "safe_runs": len(rs) - len(u),
           "runs_by": {k: dict(collections.Counter(r[k] for r in rs)) for k in ("source", "agent")},
           "steps": sum(r["n_steps"] for r in rs), "labels": dict(lab),
           "labels_by_kind": {f"{k}|{l}": n for (k, l), n in sorted(by_kind.items())},
           "verdict_mismatch": sum(r["episode_unsafe"] != r["replay_unsafe"] for r in rs),
           "position": {"all": pos(u)}}
    for dim in ("carrier", "toolkit", "agent", "source"):
        out["position"][dim] = {g: pos([r for r in u if r[dim] == g]) for g in sorted({r[dim] for r in u})}
    out["pivotal_tools"] = {"all": collections.Counter(r["pivotal_tool"] for r in u).most_common()}
    for dim in ("carrier", "toolkit", "agent"):
        out["pivotal_tools"][dim] = {g: collections.Counter(r["pivotal_tool"] for r in u if r[dim] == g).most_common(6)
                                     for g in sorted({r[dim] for r in u})}
    out["pivotal_kind"] = dict(collections.Counter(r["pivotal_kind"] for r in u))
    out["first_flag"] = dict(collections.Counter("+".join(r["first_flag"]) for r in u))
    out["first_flag_by_carrier"] = {c: dict(collections.Counter("+".join(r["first_flag"]) for r in u if r["carrier"] == c))
                                    for c in sorted({r["carrier"] for r in u})}
    out["final_flag_sets"] = dict(collections.Counter("+".join(f for f, v in r["replay_flags"].items() if v) for r in u))
    m = [r for r in u if r["multi_step_flags"]]
    out["multi_step_flags"] = {"n": len(m), "by_agent": dict(collections.Counter(r["agent"] for r in m)),
                               "by_carrier": dict(collections.Counter(r["carrier"] for r in m)),
                               "by_toolkit": dict(collections.Counter(r["toolkit"] for r in m)),
                               "order": dict(collections.Counter(" < ".join(sorted((f for f, s in r["first_step"].items() if s is not None),
                                                                                   key=lambda f: r["first_step"][f])) for r in m)),
                               "gap_median": statistics.median(
                                   max(s for s in r["first_step"].values() if s is not None) -
                                   min(s for s in r["first_step"].values() if s is not None) for r in m) if m else None}
    out["multi_flag_same_step"] = sum(1 for r in u if len(r["first_flag"]) > 1)
    out["transient"] = [{k: r[k] for k in ("task", "agent", "run", "episode_unsafe", "pivotal_step", "first_step", "transient")}
                        for r in rs if r["transient"]]
    out["issues"] = dict(collections.Counter(i for r in rs for i in r["issues"]))
    (S13 / "step13a.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("transient",)}, indent=1)[:9000])


if __name__ == "__main__":
    main()
