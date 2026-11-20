"""Step 27: play a stored step-14-era run on its old task row. arm_s16b/play.py's _play (copied; play.py is not changed)
with one addition for the old harness, which really ran terminal commands: a pseudo call {"tool": "_put", "args":
{"files": {path: text}}} writes those files to the disk as real files (harness/filegen.render), so a file the agent made
with a terminal command exists from that step on. The text is what the run's own workspace snapshot (workspace_post.json)
recorded for the file."""
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]
import play as P  # noqa: E402
import file_tools, filegen, filetext, ws_store, workspace_bridge  # noqa: E401,E402


def _bytes(p: str, text: str) -> bytes:
    """A real file from a recorded snapshot text. A zip snapshot is "[zip archive <name>] members:\n<names>\n== <member> ==\n
    <text>..." (harness/filetext.py): its members are rebuilt one by one."""
    import io, re, zipfile
    if p.lower().endswith(".zip") and str(text).startswith("[zip archive"):
        parts = re.split(r"(?m)^== (.+?) ==\n", str(text))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, body in zip(parts[1::2], parts[2::2]):
                info = zipfile.ZipInfo(name, filegen.EPOCH); info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, filegen.render(name, body.rstrip("\n") + "\n" if body.strip() else body))
        return buf.getvalue()
    return filegen.render(p.rsplit("/", 1)[-1], text)


def play(row, steps: list) -> list:
    with P._LOCK:
        prof, env, rt = P.load_env(row)
        fs = P.staged(row)
        disk = P._Disk(fs)
        blob_dir = tempfile.mkdtemp(prefix="play27_")
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
                pre = ws_store.resolve(prof.env_to_dict(env), [blob_dir]); pre_ws = P.ws_text(fs)
                t = str(s.get("tool") or ""); args = dict(s.get("args") or {})
                res, err = None, None
                if t == "_put":
                    for p, text in (args.get("files") or {}).items():
                        fs[p] = _bytes(p, text)
                    name = t
                elif t in ("file_editor", "str_replace_editor"):
                    p = args.get("path") or ""
                    if args.get("command") == "create":
                        fs[p] = str(args.get("file_text") or "").encode()
                    elif args.get("command") == "str_replace" and p in fs:
                        fs[p] = fs[p].decode().replace(str(args.get("old_str")), str(args.get("new_str") or "")).encode()
                    elif args.get("command") == "view":
                        res = filetext.extract(fs[p], p) if p in fs else None
                        err = None if p in fs else f"no such file {p}"
                    name = "file_editor"
                elif t in ("terminal", "execute_bash", "chat_npc", "finish", "think", "task_tracker"):
                    name = t
                else:
                    name = P.tool_name(t, rt)
                    args = {k: v for k, v in args.items() if v is not None or k in ("attachments",)}
                    res, err, _ = workspace_bridge.call16b(prof, env, rt, name, args, blob_dir)
                post = ws_store.resolve(prof.env_to_dict(env), [blob_dir]); post_ws = P.ws_text(fs)
                out.append({"call": {"name": name, "args": args, "result": res, "error": err},
                            "pre": pre, "post": post, "pre_ws": pre_ws, "post_ws": post_ws})
        finally:
            workspace_bridge._read, workspace_bridge._agent_files = r0, a0
            GT.FILE_SINK = FT.FILE_SINK = None
        return out
