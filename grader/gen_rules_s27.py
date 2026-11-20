"""Step 27 part 1: v4.2 rules for the task versions the step-14 warned branches ran on (arm_s27/bank/bank_27.jsonl, built
by arm_s27/bank27.py from the v0.8 bank rows and their scenario references), with the v4.2 pipeline unchanged
(grader/gen_rules42.py: prompts, ten checks, procedure; content hash of grader/gen_rules_set42.py). The tasks are not
repaired: rule sets that fail a check are reported with the reason. Additions outside the tag: grader/out/v4.2-s27/
(rules/, descriptions/, set.json in the format of v4.2-set0/set.json, usage.jsonl). Staged files: arm_hf/out_v08.
  .venv/bin/python grader/gen_rules_s27.py"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT), str(ROOT / "arm_s27")]
import gen_rules_set42 as S42  # noqa: E402
import gen_rules42 as G42  # noqa: E402
import budget  # noqa: E402
import openai_key  # noqa: E402
import bank27  # noqa: E402

OUT = G / "out/v4.2-s27"
G42.GR.P.staged = bank27.staged   # the old rows' staged files (after gen_rules_set42 set its own lookup)
S42._staged = bank27.staged        # content hash over the same files


def load():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s27/bank/bank_27.jsonl").read_text().splitlines()}
    ctx = json.loads((ROOT / "arm_s27/bank/agent_context_27.json").read_text())
    return rows, ctx


def main():
    openai_key.get("gen_rules_s27")
    G42.setup(OUT, 1.5)
    PR = G42.prompts42()
    rows, ctx = load()
    index = {t: {"content": S42.content_hash(rows[t], ctx[t]), "rule_set_of": t, "rule_file": f"grader/out/v4.2-s27/rules/{t}.json",
                 "description": f"grader/out/v4.2-s27/descriptions/{t}.md", "shares_with": [], "replaces": None,
                 "derived_from": rows[t].get("derived_from")} for t in rows}
    (OUT / "set.json").write_text(json.dumps({"n_tasks": len(rows), "n_rule_sets": len(rows), "tasks": index}, indent=1))
    todo = [t for t in sorted(rows) if "--all" in sys.argv or not (OUT / "rules" / f"{t}.json").exists()]

    def run(t):
        try:
            return t, G42.one(t, rows[t], ctx[t], PR)[1]
        except budget.OverBudget:
            raise
        except Exception as e:  # noqa: BLE001
            import traceback
            return t, f"crash {e} {traceback.format_exc()[-800:]}"
    with ThreadPoolExecutor(4) as ex:
        for t, st in ex.map(run, todo):
            f = OUT / "rules" / f"{t}.json"
            d = json.loads(f.read_text()) if f.exists() else {"checks": {}}
            print(t, st, "failed checks:", d["checks"].get("failed"), "n/a:", d["checks"].get("not_applicable"),
                  f"${budget.spent():.2f}", "key:", openai_key.which(), flush=True)


if __name__ == "__main__":
    main()
