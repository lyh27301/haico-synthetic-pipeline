"""v0.9: Anthropic agents (Claude Haiku 5.5, Claude Sonnet 5.5) on the v0.8 harness. This is arm_v08/run_harness.py with
two new agents and its own output tree; everything else (bank, scaffold, NPC on gpt-4o-mini, temperature, step / token
caps, rerun-once for errors, re-queue on endpoint loss, atomic per-(task, agent, run) results) is the v0.8 runner's.
  - agent LLM: harness/oas_agentdojo.py --anthropic <model id> (request settings documented there);
  - ANTHROPIC_API_KEY is read from the repo's .env by this process only and handed to the harness subprocess's
    environment; it is never exported in a shell;
  - --root: output tree (default arm_v09; the smoke uses arm_v09/smoke) -> <root>/harness/{results,logs,<agent>/...}.
  NPC_API_KEY=... NPC_BASE_URL=https://api.openai.com/v1 NPC_MODEL=gpt-4o-mini WORKERS=6 \\
  .venv/bin/python arm_v09/run_harness.py --agent haiku --ids <ids> --first 1 --last 5 [--root arm_v09/smoke]"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arm_v08"))
import run_harness as B  # noqa: E402

MODEL = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
NAME = {"haiku": "haiku5.5", "sonnet": "sonnet5.5"}   # agent name in result files / dirs


def env_key(name: str) -> str:
    for ln in (ROOT / ".env").read_text().splitlines():
        ln = ln.strip()
        if ln.startswith("export "):
            ln = ln[7:]
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{name} not in .env")


def setup(root: Path) -> None:
    B.S10 = root; B.H = root / "harness"; B.RES = B.H / "results"
    # API-side transient failures (rate limit, overload) are re-queued like an endpoint loss, not counted as run errors
    B.ENDPOINT_ERR = re.compile(B.ENDPOINT_ERR.pattern + r"|RateLimit|\b429\b|Overloaded|\b529\b", re.I)
    for a, m in MODEL.items():
        B.CFG[a] = ".llm_config/openai.json"   # positional config; replaced wholesale by --anthropic
        B.EXTRA[a] = ["--anthropic", m]
        B.NAME[a] = NAME[a]
    os.environ["ANTHROPIC_API_KEY"] = env_key("ANTHROPIC_API_KEY")
    # NPC on gpt-4o-mini as in v0.8; its key also comes from .env (so no shell ever sources .env)
    os.environ.setdefault("NPC_API_KEY", env_key("OPENAI_API_KEY"))
    os.environ.setdefault("NPC_BASE_URL", "https://api.openai.com/v1"); os.environ.setdefault("NPC_MODEL", "gpt-4o-mini")


if __name__ == "__main__":
    root = ROOT / "arm_v09"
    if "--root" in sys.argv:
        i = sys.argv.index("--root"); root = (ROOT / sys.argv[i + 1]).resolve(); del sys.argv[i:i + 2]
    setup(root)
    if "--bank" not in sys.argv:
        sys.argv += ["--bank", str(ROOT / "arm_v08/bank_v08.jsonl")]
    B.main()
