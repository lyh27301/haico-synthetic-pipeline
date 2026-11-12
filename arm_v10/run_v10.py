"""Step 13j re-roll of the 18 repaired tasks (task_version 0.10 in arm_v08/bank_v08.jsonl). Unattended, resumable
(a run with a final result is never redone). Same scaffold, NPC (gpt-4o-mini), temperature, step / token caps and
per-run cost caps as v0.8 / v0.9; runner arm_v09/run_harness.py with --root, watchdog arm_v09/cost_watchdog.py <tree>.
  1. smoke: one task per family (arm_v10/ids_smoke.txt) x gpt-4o-mini, Haiku 5.5, Sonnet 5.5 x run 1 -> arm_v10/smoke;
     go on only if every smoke run is graded (a per-run cap counts as graded-out, not as an error);
  2. batch: 18 tasks (arm_v10/ids_13j.txt) x gpt-4o-mini r1-5, Haiku 5.5 r1-5, Sonnet 5.5 r1-3 -> arm_v10, the three
     agents in parallel;
  3. Qwen3.5-9B r1-5 is NOT run here: arm_v10/queue_qwen.json holds the command for the next time the Babel endpoint
     is up.
Budget guard (every minute, smoke included), per provider: Anthropic (Haiku + Sonnet usage.json accumulated_cost),
cap $10, stops the Claude runners at $9.40 (room for the runs in flight); OpenAI batch (gpt-4o-mini usage.json + NPC
estimate $0.001 per chat_npc call), cap $3, stops the gpt-4o-mini runner at $2.80. The step-13j spec generation and
re-audit (gpt-5-mini usage logs since T0) is reported separately, not counted toward the batch cap. A stop writes
arm_v10/harness/budget_stop_<provider>.json; the other provider's runners go on. The runner works run by run (r1 on
every task, then r2, ...), so a cap cuts the last runs, not whole tasks. Also stops everything if more than 5% of a
phase's final runs error (counted once 40 are final).
Writes arm_v10/run_v10.json {state, phase, reason, spend, counts, t}.
  .venv/bin/python arm_v10/run_v10.py"""
import glob, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V = ROOT / "arm_v10"; PY = str(ROOT / ".venv/bin/python")
STATE = V / "run_v10.json"
CAPS = {"anthropic": 10.0, "openai": 3.0}
STOP_AT = {"anthropic": 9.40, "openai": 2.80}
GROUP = {"anthropic": ("haiku", "sonnet"), "openai": ("4omini",)}
NPC_CALL = 0.001
T0 = float(os.environ.get("T13J", "0")) or json.loads((V / "t0.json").read_text())["t0"]
GEN_LOGS = ["arm_s13/utility_usage.jsonl", "arm_s13/exposure_usage.jsonl", "arm_s13/probe_usage.jsonl",
            "arm_s13/norm_usage.jsonl"]
NAME = {"4omini": "4omini", "haiku": "haiku5.5", "sonnet": "sonnet5.5"}
RUNS = {"4omini": 5, "haiku": 5, "sonnet": 3}
WORKERS = {"4omini": "5", "haiku": "6", "sonnet": "4"}


def note(**kw):
    s = json.loads(STATE.read_text()) if STATE.exists() else {}
    s.update(kw, t=time.strftime("%Y-%m-%dT%H:%M:%S%z")); STATE.write_text(json.dumps(s, indent=1))
    print(json.dumps(kw), flush=True)


def usage(tree: Path, agent: str) -> float:
    return sum(json.loads(Path(f).read_text()).get("accumulated_cost") or 0
               for f in glob.glob(str(tree / "harness" / agent / "**/usage.json"), recursive=True))


