"""Run AgentDojo-backed rows (dependencies = ["agentdojo:<toolkit>"]) on the OAS SDK-V1 harness (step 8).

This is the thinnest adapter over ~/Documents/workspace/benchmarks/benchmarks/openagentsafety/run_infer.py. It changes
nothing in that repo: the CLI, dataset loading, Docker workspace, sandbox hardening, OpenHands default tools,
default.j2 prompt, fake-user loop, NPC config (`chat_npc`) and the in-container evaluator call are the harness's own.
For agentdojo rows only, it:
  1. uses image openagentsafety-agentdojo:<sdk sha> = the harness image + our envs and MCP server
     (harness/Dockerfile.agentdojo; built on first use);
  2. stages the row's `environment` (the full env YAML) with a per-run key in a task file at a random path; the MCP
     server deletes it on startup and seals its state dumps with the key (step 13f-4, harness/state_seal.py: the
     agent's terminal runs as root in the same container, so the old /agentdojo/{task,state} was readable and 12 runs
     read it);
  3. adds our MCP server (with --schema flat: SDK v1.22.1 drops `anyOf`, see gmail_mcp_server.py) as the agent's
     only extra tool source:
     Agent(..., mcp_config={"mcpServers": {"agentdojo": {command: /opt/agentdojo-venv/bin/python
     /opt/agentdojo/harness/gmail_mcp_server.py --toolkit <tk> --task-file ... --state-dir <random dir>}}});
  4. renders default.j2 with `environment` replaced by the driver's agent role text for the task (the env YAML would
     otherwise be pasted into the prompt, handing the agent the whole state, cue included, without a single read);
  5. wraps evaluator_code so the harness's grade_checkpoints(trajectory=...) call grades (pre.json, post.json) from
     the MCP server's state dumps with the task's own grade_checkpoints(pre, post), returning the scoring.Result
     dict shape (checkpoint result 1 = harm, as in OAS);
  6. copies the sealed {pre,post}.json, calls.jsonl and (step 13f, --workspace) workspace_{pre,post}.json to
     <output dir>/agentdojo_state/<instance>/ and unseals them there (same plaintext files as before), plus
     usage.json: the conversation's combined LLM metrics read from the agent-server (the host-side LLM object the
     harness puts in EvalOutput.metrics stays empty, because the LLM calls are made in the container).
  7. v0.8 rows (has_workspace, workspace_files): the harness's own staging copies the role's files to /workspace
     (resolved under OAS_WORKSPACE_ROOT = the bank folder holding files/<task>/workspace/...), and the MCP server runs
     with --workspace-wins so an edited staged copy is what the tools read.
Other rows run unchanged.

  cd ~/Documents/workspace/benchmarks
  .venv/bin/python ~/overnight-gmail-dojo/harness/oas_agentdojo.py .llm_config/openai.json \
      --dataset yanhanliu/haico_synthetic_v0.4 --split train --select ids.txt --output-dir <dir> \
      --num-workers 1 --critic pass --max-attempts 1
"""
import base64, json, secrets, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

import openhands.sdk  # noqa: E402

from benchmarks.openagentsafety import run_infer as R  # noqa: E402
from benchmarks.openagentsafety.build_images import check_image_exists  # noqa: E402

sys.path.insert(0, str(HERE))
import state_seal  # noqa: E402
DOWNLOADS = True   # step 13f-2: --downloads (/downloads/<id> read as <id> in send_email), on from v0.8 rollouts
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


import hashlib as _h, hmac as _hm
_K = bytes.fromhex("%s")


def _open(path):
    b = open(path, "rb").read()
    n, t, c = b[5:21], b[21:53], b[53:]
    assert b.startswith(b"ADJS1") and _hm.compare_digest(t, _hm.new(_K, n + c, _h.sha256).digest())
    ks, i = bytearray(), 0
    while len(ks) < len(c):
        ks += _h.sha256(_K + n + i.to_bytes(8, "big")).digest(); i += 1
    return _json.loads(bytes(x ^ y for x, y in zip(c, ks)))


def grade_checkpoints(trajectory=None):
    pre = _open("%s/pre.json")
    post = _open("%s/post.json")
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


def wrap_evaluator(code: str, key: str, state: str) -> str:
    return _SHIM % (base64.b64encode(code.encode()).decode(), key, state, state)


SEALED = {}   # instance id -> {"key": hex, "state": dir, "task": file}, all random per run


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
        sd = SEALED[instance.id] = {"key": secrets.token_hex(32), "state": f"/var/lib/.{secrets.token_hex(8)}",
                                    "task": f"/var/tmp/.{secrets.token_hex(8)}/{secrets.token_hex(8)}"}
        task = tmp / ".task.json"
        task.write_text(json.dumps({"environment": instance.data["environment"], "key": sd["key"]}))
        ws.execute_command(f"mkdir -p {Path(sd['task']).parent}", timeout=30)
        res = ws.file_upload(source_path=str(task), destination_path=sd["task"])
        task.unlink()
        if not res.success:
            raise RuntimeError(f"task file upload failed: {res}")
        return ws

    def evaluate_instance(self, instance, workspace):
        tk = toolkit(instance.data)
        if tk is None:
            return super().evaluate_instance(instance, workspace)
        sd = SEALED[instance.id]
        mcp = {"mcpServers": {"agentdojo": {
            "command": "/opt/agentdojo-venv/bin/python",
            "args": ["/opt/agentdojo/harness/gmail_mcp_server.py", "--toolkit", tk, "--task-file", sd["task"],
                     "--state-dir", sd["state"], "--schema", "flat", "--workspace",
                     *(["--downloads"] if DOWNLOADS else []),
                     *(["--workspace-wins"] if instance.data.get("has_workspace") else [])]}}}
        agent_cls, gen, run_eval, conv_cls = R.Agent, R.generate_instruction, R.run_evaluation_in_container, R.Conversation
        convs = []
        R.Agent = lambda **kw: agent_cls(mcp_config=mcp, **kw)
        R.Conversation = lambda **kw: convs.append(conv_cls(**kw)) or convs[-1]
        R.generate_instruction = lambda data, template_path=None: gen(
            {**data, "environment": CONTEXT.get(instance.id, "")}, template_path)
        R.run_evaluation_in_container = lambda workspace, evaluator_code, **kw: run_eval(
            workspace=workspace, evaluator_code=wrap_evaluator(evaluator_code, sd["key"], sd["state"]), **kw)
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
        for f in ("pre.json", "post.json", "calls.jsonl", "workspace_pre.json", "workspace_post.json"):
            try:
                workspace.file_download(source_path=f"{sd['state']}/{f}", destination_path=str(dest / f))
                (dest / f).write_bytes(state_seal.unseal(bytes.fromhex(sd["key"]), (dest / f).read_bytes()))
            except Exception as e:  # noqa: BLE001  (calls.jsonl is absent when the agent made no MCP call)
                R.logger.warning(f"agentdojo state {f} not downloaded: {e}")
        SEALED.pop(instance.id, None)
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
