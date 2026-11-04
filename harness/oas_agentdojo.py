"""Run AgentDojo-backed rows (dependencies = ["agentdojo:<toolkit>"]) on the OAS SDK-V1 harness (step 8).

This is the thinnest adapter over ~/Documents/workspace/benchmarks/benchmarks/openagentsafety/run_infer.py. It changes
nothing in that repo: the CLI, dataset loading, Docker workspace, sandbox hardening, OpenHands default tools,
default.j2 prompt, fake-user loop, NPC config (`chat_npc`) and the in-container evaluator call are the harness's own.
For agentdojo rows only, it:
  1. uses image openagentsafety-agentdojo:<sdk sha> = the harness image + our envs and MCP server
     (harness/Dockerfile.agentdojo; built on first use);
  2. stages the row's `environment` (the full env YAML) at /agentdojo/task/environment.yaml;
  3. adds our MCP server (with --schema flat: SDK v1.22.1 drops `anyOf`, see gmail_mcp_server.py) as the agent's
     only extra tool source:
     Agent(..., mcp_config={"mcpServers": {"agentdojo": {command: /opt/agentdojo-venv/bin/python
     /opt/agentdojo/harness/gmail_mcp_server.py --toolkit <tk> --env ... --state-dir /agentdojo/state}}});
  4. renders default.j2 with `environment` replaced by the driver's agent role text for the task (the env YAML would
     otherwise be pasted into the prompt, handing the agent the whole state, cue included, without a single read);
  5. wraps evaluator_code so the harness's grade_checkpoints(trajectory=...) call grades (pre.json, post.json) from
     the MCP server's state dumps with the task's own grade_checkpoints(pre, post), returning the scoring.Result
     dict shape (checkpoint result 1 = harm, as in OAS);
  6. copies /agentdojo/state/{pre,post}.json and calls.jsonl to <output dir>/agentdojo_state/<instance>/, plus
     usage.json: the conversation's combined LLM metrics read from the agent-server (the host-side LLM object the
     harness puts in EvalOutput.metrics stays empty, because the LLM calls are made in the container).
Other rows run unchanged.

  cd ~/Documents/workspace/benchmarks
  .venv/bin/python ~/overnight-gmail-dojo/harness/oas_agentdojo.py .llm_config/openai.json \
      --dataset yanhanliu/haico_synthetic_v0.4 --split train --select ids.txt --output-dir <dir> \
      --num-workers 1 --critic pass --max-attempts 1
"""
import base64, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

import openhands.sdk  # noqa: E402

from benchmarks.openagentsafety import run_infer as R  # noqa: E402
from benchmarks.openagentsafety.build_images import check_image_exists  # noqa: E402

STATE = "/agentdojo/state"
TASK_ENV = "/agentdojo/task/environment.yaml"
CONTEXT = json.loads((HERE / "agent_context.json").read_text())   # instance_id -> driver agent role text

_SHIM = '''
import base64 as _b64, json as _json
_ns = {}
exec(_b64.b64decode("%s").decode(), _ns)


class _Result:
    def __init__(self, d):
        self.d = d

    def to_dict(self):
        return self.d


def grade_checkpoints(trajectory=None):
    pre = _json.load(open("%s/pre.json"))
    post = _json.load(open("%s/post.json"))
    r = _ns["grade_checkpoints"](pre, post)
    cps = [{"total": 1, "result": int(bool(v))} for v in r["checkpoints"].values()]
    return _Result({"checkpoints": cps,
                    "final_score": {"total": len(cps), "result": sum(c["result"] for c in cps)},
                    "agentdojo": {"unsafe": bool(r["unsafe"]), "checkpoints": r["checkpoints"]}})
'''


def toolkit(data: dict) -> str | None:
    for d in data.get("dependencies") or []:
        if str(d).startswith("agentdojo:"):
            return str(d).split(":", 1)[1]
    return None


_BASE_BUILD = R.build_workspace_image


def sdk_commit() -> str:
    """Short sha of the SDK this process imports (harness/sdk-v1.22.1), which the agent-server image must match."""
    d = Path(openhands.sdk.__file__).resolve().parents[2]
    return subprocess.run(["git", "rev-parse", "--short=9", "HEAD"], cwd=d, capture_output=True, text=True,
                          check=True).stdout.strip()


def agentdojo_image() -> str:
    """openagentsafety-agentdojo:<sha>, built by harness/build_images.sh (agent-server from this SDK + our envs)."""
    tag = f"openagentsafety-agentdojo:{sdk_commit()}"
    if not check_image_exists(tag):
        subprocess.run(["bash", str(HERE / "build_images.sh")], check=True)
    return tag


def wrap_evaluator(code: str) -> str:
    return _SHIM % (base64.b64encode(code.encode()).decode(), STATE, STATE)


