"""Step 16b: play a reference path (or a stored run's calls) on the real toolkit with the step-16b contracts, and return
the steps in the form the rules engine reads: [{"call", "pre", "post", "pre_ws", "post_ws"}].

The disk is a dict (path -> bytes) seeded with the task's staged files as real binaries (arm_s16b/bank/files/...). The
toolkit's file tools (create_archive, merge_pdfs), download_attachment and statement downloads write into it;
file_editor create / str_replace write into it; terminal steps are not executed (a reference does not use them).
Binaries handed to a toolkit tool are held as markers and resolved to their extracted text (harness/ws_store.py), and
the workspace in a step is {path: extracted text} (harness/filetext.py), as the grader sees a real run."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
sys.path[:0] = [str(ROOT), str(ROOT / "harness"), str(ROOT / "arm_s13")]
from recipe import profiles  # noqa: E402
import file_tools, filegen, filetext, ws_store, workspace_bridge  # noqa: E401,E402
import grader_v3  # noqa: E402

BANK = S16B / "bank"


def staged(row) -> dict:
    out = {}
    for spec in row.get("workspace_files") or []:
        p = BANK / spec
        if p.exists():
            out["/workspace/" + spec.split("/workspace/", 1)[1]] = p.read_bytes()
    return out


def ws_text(fs: dict) -> dict:
    return {p: filetext.extract(b, p.rsplit("/", 1)[-1]) for p, b in sorted(fs.items())}


def tool_name(t: str, runtime) -> str:
    n = grader_v3.tool_name(t)
    if n in runtime.functions:
        return n
    import re
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", t).lower()
    for cand in (s, s.replace("bank_manager_", "bank_"), "bank_" + s.split("bank_manager_")[-1]):
        if cand in runtime.functions:
            return cand
    return t


class _Disk:
    def __init__(self, fs):
        self.fs = fs

    def read(self, path, cwd="/workspace"):
        import posixpath
        p = path if path.startswith("/") else posixpath.normpath(posixpath.join(cwd, path))
        return p, self.fs.get(p)

    def files(self, root="/workspace"):
        return sorted(p for p in self.fs if p.startswith(root + "/") and "/." not in p)


def load_env(row):
    prof = profiles.get(row["toolkit"])
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(row["environment"])
    env = prof.load_environment(fh.name); Path(fh.name).unlink()
    rt = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    file_tools.register(rt, row["toolkit"])
    return prof, env, rt


import threading
_LOCK = threading.RLock()   # play() swaps module-level hooks (file_tools.FS, the bridge's disk): one play at a time


def play(row, steps: list) -> list:
    """Run reference steps; returns engine steps. A step is {"tool", "args"}."""
    with _LOCK:
        return _play(row, steps)


def _play(row, steps: list) -> list:
    prof, env, rt = load_env(row)
    fs = staged(row)
    disk = _Disk(fs)
    blob_dir = tempfile.mkdtemp(prefix="play16b_")
    file_tools.FS = file_tools.DictFS(fs)

    def sink(path, name, text):
        fs[path] = filegen.render(name, text)
    import gmail_suite.tools as GT, finance_suite.tools as FT
    GT.FILE_SINK = FT.FILE_SINK = sink
    r0, a0 = workspace_bridge._read, workspace_bridge._agent_files
    workspace_bridge._read = disk.read
    workspace_bridge._agent_files = disk.files
    out = []
    try:
        for s in steps:
            pre = ws_store.resolve(prof.env_to_dict(env), [blob_dir]); pre_ws = ws_text(fs)
            t = str(s.get("tool") or ""); args = dict(s.get("args") or {})
            res, err = None, None
            if t in ("file_editor", "str_replace_editor"):
                p = args.get("path") or ""
                if args.get("command") == "create":
                    fs[p] = str(args.get("file_text") or "").encode()
                elif args.get("command") == "str_replace" and p in fs:
                    fs[p] = fs[p].decode().replace(str(args.get("old_str")), str(args.get("new_str") or "")).encode()
                elif args.get("command") == "view":
                    res = filetext.extract(fs[p], p) if p in fs else None
                    err = None if p in fs else f"no such file {p}"
                name = "file_editor"
            elif t in ("terminal", "execute_bash", "chat_npc", "finish", "think"):
                name = t
            else:
                name = tool_name(t, rt)
                args = {k: v for k, v in args.items() if v is not None or k in ("attachments",)}
                res, err, _ = workspace_bridge.call16b(prof, env, rt, name, args, blob_dir)
            post = ws_store.resolve(prof.env_to_dict(env), [blob_dir]); post_ws = ws_text(fs)
            out.append({"call": {"name": name, "args": args, "result": res, "error": err},
                        "pre": pre, "post": post, "pre_ws": pre_ws, "post_ws": post_ws})
    finally:
        workspace_bridge._read, workspace_bridge._agent_files = r0, a0
        GT.FILE_SINK = FT.FILE_SINK = None
    return out


def initial(row) -> tuple[dict, dict]:
    prof, env, rt = load_env(row)
    return prof.env_to_dict(env), ws_text(staged(row))


if __name__ == "__main__":
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (BANK / "bank_16b.jsonl").read_text().splitlines()}
    bad = {}
    for t, r in rows.items():
        st = play(r, r["safe_reference"])
        errs = [(i, s["call"]["name"], str(s["call"]["error"])[:160]) for i, s in enumerate(st) if s["call"]["error"]]
        if errs:
            bad[t] = errs
    print(len(rows), "tasks;", len(bad), "with failing safe-reference calls")
    for t, e in bad.items():
        print(t, e)
