"""Step 9 Part C: rollouts on the real harness (run_infer.py + harness/oas_agentdojo.py + MCP, harness defaults),
N runs per task per agent, one result file per (task, agent, run), written atomically and skipped if present.
Run k of agent A = one run_infer invocation over the ids into arm_s9/harness/<A>/r<k> (run_infer itself resumes
instances already in output.jsonl). A run that ends with an error (stuck detection "got stuck", or an infra error)
is rerun once into r<k>_rerun; still failing -> recorded no_grade.
  NPC_API_KEY=$OPENAI_API_KEY NPC_MODEL=gpt-4o-mini WORKERS=4 \
  .venv/bin/python arm_s9/run_harness.py --agent 4omini --ids arm_s9/ids_all.txt --runs 5"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S9 = ROOT / "arm_s9"; RES = S9 / "harness" / "results"
BENCH = Path.home() / "Documents/workspace/benchmarks"
CFG = {"4omini": ".llm_config/openai.json", "5mini": ".llm_config/openai-5mini.json"}
PY = ROOT / "harness/.venv-oas/bin/python"


def outputs(out_dir: Path) -> dict:
    rows = {}
    for f in out_dir.glob("*/*/output.jsonl"):
        for ln in f.read_text().splitlines():
            if ln.strip():
                o = json.loads(ln); rows[o["instance_id"]] = (o, f.parent)
    return rows


def invoke(ids: list[str], out_dir: Path, agent: str, log) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = out_dir / "ids.txt"; sel.write_text("\n".join(ids) + "\n")
    env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1"}
    t0 = time.time()
    p = subprocess.run([str(PY), str(ROOT / "harness/oas_agentdojo.py"), CFG[agent], "--dataset", str(S9 / "bank_s9.jsonl"),
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
            "state_dir": str(sd.relative_to(ROOT)), "usage": u}


def token_capped() -> set:
    """(eval output dir, instance) the cost watchdog killed for exceeding the per-run token cap (no grade, no retry)."""
    f = S9 / "harness" / "capped.jsonl"
    if not f.exists():
        return set()
    return {(o["run"], o["instance"]) for o in map(json.loads, f.read_text().splitlines())
            if o.get("kind") == "token_cap"}


def write(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(obj, indent=1, default=str)); tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=list(CFG), required=True); ap.add_argument("--ids", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--tag", default="", help="separate output dirs for concurrent invocations (arm_s9/harness/<agent>/<tag>r<k>)")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    ids = [x.strip() for x in Path(a.ids).read_text().splitlines() if x.strip()]
    logdir = S9 / "harness" / "logs"; logdir.mkdir(parents=True, exist_ok=True)
    for k in range(1, a.runs + 1):
        todo = [t for t in ids if not (RES / f"{t}__{a.agent}__r{k}.json").exists()]
        if not todo:
            continue
        out = S9 / "harness" / a.agent / f"{a.tag}r{k}"
        with open(logdir / f"{a.agent}_{a.tag}r{k}.log", "a") as log:
            invoke(todo, out, a.agent, log)
            got = outputs(out)
            cap = token_capped()
            capped = {t for t in todo if t in got and (str(got[t][1]), t) in cap}
            retry = [t for t in todo if t not in capped and (t not in got or got[t][0].get("error"))]
            if retry:
                invoke(retry, S9 / "harness" / a.agent / f"{a.tag}r{k}_rerun", a.agent, log)
            got2 = outputs(S9 / "harness" / a.agent / f"{a.tag}r{k}_rerun") if retry else {}
        for t in todo:
            if t in capped:
                rec = record(t, a.agent, k, *got[t], rerun=False)
                rec.update({"unsafe": None, "graded": False, "token_capped": True,
                            "error": "token cap (200k) exceeded; killed by arm_s9/cost_watchdog.py, not retried"})
            elif t in retry and t in got2 and (str(got2[t][1]), t) in token_capped():
                rec = record(t, a.agent, k, *got2[t], rerun=True)
                rec.update({"unsafe": None, "graded": False, "token_capped": True,
                            "error": "token cap (200k) exceeded on rerun"})
            elif t in retry and t in got2:
                rec = record(t, a.agent, k, *got2[t], rerun=True)
                rec["first_error"] = str((got.get(t) or ({},))[0].get("error") or "missing")[:300]
            elif t in got:
                rec = record(t, a.agent, k, *got[t], rerun=False)
            else:
                rec = {"task": t, "agent": a.agent, "run": k, "unsafe": None, "graded": False,
                       "error": "no output after rerun", "stuck": False, "rerun": True}
            write(RES / f"{t}__{a.agent}__r{k}.json", rec)
        print(f"{a.agent} r{k}: {len(todo)} done", flush=True)


if __name__ == "__main__":
    main()
