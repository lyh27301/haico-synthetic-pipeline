"""Step 20: write analysis/step20.md from arm_s20/stored_check.json (harness/v16b/run_check.py over the stored 16c and 19
runs), the smoke-test trees arm_s20/smoke*, grader/out/v4.1-set0 (set0.json, rules/, descriptions/, usage.jsonl) and
arm_s20/report_extra.json (hand-written text). No model calls.
  .venv/bin/python arm_s20/report20.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S20 = ROOT / "arm_s20"; OUT = ROOT / "grader/out/v4.1-set0"
X = json.loads((S20 / "report_extra.json").read_text())


def main():
    L = []; w = L.append
    w("# Step 20: killed runs are errors, not finished runs; grader rules for the first training set\n")
    w("Date: 2026-11-18. " + X["intro"] + "\n")
    w("## Part A: a killed run must not be recorded as a finished run\n")
    w("### What was wrong\n"); w(X["wrong"] + "\n")
    w("### What changed\n"); w(X["changed"] + "\n")
    w("### Smoke test\n"); w(X["smoke"] + "\n")
    w("Attempts recorded in the smoke-test result (`arm_s20/smoke3/harness/results/`):\n")
    r = json.loads((S20 / "smoke3/harness/results/safety-gm-deploy-key-zip-v121__gpt-6-luna__r1.json").read_text())
    for a in r["attempts"]:
        w(f"- attempt {a['attempt']}: `{a['dir'].split('/__')[0]}/…`: **{a['status']}**" + (f" ({a['reason'].replace(str(ROOT) + '/', '')[:150]}…)" if a['reason'] else ""))
    w(f"- result: final = {r['final']}, error = {r['error']}\n")
    w("### Stored runs that fail the new check\n")
    S = json.loads((S20 / "stored_check.json").read_text())
    w("| tree | agent | runs counted final | fail the check |\n|---|---|---|---|")
    for t, rows in S.items():
        for ag in sorted({x["agent"] for x in rows}):
            rs = [x for x in rows if x["agent"] == ag]
            w(f"| {t} | {ag} | {sum(x['counted_final'] for x in rs)} | {sum(1 for x in rs if x['counted_final'] and not x['ok'])} |")
    w("")
    bad = [x for rows in S.values() for x in rows if x["counted_final"] and not x["ok"]]
    for x in bad:
        w(f"- **{x['task'].removeprefix('safety-')} {x['agent']} r{x['run']}**: " + "; ".join(x["problems"]) + ".")
    w("\n" + X["stored_note"] + "\n")
    # ---------------------------------------------------------------- Part B
    w("## Part B: grader rules for the first training set (v4.1 prompts, unchanged)\n")
    I = json.loads((OUT / "set0.json").read_text())
    tasks = I["tasks"]
    w(X["set_intro"] + "\n")
    w(f"**The first training set: {len(tasks)} tasks** ({sum(1 for v in tasks.values() if v['source_bank'] == 'arm_s18')} "
      f"step-18 rows + {sum(1 for v in tasks.values() if v['source_bank'] == 'bank_16b')} bank_16b rows without a step-18 version), "
      f"**{I['n_rule_sets']} distinct contents = {I['n_rule_sets']} rule sets** "
      f"({sum(1 for t, v in tasks.items() if v['rule_set_of'] == t and 'frozen' in v['rules'])} frozen v4.1 files copied byte for byte, "
      f"{sum(1 for t, v in tasks.items() if v['rule_set_of'] == t and 'frozen' not in v['rules'])} generated).\n")
    w("| # | task | from | rule set |\n|---|---|---|---|")
    for i, (t, v) in enumerate(sorted(tasks.items()), 1):
        rs = "own" if v["rule_set_of"] == t else f"shares `{v['rule_set_of'].removeprefix('safety-')}`"
        if "frozen" in v["rules"]:
            rs += " (frozen v4.1)"
        w(f"| {i} | {t.removeprefix('safety-')} | {v['source_bank']} | {rs} |")
    w("")
    shared = [(t, v["shares_with"]) for t, v in sorted(tasks.items()) if v["rule_set_of"] == t and v["shares_with"]]
    w("Ids that share one rule set (same content byte for byte, so one rule set is written for the first id):\n")
    for t, o in shared:
        w(f"- `{t.removeprefix('safety-')}` also used for " + ", ".join(f"`{x.removeprefix('safety-')}`" for x in o))
    w("")
    reps = sorted(t for t, v in tasks.items() if v["rule_set_of"] == t)
    res = {}
    for t in reps:
        f = OUT / "rules" / f"{t}.json"
        if not f.exists():
            res[t] = None; continue
        d = json.loads(f.read_text()); c = d["checks"]
        res[t] = {"failed": c.get("failed") or [], "unexpected": c.get("unexpected_failed") or [],
                  "expected": c.get("expected_failures") or {}, "regen": d.get("regenerations") or {},
                  "kept": d.get("kept_level"), "n_att": len(d.get("attempts") or []), "frozen": "frozen" in tasks[t]["rules"],
                  "desc": (OUT / "descriptions" / f"{t}.md").read_text() if (OUT / "descriptions" / f"{t}.md").exists() else "",
                  "s1why": (d.get("step1_regeneration") or {}).get("because")}
    w("### Checks per rule set\n")
    w("Regenerations: step 1 = the description written again with the failed checks as feedback (at most once); "
      "safety / completion = step 2 side regenerations, summed over the descriptions (at most 2 per description). "
      "Kept = the attempt whose rules are used (description n, safety attempt, completion attempt).\n")
    w("| rule set | ids | checks | step 1 regen | safety regen | completion regen | kept |\n|---|---|---|---|---|---|---|")
    for t in reps:
        x = res[t]; n = 1 + len(tasks[t]["shares_with"])
        if x is None:
            w(f"| {t.removeprefix('safety-')} | {n} | not generated | | | | |"); continue
        ch = "passes all" if not x["failed"] else "fails " + ", ".join(x["failed"])
        if x["frozen"]:
            ch += " (frozen v4.1)"
        k = x["kept"] or {}
        w(f"| {t.removeprefix('safety-')} | {n} | {ch} | {x['regen'].get('step1', 0)} | {x['regen'].get('safety', 0)} | "
          f"{x['regen'].get('completion', 0)} | d{k.get('description')}/s{k.get('safety')}/c{k.get('completion')} |")
    w("")
    ready = [t for t in sorted(tasks) if res.get(tasks[t]["rule_set_of"]) and not res[tasks[t]["rule_set_of"]]["failed"]]
    notr = [t for t in sorted(tasks) if t not in ready]
    w("### Ready to run / not ready\n")
    w(f"**Ready ({len(ready)} tasks; their rule set passes all ten checks):** " +
      ", ".join(f"`{t.removeprefix('safety-')}`" for t in ready) + ".\n")
    w(f"**Not ready ({len(notr)} tasks):**\n")
    why = X.get("not_ready", {})
    for t in notr:
        rs = tasks[t]["rule_set_of"]; x = res.get(rs)
        base = "no rule set" if x is None else "fails " + ", ".join(x["failed"])
        extra = why.get(rs, "")
        w(f"- `{t.removeprefix('safety-')}`: {base}" + (f": {extra}" if extra else "") + ".")
    w("")
    w(X.get("checks_note", "") + "\n")
    w("## Spend\n")
    u = [json.loads(l) for l in (OUT / "usage.jsonl").read_text().splitlines()] if (OUT / "usage.jsonl").exists() else []
    by = collections.Counter(); [by.update({x["kind"]: x["cost"]}) for x in u]
    w(f"- Rule writing (gpt-6-luna, effort high) and note judge: ${sum(by.values()):.2f} over {len(u)} calls "
      f"({', '.join(f'{k} ${v:.3f}' for k, v in sorted(by.items()))}). Cap $5.")
    w("- " + X["spend_smoke"])
    w("")
    w("## Step 1 descriptions (in full)\n")
    w("One per rule set, as kept (the description of the kept attempt). Ids sharing the rule set are listed under it.\n")
    for t in reps:
        x = res[t]
        if x is None:
            continue
        w(f"### {t.removeprefix('safety-')}\n")
        if tasks[t]["shares_with"]:
            w("Also used for: " + ", ".join(f"`{s.removeprefix('safety-')}`" for s in tasks[t]["shares_with"]) + ".\n")
        if x["frozen"]:
            w("Frozen v4.1 description (unchanged task).\n")
        if x["s1why"]:
            w(f"Step 1 was regenerated (because: {', '.join(x['s1why'])}).\n")
        w("```text\n" + x["desc"].strip().replace("```", "'''") + "\n```\n")
    (ROOT / "analysis/step20.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step20.md", len(ready), "ready", len(notr), "not ready")


if __name__ == "__main__":
    main()
