"""Step 11: arm_s10/run_harness.py with a Qwen agent (--agent qwen: Qwen/Qwen3.5-9B served by vLLM on a SLURM GPU
cluster, reached through an SSH tunnel on localhost:8000, set up as in the private serving notes;
harness/oas_agentdojo.py --model/--base-url). Results are recorded with
agent=qwen3.5-9b. The OpenAI agents remain available. Step-10 rules unchanged:
  - one result file per (task, agent, run): arm_s11/harness/results/<task>__<agent>__r<k>.json, atomic, skipped if
    present;
  - run k = one run_infer invocation over the ids into arm_s11/harness/<agent>/<tag>r<k>;
  - a run killed by arm_s11/cost_watchdog.py for the token cap (200k uncached tokens) or the cost cap -> no_grade, not
    retried; a run that ended in any other error (stuck detection, hang kill, infra) -> rerun once into r<k>_rerun,
    still failing -> no_grade;
  - results are read from output.critic_attempt_1.jsonl (run_infer leaves errored instances out of output.jsonl).
  NPC_API_KEY=$OPENAI_API_KEY NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=4 \\
  .venv/bin/python arm_s11/run_harness.py --agent qwen --ids arm_s11/ids_v06.txt --first 1 --last 5"""
import argparse, json, os, subprocess, time
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
    return (RES / f"{t}__{NAME[agent]}__r{k}.json").exists()


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
        todo = [t for t in ids if not have(t, a.agent, k)]
        if not todo:
            continue
        out, out2 = H / NAME[a.agent] / f"{a.tag}r{k}", H / NAME[a.agent] / f"{a.tag}r{k}_rerun"
        with open(H / "logs" / f"{NAME[a.agent]}_{a.tag}r{k}.log", "a") as log:
            invoke(todo, out, a.agent, Path(a.bank), log)
            got, cap = outputs(out), capped()
            kind = {t: cap.get((str(got[t][1]), t)) for t in todo if t in got}
            retry = [t for t in todo if not kind.get(t) and (t not in got or got[t][0].get("error"))]
            if retry:
                invoke(retry, out2, a.agent, Path(a.bank), log)
            got2, cap = (outputs(out2) if retry else {}), capped()
        for t in todo:
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
            rec["agent"] = NAME[a.agent]
            write(RES / f"{t}__{NAME[a.agent]}__r{k}.json", rec)
        print(f"{NAME[a.agent]} {a.tag}r{k}: {len(todo)} done", flush=True)


if __name__ == "__main__":
    main()
