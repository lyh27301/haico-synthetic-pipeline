"""Tool calls the agent framework rejected before execution, recovered from a conversation history (the `history` of
run_infer's output.critic_attempt_1.jsonl). They never reach the MCP server, so calls.jsonl does not have them.
Two kinds, one event type ("rejected_call") with the raw call text:
  - schema_rejected: an AgentErrorEvent (extra / missing argument, unknown tool name, ...). The ActionEvent with the same
    tool_call_id carries the model's tool_call: name + the raw `arguments` string.
  - leaked_markup: an agent message whose content / reasoning holds tool-call markup (`<function=NAME>` +
    `<parameter=k>v</parameter>`, or `<tool_call>`) that no parser turned into a call.
`args` is the parsed argument dict when the raw text parses (JSON, or the markup's parameters), else None.

  from rejected_calls import extract; extract(history) -> [{"event": "rejected_call", "kind", "name", "raw", "args",
                                                            "error"}]
  write(history, state_dir) -> writes <state_dir>/rejected_calls.jsonl (one line per call; empty file if none)"""
import json, re
from pathlib import Path

FUNC = re.compile(r"<function=([^>\n]*)>(.*?)(?:</function>|$)", re.S)
PARAM = re.compile(r"<parameter=([^>\n]*)>\s*(.*?)\s*</parameter>", re.S)
INLINE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def _json_args(raw):
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else None
    except (TypeError, ValueError):
        return None


def _markup_args(body):
    ps = {k.strip(): v for k, v in PARAM.findall(body)}
    if not ps:   # `<function=x> a=1 b="c"` (parameters inline)
        ps = {k: v for k, v in INLINE.findall(body)}
    return ps or None


def _text(e) -> str:
    m = e.get("llm_message") or {}
    parts = [c.get("text", "") for c in m.get("content") or [] if isinstance(c, dict)]
    return "\n".join(parts + [str(m.get("reasoning_content") or "")])


def extract(history: list) -> list[dict]:
    calls = {}
    for e in history:
        c = e.get("tool_call")
        if isinstance(c, dict) and c.get("id"):
            calls[c["id"]] = c
    out = []
    for e in history:
        k = e.get("kind")
        if k == "AgentErrorEvent":
            c = calls.get(e.get("tool_call_id")) or {}
            raw = c.get("arguments")
            out.append({"event": "rejected_call", "kind": "schema_rejected", "name": c.get("name") or e.get("tool_name"),
                        "raw": raw, "args": _json_args(raw), "error": str(e.get("error"))[:600],
                        "tool_call_id": e.get("tool_call_id"), "timestamp": e.get("timestamp")})
        elif k == "MessageEvent" and e.get("source") == "agent":
            t = _text(e)
            for name, body in FUNC.findall(t):
                out.append({"event": "rejected_call", "kind": "leaked_markup", "name": name.strip(),
                            "raw": f"<function={name}>{body}", "args": _markup_args(body), "error": "unparsed tool-call markup",
                            "tool_call_id": None, "timestamp": e.get("timestamp")})
            if "<tool_call>" in t and not FUNC.search(t):
                out.append({"event": "rejected_call", "kind": "leaked_markup", "name": None, "raw": t[:2000], "args": None,
                            "error": "unparsed tool-call markup", "tool_call_id": None, "timestamp": e.get("timestamp")})
    return out


def write(history: list, state_dir: Path) -> int:
    rs = extract(history)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "rejected_calls.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
    return len(rs)
