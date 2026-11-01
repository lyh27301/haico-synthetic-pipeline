"""Step 11: arm_s10/run_harness.py with a Qwen agent (--agent qwen: Qwen/Qwen3.5-9B served by vLLM on a SLURM GPU
cluster, reached through an SSH tunnel on localhost:8000, set up as in the private serving notes;
harness/oas_agentdojo.py --model/--base-url). Results are recorded with
agent=qwen3.5-9b. The OpenAI agents remain available. Step-10 rules unchanged:
  - one result file per (task, agent, run): arm_s11/harness/results/<task>__<agent>__r<k>.json, written atomically
    (.tmp + rename) only once the run has a final outcome; on start every task+run with a final result file is skipped
    (graded, capped, or a real agent-side error after its rerun), so the runner can be restarted at any time;
  - endpoint loss is routine (the cluster preempts and requeues the vLLM job): arm_s11/endpoint_guard.py pauses the
    run_infer tree and its containers while the endpoint is down and logs each outage to harness/outages.jsonl. A task
    that errors on the agent endpoint (connection refused / timeout / 5xx in the conversation's error event) or whose
    run overlaps a logged outage is `endpoint_lost`: no result file, re-queued in the next pass of the same run;
  - run k = passes over the remaining ids, each one run_infer invocation into arm_s11/harness/<agent>/<tag>r<k>_p<n>
    (pass n's reruns into ..._p<n>_rerun); a pass ends when nothing is left or the guard gave up (endpoint_down.json);
  - a run killed by arm_s11/cost_watchdog.py for the token cap (200k uncached tokens) or the cost cap -> no_grade, not
    retried; a run that ended in any other error (stuck detection, hang kill, infra) -> rerun once into r<k>_rerun,
    still failing -> no_grade;
  - results are read from output.critic_attempt_1.jsonl (run_infer leaves errored instances out of output.jsonl).
  NPC_API_KEY=$OPENAI_API_KEY NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=4 \\
  .venv/bin/python arm_s11/run_harness.py --agent qwen --ids arm_s11/ids_v06.txt --first 1 --last 5"""
import argparse, json, os, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S10 = ROOT / "arm_s11"; H = S10 / "harness"; RES = H / "results"
BENCH = Path.home() / "Documents/workspace/benchmarks"
CFG = {"4omini": ".llm_config/openai.json", "5mini": ".llm_config/openai-5mini.json", "qwen": ".llm_config/openai.json"}
EXTRA = {"qwen": ["--model", "Qwen/Qwen3.5-9B", "--base-url", os.environ.get("QWEN_BASE_URL", "http://localhost:8000/v1"),
                  "--api-key", "EMPTY"]}
NAME = {"4omini": "4omini", "5mini": "5mini", "qwen": "qwen3.5-9b"}   # agent name in result files / dirs
PY = ROOT / "harness/.venv-oas/bin/python"
CAPS = ("token_cap", "cost_cap")


def outputs(out_dir: Path) -> dict:
    rows = {}
    for f in out_dir.rglob("output.critic_attempt_1.jsonl"):
        for ln in f.read_text().splitlines():
            if ln.strip():
                o = json.loads(ln); rows[o["instance_id"]] = (o, f.parent)
    return rows


def invoke(ids: list[str], out_dir: Path, agent: str, bank: Path, log) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = out_dir / "ids.txt"; sel.write_text("\n".join(ids) + "\n")
    env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1"}
    assert env.get("NPC_BASE_URL"), "NPC_BASE_URL must be set (step 9: without it chat_npc only returns Connection error)"
    t0 = time.time()
    p = subprocess.run([str(PY), str(ROOT / "harness/oas_agentdojo.py"), CFG[agent], *EXTRA.get(agent, []), "--dataset", str(bank),
                        "--split", "train", "--select", str(sel), "--output-dir", str(out_dir),
                        "--num-workers", os.environ.get("WORKERS", "4"), "--critic", "pass", "--max-attempts", "1"],
                       cwd=BENCH, env=env, stdout=log, stderr=subprocess.STDOUT)
    with open(out_dir / "invocations.jsonl", "a") as fh:
        fh.write(json.dumps({"n": len(ids), "start": t0, "end": time.time(), "rc": p.returncode}) + "\n")


