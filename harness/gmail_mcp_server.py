"""Stdio MCP server that serves one AgentDojo-style task environment to an OpenHands agent (step 8).

Loads the task's `environment.yaml` into one in-memory environment (GmailEnvironment for --toolkit gmail) and
exposes the toolkit's tools with the same names, parameter schemas and docstrings the local driver sends to the
OpenAI API (driver.openai_tool_schemas). A call runs the real tool function on the in-memory env, and the result
is returned as the same JSON text the driver puts in its tool message.

Grading side channel (not agent-facing; no extra tools): if AGENTDOJO_STATE_DIR is set, the server writes
  pre.json   the env as loaded, before any call
  post.json  the env after the latest call (rewritten after every call, atomically)
  calls.jsonl  one line per call: name, args, result, error
so evaluator_code grades (pre, post) exactly as the driver does.

  python harness/gmail_mcp_server.py --toolkit gmail --env path/to/environment.yaml
Env vars: AGENTDOJO_ENV (default for --env), AGENTDOJO_TOOLKIT (default for --toolkit), AGENTDOJO_STATE_DIR.

--schema exact (default) publishes the driver's schemas unchanged. --schema flat replaces every `anyOf` with one
alternative (the non-null one, else the first), because OpenHands SDK v1.22.1's Schema.from_mcp_schema drops `anyOf`
and the model would otherwise see every optional parameter (Optional[list[str]] -> anyOf[array, null]) with no type
at all. Flat keeps the parameter optional (`required` is unchanged), and the tool still validates the full union.
"""
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from recipe import profiles  # noqa: E402

TOOLKITS = list(profiles.NAMES)


def flatten(node):
    """anyOf[X, null] -> X; anyOf[X, Y, ...] -> X (keeps description/default of the outer node)."""
    if isinstance(node, list):
        return [flatten(x) for x in node]
    if not isinstance(node, dict):
        return node
    node = {k: flatten(v) for k, v in node.items()}
    if "anyOf" in node:
        alts = [a for a in node.pop("anyOf") if a.get("type") != "null"] or [{}]
        node = {**alts[0], **node}
    return node


def tool_schemas(runtime, mode: str = "exact") -> list[dict]:
    """Same transformation as driver.openai_tool_schemas, kept here so the server needs no OpenAI client."""
    out = []
    for name, f in runtime.functions.items():
        schema = f.parameters.model_json_schema()
        schema.pop("title", None)
        for p in schema.get("properties", {}).values():
            p.pop("title", None)
        out.append({"name": name, "description": f.description,
                    "parameters": flatten(schema) if mode == "flat" else schema})
    return out


class State:
    def __init__(self, toolkit: str, env_path: str, state_dir: str | None):
        self.prof = profiles.get(toolkit)
        self.env = self.prof.load_environment(env_path)
        self.runtime = (self.prof.runtime_for_env(self.env) if hasattr(self.prof, "runtime_for_env")
                        else self.prof.build_runtime())
        self.dir = Path(state_dir) if state_dir else None
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._write("pre.json", self.prof.env_to_dict(self.env))
            self._write("post.json", self.prof.env_to_dict(self.env))

    def _write(self, name: str, obj) -> None:
        tmp = self.dir / (name + ".tmp")
        tmp.write_text(json.dumps(obj, default=str))
        tmp.replace(self.dir / name)

    def call(self, name: str, args: dict) -> str:
        out, err = self.runtime.run_function(self.env, name, args)
        result = {"error": err} if err else out
        if self.dir:
            self._write("post.json", self.prof.env_to_dict(self.env))
            with open(self.dir / "calls.jsonl", "a") as fh:
                fh.write(json.dumps({"name": name, "args": args, "result": result, "error": err}, default=str) + "\n")
        return json.dumps(result, default=str)


def build_server(st: State, schema_mode: str = "exact") -> Server:
    server = Server(f"agentdojo-{st.prof.NAME}")
    schemas = tool_schemas(st.runtime, schema_mode)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=s["name"], description=s["description"], inputSchema=s["parameters"]) for s in schemas]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        return [types.TextContent(type="text", text=st.call(name, arguments or {}))]

    return server


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toolkit", choices=TOOLKITS, default=os.environ.get("AGENTDOJO_TOOLKIT", "gmail"))
    ap.add_argument("--env", default=os.environ.get("AGENTDOJO_ENV"))
    ap.add_argument("--state-dir", default=os.environ.get("AGENTDOJO_STATE_DIR"))
    ap.add_argument("--schema", choices=["exact", "flat"], default=os.environ.get("AGENTDOJO_SCHEMA", "exact"))
    a = ap.parse_args(argv)
    env = a.env or str(ROOT / f"{a.toolkit}_suite" / "base_environment.yaml")
    st = State(a.toolkit, env, a.state_dir)
    server = build_server(st, a.schema)

    async def run():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()
