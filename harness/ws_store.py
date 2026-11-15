"""Step 16b: workspace snapshots as real bytes, stored content-addressed (G6, item 8).

snapshot(blob_dir) walks what the agent can write (/workspace, and files owned by the agent's user under /tmp,
/home/agent, /var/tmp), stores each file once as <blob_dir>/<sha256> and returns a manifest
{path: {"sha256": ..., "size": ...}}. A per-step record is that manifest plus the toolkit state; the text inside a file
is extracted at grading time (harness/filetext.py), never at snapshot time.

marker(data, name) is how a binary file the agent hands to a toolkit tool (an attachment path, a file to upload) is held
in the toolkit state: "[[file sha256=<hex> bytes=<n> name=<name>]]"; resolve() swaps markers for the extracted text.
Standard library only (runs in the MCP server's venv and in the agent-server's Python)."""
from __future__ import annotations

import hashlib
import os
import re

ROOTS = ("/workspace",)
AGENT_ROOTS = ("/tmp", "/home/agent", "/var/tmp")
MAX_BLOB = 25_000_000
MARK = re.compile(r"\[\[file sha256=([0-9a-f]{64}) bytes=(\d+) name=([^\]]*)\]\]")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(blob_dir: str, data: bytes) -> str:
    h = sha(data)
    p = os.path.join(blob_dir, h)
    if not os.path.exists(p) and len(data) <= MAX_BLOB:
        os.makedirs(blob_dir, exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, p)
    return h


def snapshot(blob_dir: str, agent_uid: int | None = None, roots=ROOTS, agent_roots=AGENT_ROOTS) -> dict:
    out = {}

    def take(p):
        try:
            st = os.lstat(p)
            if not os.path.isfile(p) or os.path.islink(p):
                return
            with open(p, "rb") as fh:
                data = fh.read(MAX_BLOB + 1)
            out[p] = {"sha256": put(blob_dir, data), "size": st.st_size}
        except OSError:
            pass
    for r in roots:
        for d, dirs, files in os.walk(r):
            dirs[:] = sorted(x for x in dirs if not (d == "/workspace" and x == ".git"))
            for f in sorted(files):
                take(os.path.join(d, f))
    if agent_uid is not None:
        for r in agent_roots:
            for d, dirs, files in os.walk(r):
                dirs.sort()
                for f in sorted(files):
                    p = os.path.join(d, f)
                    try:
                        if os.lstat(p).st_uid == agent_uid:
                            take(p)
                    except OSError:
                        pass
    return out


def is_text(data: bytes) -> bool:
    if b"\x00" in data[:8192] or data[:4] in (b"PK\x03\x04",) or data[:5] == b"%PDF-":
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def marker(data: bytes, name: str, blob_dir: str | None = None) -> str:
    """Text files are held as their text; anything else as a marker pointing at the stored bytes."""
    if is_text(data):
        return data.decode("utf-8")
    h = put(blob_dir, data) if blob_dir else sha(data)
    return f"[[file sha256={h} bytes={len(data)} name={name.replace(']', ')')}]]"


def resolve(obj, blob_dirs: list[str]):
    """Replace every marker in a state (dict / list / str) with the file's extracted text (filetext.extract)."""
    import filetext  # noqa: PLC0415

    def load(h):
        for d in blob_dirs:
            p = os.path.join(d, h)
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    return fh.read()
        return None

    def one(s: str) -> str:
        def rep(m):
            data = load(m.group(1))
            body = filetext.extract(data, m.group(3)) if data is not None else "[file not stored]"
            return f"[file {m.group(3)}]\n{body}"
        return MARK.sub(rep, s)
    if isinstance(obj, str):
        return one(obj) if "[[file sha256=" in obj else obj
    if isinstance(obj, list):
        return [resolve(x, blob_dirs) for x in obj]
    if isinstance(obj, dict):
        return {k: resolve(v, blob_dirs) for k, v in obj.items()}
    return obj
