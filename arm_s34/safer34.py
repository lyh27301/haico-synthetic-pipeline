"""Step 34 part 4a: one safer run per run with a trap-based first unsafe step, as step 30 (variant D, gate from the real
state), on the kept -v34 tasks. The step-30 scripts run unchanged (arm_s30/texts30.py, branch30.py, grade30.py); this
wrapper installs arm_s34/s34.py as their `s29` module and points their folder at arm_s34/safer/ (prompts: an identical copy
of arm_s30/prompts/). Selection is step 30's rule (select30.designed): a graded run is branched when its first unsafe step
has a designed finding; not branched: off_design_first, crashed / invalid runs, tasks not kept (arm_s34/keep34.json).
  .venv/bin/python arm_s34/safer34.py select
  .venv/bin/python arm_s34/safer34.py texts [--agents haiku5.5]       (texts30 flags)
  .venv/bin/python arm_s34/safer34.py branch --agents haiku5.5 [--workers 2]
  .venv/bin/python arm_s34/safer34.py grade
Outputs in arm_s34/safer/: branches30.json, texts30.json, messages30.json, texts.md, runs/, grades30.jsonl,
safer_runs.jsonl, labels_safer.jsonl (step-30 file names)."""
import collections, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S34 = ROOT / "arm_s34"; SF = S34 / "safer"
sys.path[:0] = [str(S34), str(ROOT / "arm_s30"), str(ROOT / "grader"), str(ROOT)]
import s34  # noqa: E402
s34.install()
AGENTS = ("haiku5.5", "gpt-6-luna", "qwen3.5-9b", "qwen3.5-35b-a3b")


def select():
    import select30
    keep = set(json.loads((S34 / "keep34.json").read_text())["kept"])
    G = [json.loads(l) for l in (S34 / "grades34.jsonl").read_text().splitlines()]
    prev = json.loads((SF / "branches30.json").read_text()) if (SF / "branches30.json").exists() else {"branches": []}
    ids = {b["source_run_key"]: b["branch_id"] for b in prev["branches"]}
    branches, skipped = [], []
    for g in G:
        fu = next((i for i, l in enumerate(g.get("labels") or []) if l == "unsafe"), None)
        if fu is None:
            continue
        tr = select30.designed(g["findings"][fu])
        why = "invalid" if "crash" in g else "not_kept" if g["task"] not in keep else None if tr else "off_design_first"
        later = [i for i, (l, fs) in enumerate(zip(g["labels"], g["findings"])) if l == "unsafe" and select30.designed(fs)]
        row = {"source_run_key": g["key"], "tree": g["tree"], "task": g["task"], "agent": g["agent"], "run": g["run"],
               "source_step": "34", "grade_file": "arm_s34/grades34.jsonl", "step": fu, "tool": g["tools"][fu], "traps": tr,
               "first_designed_step": later[0] if later else None, "n_steps": g["n_steps"], "outcome": g["outcome"]}
        (skipped if why else branches).append(row | ({"why_not": why} if why else {}))
    branches.sort(key=lambda b: (AGENTS.index(b["agent"]), b["task"], b["run"]))
    nxt = max([int(i[1:]) for i in ids.values()] + [0]) + 1
    for b in branches:
        if b["source_run_key"] not in ids:
            ids[b["source_run_key"]] = f"B{nxt:03d}"; nxt += 1
        b["branch_id"] = ids[b["source_run_key"]]
    branches.sort(key=lambda b: b["branch_id"])
    SF.mkdir(exist_ok=True)
    (SF / "branches30.json").write_text(json.dumps({"branches": branches, "skipped": skipped, "withdrawn": []}, indent=1))
    print(len(branches), "branches;", "skipped:", dict(collections.Counter(s["why_not"] for s in skipped)))
    print("per agent:", dict(collections.Counter(b["agent"] for b in branches)))


def texts():
    import budget, texts30 as T
    T.S = SF; budget.USAGE = SF / "usage_texts.jsonl"
    T.main()


def branch():
    os.environ.setdefault("S30_PROXY_PORT", "18834")
    import branch30 as Bm
    Bm.S, Bm.BR, Bm.USAGE = SF, SF / "runs", SF / "usage_branches.jsonl"
    Bm.PORT = int(os.environ["S30_PROXY_PORT"])
    Bm.BANKS["arm_s34"] = ("arm_s34/bank", "bank_34_harness.jsonl", "agent_context_34.json")
    Bm.main()


def grade():
    import grade30 as Gm
    Gm.S, Gm.TREE = SF, "arm_s34/safer/runs"
    Gm.main()


if __name__ == "__main__":
    cmd = sys.argv.pop(1)
    {"select": select, "texts": texts, "branch": branch, "grade": grade}[cmd]()
