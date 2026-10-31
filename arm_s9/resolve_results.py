"""Step 9: rebuild arm_s9/harness/results/<task>__<agent>__r<k>.json from the raw attempt files, with the run rules:
  - a first attempt killed for the 200k-token cap (capped.jsonl kind token_cap) -> no_grade, not retried (a rerun that
    run_harness.py launched anyway is ignored);
  - a first attempt that errored (stuck detection, cost/hang kill, infra) -> the rerun's grade, else no_grade;
  - otherwise the first attempt's grade.
Needed because run_harness.py read output.jsonl, which omits errored instances, until it was fixed mid-run: stuck runs
were recorded as "missing" and some token-capped runs were rerun. Reads output.critic_attempt_1.jsonl, which has them.
  .venv/bin/python arm_s9/resolve_results.py   (rewrites only (task, agent, run) whose first attempt has finished)"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "arm_s9"))
from run_harness import RES, record, write  # noqa: E402

H = ROOT / "arm_s9" / "harness"


def attempts() -> dict:
    """(task, agent, run, rerun) -> (output dict, eval dir); a task appears in one tag per agent."""
    out = {}
    for f in H.glob("*/*/*/*/output.critic_attempt_1.jsonl"):
        agent, rd = f.parents[3].name, f.parents[2].name
        m = re.match(r"(?:npc\d*_)?r(\d+)(_rerun)?$", rd)
        if agent not in ("4omini", "5mini") or not m:
            continue
        for ln in f.read_text().splitlines():
            if ln.strip():
                o = json.loads(ln)
                out[(o["instance_id"], agent, int(m.group(1)), bool(m.group(2)))] = (o, f.parent)
    return out


def main():
    cap = {(o["run"], o["instance"]) for o in map(json.loads, (H / "capped.jsonl").read_text().splitlines())
           if o.get("kind") == "token_cap"}
    att = attempts()
    n = {"graded": 0, "token_capped": 0, "rerun_graded": 0, "no_grade": 0, "ignored_rerun_of_capped": 0}
    for (t, agent, k, rr), (o, base) in sorted(att.items()):
        if rr:
            continue
        first_capped = (str(base), t) in cap
        if first_capped:
            rec = record(t, agent, k, o, base, rerun=False)
            rec.update({"unsafe": None, "graded": False, "token_capped": True, "stuck": False,
                        "error": "token cap (200k) exceeded; killed by arm_s9/cost_watchdog.py, not retried"})
            n["token_capped"] += 1
            n["ignored_rerun_of_capped"] += (t, agent, k, True) in att
        elif o.get("error"):
            second = att.get((t, agent, k, True))
            if second and (str(second[1]), t) in cap:
                rec = record(t, agent, k, *second, rerun=True)
                rec.update({"unsafe": None, "graded": False, "token_capped": True,
                            "error": "token cap (200k) exceeded on rerun"})
                n["token_capped"] += 1
            elif second:
                rec = record(t, agent, k, *second, rerun=True)
                n["rerun_graded" if rec["graded"] else "no_grade"] += 1
            else:
                rec = record(t, agent, k, o, base, rerun=False)
                rec["pending_rerun"] = True
                n["no_grade"] += 1
            rec["first_error"] = str(o["error"])[:300]
            rec["first_stuck"] = "stuck" in str(o["error"]).lower()
        else:
            rec = record(t, agent, k, o, base, rerun=False)
            n["graded"] += 1
        write(RES / f"{t}__{agent}__r{k}.json", rec)
    print(json.dumps(n))


if __name__ == "__main__":
    main()
