"""Step 20 Part B: grader rules for the first training set ("set0"), with the v4.1 prompts and checks unchanged
(grader/gen_rules41.py on grader/gen_rules4.py; step 1 prompt v4, step 2 prompts v4.1, ten checks).

The set: the 30 step-18 rows of arm_s18/bank/tasks plus every row of arm_s16b/bank/bank_16b.jsonl that has no step-18
version (26), = 56 tasks. Rules are written once per distinct task content (problem statement, environment, date, NPC
fields, references, toolkit, agent role text, bytes of every staged file); ids with the same content share one rule set.
Tasks whose content is unchanged since v4 / v4.1 (the bank_16b rows among the 12 trial tasks) keep their frozen
grader/out/v4.1 rule file and description byte for byte.

Procedure per new rule set = v4's (gen_rules4.one): step 1, step 2 safety and completion, checks, up to 3 attempts per
step 2 side, one step 1 regeneration when a step-1 cause still fails (v4.1 had switched this off only because it
reused v4's descriptions for its two tasks), keep the attempt with the fewest unexpected failures. The EXPECTED
failures of v4 are keyed by the old trial ids and apply to none of the set's new rows; nothing was added to them.
Output: grader/out/v4.1-set0/ (rules/, descriptions/, set0.json = id -> rule file, usage.jsonl; cap $5).
  .venv/bin/python grader/gen_rules_set0.py [--workers 6] [--only id,id]"""
import argparse, glob, hashlib, json, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G)]
import gen_rules41 as G41  # noqa: E402  (patches gen_rules4 / gen_rules for v4.1)
import budget  # noqa: E402

G4R, GR, P = G41.G4R, G41.GR, G41.GR.P
V = "v4.1-set0"
OUT = G / "out" / V
S16B, S18 = ROOT / "arm_s16b/bank", ROOT / "arm_s18/bank"
G4R.V, G4R.OUT = V, OUT
G4R.STEP1_CAUSES = ("safe_completes", "violator_completes", "violator_flagged", "safe_not_flagged")   # v4's procedure
budget.USAGE = OUT / "usage.jsonl"; budget.CAP = 5.0
OUT.mkdir(parents=True, exist_ok=True)
G4R.judge_note4.CACHE = OUT / "judge_note_cache.jsonl"; G4R.judge_note4._cache = None   # never append to v4.1's cache
if not G4R.judge_note4.CACHE.exists():
    shutil.copy(G / "out/v4.1/judge_note_cache.jsonl", G4R.judge_note4.CACHE)


def _staged(row) -> dict:   # a row's staged files live in the bank it comes from (arm_s18 for the step-18 rows)
    out = {}
    for spec in row.get("workspace_files") or []:
        for base in (S18, S16B):
            p = base / spec
            if p.exists():
                out["/workspace/" + spec.split("/workspace/", 1)[1]] = p.read_bytes(); break
    return out


P.staged = _staged
KEYS = ("problem_statement", "environment", "current_date", "npcs", "agent_profiles", "agent_scenarios", "safe_reference",
        "violator_reference", "toolkit")


def the_set():
    old = {json.loads(l)["instance_id"]: json.loads(l) for l in (S16B / "bank_16b.jsonl").read_text().splitlines()}
    octx = json.loads((S16B / "agent_context.json").read_text())
    new = {}
    for f in sorted((S18 / "tasks").glob("*.json")):
        r = json.loads(f.read_text()); new[r["instance_id"]] = r
    replaced = {r["derived_from"] for r in new.values()}
    rows, ctx, src = {}, {}, {}
    for t, r in old.items():
        if t not in replaced:
            rows[t], ctx[t], src[t] = r, octx.get(t, ""), "bank_16b"
    for t, r in new.items():
        ctx[t] = r.pop("_agent_context", ""); rows[t], src[t] = r, "arm_s18"
    return rows, ctx, src


def content_hash(row, ctx) -> str:
    files = {k: hashlib.sha256(v).hexdigest() for k, v in _staged(row).items()}
    return hashlib.sha256(json.dumps([{k: row.get(k) for k in KEYS}, files, ctx.strip()], sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--only")
    ap.add_argument("--index-only", action="store_true")
    a = ap.parse_args()
    (OUT / "rules").mkdir(parents=True, exist_ok=True); (OUT / "descriptions").mkdir(parents=True, exist_ok=True)
    rows, ctx, src = the_set()
    groups = {}
    for t in sorted(rows):
        groups.setdefault(content_hash(rows[t], ctx[t]), []).append(t)
    frozen = {f.stem for f in (G / "out/v4.1/rules").glob("*.json")}
    v41_hash = {}
    old_rows, old_ctx = GR.bank()
    for t in frozen:
        v41_hash[t] = content_hash(old_rows[t], old_ctx[t])
    index, todo = {}, []
    for h, ids in groups.items():
        rep = ids[0]
        keep = [t for t in ids if t in frozen and v41_hash[t] == h]
        if keep:
            rep = keep[0]
            for f, d in ((G / "out/v4.1/rules" / f"{rep}.json", OUT / "rules" / f"{rep}.json"),
                         (G / "out/v4.1/descriptions" / f"{rep}.md", OUT / "descriptions" / f"{rep}.md")):
                if not d.exists():
                    shutil.copy2(f, d)
            how = "frozen v4.1 rule file, copied byte for byte (content unchanged since v4.1)"
        else:
            how = "generated in step 20 (v4.1 prompts and checks)"
            todo.append(rep)
        for t in ids:
            index[t] = {"source_bank": src[t], "content": h, "rule_file": f"grader/out/{V}/rules/{rep}.json",
                        "description": f"grader/out/{V}/descriptions/{rep}.md", "rule_set_of": rep,
                        "shares_with": [x for x in ids if x != t], "rules": how}
    (OUT / "set0.json").write_text(json.dumps({"n_tasks": len(rows), "n_rule_sets": len(groups), "tasks": index}, indent=1))
    print(len(rows), "tasks,", len(groups), "distinct contents,", len(todo), "to generate")
    if a.index_only:
        return
    if a.only:
        todo = [t for t in todo if t in a.only.split(",")]
    PR = G41.prompts41()

    def run(t):
        try:
            r = G4R.one(t, rows[t], ctx[t], PR)
        except budget.OverBudget:
            raise
        except Exception as e:  # noqa: BLE001
            import traceback
            return t, f"crash {e} {traceback.format_exc()[-600:]}"
        f = OUT / "rules" / f"{t}.json"
        d = json.loads(f.read_text())
        d["meta"] |= {"prompt_version": "v4.1", "set": V,
                      "prompt_files": ["grader/prompts/step1_task_description_v4.md", "grader/prompts/step1_user_v4.md"] +
                      [f"grader/prompts/{k}_v4.1.md" for k in ("step2_safety", "step2_completion", "step2_user_safety",
                                                              "step2_user_completion", "feedback")]}
        f.write_text(json.dumps(d, indent=1, default=str))
        return r
    with ThreadPoolExecutor(a.workers) as ex:
        for t, st in ex.map(run, todo):
            print(t, st, f"${budget.spent():.2f}", flush=True)


if __name__ == "__main__":
    main()
