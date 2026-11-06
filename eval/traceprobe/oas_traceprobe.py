"""Run converted TraceProbe rows (source = "traceprobe", eval/traceprobe/convert.py) on the OAS SDK-V1 harness: the plain
harness image (openagentsafety-agent-server:<sdk sha>), OpenHands default tools (terminal, file_editor, task tracker),
default.j2 prompt, fake-user loop and in-container evaluator call are the harness's own. On top of
harness/oas_agentdojo.py (agentdojo rows still go there; --model / --base-url / --api-key / --temperature work the
same), for traceprobe rows only:
  0. uses the plain harness image built from the SDK this process imports (plain_image());
  1. stages tp_files at their own absolute paths in the container (/srv/..., /secrets/..., /usr/..., /tmp/...);
  2. sets the conversation's iteration budget to the row's max_iterations (max_steps x 3);
  3. before the evaluator runs, writes the run's final agent response (the last agent message plus the finish
     message) to /tp_eval/final_response.txt and every tool observation (finish / think excluded) to /tp_eval/tool_outputs.txt, which the
     row's evaluator reads for response_* / tool_output_contains criteria;
  4. saves those two texts and usage.json (the agent-server's combined LLM metrics) under
     <output dir>/traceprobe_state/<instance>/.

  cd ~/Documents/workspace/benchmarks
  OPENHANDS_SUPPRESS_BANNER=1 ~/overnight-gmail-dojo/harness/.venv-oas/bin/python \
      ~/overnight-gmail-dojo/eval/traceprobe/oas_traceprobe.py .llm_config/openai.json \
      --dataset ~/overnight-gmail-dojo/eval/traceprobe/smoke.jsonl --split train --output-dir <dir> \
      --num-workers 1 --critic pass --max-attempts 1 --max-iterations 30"""
import json, shlex, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import oas_agentdojo as A  # noqa: E402  (sets R.OpenAgentSafetyEvaluation to the agentdojo adapter)
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent  # noqa: E402

R = A.R
EVAL_DIR = "/tp_eval"


def is_tp(data: dict) -> bool:
    return data.get("source") == "traceprobe"


def _text(content) -> str:
    out = []
    for c in content or []:
        t = getattr(c, "text", None)
        if t is None and isinstance(c, dict):
            t = c.get("text")
        if t:
            out.append(str(t))
    return "\n".join(out)


def extract(events) -> tuple[str, str]:
    """(final agent response, all tool outputs) of a run."""
    last_msg, finish, tools = "", "", []
    for e in events:
        if isinstance(e, MessageEvent) and e.source == "agent":
            last_msg = _text(e.llm_message.content) or last_msg
        elif isinstance(e, ActionEvent) and type(e.action).__name__ == "FinishAction":
            finish = str(getattr(e.action, "message", "") or "")
        elif isinstance(e, ObservationEvent):
            if getattr(e, "tool_name", "") in ("finish", "think"):   # not tool output: finish echoes the reply
                continue
            try:
                tools.append(_text(e.observation.to_llm_content))
            except Exception:  # noqa: BLE001
                tools.append(str(e.observation))
    return "\n".join(x for x in (last_msg, finish) if x), "\n".join(tools)


def upload_text(ws, text: str, dest: str, tmp: Path):
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text)
    parent = dest.rsplit("/", 1)[0] or "/"
    ws.execute_command(f"mkdir -p {shlex.quote(parent)}", timeout=30)
    res = ws.file_upload(source_path=str(tmp), destination_path=dest)
    if not getattr(res, "success", False):
        raise RuntimeError(f"upload of {dest} failed: {res}")


def plain_image() -> str:
    """openagentsafety-agent-server:<sha of the SDK this process imports>: the plain harness image (no AgentDojo
    layer). The base harness would pick the image of the benchmarks repo's vendored SDK, whose agent-server does not
    accept this SDK's tool registration (500: register_tool(...) only accepts ...)."""
    tag = f"openagentsafety-agent-server:{A.sdk_commit()}"
    if not A.check_image_exists(tag):
        raise RuntimeError(f"{tag} not built (harness/build_images.sh builds it)")
    return tag


class TraceProbeOASEvaluation(R.OpenAgentSafetyEvaluation):
    def prepare_workspace(self, instance, resource_factor=1, forward_env=None):
        if not is_tp(instance.data):
            return super().prepare_workspace(instance, resource_factor, forward_env)
        R.build_workspace_image = plain_image
        try:
            ws = super().prepare_workspace(instance, resource_factor, forward_env)
        finally:
            R.build_workspace_image = A._BASE_BUILD
        d = Path(self.metadata.eval_output_dir) / "traceprobe_state" / instance.id
        for i, (path, content) in enumerate(json.loads(instance.data["tp_files"]).items()):
            upload_text(ws, content, path, d / "files" / str(i))
        miss = [p for p in json.loads(instance.data["tp_files"])
                if ws.execute_command(f"test -f {shlex.quote(p)}", timeout=30).exit_code != 0]
        if miss:
            raise RuntimeError(f"files not staged: {miss}")
        return ws

    def evaluate_instance(self, instance, workspace):
        if not is_tp(instance.data):
            return super().evaluate_instance(instance, workspace)
        events, convs = [], []
        conv_cls, run_eval = R.Conversation, R.run_evaluation_in_container
        d = Path(self.metadata.eval_output_dir) / "traceprobe_state" / instance.id
        budget = int(instance.data.get("max_iterations") or 0)

        def conv(**kw):
            kw["callbacks"] = list(kw.get("callbacks") or []) + [events.append]
            if budget:
                kw["max_iteration_per_run"] = budget
            convs.append(conv_cls(**kw))
            return convs[-1]

        def ev(workspace, evaluator_code, **kw):
            resp, tools = extract(events)
            (d / "final_response.txt").write_text(resp)
            (d / "tool_outputs.txt").write_text(tools)
            upload_text(workspace, resp, f"{EVAL_DIR}/final_response.txt", d / "up_resp")
            upload_text(workspace, tools, f"{EVAL_DIR}/tool_outputs.txt", d / "up_tools")
            return run_eval(workspace=workspace, evaluator_code=evaluator_code, **kw)

        R.Conversation, R.run_evaluation_in_container = conv, ev
        try:
            out = super().evaluate_instance(instance, workspace)
        finally:
            R.Conversation, R.run_evaluation_in_container = conv_cls, run_eval
        try:
            m = convs[-1].conversation_stats.get_combined_metrics()
            (d / "usage.json").write_text(json.dumps({"accumulated_cost": m.accumulated_cost,
                                                      "token_usage": m.accumulated_token_usage.model_dump()
                                                      if m.accumulated_token_usage else None}))
        except Exception as e:  # noqa: BLE001
            R.logger.warning(f"traceprobe usage not read: {e}")
        return out


R.OpenAgentSafetyEvaluation = TraceProbeOASEvaluation

if __name__ == "__main__":
    sys.argv[1:] = A.agent_endpoint(sys.argv[1:])
    R.main()
