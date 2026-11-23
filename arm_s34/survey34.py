"""Step 34 part 1 helper (read-only): the unused base families of arm_v08/bank_v08.jsonl and, per qualified version,
its v0.8 / v0.9 / step-13 run outcomes and the step-13 norm audit's prohibition quotes and locations.
  .venv/bin/python arm_s34/survey34.py   -> arm_s34/survey34.json"""
import collections, glob, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"


def family(t):
    """base family: version (-vNN, -vNNa/b), salience, twin and step suffixes and a trailing numeric id removed"""
    return re.sub(r"-\d+$", "", re.sub(r"(-v\d+[ab]?|-sal-(quiet|medium|loud)|-twin2?)+$", "", t))


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def used_families():
    out = set()
    # in use = run in steps 21-33: the step-18 training set (arm_s18/bank/train_set0.jsonl) and every later bank
    for f in sorted(glob.glob(str(ROOT / "arm_s2*/bank/*.jsonl"))) + [str(ROOT / "arm_s18/bank/train_set0.jsonl")]:
        out |= {family(r["instance_id"]) for r in jl(f)}
    return out


def main():
    rows = [r for r in jl(ROOT / "arm_v08/bank_v08.jsonl")]
    na = {o["task"]: o for o in jl(ROOT / "arm_s13/norm_audit.jsonl")}
    oc = collections.defaultdict(list)
    for f, src in (("arm_v08/analysis/outcomes_v08.jsonl", "v0.8"), ("arm_v09/analysis/outcomes_v09.jsonl", "v0.9"),
                   ("arm_s13/outcomes_v2_13h.jsonl", "13h")):
        for o in jl(ROOT / f):
            if src == "13h" and (o.get("source") in ("v0.8", "v0.9") or o.get("contaminated")):
                continue
            oc[o["task"]].append((src, o["agent"], o["run"], o.get("unsafe"), o.get("utility"), o.get("outcome")))
    used = used_families()
    fams = collections.defaultdict(list)
    for r in rows:
        fams[family(r["instance_id"])].append(r)
    out = {"used": sorted(used), "families": {}}
    for f, rs in sorted(fams.items()):
        if f in used:
            continue
        vs = []
        for r in rs:
            t = r["instance_id"]; o = oc.get(t, []); a = na.get(t, {})
            vs.append({"task": t, "qualified": r.get("qualified"), "removed": r.get("removed"), "npcs": r.get("npcs"),
                       "toolkit": r["toolkit"],
                       "runs": len(o), "unsafe": sum(1 for x in o if x[3] is True),
                       "safe_complete": sum(1 for x in o if x[3] is False and x[4] is True),
                       "agents": sorted({x[1] for x in o}),
                       "source_type": a.get("source_type"), "status": a.get("status"),
                       "places": [(q.get("location"), q.get("quote", "")[:90]) for q in a.get("quotes") or []
                                  if q.get("restricts_graded_action")],
                       "statement": r["problem_statement"].strip()[:300]})
        out["families"][f] = vs
    (S / "survey34.json").write_text(json.dumps(out, indent=1))
    for f, vs in out["families"].items():
        print("==", f)
        for v in vs:
            print(f"  {v['task'][len(f):] or '(base)':28} q={v['qualified']!s:5} npc={v['npcs']} runs={v['runs']:3} "
                  f"uns={v['unsafe']:3} safeC={v['safe_complete']:3} {v['source_type']}/{v['status']} "
                  f"{[p[0] for p in v['places']]}")


if __name__ == "__main__":
    main()
