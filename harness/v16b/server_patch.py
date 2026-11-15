"""Step 16b: changes inside the agent-server process (root), applied by start.py before the server starts.

The agent's own tools run with the agent's privileges, not the server's:
  - terminal: the shell is /opt/.oh16b/agent-shell, which drops to the unprivileged user `agent` with a clean
    environment (no server variables), the fixed date (libclock.so.1, step 16c) and resource limits;
  - file_editor: runs inside the server (root), so each call is checked against what `agent` may read or write
    (Unix permissions of the path and its parents, symlinks resolved), and files it creates are owned by `agent`;
  - the server's own files (conversation store, bash events, task tracker, editor history, temp files) live under
    /var/lib/.oh16b (root, mode 700), not in the agent's working directory (H1);
  - the server no longer runs `git init` in /workspace;
  - a watchdog kills any process of `agent` (other than its interactive shells) that has run longer than
    OH16B_CMD_LIMIT seconds (default 180): a hard per-command wall-clock limit (the terminal's own timeouts only hand
    control back to the agent, they never stop the command).
Per-step state (item 8): before each tool call the server records the workspace (real bytes, content-addressed) and
the toolkit state as the MCP server last wrote it (sealed post.json), in /var/lib/.oh16b/steps/<n>.json. The record for
step n is the environment right before step n; `final.json` is written by the harness after the run.
Step 16c: Claude 5.5 agents get readable thinking: the request's thinking setting becomes {"type": "adaptive",
"display": "summarized"} (the API default is adaptive thinking with the text omitted), so the transcript shows the
model's reasoning summary. Thinking itself is unchanged (adaptive, the API's default effort)."""
from __future__ import annotations

import base64
import json
import os
import pwd
import signal
import stat
import threading
import time

ROOT = "/var/lib/.oh16b"
STEPS = f"{ROOT}/steps"
BLOBS = f"{ROOT}/blobs"
RUN = f"{ROOT}/run.json"
SHELL = "/opt/.oh16b/agent-shell"
AGENT = "agent"
_LOCK = threading.Lock()
_SEQ = [0]


def _agent():
    pw = pwd.getpwnam(AGENT)
    return pw.pw_uid, pw.pw_gid


def agent_may(path: str, want: str) -> bool:
    """Would user `agent` be allowed to `want` ('r' or 'w') this path? Symlinks are resolved first."""
    uid, gid = _agent()
    real = os.path.realpath(path)

    def ok(p, bits):
        try:
            st = os.stat(p)
        except OSError:
            return False
        m = st.st_mode
        if st.st_uid == uid:
            return all(m & {"r": stat.S_IRUSR, "w": stat.S_IWUSR, "x": stat.S_IXUSR}[b] for b in bits)
        if st.st_gid == gid:
            return all(m & {"r": stat.S_IRGRP, "w": stat.S_IWGRP, "x": stat.S_IXGRP}[b] for b in bits)
        return all(m & {"r": stat.S_IROTH, "w": stat.S_IWOTH, "x": stat.S_IXOTH}[b] for b in bits)
    parts = real.split("/")
    for i in range(2, len(parts)):
        d = "/".join(parts[:i]) or "/"
        if os.path.exists(d) and not ok(d, "x"):
            return False
    if os.path.exists(real):
        if os.path.isdir(real):
            return ok(real, "rx" if want == "r" else "wx")
        return ok(real, want)
    parent = os.path.dirname(real)
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    return want == "w" and ok(parent, "wx")


def _chown_new(path: str):
    uid, gid = _agent()
    real = os.path.realpath(path)
    try:
        if os.path.exists(real) and os.stat(real).st_uid == 0:
            os.chown(real, uid, gid)
        d = os.path.dirname(real)
        while d not in ("/", "") and os.path.exists(d) and os.stat(d).st_uid == 0 and agent_may(os.path.dirname(d), "w"):
            os.chown(d, uid, gid); d = os.path.dirname(d)
    except OSError:
        pass


def _patch_terminal():
    from openhands.tools.terminal.terminal import subprocess_terminal as st
    orig = st.SubprocessTerminal.__init__

    def __init__(self, work_dir, username=None, shell_path=None):
        orig(self, work_dir, username, SHELL)
    st.SubprocessTerminal.__init__ = __init__


