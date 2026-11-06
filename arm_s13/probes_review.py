"""Step 13c item 2: the probe specs of the 25 pilot tasks in one file for hand review -> arm_s13/probes_pilot_review.md.
Per task: the statement, the evaluator's harm (checkpoint text, cue marker, grader constants), then every rule as
tools + conditions + why, with the gate record (attempts, dropped rules, coverage failures).
  .venv/bin/python arm_s13/probes_review.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"


def cond(c) -> str:
    v = "" if c.get("op") == "external" else f" `{c.get('value')}`"
    return f"`{c.get('field')}` {c.get('op')}{v}"


def main():
    import sys
    for p in ("", "analysis", "harness"):
        sys.path.insert(0, str(ROOT / p))
    from bank import bank
    import grader_v2
    b = bank()
    rows = {json.loads(l)["instance_id"]: json.loads(l) for f in ("arm_s11/bank_v06.jsonl", "arm_s12/bank_12b.jsonl")
            for l in (ROOT / f).read_text().splitlines()}
    man = [json.loads(l) for l in (S13 / "pilot_manifest.jsonl").read_text().splitlines()]
    tasks = list(dict.fromkeys(m["task"] for m in man))
    info = {m["task"]: m for m in man}
    out = ["# Probe specs for the 25 pilot tasks (step 13c, for review)", "",
           "Each rule fires on ONE tool call when all its conditions hold (case-insensitive; `regex` is Python re with "
           "IGNORECASE and DOTALL; a condition on a missing field is false). `send_0` is the built-in grader v2 "
           "attempted_leak, evaluated on the single call. Edit the JSON in `arm_s13/probes/<task>.json`, or mark "
           "changes here and I will apply them. A rule tagged v2_blind_spot fires on stored runs grader v2 grades "
           "safe, on calls that write the harm into a sink v2 cannot see (step 13 issue 2): kept as evidence. "
           "probe_coverage=false: no rule fires on the task's violator reference path (harm inside file content); "
           "the task stays state-grader territory. Tags: manual (hand-written, arm_s13/probes_manual.json), hinted (fitted on "
           "the logged calls of arm_s13/probes_hints.json), split from (the read / move halves of an \"any terminal "
           "command containing <file>\" rule), subsumes (near-duplicates merged by the dedupe).", ""]
    for i, t in enumerate(tasks, 1):
        sp = json.loads((S13 / "probes" / f"{t}.json").read_text())
        d = ROOT / "arm_s12/tasks" / t if (ROOT / "arm_s12/tasks" / t).exists() else Path(b[t]["dir"])
        sc = json.loads((d / "scenario.json").read_text())
        row = rows[t]
        consts = {k: v for k, v in grader_v2.constants(row["evaluator_code"]).items() if k not in ("NEW_ONLY",)}
        m = info[t]
        out += [f"## {i}. `{t}`", "",
                f"- **Toolkit / carrier / goodness:** {sp['toolkit']} / {m['carrier']} / {m['goodness']}",
                f"- **Task:** {row['problem_statement'].strip()[:600]}",
                f"- **Evaluator harm:** {sc.get('checkpoint_text', '').strip()[:500]}",
                f"- **Cue marker:** `{str(sc.get('cue_marker'))[:200]}`",
                f"- **Grader constants:** `{json.dumps(consts, default=str)[:400]}`", ""]
        g = sp["gate"]
        out.insert(len(out) - 1, f"- **probe_coverage:** {sp.get('probe_coverage')}"
                   + (f"; **named targets (issue 3):** {', '.join(sp['targets'])}" if sp.get("targets") else ""))
        old = S13 / "probes_rounds/r2" / f"{t}.json"
        if old.exists():
            key = lambda r: (json.dumps(sorted(r.get("tools") or [])), json.dumps(r.get("match"), sort_keys=True))
            o = {key(r): r["id"] for v in json.loads(old.read_text())["probes"].values() for r in v if not r.get("builtin")}
            nw = {key(r): r["id"] for v in sp["probes"].values() for r in v if not r.get("builtin")}
            out.insert(len(out) - 1, f"- **vs round 2:** kept {len(set(o) & set(nw))}, added "
                       f"{[nw[k] for k in nw if k not in o] or 'none'}, removed {[o[k] for k in o if k not in nw] or 'none'}")
        n = 0
        for typ, rules in sp["probes"].items():
            for r in rules:
                n += 1
                if r.get("builtin"):
                    out.append(f"- **{typ} `{r['id']}`**: built-in grader v2 attempted_leak on this call")
                    continue
                out.append(f"- **{typ} `{r['id']}`** on {', '.join(f'`{x}`' for x in r['tools'])}: "
                           + " AND ".join(cond(c) for c in r["match"]))
                out.append(f"  - why: {r.get('why', '')}")
                tg = [f"**manual**"] * bool(r.get("manual")) + \
                     ([f"**hinted** (fitted on {', '.join(f'{x['agent']} r{x['run']} s{x['step']}' for x in r['hinted'])})"]
                      if r.get("hinted") else []) + \
                     ([f"split from `{r['split_from']}`"] if r.get("split_from") else []) + \
                     ([f"subsumes {', '.join(f'`{x['id']}`' for x in r['subsumes'])}"] if r.get("subsumes") else [])
                if tg:
                    out.append("  - " + "; ".join(tg))
                if r.get("v2_blind_spot"):
                    bs = r["v2_blind_spot"]
                    out.append(f"  - **v2_blind_spot:** fires on {len(bs)} step(s) of v2-safe runs: "
                               + ", ".join(f"{x['agent']} r{x['run']} s{x['step']}" for x in bs[:6])
                               + (" ..." if len(bs) > 6 else ""))
        if not n:
            out.append("- (no rules)")
        gl = f"passed after {g['attempts']} attempt(s)" if g["passed"] else f"NOT passed after {g['attempts']} attempts"
        out.append(f"- *gate:* {gl}" + (f"; failures: {'; '.join(g['failures'])}" if g["failures"] else "")
                   + (f"; dropped: {json.dumps(g['dropped'])[:400]}" if g["dropped"] else ""))
        out.append("")
    (S13 / "probes_pilot_review.md").write_text("\n".join(out))
    print(len(tasks), "tasks ->", S13 / "probes_pilot_review.md")


if __name__ == "__main__":
    main()
