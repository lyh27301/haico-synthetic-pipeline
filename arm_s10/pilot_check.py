"""Step 10 Part C2: the three pilot checks, from arm_s10/harness/results + each run's MCP call log.
  1. no-grade rate under the new cap (vs step 9's 106 token-capped + other no-grades of 970);
  2. the 5 step-9-good Gmail tasks still good (mixed over the 5 new runs; also shown over all 10);
  3. target-found rate of the 5 rescued tasks: a run reaches the target if any discoverability target id
     (recipe/discover_gate.targets: the records the violator path touches) appears in the result of one of its tool calls.
  .venv/bin/python arm_s10/pilot_check.py -> arm_s10/pilot.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402
from recipe import discover_gate as D  # noqa: E402

S10 = ROOT / "arm_s10"; RES = S10 / "harness" / "results"; RES9 = ROOT / "arm_s9" / "harness" / "results"
MAN = json.loads((ROOT / "arm_hf/out_v04/manifest.json").read_text())["tasks"]


def task_dir(t: str) -> Path:
    for d in (S10 / "tasks" / t, ROOT / "arm_s9" / "tasks" / t):
        if d.exists():
            return d
    return ROOT / MAN[t]["dir"]


def reached(rec: dict, tg: list[str]) -> bool | None:
    f = ROOT / rec.get("state_dir", "") / "calls.jsonl" if rec.get("state_dir") else None
    if not f or not f.exists():
        return None if not rec.get("state_dir") else False
    for ln in f.read_text().splitlines():
        c = json.loads(ln)
        if any(D.has(json.dumps(c.get("result"), default=str).lower(), t) for t in tg):
            return True
    return False


def main():
    good = (S10 / "ids_pilot_good.txt").read_text().split(); resc = (S10 / "ids_pilot_rescued.txt").read_text().split()
    recs = {t: [json.loads((RES / f"{t}__4omini__r{k}.json").read_text()) for k in (range(6, 11) if t in good else range(1, 6))
                if (RES / f"{t}__4omini__r{k}.json").exists()] for t in good + resc}
    allr = [r for v in recs.values() for r in v]
    out = {"runs": len(allr), "no_grade": sum(not r["graded"] for r in allr),
           "capped": sum(bool(r.get("capped")) for r in allr),
           "no_grade_reasons": [(r["task"], r["run"], (r.get("error") or "")[:120]) for r in allr if not r["graded"]]}
    out["no_grade_rate"] = out["no_grade"] / max(out["runs"], 1)
    out["good"] = {}
    for t in good:
        u = [r["unsafe"] for r in recs[t] if r["graded"]]
        old = [json.loads((RES9 / f"{t}__4omini__r{k}.json").read_text()) for k in range(1, 6)]
        u9 = [r["unsafe"] for r in old if r.get("graded")]
        out["good"][t] = {"step9": f"{sum(u9)}/{len(u9)}", "new": f"{sum(u)}/{len(u)}",
                          "still_good_new5": 0 < sum(u) < len(u), "good_all10": 0 < sum(u9 + u) < len(u9 + u)}
    out["flips"] = sum(not v["still_good_new5"] for v in out["good"].values())
    out["rescued"] = {}
    for t in resc:
        d = task_dir(t); prof = driver.profile_for(d)
        task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
        tg = D.targets(prof, task, str(d / "environment.yaml"))
        hits = [reached(r, tg) for r in recs[t]]
        u = [r["unsafe"] for r in recs[t] if r["graded"]]
        out["rescued"][t] = {"targets": tg, "reached": sum(bool(h) for h in hits), "runs": len(hits),
                             "unsafe": f"{sum(u)}/{len(u)}"}
    n = sum(v["runs"] for v in out["rescued"].values())
    out["target_found_rate"] = sum(v["reached"] for v in out["rescued"].values()) / max(n, 1)
    (S10 / "pilot.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "no_grade_reasons"}, indent=1))


if __name__ == "__main__":
    main()
