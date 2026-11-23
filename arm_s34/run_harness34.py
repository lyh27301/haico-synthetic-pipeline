"""Step 34 runner (copy of arm_s26_twins/run_harness26.py; bank folder from $BANK34, default arm_s34/bank (the -v34 tasks), arm_s34/twins for their twins; the OpenAI key is chosen once per job by openai_key.py and
the job is named in logs/openai_key.jsonl, so fallback-key runs can be told apart). Step 21 text follows.
Step 21 runner: the step-16c runner (arm_s16c/run_harness16c.py: setup, record) with the step-20 loop
(harness/v16b/runner.py: fresh folder per attempt, final only after harness/v16b/run_check.py, up to 2 retries, then
failed) on the step-21 bank (arm_s21/bank: 43 tasks of the first training set, built by arm_s21/make_bank.py).
Agents (as 16c / 19; NPC gpt-4o-mini, stateless chat_npc, unchanged):
  luna    gpt-6-luna (API defaults)                      haiku   claude-haiku-5-5 (API defaults)
  qwen    Qwen/Qwen3.5-9B, cluster vLLM on localhost:8000, temperature 1.0
  qwen35  Qwen/Qwen3.5-35B-A3B, cluster vLLM on localhost:8001, temperature 1.0
Layout (a later top-up to 5 runs uses the same roots with --first 4 --last 5; results are keyed task__agent__r<k>):
  arm_s21/runs (luna, haiku), arm_s21/qwen9b, arm_s21/qwen35; attempts in <root>/harness/<agent>/r<k>_a<n>/.
  WORKERS=4 .venv/bin/python arm_s21/run_harness21.py --agent luna --root arm_s21/runs --first 1 --last 3 [--ids f]"""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16c"), str(ROOT / "arm_v08")]
import run_harness16c as H  # noqa: E402

BANK = ROOT / os.environ.get("BANK34", "arm_s34/bank")
PORT = {"qwen": 8000, "qwen35": 8001}


def invoke(ids, out_dir: Path, agent: str, bank: Path, log) -> None:
    B = H.B
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = out_dir / "ids.txt"; sel.write_text("\n".join(ids) + "\n")
    env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1", "OAS_WORKSPACE_ROOT": str(BANK),
           "OH16B_CONTEXT": str(BANK / "agent_context_34.json")}
    t0 = time.time()
    p = subprocess.run([str(B.PY), str(ROOT / "harness/v16b/oas_agentdojo16b.py"), B.CFG[agent], *B.EXTRA.get(agent, []),
                        "--dataset", str(BANK / "bank_34_harness.jsonl"), "--split", "train", "--select", str(sel),
                        "--output-dir", str(out_dir), "--num-workers", os.environ.get("WORKERS", "3"), "--critic", "pass",
                        "--max-attempts", "1"], cwd=B.BENCH, env=env, stdout=log, stderr=subprocess.STDOUT)
    with open(out_dir / "invocations.jsonl", "a") as fh:
        fh.write(json.dumps({"n": len(ids), "start": t0, "end": time.time(), "rc": p.returncode}) + "\n")


if __name__ == "__main__":
    i = sys.argv.index("--root"); root = (ROOT / sys.argv[i + 1]).resolve(); del sys.argv[i:i + 2]
    cfg = H.setup(root)
    B = H.B
    B.invoke, B.record = invoke, H.record
    H.install_v20(B)
    B.CTX.clear()
    agent = sys.argv[sys.argv.index("--agent") + 1]
    B.CFG["qwen35"] = ".llm_config/openai.json"; B.NAME["qwen35"] = "qwen3.5-35b-a3b"
    for a, model in (("qwen", "Qwen/Qwen3.5-9B"), ("qwen35", "Qwen/Qwen3.5-35B-A3B")):
        B.EXTRA[a] = ["--model", model, "--base-url", f"http://localhost:{PORT[a]}/v1", "--api-key", "EMPTY",
                      "--temperature", "1.0"]
    sys.path.insert(0, str(ROOT)); import openai_key  # noqa: E401,E702
    openai_key.get(f"run_harness34 --agent {agent} --root {root.relative_to(ROOT)}")   # names the job in the key log
    os.environ["ANTHROPIC_API_KEY"] = H.env_key("ANTHROPIC_API_KEY") if agent == "haiku" else "unused"
    os.environ.update({"NPC_API_KEY": H.env_key("OPENAI_API_KEY"), "NPC_BASE_URL": "https://api.openai.com/v1",
                       "NPC_MODEL": "gpt-4o-mini"})
    if agent in PORT:   # the runner's outage bookkeeping (B.outages / wait_endpoint) reads this tree's guard files
        os.environ["QWEN_BASE_URL"] = f"http://localhost:{PORT[agent]}/v1"
    if agent == "luna":
        cfg.write_text(json.dumps({"model": "gpt-6-luna", "api_key": H.env_key("OPENAI_API_KEY")})); os.chmod(cfg, 0o600)
    if "--ids" not in sys.argv:
        sys.argv += ["--ids", str(BANK / "tasks.txt")]
    sys.argv += ["--bank", str(BANK / "bank_34_harness.jsonl")]
    B.ROWS.clear()
    try:
        B.main()
    finally:
        if agent == "luna":
            cfg.unlink(missing_ok=True)
