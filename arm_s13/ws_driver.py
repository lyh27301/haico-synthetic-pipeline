"""Runs inside the agent image (step 13f replay): replays one run's terminal and file_editor actions on the container
disk and returns workspace snapshots. One JSON request per stdin line, one JSON reply per stdout line:
  {"op": "terminal", "command": ...}            bash -c in the tracked cwd, stdin closed, TIMEOUT s
  {"op": "file_editor", "args": {...}}          create / str_replace / insert / undo_edit (view is a no-op)
  {"op": "snap"}                                workspace_bridge.snapshot(since=start)
No network (the container runs with --network none), so chat_npc and downloads fail as they would offline; neither
writes the agent's files."""
import json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace_bridge as W  # noqa: E402

TIMEOUT = 60
T0 = time.time() - 1
CWD = ["/workspace"]
HIST = {}


def terminal(cmd):
    marker = "/tmp/.wsb/cwd"
    script = f"cd {json.dumps(CWD[0])} 2>/dev/null || cd /workspace\n{cmd}\n__rc=$?; pwd > {marker}; exit $__rc"
    try:
        p = subprocess.run(["bash", "-c", script], stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT)
        rc, out = p.returncode, (p.stdout + p.stderr)[-400:].decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        rc, out = "timeout", ""
    try:
        CWD[0] = open(marker).read().strip() or CWD[0]
    except OSError:
        pass
    return {"rc": rc, "tail": out}


def editor(a):
    c, p = a.get("command"), a.get("path")
    if c == "view" or not p:
        return {"rc": 0}
    try:
        old = open(p).read() if os.path.exists(p) else None
        if c == "create":
            os.makedirs(os.path.dirname(p) or "/", exist_ok=True); new = a.get("file_text") or ""
        elif c == "str_replace":
            o = a.get("old_str") or ""
            if old is None or old.count(o) != 1:
                return {"rc": "no_unique_match"}
            new = old.replace(o, a.get("new_str") or "")
        elif c == "insert":
            if old is None:
                return {"rc": "missing"}
            ls = old.split("\n"); i = int(a.get("insert_line") or 0)
            new = "\n".join(ls[:i] + (a.get("new_str") or "").split("\n") + ls[i:])
        elif c == "undo_edit":
            if not HIST.get(p):
                return {"rc": "no_history"}
            new = HIST[p].pop()
            if new is None:
                os.remove(p); return {"rc": 0}
            open(p, "w").write(new); return {"rc": 0}
        else:
            return {"rc": f"unknown {c}"}
        HIST.setdefault(p, []).append(old)
        open(p, "w").write(new)
        return {"rc": 0}
    except Exception as e:  # noqa: BLE001
        return {"rc": f"{type(e).__name__}: {e}"[:200]}


os.makedirs("/workspace", exist_ok=True)
for line in sys.stdin:
    r = json.loads(line)
    if r["op"] == "terminal":
        out = terminal(r["command"])
    elif r["op"] == "file_editor":
        out = editor(r["args"])
    else:
        out = {"ws": W.snapshot(since=T0)}
    sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()
