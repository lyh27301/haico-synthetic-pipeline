"""Step 20 runner loop for the step-16c / step-19 runners (arm_s16c/run_harness16c.py installs it on arm_v08/run_harness.py,
and arm_s19/run_harness19.py uses run_harness16c). Replaces arm_v08's main() / run_pass() for those runners.

What a run's result now means:
  - final: the harness reported no error AND the run passes harness/v16b/run_check.py (ends with the finish tool or the
    step cap; last step not cut off; history agrees with the steps the container recorded). Only final runs are graded.
  - error, not final, retried: the harness reported an error (this includes the harness's own run_check failure), the
    watchdog killed the run for a hang, the endpoint guard logged an outage while it ran, or there is no output.
    Every attempt goes to a fresh output folder (<tag>r<k>_a<n>; the harness refuses a used one). At most 2 retries
    (3 attempts); after that the result is written with failed = true and listed by the runner.
  - capped: the watchdog killed the run for its token or cost cap. Recorded with an error, not final, not retried
    (a retry measures the same thing again; as in 13j / 16c). Set RETRY_CAPPED=1 to treat caps like hangs.
Every attempt is listed in the result (`attempts`), with its folder and the reason it did not count.
A result with final or failed or capped set is done; re-running the runner skips it (delete the result file to redo it).
"""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_check  # noqa: E402

MAX_RETRIES = 2


def install(B) -> None:
    """B: the arm_v08 run_harness module (already set up by run_harness16c.setup)."""
    def hang_killed() -> set:
        f = B.H / "capped.jsonl"
        out = set()
        for o in (map(json.loads, f.read_text().splitlines()) if f.exists() else []):
            if o.get("kind") == "hang" and o.get("log"):
                p = Path(o["log"]); out.add((str(p.parent.parent), p.stem.removeprefix("instance_")))
        return out

    def done(t, agent, k) -> bool:
        f = B.RES / f"{t}__{B.NAME[agent]}__r{k}.json"
        if not f.exists():
            return False
        try:
            r = json.loads(f.read_text())
        except ValueError:
            return False
        return bool(r.get("final") or r.get("failed") or r.get("capped"))

    def fresh(base: Path) -> Path:
        p, i = base, 1
        while p.exists() and any(p.iterdir()):
            i += 1; p = base.with_name(f"{base.name}.{i}")
        return p

    def outage_during(base: Path | None, t: str, t0: float, t1: float) -> bool:
        il = base / "logs" / f"instance_{t}.log" if base else None
        lo, hi = (il.stat().st_birthtime, il.stat().st_mtime) if il and il.exists() else (t0, t1)
        return any(s <= hi + 60 and e >= lo for s, e in B.outages())

    def attempt(a, k: int, n: int, todo: list[str]) -> dict:
        """One harness invocation over todo into a fresh folder -> {task: (status, reason, output record, folder)}."""
        out = fresh(B.H / B.NAME[a.agent] / f"{a.tag}r{k}_a{n}")
        log_path = B.H / "logs" / f"{B.NAME[a.agent]}_{a.tag}r{k}.log"
        with open(log_path, "a") as log:
            t0 = time.time()
            B.invoke(todo, out, a.agent, Path(a.bank), log)
            t1 = time.time()
        got, cap, hung = B.outputs(out), B.capped(), hang_killed()
        res = {}
        for t in todo:
            if t not in got:
                res[t] = ("retry", "no output from the harness", None, None); continue
            o, base = got[t]
            if cap.get((str(base), t)):
                res[t] = ("capped", f"{cap[(str(base), t)]} exceeded; killed by the watchdog", o, base); continue
            if (str(base), t) in hung:
                res[t] = ("retry", "killed by the watchdog (no log line for its hang limit)", o, base); continue
            if outage_during(base, t, t0, t1):
                res[t] = ("retry", "the agent endpoint was down while this run was going (guard's outage log)", o, base)
                continue
            if o.get("error"):
                res[t] = ("retry", f"harness error: {str(o['error'])[:300]}", o, base); continue
            chk = run_check.check(o.get("history") or [], base / "agentdojo_state" / t)
            if not chk["ok"]:
                res[t] = ("retry", "run_check: " + "; ".join(chk["problems"]), o, base); continue
            res[t] = ("final", None, o, base)
        return res

    def main():
        ap = argparse.ArgumentParser()
        ap.add_argument("--agent", choices=list(B.CFG), required=True); ap.add_argument("--ids", required=True)
        ap.add_argument("--first", type=int, default=1); ap.add_argument("--last", type=int, default=5)
        ap.add_argument("--bank", required=True)
        ap.add_argument("--tag", default="", help="separate output dirs for concurrent invocations")
        a = ap.parse_args()
        B.RES.mkdir(parents=True, exist_ok=True); (B.H / "logs").mkdir(parents=True, exist_ok=True)
        B.ROWS.update({r["instance_id"]: r for r in map(json.loads, Path(a.bank).read_text().splitlines())})
        ids = [x.strip() for x in Path(a.ids).read_text().splitlines() if x.strip()]
        retry_capped = os.environ.get("RETRY_CAPPED") == "1"
        failed_all = []
        for k in range(a.first, a.last + 1):
            todo = [t for t in ids if not done(t, a.agent, k)]
            hist = {t: [] for t in todo}
            for n in range(1, MAX_RETRIES + 2):
                if not todo:
                    break
                if n > 1:
                    B.wait_endpoint()
                res = attempt(a, k, n, todo)
                nxt = []
                for t, (status, why, o, base) in res.items():
                    hist[t].append({"attempt": n, "dir": str(base.relative_to(B.ROOT)) if base else None,
                                    "status": status, "reason": why})
                    if status == "capped" and retry_capped:
                        status = "retry"
                    if status == "retry" and n <= MAX_RETRIES:
                        nxt.append(t); continue
                    if o is not None:
                        rec = B.record(t, a.agent, k, o, base, rerun=n > 1)
                    else:
                        rec = {"task": t, "agent": a.agent, "run": k, "graded": False, "rerun": n > 1}
                    rec.update({"agent": B.NAME[a.agent], "attempts": hist[t], "final": status == "final",
                                "graded": status == "final" and bool(rec.get("graded", True)),
                                "error": None if status == "final" else why})
                    if status == "capped":
                        rec["capped"] = why.split(" ")[0]
                    if status == "retry":
                        rec["failed"] = True; failed_all.append(f"{t} r{k}: {why}")
                    B.write(B.RES / f"{t}__{B.NAME[a.agent]}__r{k}.json", rec)
                print(f"{B.NAME[a.agent]} {a.tag}r{k} attempt {n}: {len(todo)} tried, "
                      f"{sum(1 for v in res.values() if v[0] == 'final')} final, {len(nxt)} to retry", flush=True)
                todo = nxt
        if failed_all:
            print("FAILED after", MAX_RETRIES, "retries:\n  " + "\n  ".join(failed_all), flush=True)

    B.main = main
