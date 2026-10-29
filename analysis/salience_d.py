"""Step 5 Part D analysis: unsafe rate by cue salience with scenario as a block.
Cue-read is recomputed as a TEXT test on the rich records: a distinctive 40-char snippet of the cue sentence
(arm_salience_d/tasks/*/cue.txt) appears in any tool result before the agent's first state change.
Test: within-scenario permutation of salience labels (scenario = block), statistic = Spearman-style trend
sum over rollouts of unsafe * rank(loud=0, medium=1, quiet=2); also loud-vs-quiet within-block difference.

  python analysis/salience_d.py -> analysis/salience_d.json (printed table)
"""
import json, random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "arm_salience_d"
SAL = ("loud", "medium", "quiet"); RANK = {s: i for i, s in enumerate(SAL)}


def cue_read_text(rich, snippet):
    steps = rich["tool_steps"]
    first = next((i for i, s in enumerate(steps) if s["state_changing"]), None)
    pre = steps if first is None else steps[:first]
    return any(snippet in json.dumps(s["result"], default=str, ensure_ascii=False).lower() for s in pre)


def main():
    variants = {v["task"]: v for v in json.loads((D / "variants.json").read_text())}
    rows = []
    for rf in sorted((D / "eval" / "results").glob("*.json")):
        r = json.loads(rf.read_text()); v = variants[r["task"]]
        cue = (Path(v["dir"]) / "cue.txt").read_text().strip().lower()
        snip = cue.split("\n")[0][:40]
        rich = json.loads((D / "eval" / "rich" / rf.name).read_text())
        rows.append({"scenario": v["scenario"], "salience": v["salience"], "unsafe": int(r["unsafe"]),
                     "cue_read": cue_read_text(rich, snip), "acted": r["acted"]})
    tab = defaultdict(lambda: {s: [] for s in SAL})
    for r in rows:
        tab[r["scenario"]][r["salience"]].append(r)
    per = {}
    for sc, d in tab.items():
        per[sc] = {s: {"unsafe": sum(x["unsafe"] for x in d[s]), "n": len(d[s]),
                       "cue_read": sum(x["cue_read"] for x in d[s])} for s in SAL}
    pooled = {s: {"unsafe": sum(per[c][s]["unsafe"] for c in per), "n": sum(per[c][s]["n"] for c in per),
                  "cue_read": sum(per[c][s]["cue_read"] for c in per)} for s in SAL}
    # unsafe | cue read vs not, by salience
    cond = {s: {"unsafe_given_read": [sum(r["unsafe"] for r in rows if r["salience"] == s and r["cue_read"]),
                                      sum(1 for r in rows if r["salience"] == s and r["cue_read"])],
                "unsafe_given_not_read": [sum(r["unsafe"] for r in rows if r["salience"] == s and not r["cue_read"]),
                                          sum(1 for r in rows if r["salience"] == s and not r["cue_read"])]} for s in SAL}

    def trend(rs):
        return sum(r["unsafe"] * RANK[r["salience"]] for r in rs)

    def lq(rs):
        return sum(r["unsafe"] for r in rs if r["salience"] == "quiet") - sum(r["unsafe"] for r in rs if r["salience"] == "loud")

    obs_t, obs_d = trend(rows), lq(rows)
    random.seed(0); n_perm, ge_t, ge_d = 20000, 0, 0
    blocks = defaultdict(list)
    for r in rows:
        blocks[r["scenario"]].append(r)
    for _ in range(n_perm):
        perm = []
        for rs in blocks.values():
            labs = [r["salience"] for r in rs]; random.shuffle(labs)
            perm += [{"unsafe": r["unsafe"], "salience": l} for r, l in zip(rs, labs)]
        ge_t += trend(perm) >= obs_t; ge_d += abs(lq(perm)) >= abs(obs_d)
    out = {"per_scenario": per, "pooled": pooled, "conditional": cond,
           "test": {"trend_stat": obs_t, "p_trend_one_sided": round(ge_t / n_perm, 4),
                    "quiet_minus_loud_unsafe": obs_d, "p_quiet_vs_loud_two_sided": round(ge_d / n_perm, 4),
                    "n_perm": n_perm}}
    (ROOT / "analysis" / "salience_d.json").write_text(json.dumps(out, indent=1))
    print("scenario | loud | medium | quiet   (unsafe/n, cue-read before act)")
    for sc, d in per.items():
        print(sc, " | ".join(f"{d[s]['unsafe']}/{d[s]['n']} (read {d[s]['cue_read']})" for s in SAL))
    print("pooled", " | ".join(f"{pooled[s]['unsafe']}/{pooled[s]['n']} (read {pooled[s]['cue_read']})" for s in SAL))
    print(json.dumps(cond)); print(json.dumps(out["test"]))


if __name__ == "__main__":
    main()
