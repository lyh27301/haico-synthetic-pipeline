"""Step 27 part 1: the task versions the step-14 branches ran on, as rows the v4.2 pipeline reads. Nothing is repaired.
Per task id of arm_s14/r2/jobs_r2.json (the 19 steps; v1 / v2-continue use the same steps):
  - the row is the v0.8 bank row the branches ran on (arm_v08/bank_v08.jsonl, as arm_s14/branch.py loads it), unchanged;
  - safe_reference / violator_reference: the task's scenario file whose problem statement matches that row
    (arm_s13/exposure.scenario, the lookup step 14 used for its alternatives), unchanged;
  - current_date: the old versions have none (the agent saw the wall clock). The v4.2 step-1 prompt needs a "today", so
    the rows carry 2026-11-16, the day the step-14 round-2 branches ran (a pipeline input; the agent never saw it);
  - agent context: harness/agent_context.json (what the old harness showed the agent);
  - staged files: arm_hf/out_v08/<workspace_files spec> (the harness's OAS_WORKSPACE_ROOT for v0.8 rows).
  .venv/bin/python arm_s27/bank27.py   -> arm_s27/bank/bank_27.jsonl, agent_context_27.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / "arm_s27/bank"
sys.path[:0] = [str(ROOT / "arm_s13")]
STAGE = ROOT / "arm_hf/out_v08"
TODAY = "2026-11-16"


def task_ids():
    return sorted({j["task"] for j in json.loads((ROOT / "arm_s14/r2/jobs_r2.json").read_text())})


def staged(row) -> dict:
    out = {}
    for spec in row.get("workspace_files") or []:
        p = STAGE / spec
        if p.exists():
            out["/workspace/" + spec.split("/workspace/", 1)[1]] = p.read_bytes()
    return out


def build():
    import exposure as X
    rows = X.bank_rows(); ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    out, octx = [], {}
    for t in task_ids():
        r = dict(rows[t]); sc = X.scenario(t, r)
        assert X.norm(sc.get("problem_statement", "")) == X.norm(r["problem_statement"]), t
        r["safe_reference"] = sc.get("safe_reference") or []
        r["violator_reference"] = sc.get("violator_reference") or []
        r["current_date"] = TODAY
        r["derived_from"] = "arm_v08/bank_v08.jsonl (step 14 branches); references from the matching scenario file"
        out.append(r); octx[t] = ctx.get(t, "")
    return out, octx


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    rows, ctx = build()
    (OUT / "bank_27.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / "agent_context_27.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
    print(len(rows), "rows;", sum(bool(c) for c in ctx.values()), "with agent context")
