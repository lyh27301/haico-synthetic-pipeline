"""Step 6 Part D analysis: gate funnel for the variants, rollout classes (gpt-4o-mini x5 only), consistency
within mechanic (source class vs variant class), per-toolkit usable counts, variant axes vs class flips, cost.

Source class for the consistency table is the source's gpt-4o-mini bucket (the only agent run on variants), next
to its overall step-3..5 class (good = mixed under either agent). Variant class = its 4o bucket over the rollouts
present (complete = 5).

  python analysis/variants_step6.py -> analysis/variants_step6.json (+ tables on stdout)
"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "analysis"))
from aggregate_step4 import cost  # noqa: E402

V = ROOT / "arm_variants"


def bucket(us):
    return None if not us else "all_unsafe" if all(us) else "all_safe" if not any(us) else "mixed"


def main():
    src = json.loads((V / "sources.json").read_text())
    recs = [json.loads(x) for x in (V / "variants.jsonl").read_text().splitlines()]
    res = collections.defaultdict(list)
    for f in (V / "eval" / "results").glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("unsafe") != "":
            res[r["task"]].append(int(r["unsafe"]))
    # gate funnel
    fail = collections.Counter()
    for r in recs:
        if r["status"] != "passed":
            e = str(r.get("err", ""))
            # the trail keeps 600 chars, which cuts the [writer]/[independent] tag: literal failures are not split
            fail[e.split(":")[0].split(" ")[0]] += 1
    first_stage = collections.Counter(str(t).split(":")[0].split(" ")[0] for r in recs for t in r.get("trail", []))
    passed = [r for r in recs if r["status"] == "passed"]
    rows = []
    for r in passed:
        us = res.get(r["variant"], [])
        s = src[r["source"]]
        rows.append({"variant": r["variant"], "source": r["source"], "toolkit": r["toolkit"],
                     "source_class": s["class"], "source_4o": s["buckets"].get("4omini"), "source_rate_4o": s["rate_4o"],
                     "n": len(us), "unsafe": sum(us), "variant_class": bucket(us), "complete": len(us) >= 5,
                     "axes": r.get("variant_axes") or [], "summary": r.get("summary", "")})
    complete = [x for x in rows if x["complete"]]
    cls = collections.Counter(x["variant_class"] for x in complete)
    two = collections.Counter((x["source_4o"], x["variant_class"]) for x in complete)
    # per toolkit usable
    per_tk = {}
    for tk in ("gmail", "sqldb", "evidence", "medical"):
        srcs = [t for t, s in src.items() if (Path(s["dir"]) / "toolkit.txt").exists() and
                (Path(s["dir"]) / "toolkit.txt").read_text().strip() == tk or
                (tk == "gmail" and not (Path(s["dir"]) / "toolkit.txt").exists())]
        vs = [x for x in complete if x["toolkit"] == tk]
        per_tk[tk] = {"sources": len(srcs), "variants_tried": sum(1 for r in recs if r.get("toolkit") == tk),
                      "variants_passed": sum(1 for r in passed if r["toolkit"] == tk),
                      "variants_rolled": len(vs),
                      "usable_variants": sum(1 for x in vs if x["variant_class"] in ("mixed", "all_unsafe")),
                      "mixed": sum(1 for x in vs if x["variant_class"] == "mixed")}
    # axes vs flips (flip = variant 4o class != source 4o class)
    ax = collections.defaultdict(lambda: [0, 0])
    for x in complete:
        flip = x["variant_class"] != x["source_4o"]
        for a in x["axes"]:
            ax[a][0] += 1; ax[a][1] += flip
    gen = cost(V / "gen_usage.jsonl"); ev = cost(V / "eval" / "usage.jsonl")
    out = {"candidates": len(recs), "passed": len(passed), "fail_reasons": dict(fail), "trail_stages": dict(first_stage),
           "rolled_complete": len(complete), "rollouts": sum(x["n"] for x in rows), "variant_classes": dict(cls),
           "two_by_two": {f"{a}->{b}": n for (a, b), n in two.items()}, "per_toolkit": per_tk,
           "axes": {a: {"variants": n, "flips": f} for a, (n, f) in ax.items()},
           "cost": {"gen": gen, "eval": ev}, "rows": rows}
    usable = sum(1 for x in complete if x["variant_class"] in ("mixed", "all_unsafe"))
    tot = sum(gen.values()) + sum(ev.values())
    out["cost_total"] = round(tot, 3)
    out["usable"] = usable
    out["cost_per_usable"] = round(tot / usable, 3) if usable else None
    (ROOT / "analysis" / "variants_step6.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    for x in sorted(rows, key=lambda x: x["source"]):
        print(f"{x['source']:45s} {x['source_class']:10s} 4o={x['source_4o']!s:10s} | {x['variant']:50s} {x['unsafe']}/{x['n']} {x['variant_class']} {','.join(x['axes'])}")


if __name__ == "__main__":
    main()
