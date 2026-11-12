"""v0.9 Sonnet 5.5 task set, chosen once the Haiku 5.5 batch is graded (arm_v09/analysis/outcomes_v09.jsonl).
  - runs of record so far: for the 130 re-rolled tasks (arm_v08/ids_v08.txt) their v0.8 runs; for the other tasks the
    step-13f runs of record (arm_s13/outcomes_record.jsonl), contaminated runs excluded, with the 4 v0.8 slot runs
    replacing their contaminated runs; plus every Haiku 5.5 run. A run counts only if the hidden-state scan is clean
    (record: `contaminated`; v0.8 and Haiku runs: arm_v09/analyze_v09.py hidden(), on their replay steps);
  - unsolved: no natural honest_success on any agent (4o-mini, Qwen3.5-9B, Haiku 5.5) -> Sonnet x 3 runs;
  - control: 15 tasks that do have a natural honest success, spread over toolkits (round-robin over toolkits in a fixed
    shuffled order, seed 20261112) -> Sonnet x 3 runs, as the honest_success baseline.
Writes arm_v09/ids_sonnet.txt and arm_v09/sonnet_set.json.
  .venv/bin/python arm_v09/sonnet_set.py"""
import collections, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V9 = ROOT / "arm_v09"
sys.path[:0] = [str(V9)]
N_CONTROL, SEED = 15, 20261112


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def runs_of_record():
    """4o-mini / Qwen runs of record over the 302 tasks (see the docstring)."""
    import analyze_v09 as Z
    ids = set((ROOT / "arm_v08/ids_v08.txt").read_text().split())
    v8 = [o for o in jl(ROOT / "arm_v08/analysis/outcomes_v08.jsonl") if "crash" not in o and o.get("outcome")]
    for o in v8:   # hidden-state scan on the v0.8 replay steps
        f = ROOT / "arm_v08/analysis/steps" / f"{o['task']}__{o['agent']}__r{o['run']}.json"
        o["contaminated"] = Z.hidden(json.loads(f.read_text()))["contaminated"] if f.exists() else False
    slots = {(o["task"], o["agent"], o["run"]) for o in v8 if o["slot"]}
    rec = [o | {"source": "step13f"} for o in jl(ROOT / "arm_s13/outcomes_record.jsonl")
           if o["task"] not in ids and not o["contaminated"] and (o["task"], o["agent"], o["run"]) not in slots
           and o.get("outcome")]
    return rec + [o | {"source": "v0.8"} for o in v8 if not o["contaminated"]]


def main():
    bank = [json.loads(l) for l in (ROOT / "arm_v08/bank_v08.jsonl").read_text().splitlines()]
    tk = {r["instance_id"]: next(d.split(":")[1] for d in r["dependencies"] if d.startswith("agentdojo:")) for r in bank}
    old = runs_of_record()
    hk = [o for o in jl(V9 / "analysis/outcomes_v09.jsonl") if o["agent"] == "haiku5.5" and "crash" not in o
          and o.get("outcome") and not o["hidden"]["contaminated"]]
    hs = collections.defaultdict(set)
    for o in old + hk:
        if o["outcome"] == "honest_success":
            hs[o["task"]].add(o["agent"])
    unsolved = sorted(t for t in tk if not hs[t])
    solved_before = {t for t in tk if hs[t] - {"haiku5.5"}}
    by = collections.defaultdict(list)
    for t in sorted(t for t in tk if hs[t]):
        by[tk[t]].append(t)
    rng = random.Random(SEED)
    for v in by.values():
        rng.shuffle(v)
    order = sorted(by); rng.shuffle(order); control = []
    while len(control) < N_CONTROL and any(by.values()):
        for g in order:
            if by[g] and len(control) < N_CONTROL:
                control.append(by[g].pop())
    ids = unsolved + sorted(control)
    (V9 / "ids_sonnet.txt").write_text("\n".join(ids) + "\n")
    out = {"unsolved": len(unsolved), "control": len(control), "tasks": len(ids), "runs": 3 * len(ids),
           "unsolved_by_toolkit": dict(collections.Counter(tk[t] for t in unsolved)),
           "control_by_toolkit": dict(collections.Counter(tk[t] for t in control)),
           "solved_by_haiku_only": sorted(t for t in tk if hs[t] == {"haiku5.5"}),
           "unsolved_before_haiku": sum(t not in solved_before for t in tk),
           "runs_of_record": {"4omini_qwen": len(old), "haiku5.5": len(hk)},
           "unsolved_tasks": unsolved, "control_tasks": sorted(control)}
    (V9 / "sonnet_set.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("unsolved_tasks", "control_tasks", "solved_by_haiku_only")}))


if __name__ == "__main__":
    main()
