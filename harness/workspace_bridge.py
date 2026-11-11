"""Step 13f: make files the agent builds in its Docker workspace visible to the task environment.

The gap: the agent's terminal and file_editor write to the container's disk (/workspace, /tmp, ...), but the toolkits
read files from the environment's own in-memory store (finance / evidence `files`; gmail attachments by id). A CSV the
agent writes to /workspace and then passes to bank_send_statement fails with FileNotFound, so the deliverable never
lands and neither the evaluator nor a utility check can see it.

This module, stdlib only (it runs inside the container with the MCP server, and in the step-13f replay):
  snapshot(roots, since)  agent-created files as {absolute path: text}. Text files as they are; zip archives (and
                          zip-based office files: xlsx, docx, pptx) as their member names plus each member's text, XML
                          stripped to its text; other binaries (pdf, images) as their printable strings. Capped.
  call(prof, env, runtime, name, args, ws, downloads)
                          runs one tool call with the workspace overlaid:
    - finance / evidence: a file argument absent from env.files but present in the workspace is visible to the tool for
      this call only (env.files is restored afterwards; the content lands in what the tool writes, e.g. the shared
      statement or the uploaded evidence record);
    - gmail send_email: an attachment given as a workspace path attaches that file (id = the path, name = its base
      name, content = its text);
    - wins=True (v0.8 tasks, whose files are staged on disk): a file argument the env does hold but whose workspace copy
      differs (the agent edited the staged copy) is read from the workspace for that call;
    - downloads=True (separate switch, a tool-contract fix rather than a workspace one): an attachment given as
      /downloads/<id>, the path download_attachment returns, is read as <id>.
The state dumps keep the snapshot under the top-level key `workspace` (path -> text) so utility checks can read it;
graders keep reading the toolkit state as before."""
import io, os, re, zipfile

MAX_FILE = 2_000_000       # bytes read per file
MAX_TEXT = 100_000         # chars kept per file
FILE_ARGS = {"bank_send_statement": ("file_path",), "upload_evidence": ("file_path",)}
SKIP_DIRS = ("/proc", "/sys", "/dev", "/usr", "/lib", "/bin", "/sbin", "/etc", "/var", "/opt", "/run", "/npc",
             "/utils", "/instruction", "/agentdojo", "/root/.cache", "/tmp/.X11-unix")
AGENT_SERVER_DIRS = ("bash_events", "conversations")   # the agent-server's own store under /workspace/workspace


def _strip_xml(b: bytes) -> str:
    t = re.sub(rb"<[^>]+>", b" ", b)
    return re.sub(r"\s+", " ", t.decode("utf-8", "replace")).strip()


def _printable(b: bytes) -> str:
    return "\n".join(m.decode("latin-1") for m in re.findall(rb"[\x20-\x7e]{4,}", b))


def render(data: bytes, name: str = "") -> str:
    if data[:4] == b"PK\x03\x04":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = z.namelist()
            parts = [f"[zip archive {name}] members:"] + names
            for n in names:
                if n.endswith("/"):
                    continue
                b = z.read(n)[:MAX_FILE]
                txt = _strip_xml(b) if n.endswith((".xml", ".rels")) else render(b, n)
                parts += [f"== {n} ==", txt]
            return "\n".join(parts)[:MAX_TEXT]
        except Exception:  # noqa: BLE001
            pass
    if b"\x00" not in data[:8192]:
        try:
            return data.decode("utf-8")[:MAX_TEXT]
        except UnicodeDecodeError:
            pass
    return (f"[binary file {name}, {len(data)} bytes] printable strings:\n" + _printable(data))[:MAX_TEXT]


def snapshot(roots=("/workspace",), since: float | None = None, extra=("/tmp", "/root", "/home"), exclude=()) -> dict:
    """Files under `roots`, plus files under `extra` modified after `since` (agent-created elsewhere); paths under
    `exclude` (the MCP server's own state dir) are left out."""
    out = {}
    exclude = tuple(str(x).rstrip("/") + "/" for x in exclude)

    def walk(root, newer):
        for d, dirs, files in os.walk(root):
            if d.startswith(SKIP_DIRS) and not d.startswith("/workspace"):
                dirs[:] = []; continue
            dirs[:] = [x for x in dirs if (not x.startswith(".") or root == "/workspace")
                       and not (d == "/workspace/workspace" and x in AGENT_SERVER_DIRS)]
            for f in files:
                p = os.path.join(d, f)
                if exclude and p.startswith(exclude):
                    continue
                try:
                    st = os.stat(p)
                    if newer is not None and st.st_mtime < newer:
                        continue
                    with open(p, "rb") as fh:
                        out[p] = render(fh.read(MAX_FILE), f)
                except OSError:
                    continue
    for r in roots:
        walk(r, None)
    if since is not None:
        for r in extra:
            if os.path.isdir(r):
                walk(r, since)
    return out


def lookup(ws: dict, path, cwd: str = "/workspace"):
    if not isinstance(path, str) or not path:
        return None
    p = path if path.startswith("/") else os.path.normpath(os.path.join(cwd, path))
    return ws.get(p)


def call(prof, env, runtime, name: str, args: dict, ws: dict | None, downloads: bool = False, wins: bool = False):
    """runtime.run_function(env, name, args) with the workspace overlaid. Returns (result, error, note); note says
    what the overlay supplied (None if nothing)."""
    ws = ws or {}
    note, added, swapped, temp_email, args = [], [], {}, None, dict(args or {})
    files = getattr(env, "files", None)
    if isinstance(files, dict):
        for k in FILE_ARGS.get(name, ()):
            p = args.get(k)
            if not isinstance(p, str):
                continue
            hit = lookup(ws, p)
            if hit is not None and p not in files:
                files[p] = hit; added.append(p); note.append(f"workspace:{p}")
            elif hit is not None and wins and files[p] != hit:
                swapped[p] = files[p]; files[p] = hit; note.append(f"workspace-edited:{p}")
    if name == "send_email" and isinstance(args.get("attachments"), list) and hasattr(env, "inbox"):
        known = {a.id for e in env.inbox for a in e.attachments}
        atts, new = [], []
        for a in args["attachments"]:
            if downloads and isinstance(a, str) and a.startswith("/downloads/") and a.rsplit("/", 1)[-1] in known:
                atts.append(a.rsplit("/", 1)[-1]); note.append(f"downloads:{a}")
                continue
            hit = lookup(ws, a) if isinstance(a, str) and a not in known else None
            if hit is not None:
                new.append((a, hit)); note.append(f"workspace:{a}")
            atts.append(a)
        args["attachments"] = atts
        if new:
            from gmail_suite.environment import Attachment, Email   # noqa: E402  (gmail only)
            temp_email = Email(id="__workspace__", attachments=[
                Attachment(id=p, name=p.rsplit("/", 1)[-1], content=t) for p, t in new])
            env.inbox.append(temp_email)
    try:
        res, err = runtime.run_function(env, name, args)
    finally:
        for p in added:
            files.pop(p, None)
        for p, orig in swapped.items():
            files[p] = orig
        if temp_email is not None:
            env.inbox.remove(temp_email)
    return res, err, (note or None)
