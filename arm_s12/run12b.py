"""Step 12b orchestration after batch 1 (run unattended): wait for the batch-2 runners (started by hand), then
  1. stop rule (arm_s12/agg12b.py): good_any on the last 50 evaluated new tasks < 0.35 -> stop; bank >= 300 -> stop;
  2. budget: OpenAI spend so far + batch-3 projection (generation $/candidate and 4o-mini rollout $/task, both
     measured on batches 1-2) > $30 -> skip batch 3;
  3. batch 3 (the last one): enough candidates for the bank to reach ~300 (at the measured gate pass rate x member
     rate), generated with gen12b.py --batch 3 --max N, then gpt-4o-mini x5 and Qwen x5 concurrently;
  4. final aggregate.
Endpoint: arm_s12/endpoint_guard.py pauses on loss; if it gives up (harness/endpoint_down.json) the runners exit, and so
does this, printing the guard's resume recipe plus `--from-batch 3` / the runner commands to finish.
Writes arm_s12/run12b.json {state, reason, ...} at every step.
  NPC_API_KEY=$OPENAI_API_KEY ... .venv/bin/python arm_s12/run12b.py"""
import argparse, json, math, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"; H = S12 / "harness"
PY = str(ROOT / ".venv/bin/python")
CAP, TARGET, V06 = 30.0, 300, 103
STATE = S12 / "run12b.json"


def note(**kw):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.update(kw, t=time.strftime("%Y-%m-%dT%H:%M:%S%z")); STATE.write_text(json.dumps(s, indent=1))
    print(json.dumps(kw), flush=True)


def runners() -> list[str]:
    return subprocess.run(["pgrep", "-f", "bin/python[0-9.]* ([^ ]*/)?arm_s12/run_harness[.]py"], capture_output=True,
                          text=True).stdout.split()


def down() -> bool:
    if (ROOT / "harness/budget_stop.json").exists():
        note(state="budget_stop", reason="arm_s12/budget_guard.py stopped the runs at the spend limit",
             detail=json.loads((ROOT / "harness/budget_stop.json").read_text()))
        return True
    if (H / "endpoint_down.json").exists():
        d = json.loads((H / "endpoint_down.json").read_text())
        note(state="endpoint_down", reason="endpoint guard gave up after 45 min", runner_cmds=d.get("runner_cmds"),
             resume="see arm_s12/harness/guard.out (RESUME recipe); then rerun the batch's runners and "
                    ".venv/bin/python arm_s12/run12b.py --from-batch <b>")
        return True
    return False


def wait_runners():
    while runners():
        if down():
            sys.exit(2)
        time.sleep(60)
    if down():
        sys.exit(2)


def agg() -> dict:
    """Re-grade with the current grader (only called when no runner is active), then aggregate."""
    subprocess.run([PY, str(S12 / "regrade12b.py")], check=True, stdout=open(S12 / "regrade12b.out", "a"))
    subprocess.run([PY, str(S12 / "agg12b.py")], check=True, stdout=subprocess.DEVNULL)
    return json.loads((S12 / "agg12b.json").read_text())


def check(a: dict, batch: int) -> bool:
    keep = {k: a[k] for k in ("evaluated", "new_members", "bank_size", "good_any_last50", "rates_evaluated", "spend")}
    if a["stop"]["good_any_last50_lt_0.35"]:
        note(state="stopped", reason=f"stop rule after batch {batch}: good_any last 50 = {a['good_any_last50']} < 0.35", **keep)
        return False
    if a["stop"]["bank_ge_300"]:
        note(state="stopped", reason=f"bank size {a['bank_size']} >= {TARGET} after batch {batch}", **keep)
        return False
    note(state="passed", reason=f"batch {batch} passed the stop rule", **keep)
    return True


def run_batch(b: int):
    ids = str(S12 / f"ids_b{b}.txt")
    env = {**os.environ, "NPC_BASE_URL": "https://api.openai.com/v1", "NPC_MODEL": "gpt-4o-mini"}
    env.setdefault("NPC_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    ps = [subprocess.Popen([PY, str(S12 / "run_harness.py"), "--agent", ag, "--ids", ids, "--first", "1", "--last", "5"],
                           env={**env, "WORKERS": w}, stdout=open(S12 / f"run_{ag}_b{b}.out", "a"), stderr=subprocess.STDOUT,
                           cwd=ROOT) for ag, w in (("4omini", "4"), ("qwen", "5"))]
    note(state=f"batch{b}_rollouts", pids=[p.pid for p in ps])
    for p in ps:
        p.wait()
    if down():
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--from-batch", type=int, default=2)
    a = ap.parse_args()
    if a.from_batch <= 2:
        note(state="waiting_batch2")
        wait_runners()
        if not check(agg(), 2):
            return
    vs = [json.loads(l) for l in (S12 / "variants.jsonl").read_text().splitlines()]
    if a.from_batch <= 3 and not (S12 / "ids_b3.txt").exists():
        A = agg(); sp = A["spend"]
        ev = [t for t, x in A["tasks"].items() if x["evaluated"]]
        per_cand = sp["generation_gates"] / len(vs)
        per_task = (sp["rollouts"] + sp["npc_est"]) / max(len(ev), 1)
        yield_ = sum(v["status"] == "passed" for v in vs) / len(vs) * A["rates_evaluated"]["member"]
        need = TARGET - A["bank_size"]
        n = min(125, math.ceil(need / yield_ * 1.05))
        proj = n * per_cand + n * (sum(v["status"] == "passed" for v in vs) / len(vs)) * per_task
        note(state="batch3_plan", need=need, candidates=n, yield_per_candidate=round(yield_, 3),
             projected_cost=round(proj, 2), spend=sp["total"])
        if sp["total"] + proj > CAP - 1.0:
            note(state="skipped_batch3", reason=f"projected ${sp['total'] + proj:.2f} > cap ${CAP} (with $1 margin)")
            return
        subprocess.run([PY, str(S12 / "gen12b.py"), "--batch", "3", "--workers", "6", "--max", str(n)], check=True,
                       stdout=open(S12 / "gen_b3.out", "a"), stderr=subprocess.STDOUT, cwd=ROOT,
                       env={**os.environ, "USAGE_LOG": str(S12 / "gen_usage.jsonl")})
    if a.from_batch <= 3:
        run_batch(3)
        A = agg()
        check(A, 3)
    note(state="done", reason="all batches graded", bank_size=agg()["bank_size"])


if __name__ == "__main__":
    main()
