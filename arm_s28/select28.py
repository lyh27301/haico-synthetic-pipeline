"""Step 28 part 1: the steps. From the graded step-21 and step-23 runs (grader/out/v4.2-set0/grades21.jsonl, grades23.jsonl):
per run, the first unsafe step with a designed finding (tag 'designed'). A task is eligible when
  - its rule file passes all ten checks (checks.failed empty);
  - at least one stored run of any agent on it is a safe completion (outcome honest_success);
  - it is not on the repair list and not a safe twin (counter_example);
  - the step is not the falsification pattern ("attached but labelled as wrong": gm-consolidated-falsify family).
Agents: gpt-6-luna and claude-haiku-5-5 (Qwen endpoints are not up: the cluster jobs are still queued). At most 2 steps
per task: the earliest branch points first (shorter prefix), luna and haiku alternating.
  .venv/bin/python arm_s28/select28.py   -> arm_s28/steps28.json"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPAIR = ("cm-firmware-lock", "sq-partner-grant-v12", "sq-active-studies-changelog", "gm-acme-forward-v141",
          "gm-q3-reply-prelim-v121", "sq-measure-export-v121")
FALSIFY = ("gm-consolidated-falsify",)
API = ("gpt-6-luna", "haiku5.5")


def main():
    G = []
    for f in ("grader/out/v4.2-set0/grades21.jsonl", "grader/out/v4.2-set0/grades23.jsonl"):
        G += [json.loads(l) | {"grades": f} for l in (ROOT / f).read_text().splitlines()]
    G = [g for g in G if "crash" not in g]
    by = collections.defaultdict(list)
    for g in G:
        by[g["task"]].append(g)
    steps, excluded = [], {}
    for t, gs in sorted(by.items()):
        rf = json.loads((ROOT / gs[0]["rule_file"]).read_text())
        failed = rf["checks"].get("failed") or []
        safe = [g["key"] for g in gs if g["outcome"] == "honest_success"]
        cand = []
        for g in gs:
            if g["agent"] not in API:
                continue
            for i, (lab, fs) in enumerate(zip(g["labels"], g["findings"])):
                if lab == "unsafe" and any(f.get("label") == "unsafe" and f.get("tag") == "designed" for f in fs):
                    cand.append({"task": t, "agent": g["agent"], "run": g["run"], "key": g["key"], "tree": g["tree"],
                                 "step": i, "tool": g["tools"][i], "grades": g["grades"],
                                 "traps": sorted({f.get("item") or f.get("harm") for f in fs if f.get("tag") == "designed"} - {None})})
                    break
        why = []
        if any(r in t for r in REPAIR):
            why.append("on the repair list")
        if gs[0].get("counter_example"):
            why.append("safe twin (control)")
        if failed:
            why.append(f"rules fail {failed}")
        if not safe:
            why.append("no stored run is a safe completion")
        if any(x in t for x in FALSIFY):
            why.append("falsification pattern (attached but labelled as wrong)")
        if not cand:
            why.append("no gpt-6-luna / Haiku run has a designed unsafe step")
        if why:
            excluded[t] = {"why": why, "api_steps": len(cand), "safe_completions": len(safe)}
            continue
        cand.sort(key=lambda c: (c["step"], c["agent"] != "haiku5.5", c["run"]))
        pick = []
        for c in cand:   # prefer one per agent, then the next earliest
            if len(pick) < 2 and (not pick or c["agent"] != pick[0]["agent"] or not any(x["agent"] != pick[0]["agent"] for x in cand)):
                pick.append(c)
        for c in cand:
            if len(pick) < 2 and c not in pick:
                pick.append(c)
        steps += [p | {"safe_completions": len(safe), "candidates": len(cand)} for p in pick]
    (ROOT / "arm_s28/steps28.json").write_text(json.dumps({"steps": steps, "excluded": excluded}, indent=1))
    print(len(steps), "steps over", len({s["task"] for s in steps}), "tasks;", collections.Counter(s["agent"] for s in steps))
    for s in steps:
        print(" ", s["task"][7:], s["agent"], "r", s["run"], "step", s["step"], s["tool"], s["traps"])
    for t, e in excluded.items():
        print("X", t[7:], e)


if __name__ == "__main__":
    main()
