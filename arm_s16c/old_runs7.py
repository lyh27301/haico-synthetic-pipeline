"""Step 16c: arm_s16b/old_runs.py (unchanged there) with the step-16c attribution of terminal-built files in stored runs
(stored runs keep only the initial and final workspace): a file new or changed at the end is placed at the first
terminal / editor step that names it, could write it (zip, cp, mv, tar, 7z, unzip, python, a shell redirect, tee, touch,
sed -i, pdfunite / qpdf, or an editor create / str_replace / insert) and did not fail (no zip error, missing file,
permission error, traceback or non-zero exit in its output); a failed command's simulated zip / cp effects are dropped.
So the successful re-zip, not the failed first attempt or a `cat` of the file, gets the file. Runs on the 16b / 16c
harness record every step's workspace and need none of this."""
from __future__ import annotations

import json, re, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s16b")]
import old_runs as O  # noqa: E402
from old_runs import RN, R, workspace_bridge, profiles, js, bank, runs  # noqa: E402,F401

WRITE_CMD = re.compile(r"(^|[\s;&|(])(zip|cp|mv|tar|7z|7za|unzip|python3?|tee|touch|pdfunite|qpdf|install|rsync|ln)\b|"
                       r"[^2]>{1,2}\s*[\w/.~\"']|\bsed\s+-i", re.I)
FAILED = re.compile(r"zip error|zip warning: name not matched|No such file or directory|cannot (stat|create|open|move|copy)|"
                    r"Permission denied|command not found|Traceback \(most recent|exit code [1-9]|Read-only file system|"
                    r"Is a directory|Not a directory", re.I)


def can_write(s) -> bool:
    a = s.get("args") or {}
    if s["tool"] in ("file_editor", "str_replace_editor"):
        return str(a.get("command")) in ("create", "str_replace", "insert", "write", "undo_edit")
    return bool(WRITE_CMD.search(str(a.get("command") or "")))


def ok(s) -> bool:
    return not FAILED.search(str(s.get("observation") or ""))


def steps(x) -> list:
    t = x["task"]; row = bank()[t]
    sd, td = Path(x["state_dir"]), Path(x["traj_dir"])
    prof = profiles.get(R.toolkit(row))
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(row["environment"])
    env = prof.load_environment(fh.name); Path(fh.name).unlink()
    rt = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    wpre, wpost = RN.rn(js(sd / "workspace_pre.json")), RN.rn(js(sd / "workspace_post.json"))
    has_ws = bool(wpre or wpost) or x["source"] != "step13f"
    patch = RN.rn(x.get("g6_patch") or {})
    ws_final = {k: v for k, v in (wpre | wpost | patch).items() if not k.startswith("/workspace/.git/")}
    ws_init = {k: v for k, v in wpre.items() if not k.startswith("/workspace/.git/")}
    calls = iter(RN.rn(R.jl(sd / "calls.jsonl")))
    hist = RN.rn(R.history(td, t))
    if hist is None:
        return []
    st = R.steps_of(hist, set(rt.functions))
    # file attribution for terminal / editor steps
    changed = [p for p, v in ws_final.items() if ws_init.get(p) != v]
    writers = [i for i, s in enumerate(st) if s["tool"] in ("terminal", "file_editor", "execute_bash", "str_replace_editor")]
    writes = [i for i in writers if can_write(st[i]) and ok(st[i])]
    born = {}
    for p in changed:
        b = p.rsplit("/", 1)[-1]
        named = lambda i: b in json.dumps(st[i].get("args") or {}, default=str)
        hits = [i for i in writes if named(i)] or [i for i in writers if can_write(st[i]) and named(i)]
        born[p] = hits[0] if hits else (writes[-1] if writes else writers[-1] if writers else None)
    out, cur_ws, cwd = [], dict(ws_init), "/workspace"
    cur = R.rt(prof.env_to_dict(env))
    for i, s in enumerate(st):
        pre, pre_ws = cur, dict(cur_ws)
        err, res = None, s.get("observation")
        args = s.get("args") or {}
        if s["kind"] == "env":
            c = next(calls, None) or {"name": s["tool"], "args": {k: v for k, v in args.items() if k != "summary"}}
            logged = c.get("result")
            if isinstance(logged, dict) and set(logged) == {"error"}:
                err = logged["error"]
            elif has_ws:
                res, err, _ = workspace_bridge.call(prof, env, rt, c["name"], c["args"], ws_final, downloads=True,
                                                    wins=bool(row.get("has_workspace")))
            else:
                res, err = rt.run_function(env, c["name"], c["args"])
            if c.get("error") is not None and err is None:
                err = c.get("error")
            args = c["args"]; name = c["name"]
            cur = R.rt(prof.env_to_dict(env))
        else:
            name = s["tool"]
            if s["kind"] == "rejected":
                err = err or "rejected by the framework"
            if name in ("terminal", "execute_bash") and isinstance(args.get("command"), str):
                cwd, wrote = O._sim_shell(args["command"], cwd, cur_ws)
                if ok(s):   # step 16c: a failed command (zip error, missing file, non-zero exit) writes nothing
                    cur_ws.update(wrote)
        for p, k in born.items():
            if k == i and p not in cur_ws or (k == i and cur_ws.get(p) == ws_init.get(p)):
                cur_ws[p] = ws_final[p]
        out.append({"call": {"name": name, "args": args, "result": res, "error": err, "kind": s["kind"]},
                    "pre": pre, "post": cur, "pre_ws": pre_ws, "post_ws": dict(cur_ws)})
    return out
