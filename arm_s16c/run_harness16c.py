"""Step 16c Part A runner: arm_v08/run_harness.py (resumable; atomic per-(task, agent, run) results; endpoint loss =
re-queue, not an outcome; one rerun for other errors; watchdog caps) on the step-16b/16c harness
(harness/v16b/oas_agentdojo16b.py: agent as an unprivileged user, no network, limits, the task's date from
libclock.so.1, real files, archive / merge / forward tools, per-step states) and the 16b bank (arm_s16b/bank).
Agents:
  qwen   Qwen/Qwen3.5-9B on the cluster's vLLM endpoint (localhost:8000 via the tunnel), temperature 1.0 (as 13j);
  luna   gpt-6-luna (API defaults, as the 16b smoke);
  haiku  claude-haiku-5-5 (API defaults: adaptive thinking, effort medium; as 13j).
NPC gpt-4o-mini. Keys come from the repo's .env, read by this process only and handed to the harness subprocess.
No grading here (the result keeps pointers to the run's state and transcript; arm_s16c/grade16c.py grades).
  .venv/bin/python arm_s16c/run_harness16c.py --agent luna --root arm_s16c/runs --first 1 --last 5 [--ids <file>]"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arm_v08"))
import run_harness as B  # noqa: E402

BANK = ROOT / "arm_s16b/bank"


def env_key(name: str) -> str:
    if name == "OPENAI_API_KEY":   # step 23: group key, or the fallback if the group hit its spend limit (once per job)
        sys.path.insert(0, str(ROOT)); import openai_key  # noqa: E401
        return openai_key.get()
    for ln in (ROOT / ".env").read_text().splitlines():
        ln = ln.strip().removeprefix("export ")
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{name} not in .env")


def setup(root: Path) -> None:
    B.S10 = root; B.H = root / "harness"; B.RES = B.H / "results"
    B.ENDPOINT_ERR = __import__("re").compile(B.ENDPOINT_ERR.pattern + r"|RateLimit|\b429\b|Overloaded|\b529\b", 2)
    luna_cfg = B.H / ".luna.json"   # 0600, holds the key; removed when this process exits
    B.H.mkdir(parents=True, exist_ok=True)
    B.CFG.update({"qwen": ".llm_config/openai.json", "haiku": ".llm_config/openai.json", "luna": str(luna_cfg)})
    B.EXTRA.update({"haiku": ["--anthropic", "claude-haiku-5-5"], "luna": []})
    B.NAME.update({"qwen": "qwen3.5-9b", "haiku": "haiku5.5", "luna": "gpt-6-luna"})
    return luna_cfg


def invoke(ids, out_dir: Path, agent: str, bank: Path, log) -> None:
    import subprocess, time
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = out_dir / "ids.txt"; sel.write_text("\n".join(ids) + "\n")
    env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1", "OAS_WORKSPACE_ROOT": str(BANK),
           "OH16B_CONTEXT": str(BANK / "agent_context.json")}
    t0 = time.time()
    p = subprocess.run([str(B.PY), str(ROOT / "harness/v16b/oas_agentdojo16b.py"), B.CFG[agent], *B.EXTRA.get(agent, []),
                        "--dataset", str(BANK / "bank_16b_harness.jsonl"), "--split", "train", "--select", str(sel),
                        "--output-dir", str(out_dir), "--num-workers", os.environ.get("WORKERS", "3"), "--critic", "pass",
                        "--max-attempts", "1"], cwd=B.BENCH, env=env, stdout=log, stderr=subprocess.STDOUT)
    with open(out_dir / "invocations.jsonl", "a") as fh:
        fh.write(json.dumps({"n": len(ids), "start": t0, "end": time.time(), "rc": p.returncode}) + "\n")


def install_v20(B) -> None:
    """Step 20: the runner loop of harness/v16b/runner.py (a killed / cut / endpoint-lost run is an error, retried in a
    fresh folder up to 2 times, then listed as failed; final only after harness/v16b/run_check.py passes). The stored
    16c and 19 runs were made before this change, with arm_v08's loop."""
    sys.path.insert(0, str(ROOT / "harness/v16b"))
    import runner
    runner.install(B)


def record(t, agent, k, o, base, rerun) -> dict:
    sd = base / "agentdojo_state" / t
    u = json.loads((sd / "usage.json").read_text()) if (sd / "usage.json").exists() else {}
    err = o.get("error")
    done = not err and (sd / "post.json").exists() and (sd / "v16b/steps").exists()
    return {"task": t, "agent": agent, "run": k, "graded": done, "final": done, "error": (str(err)[:500] if err else
            None if done else "no final state"), "stuck": bool(err and "stuck" in str(err).lower()), "rerun": rerun,
            "state_dir": str(sd.relative_to(ROOT)), "traj_dir": str(base.relative_to(ROOT)), "usage": u}


if __name__ == "__main__":
    i = sys.argv.index("--root"); root = (ROOT / sys.argv[i + 1]).resolve(); del sys.argv[i:i + 2]
    cfg = setup(root)
    B.invoke, B.record = invoke, record
    install_v20(B)
    B.CTX.clear()
    os.environ["ANTHROPIC_API_KEY"] = env_key("ANTHROPIC_API_KEY")
    os.environ.update({"NPC_API_KEY": env_key("OPENAI_API_KEY"), "NPC_BASE_URL": "https://api.openai.com/v1",
                       "NPC_MODEL": "gpt-4o-mini"})
    agent = sys.argv[sys.argv.index("--agent") + 1]
    if agent == "luna":
        cfg.write_text(json.dumps({"model": "gpt-6-luna", "api_key": env_key("OPENAI_API_KEY")})); os.chmod(cfg, 0o600)
    if agent == "qwen":
        B.EXTRA["qwen"] = ["--model", "Qwen/Qwen3.5-9B", "--base-url", "http://localhost:8000/v1", "--api-key", "EMPTY",
                           "--temperature", "1.0"]
    if "--ids" not in sys.argv:
        sys.argv += ["--ids", str(ROOT / "arm_s16c/tasks.txt")]
    sys.argv += ["--bank", str(BANK / "bank_16b_harness.jsonl")]
    B.ROWS.clear()
    try:
        B.main()
    finally:
        if agent == "luna":   # only the luna runner owns the key file (another agent's runner must not remove it)
            cfg.unlink(missing_ok=True)
