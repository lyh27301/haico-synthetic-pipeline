"""Step 22: write analysis/step22.md from grader/out/v4.2-set0 (set.json, rules, descriptions, recheck_set0b.json,
usage), grader/out/v4.2/score.json, arm_s22/tasks_report.json, arm_s22/venmo_note.json and arm_s22/report_extra.json.
No model calls.   .venv/bin/python arm_s22/report22.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; O = ROOT / "grader/out/v4.2-set0"; S22 = ROOT / "arm_s22"
X = json.loads((S22 / "report_extra.json").read_text())
s = lambda t: t.removeprefix("safety-")


def checks_of(t):
    d = json.loads((O / "rules" / f"{t}.json").read_text()); c = d["checks"]
    return d, c.get("failed") or [], c.get("not_applicable") or []


def main():
    L = []; w = L.append
    I = json.loads((O / "set.json").read_text())["tasks"]
    old = json.loads((ROOT / "grader/out/v4.1-set0b/set0b.json").read_text())["tasks"]
    w("# Step 22: the 12 tasks whose rules failed a check\n")
    w("Date: 2026-11-18. Branch `step22`, in a separate worktree while step 21 ran in the main checkout. No agent runs; "
      "the step 21 run folders were not read. Nothing under arm_s18/bank, harness/v16b or the agent image was changed.\n")
    w(X["intro"] + "\n")
    w("## The 12 tasks\n")
    w("| task | failed in v4.1-set0b | cause | what changed | ten checks now (v4.2) |\n|---|---|---|---|---|")
    new_of = {v["replaces"]: k for k, v in I.items() if v.get("replaces")}
    for t, row in X["rows"].items():
        rid = I[new_of.get(t, t)]["rule_set_of"]
        d, fl, na = checks_of(rid)
        now = ("all pass" if not fl else "fails " + ", ".join(fl)) + (f"; {', '.join(na)}: not applicable" if na else "")
        w(f"| {s(t)} | {row['failed']} | {row['cause']} | {row['changed']} | {now} |")
    w("")
    w("## A. fn-venmo-anonymity: the safe-variant note, before and after\n")
    vn = json.loads((S22 / "venmo_note.json").read_text())
    for k in ("before (v4.1)", "after (v4.2)"):
        w(f"- **{k}**: appended text `{vn[k]['note']}` → fires {vn[k]['fires'] or 'nothing'} (safe_variant_ok = {vn[k]['safe_variant_ok']})")
    w("\n" + X["venmo"] + "\n")
    w("## C. fn-payroll-reroute: \"modify on scheduled_payments is not recorded\"\n")
    w(X["payroll_modify"] + "\n")
    w("## E. Task changes (arm_s22/bank)\n")
    T = json.loads((S22 / "tasks_report.json").read_text())
    for t, r in T.items():
        w(f"### {s(t)} (from `{s(r['derived_from'])}`)\n")
        v = r["validate"]
        w(f"validate(): safe reference {v['safe_reference']['steps']} steps, {len(v['safe_reference']['errors'])} tool errors; "
          f"violator {v['violator_reference']['steps']} steps, {len(v['violator_reference']['errors'])} tool errors. "
          f"synthetic(): " + ("; ".join(f"{k}: {x}" for k, x in r["synthetic"].items() if x) or "clean") + ".\n")
        w("Environment diff:\n\n```diff\n" + r["environment_diff"] + "\n```\n")
        for f, txt in r["new_files"].items():
            w(f"New staged file `{f}`:\n\n```text\n{txt.strip()}\n```\n")
        rid = I[t]["rule_set_of"]; d, fl, na = checks_of(rid)
        w(f"Rules: {'all ten checks pass' if not fl else 'fails ' + ', '.join(fl)}.\n")
    w("## All 46 rule sets regenerated and re-checked\n")
    w(X["all_intro"] + "\n")
    w("| task | rule set | v4.1-set0b | v4.2 | step 1 / safety / completion regenerations |\n|---|---|---|---|---|")
    changed_pass = []
    for t in sorted(I):
        rid = I[t]["rule_set_of"]; d, fl, na = checks_of(rid)
        o = old.get(I[t].get("replaces") or t)
        ofl = None
        if o:
            od = json.loads((ROOT / o["rule_file"]).read_text()); ofl = od["checks"].get("failed") or []
        before = "—" if ofl is None else ("pass" if not ofl else "fails " + ", ".join(ofl))
        now = ("pass" if not fl else "fails " + ", ".join(fl)) + (" (violator_flagged n/a)" if na else "")
        rg = d.get("regenerations") or {}
        if ofl == [] and fl:
            changed_pass.append(t)
        w(f"| {s(t)} | {'own' if rid == t else s(rid)} | {before} | {now} | {rg.get('step1', 0)} / {rg.get('safety', 0)} / {rg.get('completion', 0)} |")
    w("")
    w(("**Previously passing, now failing:** " + ", ".join(f"`{s(t)}`" for t in changed_pass) + ".") if changed_pass else
      "**No task that passed in v4.1-set0b fails in v4.2.**")
    w("\n" + X.get("all_note", "") + "\n")
    rc = json.loads((O / "recheck_set0b.json").read_text())
    w("Check changes alone (the v4.2 checks run on the frozen v4.1-set0b rule files, before regenerating): " +
      "; ".join(f"`{s(t)}`: {', '.join(v['failed']) or 'pass'}" + (" (violator_flagged n/a)" if v["not_applicable"] else "")
                for t, v in rc.items() if v["failed"] or v["not_applicable"]) +
      ". Every other set0b rule set passes the v4.2 checks unchanged.\n")
    w("## Pilot v3 dev files\n")
    sc = json.loads((ROOT / "grader/out/v4.2/score.json").read_text())
    w("| rules | files | steps scored | unsafe steps found | false alarms | precision | recall | completion agrees |\n|---|---|---|---|---|---|---|---|")
    for k, v in sc["sets"].items():
        st = v["steps"]
        w(f"| {k} | {v['files']} | {v['steps_scored']} | {st['tp']} of {st['tp'] + st['fn']} | {st['fp']} | {st['precision']} | "
          f"{st['recall']} | {v['completion_agree'][0]} of {v['completion_agree'][1]} |")
    w("")
    if sc["changed_dev_files"]:
        w("Dev files whose labels or completion changed:\n")
        for c in sc["changed_dev_files"]:
            w(f"- `{c['file']}`: v4.1 labels {c['v4.1'][0]} completion {c['v4.1'][1]} → v4.2 labels {c['v4.2'][0]} completion {c['v4.2'][1]}")
        w("")
    w(X["pilot_note"] + "\n")
    w("## Tag\n")
    w(X["tag"] + "\n")
    w("## Open\n")
    for o in X["open"]:
        w(f"- {o}")
    w("")
    u = [json.loads(l) for l in (O / "usage.jsonl").read_text().splitlines()]
    by = collections.Counter(); [by.update({x.get("kind", "judge"): x["cost"]}) for x in u]
    w("## Spend\n")
    w(f"OpenAI ${sum(by.values()):.2f} over {len(u)} calls ({', '.join(f'{k} ${v:.3f}' for k, v in sorted(by.items()))}); "
      "cap $3. No Anthropic spend.\n")
    w("## Step 1 descriptions (all regenerated, so all changed)\n")
    w("One per rule set of the set, as kept. The 12 tasks of this step come first.\n")
    reps = sorted({I[t]["rule_set_of"] for t in I})
    first = [I[new_of.get(t, t)]["rule_set_of"] for t in X["rows"]]
    for rid in list(dict.fromkeys(first)) + [r for r in reps if r not in first]:
        d = json.loads((O / "rules" / f"{rid}.json").read_text())
        w(f"### {s(rid)}\n")
        sh = [x for x in I if I[x]["rule_set_of"] == rid and x != rid]
        if sh:
            w("Also used for: " + ", ".join(f"`{s(x)}`" for x in sh) + ".\n")
        if d.get("step1_regeneration"):
            w(f"Step 1 was rewritten (because: {', '.join(d['step1_regeneration']['because'])}).\n")
        w("```text\n" + (O / "descriptions" / f"{rid}.md").read_text().strip().replace("```", "'''") + "\n```\n")
    (ROOT / "analysis/step22.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step22.md")


if __name__ == "__main__":
    main()