class AgentDojoOASEvaluation(R.OpenAgentSafetyEvaluation):
    def prepare_workspace(self, instance, resource_factor=1, forward_env=None):
        tk = toolkit(instance.data)
        if tk is None:
            return super().prepare_workspace(instance, resource_factor, forward_env)
        R.build_workspace_image = agentdojo_image
        try:
            ws = super().prepare_workspace(instance, resource_factor, forward_env)
        finally:
            R.build_workspace_image = _BASE_BUILD
        tmp = Path(self.metadata.eval_output_dir) / "agentdojo_state" / instance.id
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "environment.yaml").write_text(instance.data["environment"])
        ws.execute_command(f"mkdir -p {STATE} {Path(TASK_ENV).parent}", timeout=30)
        res = ws.file_upload(source_path=str(tmp / "environment.yaml"), destination_path=TASK_ENV)
        if not res.success:
            raise RuntimeError(f"environment.yaml upload failed: {res}")
        return ws

    def evaluate_instance(self, instance, workspace):
        tk = toolkit(instance.data)
        if tk is None:
            return super().evaluate_instance(instance, workspace)
        mcp = {"mcpServers": {"agentdojo": {
            "command": "/opt/agentdojo-venv/bin/python",
            "args": ["/opt/agentdojo/harness/gmail_mcp_server.py", "--toolkit", tk, "--env", TASK_ENV,
                     "--state-dir", STATE, "--schema", "flat"]}}}
        agent_cls, gen, run_eval, conv_cls = R.Agent, R.generate_instruction, R.run_evaluation_in_container, R.Conversation
        convs = []
        R.Agent = lambda **kw: agent_cls(mcp_config=mcp, **kw)
        R.Conversation = lambda **kw: convs.append(conv_cls(**kw)) or convs[-1]
        R.generate_instruction = lambda data, template_path=None: gen(
            {**data, "environment": CONTEXT.get(instance.id, "")}, template_path)
        R.run_evaluation_in_container = lambda workspace, evaluator_code, **kw: run_eval(
            workspace=workspace, evaluator_code=wrap_evaluator(evaluator_code), **kw)
        try:
            out = super().evaluate_instance(instance, workspace)
        finally:
            R.Agent, R.generate_instruction, R.run_evaluation_in_container = agent_cls, gen, run_eval
            R.Conversation = conv_cls
        dest = Path(self.metadata.eval_output_dir) / "agentdojo_state" / instance.id
        try:
            m = convs[-1].conversation_stats.get_combined_metrics()
            (dest / "usage.json").write_text(json.dumps({"accumulated_cost": m.accumulated_cost,
                                                         "token_usage": m.accumulated_token_usage.model_dump()
                                                         if m.accumulated_token_usage else None}))
        except Exception as e:  # noqa: BLE001
            R.logger.warning(f"agentdojo usage not read: {e}")
        for f in ("pre.json", "post.json", "calls.jsonl"):
            try:
                workspace.file_download(source_path=f"{STATE}/{f}", destination_path=str(dest / f))
            except Exception as e:  # noqa: BLE001  (calls.jsonl is absent when the agent made no MCP call)
                R.logger.warning(f"agentdojo state {f} not downloaded: {e}")
        return out


R.OpenAgentSafetyEvaluation = AgentDojoOASEvaluation


def agent_endpoint(argv: list[str]) -> list[str]:
    """Step 11: --model / --base-url / --api-key override the agent LLM of the positional LLM config (OpenAI-compatible
    endpoint, e.g. vLLM). They are consumed here and written into a derived config that replaces the positional path;
    the NPC (NPC_* env) is untouched. The agent's LLM calls are made inside the Docker workspace, so a localhost base
    URL is rewritten to host.docker.internal (an SSH tunnel on the Mac is reachable from the container that way). A
    model without a litellm provider prefix gets openai/ so litellm treats the endpoint as OpenAI-compatible.
    Step 12: --temperature sets the agent's sampling temperature explicitly (otherwise the provider default applies:
    1.0 for OpenAI, the model's generation_config for vLLM)."""
    import argparse, os, re, tempfile
    p = argparse.ArgumentParser(add_help=False)
    for a in ("--model", "--base-url", "--api-key"):
        p.add_argument(a)
    p.add_argument("--temperature", type=float)
    ov, rest = p.parse_known_args(argv)
    if not (ov.model or ov.base_url or ov.api_key or ov.temperature is not None):
        return argv
    i = next(k for k, x in enumerate(rest) if x.endswith(".json") and not x.startswith("-"))
    cfg = json.loads(Path(rest[i]).read_text())
    if ov.base_url:
        cfg["base_url"] = re.sub(r"//(localhost|127\.0\.0\.1)([:/])", r"//host.docker.internal\2", ov.base_url)
    if ov.model:
        cfg["model"] = ov.model if not ov.base_url or ov.model.startswith("openai/") else f"openai/{ov.model}"
    if ov.api_key or ov.base_url:
        cfg["api_key"] = ov.api_key or "EMPTY"
    if ov.temperature is not None:
        cfg["temperature"] = ov.temperature
    fd, path = tempfile.mkstemp(prefix="llm_agent_", suffix=".json"); os.close(fd)
    Path(path).write_text(json.dumps(cfg))
    print(f"[oas_agentdojo] agent LLM: model={cfg['model']} base_url={cfg.get('base_url')} "
          f"temperature={cfg.get('temperature')}", file=sys.stderr)
    return rest[:i] + [path] + rest[i + 1:]


if __name__ == "__main__":
    sys.argv[1:] = agent_endpoint(sys.argv[1:])
    R.main()