def record(t, agent, k, o, base, rerun) -> dict:
    tr = o.get("test_result") or {}
    ad = tr.get("agentdojo") or {}
    sd = base / "agentdojo_state" / t
    u = json.loads((sd / "usage.json").read_text()) if (sd / "usage.json").exists() else {}
    err = o.get("error")
    return {"task": t, "agent": agent, "run": k, "unsafe": ad.get("unsafe") if not err else None,
            "graded": bool(ad) and not err, "error": (str(err)[:500] if err else None),
            "stuck": bool(err and "stuck" in str(err).lower()), "rerun": rerun, "checkpoints": ad.get("checkpoints"),
            "state_dir": str(sd.relative_to(ROOT)), "traj_dir": str(base.relative_to(ROOT)), "usage": u}


def capped() -> dict:
    """(eval output dir, instance) -> cap kind, for the runs the watchdog killed for a cap (no grade, no retry)."""
    f = H / "capped.jsonl"
    if not f.exists():
        return {}
    return {(o["run"], o["instance"]): o["kind"] for o in map(json.loads, f.read_text().splitlines())
            if o.get("kind") in CAPS}


def write(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(obj, indent=1, default=str)); tmp.replace(path)


def have(t: str, agent: str, k: int) -> bool:
    """A final result exists (graded or a final no-grade). endpoint_lost runs never get a result file."""
    f = RES / f"{t}__{NAME[agent]}__r{k}.json"
    if not f.exists():
        return False
    try:
        return not json.loads(f.read_text()).get("endpoint_lost")
    except ValueError:   # unreadable = not done
        return False


ENDPOINT_ERR = re.compile(r"LLMServiceUnavailable|APIConnectionError|Connection error|Connection refused|"
                          r"ServiceUnavailable|InternalServerError|BadGateway|GatewayTimeout|Timeout|"
                          r"\b50[0234]\b", re.I)
MAX_PASSES = 12


def outages() -> list[tuple[float, float]]:
    """(start, end) of every outage the guard logged; an ongoing one ends now."""
    f = H / "outages.jsonl"
    out, start = [], None
    for o in (map(json.loads, f.read_text().splitlines()) if f.exists() else []):
        if o["event"] == "pause":
            start = o["t"]
        elif o["event"] in ("resume", "give_up") and start is not None:
            out.append((start, o["t"])); start = None
    if start is not None:
        out.append((start, time.time()))
    return out


def endpoint_lost(t: str, o: dict | None, base: Path | None, log_path: Path, t0: float) -> bool:
    """An errored (or missing) instance lost to the agent endpoint, not to the agent: the conversation's error event
    names a connection / timeout / 5xx error, or the instance ran while an outage was logged."""
    if o is not None and not o.get("error"):
        return False
    il = base / "logs" / f"instance_{t}.log" if base else None
    lo, hi = (il.stat().st_birthtime, il.stat().st_mtime) if il and il.exists() else (t0, time.time())
    if any(s <= hi + 60 and e >= lo for s, e in outages()):
        return True
    for ln in open(log_path, errors="replace"):
        if (f'"instance_id": "{t}"' in ln and ("ConversationErrorEvent" in ln or "AgentErrorEvent" in ln)
                and ln.startswith("{")):
            try:
                ev = json.loads(json.loads(ln).get("event") or "{}")
            except ValueError:
                continue
            if ev.get("kind") in ("ConversationErrorEvent", "AgentErrorEvent") and \
                    ENDPOINT_ERR.search(str(ev.get("detail") or ev.get("error") or "") + str(ev.get("code") or "")):
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=list(CFG), required=True); ap.add_argument("--ids", required=True)
    ap.add_argument("--first", type=int, default=1); ap.add_argument("--last", type=int, default=5)
    ap.add_argument("--bank", default=str(S10 / "bank_v06.jsonl"))
    ap.add_argument("--tag", default="", help="separate output dirs for concurrent invocations")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    ids = [x.strip() for x in Path(a.ids).read_text().splitlines() if x.strip()]
    (H / "logs").mkdir(parents=True, exist_ok=True)
    for k in range(a.first, a.last + 1):
        for n in range(1, MAX_PASSES + 1):
            if (H / "endpoint_down.json").exists():
                print("endpoint guard gave up (endpoint_down.json); stopping", flush=True); return
            todo = [t for t in ids if not have(t, a.agent, k)]
            if not todo:
                break
            lost = run_pass(a, k, n, todo)
            print(f"{NAME[a.agent]} {a.tag}r{k} pass {n}: {len(todo)} tried, {len(todo) - len(lost)} final, "
                  f"{len(lost)} endpoint_lost (re-queued)", flush=True)
            if lost:
                wait_endpoint()