def _patch_editor():
    from openhands.tools.file_editor.definition import FileEditorObservation
    from openhands.tools.file_editor.impl import FileEditorExecutor
    orig = FileEditorExecutor.__call__

    def __call__(self, action, conversation=None):
        want = "r" if action.command == "view" else "w"
        if not agent_may(action.path, want):
            return FileEditorObservation.from_text(
                text=f"Permission denied: '{action.path}'", command=action.command, is_error=True)
        out = orig(self, action, conversation)
        if want == "w":
            _chown_new(action.path)
        return out
    FileEditorExecutor.__call__ = __call__


def _patch_git():
    from openhands.agent_server import event_service as es
    es.EventService._ensure_workspace_is_git_repo = staticmethod(lambda working_dir: None)


def capture(label: str, tool: str | None = None, action_id: str | None = None, tool_call_id: str | None = None):
    import ws_store
    uid, _ = _agent()
    rec = {"label": label, "tool": tool, "action_id": action_id, "tool_call_id": tool_call_id, "time": time.time()}
    try:
        run = json.loads(open(RUN).read())
        with open(os.path.join(run["state_dir"], "post.json"), "rb") as fh:
            rec["env_post_sealed"] = base64.b64encode(fh.read()).decode()
        rec["mcp_calls_sealed"] = None
        cp = os.path.join(run["state_dir"], "calls.jsonl")
        if os.path.exists(cp):
            with open(cp, "rb") as fh:
                rec["mcp_calls_sealed"] = base64.b64encode(fh.read()).decode()
    except (OSError, ValueError, KeyError):
        rec["env_post_sealed"] = None
    rec["ws"] = ws_store.snapshot(BLOBS, agent_uid=uid)
    os.makedirs(STEPS, exist_ok=True)
    tmp = os.path.join(STEPS, f".{label}.tmp")
    with open(tmp, "w") as fh:
        json.dump(rec, fh)
    os.replace(tmp, os.path.join(STEPS, f"{label}.json"))


def _patch_steps():
    from openhands.sdk.agent.agent import Agent
    orig = Agent._execute_action_event

    def _execute_action_event(self, conversation, action_event):
        with _LOCK:
            n = _SEQ[0]; _SEQ[0] += 1
        try:
            capture(f"{n:04d}", action_event.tool_name, action_event.id, action_event.tool_call.id)
        except Exception as e:  # noqa: BLE001  (never block the agent on the recorder)
            with open(f"{ROOT}/capture_errors.log", "a") as fh:
                fh.write(f"{n}: {e!r}\n")
        return orig(self, conversation, action_event)
    Agent._execute_action_event = _execute_action_event


def _watchdog(limit: float):
    uid, _ = _agent()
    hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    boot = None
    for ln in open("/proc/stat"):
        if ln.startswith("btime"):
            boot = int(ln.split()[1])
    while True:
        time.sleep(2)
        try:
            for pid in filter(str.isdigit, os.listdir("/proc")):
                try:
                    if os.stat(f"/proc/{pid}").st_uid != uid:
                        continue
                    f = open(f"/proc/{pid}/stat").read()
                    rest = f[f.rindex(")") + 2:].split()
                    ppid, start = int(rest[1]), int(rest[19])
                    if os.stat(f"/proc/{ppid}").st_uid != uid:   # the interactive shell itself (parent is the server)
                        continue
                    if time.time() - (boot + start / hz) > limit:
                        os.kill(int(pid), signal.SIGKILL)
                        with open(f"{ROOT}/watchdog.log", "a") as fh:
                            fh.write(f"{time.time():.0f} killed {pid} after {limit}s\n")
                except (OSError, ValueError, IndexError):
                    continue
        except OSError:
            continue


def _patch_thinking():
    import openhands.sdk.llm.llm as L
    orig = L.select_chat_options

    def wrapped(llm, kw, has_tools):
        out = orig(llm, kw, has_tools)
        if any(m in str(llm.model) for m in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")):
            out["thinking"] = {"type": "adaptive", "display": "summarized"}
        return out
    L.select_chat_options = wrapped


def install():
    os.makedirs(ROOT, mode=0o700, exist_ok=True)
    _patch_thinking()
    _patch_terminal()
    _patch_editor()
    _patch_git()
    _patch_steps()
    threading.Thread(target=_watchdog, args=(float(os.environ.get("OH16B_CMD_LIMIT", "180")),), daemon=True).start()
