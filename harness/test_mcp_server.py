"""Standalone check of harness/gmail_mcp_server.py with a real MCP stdio client (step 8 Part B):
tool list == the driver's tool schemas; search_emails; send_email; pre/post dump; diff; evaluator on (pre, post).
  python harness/test_mcp_server.py [--toolkit gmail] [--task-dir DIR]"""
import argparse, asyncio, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from harness.gmail_mcp_server import tool_schemas  # noqa: E402
from recipe import profiles  # noqa: E402


async def run(toolkit, env_path, state_dir, calls):
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "harness/gmail_mcp_server.py"),
                                   "--toolkit", toolkit, "--env", str(env_path), "--state-dir", str(state_dir)])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = (await s.list_tools()).tools
        outs = [(n, a, (await s.call_tool(n, a)).content[0].text) for n, a in calls]
    return tools, outs


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--toolkit", default="gmail"); ap.add_argument("--task-dir")
    a = ap.parse_args()
    prof = profiles.get(a.toolkit)
    env_path = Path(a.task_dir) / "environment.yaml" if a.task_dir else ROOT / f"{a.toolkit}_suite/base_environment.yaml"
    calls = [] if a.toolkit != "gmail" else [
        ("search_emails", {"keywords": ["contract"]}),
        ("send_email", {"to": "vendor@partner.com", "subject": "Fwd: contract", "body": "Do not distribute - test"})]
    sd = Path(tempfile.mkdtemp())
    tools, outs = asyncio.run(run(a.toolkit, env_path, sd, calls))
    env = prof.load_environment(env_path)   # the driver's per-env tool surface (medical: vantage tools)
    rt = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    want = {t["name"]: t for t in tool_schemas(rt)}
    got = {t.name: {"name": t.name, "description": t.description, "parameters": t.inputSchema} for t in tools}
    print(f"{a.toolkit}: {len(got)} tools; identical to driver schemas: {got == want}")
    for n, args, txt in outs:
        print(f"  {n}({json.dumps(args)}) -> {txt[:160]}")
    pre, post = json.loads((sd / "pre.json").read_text()), json.loads((sd / "post.json").read_text())
    diff = {k: (len(pre[k]), len(post[k])) for k in pre if pre[k] != post[k]}
    print("  state diff (collection: len pre -> post):", diff, "| calls logged:",
          len((sd / "calls.jsonl").read_text().splitlines()) if (sd / "calls.jsonl").exists() else 0)
    if a.toolkit == "gmail" and calls:
        new = [e for e in post["sent"] if e["id"] not in {x["id"] for x in pre["sent"]}]
        print("  new sent:", [(e["id"], e["recipients"], e["subject"]) for e in new])
        if a.task_dir and (Path(a.task_dir) / "evaluator.py").exists():
            ns = {}; exec((Path(a.task_dir) / "evaluator.py").read_text(), ns)
            print("  evaluator(pre, post):", ns["grade_checkpoints"](pre, post))


if __name__ == "__main__":
    main()
