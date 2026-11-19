"""Step 25 parts 4-5: v4.2 rules for the two repaired versions (arm_s25/bank/tasks: sq-active-studies-changelog-v25, sq-partner-grant-v12-v25),
with the v4.2 pipeline unchanged (grader/gen_rules42.py: prompts, ten checks, procedure; staged-file lookup and content
hash of grader/gen_rules_set42.py). These are additions: they go to grader/out/v4.2-s25/ (rules/, descriptions/, set.json
in the format of v4.2-set0/set.json, usage.jsonl), not into the tagged v4.2-set0 folder.
  .venv/bin/python grader/gen_rules_s25.py"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT)]
import gen_rules_set42 as S42  # noqa: E402  (sets P.staged for the staged-file lookup; no task here has staged files)
import gen_rules42 as G42  # noqa: E402
import budget  # noqa: E402
import openai_key  # noqa: E402

OUT = G / "out/v4.2-s25"


def main():
    openai_key.get("gen_rules_s25")
    for d in (OUT / "rules", OUT / "descriptions"):
        d.mkdir(parents=True, exist_ok=True)
    G42.setup(OUT, 0.6)
    PR = G42.prompts42()
    rows, ctx = {}, {}
    for f in sorted((ROOT / "arm_s25/bank/tasks").glob("*.json")):
        r = json.loads(f.read_text()); ctx[r["instance_id"]] = r.pop("_agent_context", ""); rows[r["instance_id"]] = r
    index = {t: {"content": S42.content_hash(rows[t], ctx[t]), "rule_set_of": t, "rule_file": f"grader/out/v4.2-s25/rules/{t}.json",
                 "description": f"grader/out/v4.2-s25/descriptions/{t}.md", "shares_with": [], "replaces": None,
                 "derived_from": rows[t].get("derived_from")} for t in rows}
    (OUT / "set.json").write_text(json.dumps({"n_tasks": len(rows), "n_rule_sets": len(rows), "tasks": index}, indent=1))

    def run(t):
        return t, G42.one(t, rows[t], ctx[t], PR)[1]
    with ThreadPoolExecutor(2) as ex:
        for t, st in ex.map(run, sorted(rows)):
            d = json.loads((OUT / "rules" / f"{t}.json").read_text())
            print(t, st, "failed checks:", d["checks"].get("failed"), "n/a:", d["checks"].get("not_applicable"),
                  f"${budget.spent():.2f}", "key:", openai_key.which(), flush=True)


if __name__ == "__main__":
    main()
