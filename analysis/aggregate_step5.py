"""Step 5 aggregation for the evidence / medical batches (and the step-4 Gmail / SQL numbers they are compared
with): reuses aggregate_step4.agg per arm, adds Petri cost (inspect logs, list prices), literal-gate counts from
the funnel trails, Stage-B run history, and the medical vantage split.

  python analysis/aggregate_step5.py  -> analysis/step5_agg.json (+ markdown tables on stdout)
"""
import glob, json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
from aggregate_step4 import agg, md, PRICE  # noqa: E402

ARMS = {"gmail": "arm_gmail_c", "sqldb": "arm_sqldb_d", "evidence": "arm_evidence_c", "medical": "arm_medical_c"}


def petri_cost(arm: Path) -> float:
    from inspect_ai.log import read_eval_log
    tot = 0.0
    for f in glob.glob(str(arm / "petri*" / "petri_logs" / "*.eval")):
        st = read_eval_log(f, header_only=True).stats
        for m, u in (st.model_usage or {}).items():
            pi, po = PRICE.get(m.split("/")[-1], (0, 0))
            tot += (u.input_tokens * pi + u.output_tokens * po) / 1e6
    return round(tot, 3)


def literal_stats(arm: Path) -> dict:
    """Literal-gate rejections across every Stage-B run kept for the arm. Each funnel file (funnel_<tag>.json =
    the state before a later run, ext_*/funnel.json, funnel.json) lists task rows; rows kept across runs appear in
    several files, so rows are de-duplicated on (idx, instance_id, trail) before counting."""
    seen, rows, per_file = set(), [], {}
    for fp in sorted(arm.glob("funnel*.json")) + sorted(arm.glob("ext_*/funnel.json")):
        f = json.loads(fp.read_text())
        new = 0
        for r in f.get("tasks") or []:
            key = json.dumps([r.get("idx"), r.get("instance_id"), r.get("trail")], default=str)
            if key not in seen:
                seen.add(key); rows.append(r); new += 1
        per_file[str(fp.relative_to(arm))] = new
    trail = [str(t) for r in rows for t in (r.get("trail") or [])]
    return {
        "build_attempts_rows": len(rows), "rows_per_file": per_file,
        "literal_rejections": sum(t.startswith("harm_not_on_literal_path") for t in trail),
        "of_which_blind": sum(t.startswith("harm_not_on_literal_path") and "[independent" in t for t in trail),
        "of_which_writer": sum(t.startswith("harm_not_on_literal_path") and "[writer" in t for t in trail),
        "scenarios_lost_to_literal": sum(1 for r in rows if not r.get("dir") and str(r.get("err", "")).startswith("harm_not_on_literal_path")),
        "fail_stages": dict(Counter(t.split(":")[0].split(" ")[0] for t in trail)),
    }


def main():
    out = {}
    for tk, a in ARMS.items():
        arm = ROOT / a
        if not (arm / "eval" / "manifest.json").exists():
            continue
        o = agg(arm)
        o["petri_cost"] = petri_cost(arm)
        o["literal"] = literal_stats(arm)
        # rollouts of superseded eval runs (archived as eval_v1_*) were spent too
        from aggregate_step4 import cost as _cost
        for old in sorted(arm.glob("eval_v1*")):
            for k, v in _cost(old / "usage.jsonl").items():
                o["cost_usd"][f"superseded_{k}"] = round(o["cost_usd"].get(f"superseded_{k}", 0) + v, 3)
        gen = sum(v for k, v in o["cost_usd"].items() if not k.startswith(("rollout", "superseded_rollout")))
        ev = sum(v for k, v in o["cost_usd"].items() if k.startswith(("rollout", "superseded_rollout")))
        o["cost_total"] = round(gen + ev + o["petri_cost"], 3)
        o["cost_per_task"] = round(o["cost_total"] / o["n_tasks"], 3) if o["n_tasks"] else None
        if tk == "medical":
            man = json.loads((arm / "eval" / "manifest.json").read_text())
            van = {}
            for m in man:
                t = json.loads((Path(m["dir"]) / "scenario.json").read_text())
                van[m["task"]] = t["axes"].get("vantage")
            o["vantage"] = {v: {"tasks": sum(1 for x in van.values() if x == v),
                                "good": sum(o["per_task"][t]["good"] for t, x in van.items() if x == v),
                                "all_safe_both": sum(o["per_task"][t]["all_safe_both"] for t, x in van.items() if x == v)}
                            for v in ("clinic", "patient")}
        out[tk] = o
        md(a, o)
        print("petri", o["petri_cost"], "total", o["cost_total"], "per task", o["cost_per_task"])
        print("literal", json.dumps(o["literal"]))
        if "vantage" in o:
            print("vantage", o["vantage"])
    (ROOT / "analysis" / "step5_agg.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
