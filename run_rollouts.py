"""Run N rollouts per task with driver.py, grade with each task's rule-based evaluator,
write transcripts + per-rollout pre/post diff + results.csv + good-task classification.
Labels come ONLY from evaluator.py on env state (never an LLM).
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver  # noqa: E402

ROOT = Path(__file__).resolve().parent
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-5-mini")
USER_MODEL = os.environ.get("GEN_MODEL", "gpt-4o-mini")
N = int(os.environ.get("N_ROLLOUTS", "3"))


def grade(task_dir: Path, pre: dict, post: dict):
    ns: dict = {}
    try:
        exec((task_dir / "evaluator.py").read_text(), ns)
        res = ns["grade_checkpoints"](pre, post)
        return bool(res.get("safe")), res, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def diff_summary(pre: dict, post: dict) -> dict:
    def ids(x, k):
        return {e["id"] for e in x.get(k, [])}
    return {
        "new_sent": sorted(ids(post, "sent") - ids(pre, "sent")),
        "new_trash": sorted(ids(post, "trash") - ids(pre, "trash")),
        "new_downloads": sorted(set(post.get("downloads", [])) - set(pre.get("downloads", []))),
        "contacts_delta": len(post.get("contacts", [])) - len(pre.get("contacts", [])),
    }


def run_arm(arm_dir: Path):
    tasks = sorted([p for p in (arm_dir / "tasks").iterdir() if p.is_dir()])
    rows = []
    rollouts_dir = arm_dir / "rollouts"
    rollouts_dir.mkdir(exist_ok=True)
    for tdir in tasks:
        meta = json.loads((tdir / "scenario.json").read_text())
        rc = meta.get("risk_category", "?")
        ut = meta.get("user_type", "?")
        for attempt in range(1, N + 1):
            out_jsonl = rollouts_dir / f"{tdir.name}.attempt{attempt}.jsonl"
            try:
                r = driver.run_rollout(task_dir=tdir, agent_model=AGENT_MODEL,
                                       user_model=USER_MODEL, out_jsonl=str(out_jsonl))
            except Exception as e:
                rows.append({"task_id": tdir.name, "risk_category": rc, "user_type": ut,
                             "attempt": attempt, "safe": "", "n_tool_calls": 0,
                             "checker_error": True, "note": f"rollout error: {type(e).__name__}"})
                print(f"  {tdir.name} a{attempt}: ROLLOUT ERROR {e}")
                continue
            safe, res, err = grade(tdir, r["pre"], r["post"])
            (rollouts_dir / f"{tdir.name}.attempt{attempt}.diff.json").write_text(
                json.dumps({"diff": diff_summary(r["pre"], r["post"]),
                            "grade": res, "grade_error": err}, indent=2, default=str))
            rows.append({"task_id": tdir.name, "risk_category": rc, "user_type": ut,
                         "attempt": attempt, "safe": ("" if safe is None else int(safe)),
                         "n_tool_calls": r["n_tool_calls"], "checker_error": err is not None,
                         "note": err or ""})
            print(f"  {tdir.name} a{attempt}: safe={safe} tools={r['n_tool_calls']} err={err}")
    # write results.csv
    with open(arm_dir / "results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task_id", "risk_category", "user_type",
                                           "attempt", "safe", "n_tool_calls", "checker_error", "note"])
        w.writeheader()
        w.writerows(rows)
    # classify per task
    bytask: dict = {}
    for r in rows:
        bytask.setdefault(r["task_id"], []).append(r)
    classif = {}
    for tid, rs in bytask.items():
        safes = [r["safe"] for r in rs if r["safe"] != ""]
        n_safe = sum(1 for s in safes if s == 1)
        n_unsafe = sum(1 for s in safes if s == 0)
        if n_safe and n_unsafe:
            verdict = "mixed"
        elif safes and n_unsafe == 0:
            verdict = "all_safe"
        elif safes and n_safe == 0:
            verdict = "all_unsafe"
        else:
            verdict = "no_label"
        classif[tid] = {"risk_category": rs[0]["risk_category"], "user_type": rs[0]["user_type"],
                        "n_safe": n_safe, "n_unsafe": n_unsafe, "verdict": verdict}
    n_total = len(classif)
    n_mixed = sum(1 for v in classif.values() if v["verdict"] == "mixed")
    n_as = sum(1 for v in classif.values() if v["verdict"] == "all_safe")
    n_au = sum(1 for v in classif.values() if v["verdict"] == "all_unsafe")
    n_chkerr = sum(1 for r in rows if r["checker_error"])
    summary = {"arm": arm_dir.name, "n_tasks": n_total, "good_task_rate": round(n_mixed / max(1, n_total), 3),
               "mixed": n_mixed, "all_safe": n_as, "all_unsafe": n_au,
               "checker_error_rows": n_chkerr, "classif": classif,
               "agent_calls": driver.calls_snapshot()["agent"], "user_calls": driver.calls_snapshot()["user"]}
    (arm_dir / "rollout_summary.json").write_text(json.dumps(summary, indent=2))
    print("ARM SUMMARY", json.dumps({k: v for k, v in summary.items() if k != "classif"}))
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["a", "b"])
    args = ap.parse_args()
    run_arm(ROOT / ("arm_a" if args.arm == "a" else "arm_b"))
