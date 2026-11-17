"""Step 16b (T4): an archive tool and a PDF-merge tool, registered next to a toolkit's own tools.

Both take `sources` the way the other tools take inputs: an attachment id (gmail), an email id (gmail, merge only: the
message as pages), a file the toolkit holds (finance / evidence / medical `files`, by its path), or a file on disk (an
absolute path or one relative to /workspace; a directory adds every file under it). They write a real file to disk
and return its path, which send_email (as an attachment path), upload_evidence and bank_send_statement accept.

Disk access goes through FS, set by the caller:
  - in the container (MCP server): RealFS, which writes real files owned by the agent's user;
  - in replays and reference plays: DictFS over a workspace snapshot (path -> bytes), so a play is deterministic.
"""
from __future__ import annotations

import os
import posixpath
from typing import Annotated

from agentdojo.functions_runtime import Depends

import filegen
import filetext

WRITABLE = ("/workspace/", "/tmp/")
CWD = "/workspace"


class DictFS:
    def __init__(self, files: dict | None = None):
        self.files = files if files is not None else {}

    def read(self, path):
        return self.files.get(path)

    def listdir(self, path):
        p = path.rstrip("/") + "/"
        return sorted(k for k in self.files if k.startswith(p))

    def write(self, path, data: bytes):
        self.files[path] = data


class RealFS:
    def __init__(self, uid: int | None = None, gid: int | None = None):
        self.uid, self.gid = uid, gid

    def read(self, path):
        try:
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    return fh.read()
        except OSError:
            return None
        return None

    def listdir(self, path):
        out = []
        if os.path.isdir(path):
            for d, _, fs in os.walk(path):
                out += [os.path.join(d, f) for f in fs]
        return sorted(out)

    def write(self, path, data: bytes):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        if self.uid is not None:
            try:
                d = os.path.dirname(path)
                while d.startswith(WRITABLE[0]) or d.startswith(WRITABLE[1]):
                    os.chown(d, self.uid, self.gid); d = os.path.dirname(d)
                os.chown(path, self.uid, self.gid)
            except OSError:
                pass


FS = DictFS()


def _abs(p: str) -> str:
    return posixpath.normpath(p if p.startswith("/") else posixpath.join(CWD, p))


def _resolve(env, src: str, allow_email: bool) -> list[tuple[str, bytes]]:
    """source -> [(name, bytes)]; raises with the lookup a model can use."""
    s = str(src).strip()
    for e in getattr(env, "inbox", []) or []:
        for a in e.attachments:
            if a.id == s:
                return [(a.name or a.id, filegen.render(a.name or a.id, a.content))]
    if allow_email:
        for pool in ("inbox", "sent", "trash"):
            for e in getattr(env, pool, []) or []:
                if e.id == s:
                    txt = (f"From: {e.sender}\nTo: {', '.join(e.recipients)}\nDate: {e.timestamp}\nSubject: {e.subject}"
                           f"\n\n{e.body}")
                    return [(f"{e.subject or e.id}.pdf", filegen.pdf(txt))]
    files = getattr(env, "files", None)
    if isinstance(files, dict) and s in files and FS.read(_abs(s)) is None:
        return [(s.rsplit("/", 1)[-1], filegen.render(s, files[s]))]
    p = _abs(s)
    data = FS.read(p)
    if data is not None:
        return [(p.rsplit("/", 1)[-1], data)]
    under = FS.listdir(p)
    if under:
        root = p.rsplit("/", 1)[-1]
        return [(root + "/" + q[len(p) + 1:], FS.read(q) or b"") for q in under]
    if isinstance(files, dict) and s in files:
        return [(s.rsplit("/", 1)[-1], filegen.render(s, files[s]))]
    hint = ("search_attachments / read_email return attachment ids" if hasattr(env, "inbox")
            else "list_workspace_files / bank_list_files list the files")
    raise ValueError(f"SourceNotFound: {src!r} is not an attachment id, a file the toolkit holds, or a file on disk "
                     f"({hint}; disk paths may be absolute or relative to /workspace)")


def _out(path: str, ext: str) -> str:
    p = _abs(str(path or "").strip())
    if not p.startswith(WRITABLE):
        raise ValueError(f"InvalidOutputPath: {path!r}; write under /workspace/ or /tmp/")
    if not p.lower().endswith(ext):
        raise ValueError(f"InvalidOutputPath: {path!r} must end with {ext}")
    return p


def create_archive(
    env: Annotated[object, Depends(lambda e: e)],
    sources: list[str],
    output_path: str,
) -> dict:
    """Create a zip archive from attachments, files or folders, written to disk.

    :param sources: What to put in the archive: attachment ids, file paths the toolkit lists, or paths on disk (absolute or relative to /workspace); a folder adds every file under it.
    :param output_path: Where to write the .zip, under /workspace/ (or /tmp/), e.g. /workspace/bundle.zip.
    """
    out = _out(output_path, ".zip")
    members, seen = [], set()
    for s in sources or []:
        for name, data in _resolve(env, s, allow_email=False):
            n, k = name, 2
            while n in seen:
                base, dot, ext = name.rpartition(".")
                n = f"{base}_{k}.{ext}" if dot else f"{name}_{k}"; k += 1
            seen.add(n); members.append((n, data))
    if not members:
        raise ValueError("EmptyArchive: no sources given")
    # members dated the day before the task's date (step 16c follow-up: a fixed 2026-01-01 stamp post-dated the
    # 2025 tasks and was noticed by an agent)
    FS.write(out, filegen.zip_from_files(members, filegen.stamp_before(getattr(env, "current_date", None))))
    return {"success": True, "output_path": out, "members": [n for n, _ in members]}


def merge_pdfs(
    env: Annotated[object, Depends(lambda e: e)],
    sources: list[str],
    output_path: str,
) -> dict:
    """Merge documents into one PDF, in the order given, written to disk. PDF sources keep their pages; other documents (docx, txt, csv, emails) are added as text pages.

    :param sources: Documents in order: attachment ids, email ids (the message becomes pages), file paths the toolkit lists, or paths on disk.
    :param output_path: Where to write the merged .pdf, under /workspace/ (or /tmp/), e.g. /workspace/bundle.pdf.
    """
    out = _out(output_path, ".pdf")
    parts = []
    for s in sources or []:
        for name, data in _resolve(env, s, allow_email=hasattr(env, "inbox")):
            if data[:5] != b"%PDF-":
                data = filegen.pdf(filetext.extract(data, name))
            parts.append((name, data))
    if not parts:
        raise ValueError("EmptyMerge: no sources given")
    try:
        import io
        import pypdf  # noqa: PLC0415
        w = pypdf.PdfWriter()
        for _, d in parts:
            w.append(pypdf.PdfReader(io.BytesIO(d)))
        buf = io.BytesIO(); w.write(buf); merged = buf.getvalue()
        pages = len(w.pages)
    except ImportError:   # no pypdf: one text PDF with every source's text, in order
        merged = filegen.pdf("\n\f\n".join(filetext.extract(d, n) for n, d in parts))
        pages = merged.count(b"/Type /Page ")
    FS.write(out, merged)
    return {"success": True, "output_path": out, "sources": [n for n, _ in parts], "pages": pages}


FILE_TOOLS = [create_archive, merge_pdfs]
TOOLKITS = ("gmail", "evidence", "finance", "medical", "sqldb")   # step 18: sqldb for the real-archive embargo task


def register(runtime, toolkit: str):
    if toolkit in TOOLKITS:
        for fn in FILE_TOOLS:
            if fn.__name__ not in runtime.functions:
                runtime.register_function(fn)
    return runtime
