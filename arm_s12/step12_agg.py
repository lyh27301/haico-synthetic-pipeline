"""Step 12 final numbers -> arm_s12/step12.json (for analysis/step12.md), after arm_s12/regrade12b.py, agg12b.py and
arm_hf/build_bank_v07.py:
  - the v0.7 bank per toolkit / harm_carrier (v0.6 tasks: arm_s11/harm_carrier.json; new tasks inherit their source
    mechanic's carrier), and per source (v0.6 / 12b batch);
  - per-agent good rates (good_4omini, good_qwen, good_any) on the whole bank, v0.6 part and new part, per toolkit and
    per carrier;
  - agreement at bank scale: Jaccard of the good_4omini and good_qwen sets, and class agreement;
  - 12b generation yield (candidates -> gated rows -> members) per batch;
  - capped mechanics: runs killed for a cap (cost / token / hang) or ended by the SDK stuck detector, per mechanic and
    agent; a mechanic with such runs on BOTH agents is flagged as a task problem;
  - cost per 100 new tasks: OpenAI $ (arm_s12/budget_guard.spend) and GPU-hours (GPU_HOURS env / --gpu-hours: the vLLM
    jobs' allocated GPU time while 12b Qwen runners were active; computed from sacct outside the repo).
  .venv/bin/python arm_s12/step12_agg.py --gpu-hours <h>"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"; sys.path.insert(0, str(S12))
from budget_guard import spend  # noqa: E402


def jac(a: set, b: set) -> dict:
    return {"a": len(a), "b": len(b), "both": len(a & b), "either": len(a | b),
            "jaccard": round(len(a & b) / len(a | b), 3) if a | b else None}


def rates(ts, man):
    n = len(ts)
    return {"n": n, **{f: round(sum(man[t][f] for t in ts) / n, 3) if n else None
                       for f in ("good_4omini", "good_qwen", "good_any")}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--gpu-hours", type=float); a = ap.parse_args()
    import pyarrow.parquet as pq
    rows = pq.read_table(ROOT / "arm_hf/out_v07/data/train-00000-of-00001.parquet").to_pylist()
    man = {r["instance_id"]: r for r in rows}
    mf = json.loads((ROOT / "arm_hf/out_v07/manifest.json").read_text())["tasks"]
    hc = json.loads((ROOT / "arm_s11/harm_carrier.json").read_text())
    var = {json.loads(l)["variant"]: json.loads(l) for l in (S12 / "variants.jsonl").read_text().splitlines()}
    agg = json.loads((S12 / "agg12b.json").read_text())
    carrier = {t: (hc[t]["harm_carrier"] if t in hc else var[t]["carrier"]) for t in man}
    mech = {t: (var[t]["mechanic"] if t in var else t) for t in man}
    src = {t: ("v0.6" if mf[t]["source"] == "v0.6" else f"12b_b{agg['tasks'][t]['batch']}") for t in man}
    out = {"n": len(man)}
    for dim, key in (("toolkit", lambda t: man[t]["toolkit"]), ("harm_carrier", lambda t: carrier[t]),
                     ("source", lambda t: src[t])):
        groups = collections.defaultdict(list)
        for t in man:
            groups[key(t)].append(t)
        out[f"by_{dim}"] = {g: rates(ts, man) for g, ts in sorted(groups.items())}
    out["rates"] = {"all": rates(list(man), man), "v0.6": rates([t for t in man if src[t] == "v0.6"], man),
                    "new": rates([t for t in man if src[t] != "v0.6"], man)}
    out["toolkit_x_carrier"] = {tk: dict(collections.Counter(carrier[t] for t in man if man[t]["toolkit"] == tk))
                                for tk in sorted({r["toolkit"] for r in rows})}
    g4 = {t for t in man if man[t]["good_4omini"]}; gq = {t for t in man if man[t]["good_qwen"]}
    new = {t for t in man if src[t] != "v0.6"}
    out["jaccard"] = {"bank": jac(g4, gq), "v0.6": jac(g4 - new, gq - new), "new": jac(g4 & new, gq & new)}
    cls = {t: (mf[t]["4omini"], mf[t]["qwen"]) for t in man}
    out["class_pairs"] = {f"{x}|{y}": n for (x, y), n in collections.Counter(cls.values()).most_common()}
    # generation yield per batch
    b = collections.defaultdict(collections.Counter)
    for v in var.values():
        b[v["batch"]][v["status"]] += 1
    for t, x in agg["tasks"].items():
        b[x["batch"]]["evaluated"] += x["evaluated"]; b[x["batch"]]["member"] += x["member"]
        b[x["batch"]]["good_any"] += x["good_any"]
    out["yield"] = {str(k): dict(v) for k, v in sorted(b.items())}
    # capped / stuck runs per mechanic and agent
    capped = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for f in (S12 / "harness/results").glob("*.json"):
        r = json.loads(f.read_text())
        kind = r.get("capped") or ("stuck" if r.get("stuck") else "hang_rerun_error" if r.get("error") and not r.get("graded")
                                   and not r.get("endpoint_lost") else None)
        if kind:
            capped[var.get(r["task"], {}).get("mechanic", r["task"])][r["agent"]][kind] += 1
    out["capped_by_mechanic"] = {m: {ag: dict(c) for ag, c in d.items()} for m, d in sorted(capped.items())}
    out["capped_both_agents"] = sorted(m for m, d in capped.items() if len(d) >= 2)
    # cost
    s = spend(); n_new = len(agg["tasks"]); n_mem = agg["new_members"]
    gh = a.gpu_hours
    out["cost"] = {"openai_usd": s, "new_rows_evaluated": n_new, "new_members": n_mem, "gpu_hours": gh,
                   "per_100_new_evaluated": {"openai_usd": round(100 * s["total"] / n_new, 2) if n_new else None,
                                             "gpu_hours": round(100 * gh / n_new, 2) if gh and n_new else None},
                   "per_100_new_members": {"openai_usd": round(100 * s["total"] / n_mem, 2) if n_mem else None,
                                           "gpu_hours": round(100 * gh / n_mem, 2) if gh and n_mem else None}}
    (S12 / "step12.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("capped_by_mechanic",)}, indent=1)[:6000])


if __name__ == "__main__":
    main()
