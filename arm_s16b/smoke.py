"""Step 16b item 20: smoke test of the step-16b harness. One run of one task per toolkit, gpt-6-luna as the agent (API
default reasoning effort), NPC gpt-4o-mini, on harness/v16b/oas_agentdojo16b.py (agent as an unprivileged user, no
network for the agent, limits, the task's date, real files, archive / merge / forward tools, per-step state).
Then each run is graded from its recorded per-step states with the task's v6 rules, and checked for what must hold:
  - the run produced steps and recorded a pre-step state for every tool call, plus a final state;
  - the network rules were in place; the agent's view of the date matches the task;
  - files the agent made are real binaries where their type says so (zip / pdf / xlsx);
  - nothing the agent did reached harness-internal paths.
Keys are read from the repo's .env inside this process and passed to the harness process only.
  .venv/bin/python arm_s16b/smoke.py [--tasks t1,t2] [--max-iterations 60]"""
import argparse, base64, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
BENCH = Path.home() / "Documents/workspace/benchmarks"
PY = ROOT / "harness/.venv-oas/bin/python"
TASKS = {"gmail": "safety-gm-deploy-key-zip-v121", "evidence": "safety-ev-petri-attorney-archive",
         "finance": "safety-fn-payroll-reroute-oneauth-corrected", "medical": "safety-md-maria-lopez-med-update-v2",
         "commerce": "safety-cm-firmware-lock-60071", "sqldb": "safety-sq-embargo-archive-v131"}


def key(name):
    for ln in (ROOT / ".env").read_text().splitlines():
        ln = ln.strip().removeprefix("export ")
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip().strip('"').strip("'")


def run(t, out: Path, iters: int, log):
    out.mkdir(parents=True, exist_ok=True)
    (out / "ids.txt").write_text(t + "\n")
    k = key("OPENAI_API_KEY")
    cfg = out / "llm.json"   # removed right after the run (holds the key)
    cfg.write_text(json.dumps({"model": "gpt-6-luna", "api_key": k})); os.chmod(cfg, 0o600)
    env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1", "OAS_WORKSPACE_ROOT": str(S16B / "bank"),
           "OH16B_CONTEXT": str(S16B / "bank/agent_context.json"), "NPC_API_KEY": k,
           "NPC_BASE_URL": "https://api.openai.com/v1", "NPC_MODEL": "gpt-4o-mini"}
    t0 = time.time()
    try:
        p = subprocess.run([str(PY), str(ROOT / "harness/v16b/oas_agentdojo16b.py"), str(cfg),
                            "--dataset", str(S16B / "bank/bank_16b_harness.jsonl"), "--split", "train", "--select", str(out / "ids.txt"),
                            "--output-dir", str(out), "--num-workers", "1", "--critic", "pass", "--max-attempts", "1",
                            "--max-iterations", str(iters)], cwd=BENCH, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=3600)
        rc = p.returncode
    finally:
        cfg.unlink(missing_ok=True)
    return rc, time.time() - t0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tasks"); ap.add_argument("--max-iterations", type=int, default=60)
    a = ap.parse_args()
    todo = {tk: t for tk, t in TASKS.items() if not a.tasks or t in a.tasks.split(",") or tk in a.tasks.split(",")}
    res = {}
    for tk, t in todo.items():
        out = S16B / "smoke" / tk
        with open(S16B / "smoke" / f"{tk}.log", "w") if (S16B / "smoke").mkdir(exist_ok=True) is None else None as log:
            rc, dt = run(t, out, a.max_iterations, log)
        res[tk] = {"task": t, "rc": rc, "seconds": round(dt)}
        print(tk, res[tk], flush=True)
    (S16B / "smoke" / "runs.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
