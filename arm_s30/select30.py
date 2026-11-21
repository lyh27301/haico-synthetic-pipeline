"""Step 30 part 1: which runs get a safer branch.

Source: every graded run of steps 21, 23 and 25 (copies of the grade files as they were when this step started, in
arm_s30/source/: grades21.jsonl and grades23.jsonl of grader/out/v4.2-set0, arm_s25/grades25.jsonl; the copies hold the
step-23 / step-25 Qwen3.5-9B rows that were graded but not yet committed on main). Step 29's repaired -v29 versions are
added when step 29 part 2 is graded (run this again with their grade file listed in GRADES).

A run is branched when its FIRST unsafe step has a designed finding (tag 'designed', label unsafe). One branch per run,
at that step. Not branched:
  off_design_first   the first unsafe step has only off_design findings (also when a designed step follows later:
                     the prefix would then carry an unasked harm)
  borderline         the "attached but labelled as wrong" pattern (gm-consolidated-falsify family)
  repair_list        a task on the step-29 repair list (cm-firmware-lock all versions, gm-q3-reply-prelim-v121,
                     sq-measure-export-v121, gm-acme-forward-v141, ev-petri-attorney-archive all versions and twins);
                     their -v29 versions come later
  superseded         a version replaced by a later one (sq-active-studies-changelog -> -v25, sq-partner-grant-v12 -> -v25)
  invalid            the two step-21 9B runs whose NPC returned a 429 (not in the grade file; their step-23 re-runs are)
                     and any crashed grade row
  .venv/bin/python arm_s30/select30.py   -> arm_s30/branches30.json"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s30"
GRADES = [("21", "arm_s30/source/grades21.jsonl"), ("23", "arm_s30/source/grades23.jsonl"), ("25", "arm_s30/source/grades25.jsonl")]
REPAIR = ("cm-firmware-lock", "gm-q3-reply-prelim-v121", "sq-measure-export-v121", "gm-acme-forward-v141",
          "ev-petri-attorney-archive")
SUPERSEDED = {"safety-sq-active-studies-changelog": "safety-sq-active-studies-changelog-v25",
              "safety-sq-partner-grant-v12": "safety-sq-partner-grant-v12-v25"}
BORDERLINE = ("gm-consolidated-falsify",)
AGENTS = ("haiku5.5", "gpt-6-luna", "qwen3.5-9b", "qwen3.5-35b-a3b")


def designed(fs):
    return sorted({f.get("item") or f.get("harm") for f in fs if f.get("label") == "unsafe" and f.get("tag") == "designed"} - {None})


def why_not(g):
    t = g["task"]
    if "crash" in g:
        return "invalid"
    if any(r in t for r in REPAIR):
        return "repair_list"
    if t in SUPERSEDED:
        return "superseded"
    if any(b in t for b in BORDERLINE):
        return "borderline"
    return None


def main():
    G = []
    for step, f in GRADES:
        G += [json.loads(l) | {"source_step": step, "grade_file": f} for l in (ROOT / f).read_text().splitlines()]
    branches, skipped = [], []
    for g in G:
        fu = next((i for i, l in enumerate(g.get("labels") or []) if l == "unsafe"), None)
        if fu is None:
            continue
        tr = designed(g["findings"][fu])
        r = why_not(g) or (None if tr else "off_design_first")
        later = [i for i, (l, fs) in enumerate(zip(g["labels"], g["findings"])) if l == "unsafe" and designed(fs)]
        row = {"source_run_key": g["key"], "tree": g["tree"], "task": g["task"], "agent": g["agent"], "run": g["run"],
               "source_step": g["source_step"], "grade_file": g["grade_file"], "step": fu, "tool": g["tools"][fu],
               "traps": tr, "first_designed_step": later[0] if later else None, "n_steps": g["n_steps"],
               "outcome": g["outcome"]}
        (skipped if r else branches).append(row | ({"why_not": r} if r else {}))
    branches.sort(key=lambda b: (AGENTS.index(b["agent"]), b["task"], b["run"]))
    for i, b in enumerate(branches):
        b["branch_id"] = f"B{i + 1:03d}"
    (S / "branches30.json").write_text(json.dumps({"branches": branches, "skipped": skipped}, indent=1))
    print(len(branches), "branches;", "skipped runs with an unsafe step:", dict(collections.Counter(s["why_not"] for s in skipped)))
    print("per agent:", dict(collections.Counter(b["agent"] for b in branches)))
    print("per task x agent:")
    ta = collections.defaultdict(collections.Counter)
    for b in branches:
        ta[b["task"]][b["agent"]] += 1
    for t, c in sorted(ta.items()):
        print(f"  {t.removeprefix('safety-'):58s}", " ".join(f"{a.split('.')[0][:6]}{('.' + a.split('.')[1][:3]) if '.' in a else ''}={c[a]}" for a in AGENTS if c[a]),
              "| traps", sorted({x for b in branches if b["task"] == t for x in b["traps"]}))
    print("traps per task (text units):", len({(b["task"], tuple(b["traps"])) for b in branches}))
    od = [s for s in skipped if s["why_not"] == "off_design_first" and s["first_designed_step"] is not None]
    print("off_design_first runs with a later designed step:", len(od))


if __name__ == "__main__":
    main()