def wait_endpoint() -> None:
    """Before re-queueing: wait while the guard reports an ongoing outage (paused file present)."""
    while (H / "paused").exists() and not (H / "endpoint_down.json").exists():
        time.sleep(30)


def run_pass(a, k: int, n: int, todo: list[str]) -> list[str]:
    """One pass of run k over todo. Writes a result for every task with a final outcome; returns the endpoint_lost ones."""
    out, out2 = H / NAME[a.agent] / f"{a.tag}r{k}_p{n}", H / NAME[a.agent] / f"{a.tag}r{k}_p{n}_rerun"
    log_path = H / "logs" / f"{NAME[a.agent]}_{a.tag}r{k}.log"
    with open(log_path, "a") as log:
        t0 = time.time()
        invoke(todo, out, a.agent, Path(a.bank), log)
        got, cap = outputs(out), capped()
        kind = {t: cap.get((str(got[t][1]), t)) for t in todo if t in got}
        lost = [t for t in todo if not kind.get(t) and endpoint_lost(t, *(got.get(t) or (None, None)), log_path, t0)]
        retry = [t for t in todo if t not in lost and not kind.get(t) and (t not in got or got[t][0].get("error"))]
        got2 = {}
        if retry:
            t1 = time.time()
            invoke(retry, out2, a.agent, Path(a.bank), log)
            got2, cap = outputs(out2), capped()
            lost += [t for t in retry if t in got2 and not cap.get((str(got2[t][1]), t))
                     and endpoint_lost(t, *got2[t], log_path, t1)]
            lost += [t for t in retry if t not in got2 and endpoint_lost(t, None, None, log_path, t1)]
    for t in todo:
        if t in lost:
            continue
        if kind.get(t):
            rec = record(t, a.agent, k, *got[t], rerun=False)
            rec.update({"unsafe": None, "graded": False, "capped": kind[t],
                        "error": f"{kind[t]} exceeded; killed by arm_s11/cost_watchdog.py, not retried"})
        elif t in retry and t in got2:
            rec = record(t, a.agent, k, *got2[t], rerun=True)
            k2 = cap.get((str(got2[t][1]), t))
            if k2:
                rec.update({"unsafe": None, "graded": False, "capped": k2, "error": f"{k2} exceeded on rerun"})
            rec["first_error"] = str((got.get(t) or ({},))[0].get("error") or "missing")[:300]
        elif t in got:
            rec = record(t, a.agent, k, *got[t], rerun=False)
        else:
            rec = {"task": t, "agent": a.agent, "run": k, "unsafe": None, "graded": False,
                   "error": "no output after rerun", "stuck": False, "rerun": True}
        rec.update({"agent": NAME[a.agent], "pass": n})
        write(RES / f"{t}__{NAME[a.agent]}__r{k}.json", rec)
    return lost

if __name__ == "__main__":
    main()
