"""Step 16b: stored runs of the 50 tasks as engine steps (for the comparison with 16a, the review and the pilot score).

Each run is renamed with the rename table and replayed on the renamed v0.8 environment exactly as step 16a replays it
(arm_s16/regrade.py: logged failures stay failed, v0.8+ runs go through the workspace bridge; the regression of item 12
shows this replay grades identically to 16a). Steps are indexed like 16a's steps files (replay.steps_of), so step
labels line up with 16a's and with the pilot gold.
Workspace per step: stored runs have only the initial and final workspace snapshots (plus 16a's G6 rebuilt PDF text);
a file that is new or changed at the end is placed at the first terminal / file_editor step whose arguments name it
(else the last such step). The 16b runs record every step's workspace instead."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16, S16B = ROOT / "arm_s16", ROOT / "arm_s16b"
sys.path[:0] = [str(S16B), str(ROOT), str(ROOT / "harness"), str(ROOT / "arm_s13"), str(S16)]
import rename as RN  # noqa: E402
import replay as R  # noqa: E402
import exposure as X  # noqa: E402
import workspace_bridge  # noqa: E402
from recipe import profiles  # noqa: E402

RN.load()
_BANK = None


def js(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else {}


def bank():
    global _BANK
    if _BANK is None:
        _BANK = {t: RN.rn(r) | {"environment": RN.rn_yaml(r["environment"])} for t, r in X.bank_rows().items()}
    return _BANK


def runs(pilot=False) -> list:
    sel = {s["task"] for s in json.loads((S16B / "selection.json").read_text())}
    f = S16 / ("runs_pilot.jsonl" if pilot else "runs.jsonl")
    out = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [r for r in out if r["task"] in sel and "crash" not in r and "unsafe_v5" in r]


def _sim_shell(cmd: str, cwd: str, ws: dict) -> tuple[str, dict]:
    """The file effects of `cd`, `zip` and `cp` in a stored terminal command, on a {path: text} workspace (stored runs
    did not snapshot the disk after terminal steps). Returns (new cwd, {path: text} written)."""
    import fnmatch, posixpath, re, shlex
    out = {}
    for part in re.split(r"\s*(?:&&|;|\n)\s*", cmd):
        try:
            tok = shlex.split(part)
        except ValueError:
            continue
        if not tok:
            continue
        ab = lambda q: posixpath.normpath(q if q.startswith("/") else posixpath.join(cwd, q))
        if tok[0] == "cd" and len(tok) > 1:
            cwd = ab(tok[1]); continue
        if tok[0] == "zip":
            args = [a for a in tok[1:] if not a.startswith("-")]
            if not args:
                continue
            arc = ab(args[0] if args[0].endswith(".zip") else args[0] + ".zip")
            mem = []
            for a in args[1:]:
                q = ab(a)
                for p in sorted({**ws, **out}):
                    rel = None
                    if fnmatch.fnmatch(p, q) or p == q:
                        rel = posixpath.relpath(p, cwd) if p.startswith(cwd + "/") else p.rsplit("/", 1)[-1]
                    elif p.startswith(q.rstrip("/") + "/"):
                        rel = posixpath.relpath(p, cwd) if p.startswith(cwd + "/") else p[len(posixpath.dirname(q)) + 1:]
                    if rel and rel not in [m for m, _ in mem]:
                        mem.append((rel, {**ws, **out}[p]))
            if mem:
                out[arc] = "[zip archive " + arc.rsplit("/", 1)[-1] + "] members:\n" + "\n".join(m for m, _ in mem) + \
                    "".join(f"\n== {m} ==\n{v}" for m, v in mem)
        if tok[0] == "cp" and len(tok) >= 3:
            src, dst = ab(tok[-2]), ab(tok[-1])
            v = {**ws, **out}.get(src)
            if v is not None:
                out[dst if not dst.endswith("/") and not any(k.startswith(dst + "/") for k in ws) else dst.rstrip("/") + "/" + src.rsplit("/", 1)[-1]] = v
    return cwd, out


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
    born = {}
    for p in changed:
        b = p.rsplit("/", 1)[-1]
        hits = [i for i in writers if b in json.dumps(st[i].get("args") or {}, default=str)]
        born[p] = hits[0] if hits else (writers[-1] if writers else None)
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
                cwd, wrote = _sim_shell(args["command"], cwd, cur_ws)
                cur_ws.update(wrote)
        for p, k in born.items():
            if k == i and p not in cur_ws or (k == i and cur_ws.get(p) == ws_init.get(p)):
                cur_ws[p] = ws_final[p]
        out.append({"call": {"name": name, "args": args, "result": res, "error": err, "kind": s["kind"]},
                    "pre": pre, "post": cur, "pre_ws": pre_ws, "post_ws": dict(cur_ws)})
    return out
