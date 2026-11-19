"""Step 21: the follow-up of arm_s21/followup21.py asked one run at a time with a 120 s limit per question (the
thread-pool version stalled twice on Haiku 5.5 in retry back-off with no answer written). Same question, same rebuild,
same classifier; rows appended to arm_s21/followup21.jsonl; runs that time out are listed in arm_s21/followup21_timeouts.txt.
  harness/.venv-oas/bin/python arm_s21/followup21_seq.py --trees arm_s21/runs --agents haiku5.5"""
import argparse, concurrent.futures as cf, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s21")]
import followup21 as M  # noqa: E402

F = M.F


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trees"); ap.add_argument("--agents"); a = ap.parse_args()
    F.patch_thinking()
    import openhands.tools.terminal, openhands.tools.file_editor, openhands.tools.task_tracker  # noqa: F401
    from openhands.sdk.event.base import Event
    done = {(o["task"], o["agent"], o["run"], o["tree"]) for o in map(json.loads, F.OUT.read_text().splitlines())} if F.OUT.exists() else set()
    jobs = []
    for tree in a.trees.split(","):
        for f in sorted((ROOT / tree / "harness/results").glob("*.json")):
            r = json.loads(f.read_text())
            if r.get("graded") and r.get("traj_dir") and r["agent"] in a.agents.split(",") and \
                    (r["task"], r["agent"], int(r["run"]), tree) not in done:
                jobs.append((tree, r))
    print(len(jobs), "runs to ask", flush=True)
    ex = cf.ThreadPoolExecutor(1)
    for tree, r in jobs:
        if r["task"] not in F.SYSTEM:
            for e in F.R.history(ROOT / r["traj_dir"], r["task"]) or []:
                if e.get("kind") == "SystemPromptEvent":
                    F.SYSTEM[r["task"]] = Event.model_validate(e); break
        fut = ex.submit(F.ask, (tree, r))
        try:
            x = fut.result(timeout=120)
        except cf.TimeoutError:
            with open(ROOT / "arm_s21/followup21_timeouts.txt", "a") as fh:
                fh.write(f"{r['agent']} {r['task']} r{r['run']}\n")
            print("timeout", r["task"], r["run"], flush=True)
            ex = cf.ThreadPoolExecutor(1)   # abandon the stuck thread
            continue
        except Exception as e:  # noqa: BLE001
            print("error", r["task"], r["run"], type(e).__name__, str(e)[:200], flush=True); continue
        F.classify([x])
        with open(F.OUT, "a") as fh:
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("done", json.dumps(F.SPENT), flush=True)
    import os; os._exit(0)


if __name__ == "__main__":
    main()
