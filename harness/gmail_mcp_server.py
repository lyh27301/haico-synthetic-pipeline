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

--workspace (step 13f; off by default, so replays of earlier runs are unchanged): the agent's files on the container
disk become visible to the toolkit (harness/workspace_bridge.py). Each call first snapshots /workspace (plus files the
agent created under /tmp, /root, /home), a file argument the env does not hold is read from that snapshot, and the
snapshot is written next to the state as workspace_pre.json / workspace_post.json (path -> text). pre.json and
post.json keep their exact shape. --workspace-wins (v0.8 tasks, files staged on disk) reads an edited staged copy of an
env file instead of the env's copy. --downloads also reads a /downloads/<id> attachment path as <id> (a tool-contract
fix, separate switch).

--task-file (step 13f-4; harness/state_seal.py): a JSON file {"environment": <env YAML text>, "key": <hex>} staged
at a random path. The server reads it and deletes it (and its directory) on startup, before the agent can act, and
seals every state dump with the key, so neither the task state (cue included) nor the grader's state is readable from
the agent's terminal. Without it the server behaves as before (--env, plaintext dumps).

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import state_seal, workspace_bridge  # noqa: E402

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
    def __init__(self, toolkit: str, env_path: str, state_dir: str | None, workspace: bool = False,
                 downloads: bool = False, key: bytes | None = None, wins: bool = False):
        import time
        self.workspace, self.downloads, self.t0, self.key = workspace, downloads, time.time(), key
        self.wins = wins
        self.prof = profiles.get(toolkit)
        self.env = self.prof.load_environment(env_path)
        self.runtime = (self.prof.runtime_for_env(self.env) if hasattr(self.prof, "runtime_for_env")
                        else self.prof.build_runtime())
        self.dir = Path(state_dir) if state_dir else None
        if self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._write("pre.json", self.prof.env_to_dict(self.env))
            self._write("post.json", self.prof.env_to_dict(self.env))
            if self.workspace:
                ws = workspace_bridge.snapshot(since=self.t0, exclude=[self.dir] if self.dir else [])
                self._write("workspace_pre.json", ws); self._write("workspace_post.json", ws)

    def _write(self, name: str, obj) -> None:
        tmp = self.dir / (name + ".tmp")
        data = (obj if isinstance(obj, str) else json.dumps(obj, default=str)).encode()
        tmp.write_bytes(state_seal.seal(self.key, data) if self.key else data)
        tmp.replace(self.dir / name)

    def call(self, name: str, args: dict) -> str:
        ws, note = None, None
        if self.workspace or self.downloads:
            ws = workspace_bridge.snapshot(since=self.t0, exclude=[self.dir] if self.dir else []) if self.workspace else {}
            out, err, note = workspace_bridge.call(self.prof, self.env, self.runtime, name, args, ws, self.downloads,
                                                  self.wins)
        else:
            out, err = self.runtime.run_function(self.env, name, args)
        result = {"error": err} if err else out
        if self.dir:
            self._write("post.json", self.prof.env_to_dict(self.env))
            if self.workspace:
                self._write("workspace_post.json", ws)
            line = json.dumps({"name": name, "args": args, "result": result, "error": err,
                               **({"workspace": note} if note else {})}, default=str) + "\n"
            if self.key:   # sealed: the whole log is rewritten each call
                self.calls = getattr(self, "calls", "") + line
                self._write("calls.jsonl", self.calls)
            else:
                with open(self.dir / "calls.jsonl", "a") as fh:
                    fh.write(line)
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
    ap.add_argument("--workspace-wins", action="store_true",
                    help="v0.8 tasks: an edited staged copy of an env file wins over the env's copy")
    ap.add_argument("--task-file", help="consumed on startup: {environment, key}; seals the state dumps")
    ap.add_argument("--schema", choices=["exact", "flat"], default=os.environ.get("AGENTDOJO_SCHEMA", "exact"))
    ap.add_argument("--workspace", action="store_true", default=os.environ.get("AGENTDOJO_WORKSPACE") == "1")
    ap.add_argument("--downloads", action="store_true", default=os.environ.get("AGENTDOJO_DOWNLOADS") == "1")
    a = ap.parse_args(argv)
    env, key = a.env or str(ROOT / f"{a.toolkit}_suite" / "base_environment.yaml"), None
    if a.task_file:
        import shutil, tempfile
        tf = Path(a.task_file); task = json.loads(tf.read_text())
        tf.unlink()
        if tf.parent != Path("/") and not any(tf.parent.iterdir()):
            shutil.rmtree(tf.parent, ignore_errors=True)
        key = bytes.fromhex(task["key"])
        # the YAML is needed on disk only while it loads; inside the state dir it is outside the workspace snapshot
        if a.state_dir:
            Path(a.state_dir).mkdir(parents=True, exist_ok=True)
        fd, env = tempfile.mkstemp(suffix=".yaml", dir=a.state_dir); os.close(fd)
        Path(env).write_text(task["environment"])
    try:
        st = State(a.toolkit, env, a.state_dir, a.workspace, a.downloads, key, a.workspace_wins)
    finally:
        if a.task_file:
            os.unlink(env)
    server = build_server(st, a.schema)

    async def run():
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()
