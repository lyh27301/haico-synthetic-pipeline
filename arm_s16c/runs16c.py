"""Step 16c: the Part A runs as engine steps, from their recorded per-step states (arm_s16b/smoke_grade.py's reading,
for every run): the agent's actions from the conversation history; the state before action n is the step record the
agent-server wrote just before it ran (toolkit state + workspace bytes), the state after it is the next record (or the
final one). Binary markers and workspace files are resolved to text with harness/filetext.py.
  import runs16c; runs16c.results() -> [result dict]; runs16c.load(result) -> {...}"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; C = ROOT / "arm_s16c"
sys.path[:0] = [str(ROOT / "arm_s16b"), str(ROOT / "harness")]
import filetext, ws_store  # noqa: E402,E401
from smoke_grade import actions  # noqa: E402

TREES = (C / "runs", C / "qwen")
_BANK = None


def bank():
    global _BANK
    if _BANK is None:
        _BANK = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s16b/bank/bank_16b.jsonl").read_text().splitlines()}
    return _BANK


def results(final_only=True) -> list:
    out = []
    for t in TREES:
        for f in sorted((t / "harness/results").glob("*.json")):
            r = json.loads(f.read_text())
            if not final_only or r.get("final"):
                out.append(r | {"key": f.stem})
    return out


def output_row(r) -> dict:
    for ln in (ROOT / r["traj_dir"] / "output.critic_attempt_1.jsonl").read_text().splitlines():
        o = json.loads(ln)
        if o["instance_id"] == r["task"]:
            return o
    raise KeyError(r["task"])


def load(r) -> dict:
    sd = ROOT / r["state_dir"] / "v16b"
    o = output_row(r)
    recs = {p.stem: json.loads(p.read_text()) for p in (sd / "steps").glob("*.json")}
    blobs = [str(sd / "blobs")]
    cache = {}

    def ws_of(rec):
        out = {}
        for p, m in (rec or {}).get("ws", {}).items():
            if m["sha256"] not in cache:
                b = sd / "blobs" / m["sha256"]
                cache[m["sha256"]] = filetext.extract(b.read_bytes(), p.rsplit("/", 1)[-1]) if b.exists() else "[not stored]"
            out[p] = cache[m["sha256"]]
        return out

    def env_of(rec):
        return ws_store.resolve((rec or {}).get("env_post") or {}, blobs)
    acts = actions(o.get("history") or [])
    by_id = {x.get("action_id"): x for k, x in recs.items() if k != "final"}
    order = [by_id.get(a[0]) for a in acts]
    steps, missing = [], []
    raw = {e.get("id"): e for e in (o.get("history") or []) if e.get("kind") == "ActionEvent"}
    for i, (aid, tool, args, txt, err) in enumerate(acts):
        pre_rec = by_id.get(aid)
        nxt = next((x for x in order[i + 1:] if x is not None), None) or recs.get("final")
        if pre_rec is None:
            # a call the framework rejected before it ran (arguments failed validation): no state was recorded because
            # nothing reached the server; the step keeps the state unchanged, the agent's raw arguments and the error
            missing.append((i, tool))
            try:
                args = json.loads(((raw.get(aid) or {}).get("tool_call") or {}).get("arguments") or "{}")
            except ValueError:
                args = {"raw_arguments": ((raw.get(aid) or {}).get("tool_call") or {}).get("arguments")}
            st = env_of(nxt); w = ws_of(nxt)
            steps.append({"i": i, "rejected": True, "call": {"name": tool, "args": args, "result": txt,
                          "error": txt or "rejected"}, "pre": st, "post": st, "pre_ws": w, "post_ws": w})
            continue
        steps.append({"i": i, "call": {"name": tool, "args": args, "result": txt, "error": txt if err else None},
                      "pre": env_of(pre_rec), "post": env_of(nxt), "pre_ws": ws_of(pre_rec), "post_ws": ws_of(nxt)})
    return {"row": bank()[r["task"]], "steps": steps, "missing": missing, "history": o.get("history") or [],
            "output": o, "state_dir": sd, "n_actions": len(acts)}
