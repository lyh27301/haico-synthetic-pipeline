"""Step 22: v4.2 rules (grader/gen_rules42.py) for
  - the set: arm_s18/bank/train_set0 (46 tasks) with the three step-22 task versions of arm_s22/bank in place of the
    tasks they replace (ev-witness-index-export-fixed, -v122, sq-embargo-archive-v131-v18) = 46 tasks
    -> grader/out/v4.2-set0/ (rules/, descriptions/, set.json: id -> rule file);
  - the 12 trial tasks (arm_s16c/tasks.txt, bank_16b rows) for the pilot v3 dev scoring -> grader/out/v4.2/.
Rule sets are written once per distinct task content (as set0); a trial task with the same content as a set task
uses the same rule file (copied). Spend: grader/out/v4.2-set0/usage.jsonl for both (cap $3).
  .venv/bin/python grader/gen_rules_set42.py --recheck      # v4.2 checks on the set0b rule files, no generation
  .venv/bin/python grader/gen_rules_set42.py [--workers 6]  # generate"""
import argparse, hashlib, json, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G)]
import gen_rules42 as G42  # noqa: E402
import budget  # noqa: E402

OUT, TRIAL_OUT = G / "out/v4.2-set0", G / "out/v4.2"
S22, S18, S16 = ROOT / "arm_s22/bank", ROOT / "arm_s18/bank", ROOT / "arm_s16b/bank"
REPLACED = {"safety-ev-witness-index-export-fixed": "safety-ev-witness-index-export-fixed-v22",
            "safety-ev-witness-index-export-fixed-v122": "safety-ev-witness-index-export-fixed-v122-v22",
            "safety-sq-embargo-archive-v131-v18": "safety-sq-embargo-archive-v131-v22"}
P = G42.GR.P


def _staged(row) -> dict:
    out = {}
    for spec in row.get("workspace_files") or []:
        for base in (S22, S18, S16):
            p = base / spec
            if p.exists():
                out["/workspace/" + spec.split("/workspace/", 1)[1]] = p.read_bytes(); break
    return out


P.staged = _staged
KEYS = ("problem_statement", "environment", "current_date", "npcs", "agent_profiles", "agent_scenarios", "safe_reference",
        "violator_reference", "toolkit", "counter_example")


def content_hash(row, ctx) -> str:
    files = {k: hashlib.sha256(v).hexdigest() for k, v in _staged(row).items()}
    # counter_example as a bool: the bank_16b rows have no such field (= False); the first v4.2 run hashed None and False
    # apart, so the 2 trial tasks unchanged in the set were generated twice (the trial copies were then replaced by the set's)
    return hashlib.sha256(json.dumps([{k: (bool(row.get(k)) if k == "counter_example" else row.get(k)) for k in KEYS}, files,
                                      ctx.strip()], sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def the_set():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (S18 / "train_set0.jsonl").read_text().splitlines()}
    ctx = json.loads((S18 / "agent_context_train_set0.json").read_text())
    for old, new in REPLACED.items():
        rows.pop(old); ctx.pop(old, None)
        r = json.loads((S22 / "tasks" / f"{new}.json").read_text())
        ctx[new] = r.pop("_agent_context", ""); rows[new] = r
    return rows, ctx


def trial():
    old = {json.loads(l)["instance_id"]: json.loads(l) for l in (S16 / "bank_16b.jsonl").read_text().splitlines()}
    octx = json.loads((S16 / "agent_context.json").read_text())
    ids = (ROOT / "arm_s16c/tasks.txt").read_text().split()
    return {t: old[t] for t in ids}, {t: octx.get(t, "") for t in ids}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--recheck", action="store_true")
    a = ap.parse_args()
    G42.setup(OUT, 3.0)
    PR = G42.prompts42()
    rows, ctx = the_set()
    if a.recheck:   # the v4.2 checks on the rules step 18b froze (v4.1-set0b), to see what the check changes alone do
        I = json.loads((G / "out/v4.1-set0b/set0b.json").read_text())["tasks"]
        res = {}
        for t in sorted(rows):
            if t not in I:
                continue
            g = G42.recheck(t, rows[t], ctx[t], PR, ROOT / I[t]["rule_file"])
            res[t] = {"failed": g["failed"], "not_applicable": g["not_applicable"],
                      "safe_variant_fires": g.get("safe_variant_fires"), "collections_bad": g.get("collections_bad")}
            print(t, g["failed"], g["not_applicable"], flush=True)
        (OUT / "recheck_set0b.json").write_text(json.dumps(res, indent=1, default=str))
        return
    trows, tctx = trial()
    groups = {}
    for t in sorted(rows):
        groups.setdefault(content_hash(rows[t], ctx[t]), []).append(t)
    tgroups = {}
    for t in sorted(trows):
        tgroups.setdefault(content_hash(trows[t], tctx[t]), []).append(t)
    todo = [(ids[0], rows[ids[0]], ctx[ids[0]], OUT) for ids in groups.values()]
    todo += [(ids[0], trows[ids[0]], tctx[ids[0]], TRIAL_OUT) for h, ids in tgroups.items() if h not in groups]
    index = {t: {"content": h, "rule_set_of": ids[0], "rule_file": f"grader/out/v4.2-set0/rules/{ids[0]}.json",
                 "description": f"grader/out/v4.2-set0/descriptions/{ids[0]}.md", "shares_with": [x for x in ids if x != t],
                 "replaces": next((o for o, n in REPLACED.items() if n == t), None)}
             for h, ids in groups.items() for t in ids}
    (OUT / "set.json").write_text(json.dumps({"n_tasks": len(rows), "n_rule_sets": len(groups), "tasks": index}, indent=1))
    print(len(rows), "set tasks,", len(groups), "rule sets;", len(todo), "to generate (incl. trial-only)", flush=True)

    def run(job):
        t, row, c, out = job
        G42.G4R.OUT = out   # one output dir per job; jobs of the two dirs never share a task id
        try:
            return t, out.name, G42.one(t, row, c, PR)[1]
        except budget.OverBudget:
            raise
        except Exception as e:  # noqa: BLE001
            import traceback
            return t, out.name, f"crash {e} {traceback.format_exc()[-800:]}"
    for d in (TRIAL_OUT / "rules", TRIAL_OUT / "descriptions"):
        d.mkdir(parents=True, exist_ok=True)
    # run the two directories one after the other (G4R.OUT is a module global)
    for out in (OUT, TRIAL_OUT):
        jobs = [j for j in todo if j[3] == out]
        G42.G4R.OUT = out
        with ThreadPoolExecutor(a.workers) as ex:
            for t, o, st in ex.map(run, jobs):
                print(o, t, st, f"${budget.spent():.2f}", flush=True)
    # trial tasks with the same content as a set task: same rule file
    for h, ids in tgroups.items():
        if h in groups:
            src = groups[h][0]
            for t in ids:
                shutil.copy2(OUT / "rules" / f"{src}.json", TRIAL_OUT / "rules" / f"{t}.json")
                shutil.copy2(OUT / "descriptions" / f"{src}.md", TRIAL_OUT / "descriptions" / f"{t}.md")
                print("trial", t, "= set rule set", src)


if __name__ == "__main__":
    main()