def spend() -> dict:
    trees = [V, V / "smoke"]
    anth = sum(usage(t, a) for t in trees for a in ("haiku5.5", "sonnet5.5"))
    oai = sum(usage(t, "4omini") for t in trees)
    npc = sum(Path(f).read_text().count("chat_npc \\\"") for t in trees
              for f in glob.glob(str(t / "harness/**/output.critic_attempt_1.jsonl"), recursive=True))
    gen = 0.0
    for f in GEN_LOGS:
        p = ROOT / f
        for o in map(json.loads, p.read_text().splitlines()) if p.exists() else []:
            if o.get("t", 0) >= T0 and o.get("model") == "gpt-5-mini" and "in" in o:
                gen += (o["in"] * 0.25 + o["out"] * 2.0) / 1e6
    return {"anthropic": round(anth, 3), "openai": round(oai + npc * NPC_CALL, 3), "openai_agent": round(oai, 3),
            "npc_calls": npc, "openai_specgen_separate": round(gen, 3)}


def counts(tree: Path, agents) -> dict:
    rs = []
    for a in agents:
        for f in (tree / "harness/results").glob(f"*__{NAME[a]}__r*.json"):
            try:
                r = json.loads(f.read_text())
            except ValueError:
                continue
            if not r.get("endpoint_lost"):
                rs.append(r)
    return {"final": len(rs), "graded": sum(bool(r.get("graded")) for r in rs),
            "capped": sum(bool(r.get("capped")) for r in rs),
            "errors": sum(not r.get("graded") and not r.get("capped") for r in rs),
            "unsafe": sum(r.get("unsafe") is True for r in rs)}


def start(agent, ids, last, root):
    log = open(V / f"run_{agent}{'_smoke' if 'smoke' in str(root) else ''}.out", "a")
    return subprocess.Popen([PY, str(ROOT / "arm_v09/run_harness.py"), "--agent", agent, "--ids", str(ids), "--first", "1",
                             "--last", str(last), "--root", str(root.relative_to(ROOT))], cwd=ROOT,
                            env={**os.environ, "WORKERS": WORKERS[agent]}, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def stop(procs):
    for p in procs:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def phase(name, ids, runs, root):
    (root / "harness").mkdir(parents=True, exist_ok=True)
    wd = subprocess.Popen([PY, str(ROOT / "arm_v09/cost_watchdog.py"), str(root.relative_to(ROOT))], cwd=ROOT,
                          stdout=open(V / f"watchdog_{name}.out", "a"), stderr=subprocess.STDOUT, start_new_session=True)
    procs = {a: start(a, ids, runs[a], root) for a in runs if not (V / f"harness/budget_stop_{prov(a)}.json").exists()}
    note(state="running", phase=name, pids={a: p.pid for a, p in procs.items()})
    reason, capped = None, []
    while any(p.poll() is None for p in procs.values()):
        s = spend(); c = counts(root, runs)
        for k, lim in STOP_AT.items():
            if s[k] > lim and k not in capped:
                capped.append(k)
                (V / "harness").mkdir(parents=True, exist_ok=True)
                (V / f"harness/budget_stop_{k}.json").write_text(json.dumps({"spend": s, "t": time.time()}))
                stop([p for a, p in procs.items() if a in GROUP[k]])
                note(state="running", phase=name, capped=capped, spend=s)
        if c["final"] >= 40 and c["errors"] > 0.05 * c["final"]:
            reason = f"{c['errors']} of {c['final']} final runs errored (> 5%)"
            stop(list(procs.values())); break
        note(state="running", phase=name, spend=s, counts=c, capped=capped)
        time.sleep(60)
    if capped and not reason:
        reason = None   # a provider cap is a planned cut, recorded in `capped`
    stop([wd])
    c = counts(root, runs)
    note(state="stopped" if reason else "phase_done", phase=name, reason=reason, capped=capped, spend=spend(), counts=c)
    return reason, c


def prov(agent):
    return next(k for k, g in GROUP.items() if agent in g)


def main():
    reason, c = phase("smoke", V / "ids_smoke.txt", {a: 1 for a in RUNS}, V / "smoke")
    expect = len((V / "ids_smoke.txt").read_text().split()) * len(RUNS)
    if reason or c["final"] < expect or c["errors"]:
        note(state="stopped", phase="smoke", reason=reason or f"smoke incomplete or errored: {c} (expected {expect})")
        return
    reason, c = phase("batch", V / "ids_13j.txt", RUNS, V)
    note(state="stopped" if reason else "done", phase="batch", reason=reason, counts=c, spend=spend())


if __name__ == "__main__":
    main()
