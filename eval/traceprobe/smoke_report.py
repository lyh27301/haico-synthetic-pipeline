"""Step 15-smoke: per-scenario outcome of a smoke run of the converted TraceProbe rows on the OAS harness.
Checks per scenario: row loads (instance in output), container started (files staged), rollout completed (history and
no conversation error), every checkpoint evaluated (no evaluator error, one result per criterion), final verdict
produced. Writes eval/traceprobe/smoke_result.json.
  .venv/bin/python eval/traceprobe/smoke_report.py <run output dir> [wall seconds]"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def first_err(log: Path) -> str:
    if not log.exists():
        return "no instance log"
    for ln in log.read_text(errors="replace").splitlines():
        if re.search(r"\b(ERROR|Traceback|Exception)\b", ln):
            return ln.strip()[:240]
    return ""


def main():
    out_dir = Path(sys.argv[1]); wall = float(sys.argv[2]) if len(sys.argv) > 2 else None
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (HERE / "smoke.jsonl").read_text().splitlines()}
    res = {}
    for f in out_dir.rglob("output.jsonl"):
        for l in f.read_text().splitlines():
            o = json.loads(l); res[o["instance_id"]] = (o, f.parent)
    table, cost = [], 0.0
    for iid, r in rows.items():
        o, base = res.get(iid, (None, None))
        n_crit = len(json.loads(__import__("base64").b64decode(
            re.search(r'b64decode\("([^"]+)"\)', r["evaluator_code"]).group(1))))
        rec = {"instance": iid, "track": r["tp_track"], "difficulty": r["tp_difficulty"], "loads": o is not None}
        if o is None:
            rec |= {"outcome": "not run", "first_error": "instance missing from output.jsonl"}
            table.append(rec); continue
        st = base / "traceprobe_state" / iid
        tr = o.get("test_result") or {}
        tp = tr.get("traceprobe") or {}
        crit = tp.get("criteria") or []
        u = json.loads((st / "usage.json").read_text()) if (st / "usage.json").exists() else {}
        cost += u.get("accumulated_cost") or 0.0
        rec |= {"container_started": (st / "files").exists(),
                "rollout_completed": bool(o.get("history")) and not o.get("error"),
                "checkpoints_ok": len(crit) == n_crit and "error" not in tr,
                "verdict": None if not tp else ("unsafe" if tp["unsafe"] else "safe"),
                "task_complete": tp.get("task_complete"), "accepted": tp.get("accepted"),
                "n_steps": sum(1 for e in o.get("history") or [] if e.get("kind") == "ActionEvent"),
                "cost": u.get("accumulated_cost")}
        ok = rec["container_started"] and rec["rollout_completed"] and rec["checkpoints_ok"] and rec["verdict"] is not None
        rec["outcome"] = "ok" if ok else "fail"
        rec["first_error"] = "" if ok else (o.get("error") or tr.get("error") or
                                            first_err(base / "logs" / f"instance_{iid}.log"))[:240]
        table.append(rec)
    summ = {"n": len(table), "end_to_end": sum(r["outcome"] == "ok" for r in table), "wall_seconds": wall,
            "cost_usd": round(cost, 4), "table": table}
    (HERE / "smoke_result.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
