"""Step 34: v4.2 rules for the -v34 tasks (arm_s34/bank/tasks) and, later, their twins (arm_s34/twins/tasks), with the v4.2 pipeline unchanged
(grader/gen_rules42.py: prompts, ten checks, procedure), as grader/gen_rules_s25.py. The staged-file lookup of
grader/gen_rules_set42.py is extended to look in arm_s34/bank and arm_s34/twins first (every new row has its staged files there); the
content hash is computed the same way. Additions go to grader/out/v4.2-s34/ (rules/, descriptions/, set.json, usage.jsonl),
not into the tagged v4.2-set0 folder.
  .venv/bin/python grader/gen_rules_s34.py [ids...]"""
import hashlib, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; G = ROOT / "grader"
sys.path[:0] = [str(G), str(ROOT)]
import gen_rules_set42 as S42  # noqa: E402
import gen_rules42 as G42  # noqa: E402
import budget  # noqa: E402
import openai_key  # noqa: E402

OUT = G / "out/v4.2-s34"; B34 = ROOT / "arm_s34/bank"; B34t = ROOT / "arm_s34/twins"; BANKS = (B34, B34t)


def staged(row) -> dict:
    out = {}
    for spec in row.get("workspace_files") or []:
        for base in (B34, B34t, S42.S22, S42.S18, S42.S16):
            p = base / spec
            if p.exists():
                out["/workspace/" + spec.split("/workspace/", 1)[1]] = p.read_bytes(); break
        else:
            raise FileNotFoundError(spec)
    return out


S42.P.staged = staged; S42._staged = staged   # content_hash reads the module-level _staged


def main():
    openai_key.get("gen_rules_s34")
    G42.setup(OUT, 1.0)
    PR = G42.prompts42()
    rows, ctx = {}, {}
    for f in sorted(f for b in BANKS for f in (b / "tasks").glob("*.json")):
        r = json.loads(f.read_text()); ctx[r["instance_id"]] = r.pop("_agent_context", ""); rows[r["instance_id"]] = r
    index = {t: {"content": S42.content_hash(rows[t], ctx[t]), "rule_set_of": t, "rule_file": f"grader/out/v4.2-s34/rules/{t}.json",
                 "description": f"grader/out/v4.2-s34/descriptions/{t}.md", "shares_with": [], "replaces": None,
                 "derived_from": rows[t].get("derived_from")} for t in rows}
    if (OUT / "set.json").exists():   # keep rows of an earlier call (tasks first, twins later)
        old = json.loads((OUT / "set.json").read_text())["tasks"]; index = {**old, **index}
    (OUT / "set.json").write_text(json.dumps({"n_tasks": len(index), "n_rule_sets": len(index), "tasks": index}, indent=1))
    todo = [t for t in sorted(rows) if not sys.argv[1:] or t in sys.argv[1:]]

    def run(t):
        return t, G42.one(t, rows[t], ctx[t], PR)[1]
    with ThreadPoolExecutor(3) as ex:
        for t, st in ex.map(run, todo):
            d = json.loads((OUT / "rules" / f"{t}.json").read_text())
            print(t, st, "failed checks:", d["checks"].get("failed"), "n/a:", d["checks"].get("not_applicable"),
                  f"${budget.spent():.2f}", "key:", openai_key.which(), flush=True)


if __name__ == "__main__":
    main()
