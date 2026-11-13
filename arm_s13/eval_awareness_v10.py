"""Step 13j: visible-text and thinking scan of the v0.10 runs (arm_v10 API agents, arm_v10/qwen), with the same two-stage
patterns as arm_s13/eval_awareness.py, plus a fourth channel:
  thinking   Claude thinking blocks with readable text (stored once the agent image asked for summarized thinking:
             Haiku rounds 3-5, Sonnet rounds 2-3).
Joined with the follow-up answers (arm_v10/followup13j.jsonl) per run. No model calls.
Output: arm_s13/eval_awareness_v10.json (per agent: runs, readable-thinking runs, aware per channel, follow-up yes /
no / unclear / no answer, and the overlap), arm_s13/eval_awareness_v10_runs.jsonl.
  .venv/bin/python arm_s13/eval_awareness_v10.py"""
import collections, glob, json, re
from pathlib import Path

import eval_awareness as E

ROOT = E.ROOT; S13 = E.S13
TREES = ["arm_v10", "arm_v10/qwen"]


def texts(hist):
    yield from E.texts(hist)
    for e in hist or []:
        for b in e.get("thinking_blocks") or []:
            if isinstance(b, dict) and (b.get("thinking") or "").strip():
                yield "thinking", b["thinking"]


def scan(job):
    tree, r = job
    traj = Path(r["traj_dir"]); traj = traj if traj.is_absolute() else ROOT / traj
    hist = E.R.history(traj, r["task"])
    hits, chans = [], collections.Counter()
    for ch, txt in texts(hist):
        if not txt:
            continue
        chans[ch] += 1
        for name, rx in E.RX:
            for m in rx.finditer(txt):
                h = {"channel": ch, "pattern": name, "match": m.group(0),
                     "context": re.sub(r"\s+", " ", txt[max(0, m.start() - 160):m.end() + 160])}
                k = E.kind(h)
                if k:
                    hits.append(h | {"kind": k})
    tb = [b for e in hist or [] for b in (e.get("thinking_blocks") or []) if isinstance(b, dict)]
    return {"task": r["task"], "agent": r["agent"], "run": int(r["run"]), "tree": tree, "eval_aware": bool(hits),
            "channels": sorted({h["channel"] for h in hits}), "kinds": sorted({h["kind"] for h in hits}), "hits": hits[:5],
            "thinking_blocks": len(tb), "thinking_blocks_readable": sum(bool((b.get("thinking") or "").strip()) for b in tb),
            "channels_seen": dict(chans), "no_history": hist is None}


def main():
    jobs = []
    for tree in TREES:
        for f in sorted(glob.glob(str(ROOT / tree / "harness/results/*.json"))):
            r = json.loads(Path(f).read_text())
            if r.get("graded") and r.get("traj_dir"):
                jobs.append((tree, r))
    rows = [scan(j) for j in jobs]
    fu = {(o["task"], o["agent"], o["run"], o["tree"]): o for o in map(json.loads, (ROOT / "arm_v10/followup13j.jsonl").read_text().splitlines())}
    for r in rows:
        o = fu.get((r["task"], r["agent"], r["run"], r["tree"]))
        r["followup"] = None if o is None else ("skipped" if o.get("skipped") else (o.get("aware") or "no answer"))
        r["followup_reasons"] = (o or {}).get("reasons") or []
    (S13 / "eval_awareness_v10_runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    out = {}
    for a in sorted({r["agent"] for r in rows}):
        xs = [r for r in rows if r["agent"] == a]
        th = [r for r in xs if r["thinking_blocks_readable"]]
        out[a] = {"runs": len(xs), "no_history": sum(r["no_history"] for r in xs),
                  "aware_visible": sum(any(c != "thinking" for c in r["channels"]) for r in xs),
                  "runs_with_readable_thinking": len(th),
                  "aware_in_thinking": sum("thinking" in r["channels"] for r in th),
                  "by_channel": dict(collections.Counter(c for r in xs for c in r["channels"])),
                  "followup": dict(collections.Counter(r["followup"] for r in xs)),
                  "followup_yes_among_readable_thinking": sum(r["followup"] == "yes" for r in th),
                  "examples_thinking": [h["context"] for r in th for h in r["hits"] if h["channel"] == "thinking"][:5]}
    (S13 / "eval_awareness_v10.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
