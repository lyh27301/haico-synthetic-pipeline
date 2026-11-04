"""Re-grade every 12b result (arm_s12/harness/results/*.json) in place with the current harness/grader_v2.py, from the
stored pre/post state, calls.jsonl and rejected_calls.jsonl (no model calls). Needed once at the end of 12b: the
batch-1/2 runners graded with grader v2 as it was before the step-12b audit fixes (analysis/step12a.md, "Correction
after the held-out audit"). Only graded results change; each changed verdict is listed.
  .venv/bin/python arm_s12/regrade12b.py"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"
sys.path.insert(0, str(ROOT / "harness"))
import grader_v2  # noqa: E402

FIELDS = ("unsafe", "harm_realized", "attempted_leak", "leak_rule", "side_effect", "side_effects")


def main():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (S12 / "bank_12b.jsonl").read_text().splitlines()}
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    n = changed = 0
    for f in sorted((S12 / "harness/results").glob("*.json")):
        r = json.loads(f.read_text())
        if not r.get("graded"):
            continue
        sd = ROOT / r["state_dir"]
        js = lambda x: [json.loads(l) for l in (sd / x).read_text().splitlines() if l.strip()] if (sd / x).exists() else []
        v = grader_v2.grade(rows[r["task"]], json.loads((sd / "pre.json").read_text()),
                            json.loads((sd / "post.json").read_text()), js("calls.jsonl"), ctx.get(r["task"], ""),
                            js("rejected_calls.jsonl"))
        n += 1
        if bool(v["unsafe"]) != bool(r["unsafe"]):
            changed += 1
            print(f.stem, r["unsafe"], "->", v["unsafe"], r.get("leak_rule"), "->", v["leak_rule"],
                  json.dumps(r.get("side_effects"))[:160], flush=True)
        r.update({k: v[k] for k in FIELDS}, regraded=True)
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(r, indent=1, default=str)); tmp.replace(f)
    print(f"{n} graded results re-graded, {changed} verdicts changed")


if __name__ == "__main__":
    main()
