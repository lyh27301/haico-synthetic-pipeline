"""Step 18b: grader rules for the first training set after the step-18b changes ("set0b"), v4.1 prompts and checks unchanged,
same procedure as grader/gen_rules_set0.py (imported). The set is arm_s18/bank/train_set0.jsonl (removed rows left out).
A rule set whose task content is unchanged since set0 is copied from grader/out/v4.1-set0 byte for byte (rule file and
description, under the id that now represents the group when the old representative was removed); a changed task gets
new rules. Output: grader/out/v4.1-set0b/ (rules/, descriptions/, set0b.json, usage.jsonl; cap $5).
  .venv/bin/python grader/gen_rules_set0b.py [--index-only]"""
import argparse, json, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G)]
import gen_rules_set0 as S0  # noqa: E402
import budget  # noqa: E402

G4R, G41 = S0.G4R, S0.G41
V = "v4.1-set0b"
OUT = G / "out" / V; PREV = G / "out" / "v4.1-set0"
G4R.V, G4R.OUT = V, OUT
budget.USAGE = OUT / "usage.jsonl"; budget.CAP = 5.0
OUT.mkdir(parents=True, exist_ok=True)
G4R.judge_note4.CACHE = OUT / "judge_note_cache.jsonl"; G4R.judge_note4._cache = None
if not G4R.judge_note4.CACHE.exists():
    shutil.copy(PREV / "judge_note_cache.jsonl", G4R.judge_note4.CACHE)
BANK = ROOT / "arm_s18/bank"


def the_set():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (BANK / "train_set0.jsonl").read_text().splitlines()}
    ctx = json.loads((BANK / "agent_context_train_set0.json").read_text())
    return rows, ctx


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--index-only", action="store_true")
    a = ap.parse_args()
    (OUT / "rules").mkdir(parents=True, exist_ok=True); (OUT / "descriptions").mkdir(parents=True, exist_ok=True)
    rows, ctx = the_set()
    prev = json.loads((PREV / "set0.json").read_text())["tasks"]
    by_hash = {v["content"]: v for v in prev.values()}
    groups = {}
    for t in sorted(rows):
        groups.setdefault(S0.content_hash(rows[t], ctx[t]), []).append(t)
    index, todo = {}, []
    for h, ids in groups.items():
        rep = ids[0]
        old = by_hash.get(h)
        if old:
            src = old["rule_set_of"]
            for kind, ext in (("rules", ".json"), ("descriptions", ".md")):
                d = OUT / kind / f"{rep}{ext}"
                if not d.exists():
                    shutil.copy2(PREV / kind / f"{src}{ext}", d)
            how = (f"unchanged since set0: rule set of {src} copied byte for byte" + (" (" + old["rules"] + ")" if "frozen" in old["rules"] else ""))
        else:
            how = "content changed in step 18b: generated (v4.1 prompts and checks)"
            todo.append(rep)
        for t in ids:
            index[t] = {"source_bank": "arm_s18" if t.endswith(("-v18", "-v18a", "-v18b")) else "bank_16b", "content": h,
                        "rule_file": f"grader/out/{V}/rules/{rep}.json", "description": f"grader/out/{V}/descriptions/{rep}.md",
                        "rule_set_of": rep, "shares_with": [x for x in ids if x != t], "rules": how}
    (OUT / "set0b.json").write_text(json.dumps({"n_tasks": len(rows), "n_rule_sets": len(groups), "tasks": index}, indent=1))
    print(len(rows), "tasks,", len(groups), "rule sets,", len(todo), "to generate:", todo)
    if a.index_only or not todo:
        return
    PR = G41.prompts41()

    def run(t):
        r = G4R.one(t, rows[t], ctx[t], PR)
        f = OUT / "rules" / f"{t}.json"; d = json.loads(f.read_text())
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
