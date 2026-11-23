"""Step 34 report: analysis/step34.md from the step's files (no model call).
  .venv/bin/python arm_s34/report34.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s34"
AG = ["haiku5.5", "gpt-6-luna", "qwen3.5-9b", "qwen3.5-35b-a3b"]
AGN = {"haiku5.5": "Haiku", "gpt-6-luna": "luna", "qwen3.5-9b": "9B", "qwen3.5-35b-a3b": "35B"}
TREES = ["arm_s34/runs", "arm_s34/qwen9b", "arm_s34/qwen35", "arm_s34/twins/runs", "arm_s34/twins/qwen9b", "arm_s34/twins/qwen35"]

# read by hand from the runs (filled in after the runs; see section 2)
NOT_KEPT_NOTES = json.loads((S / "not_kept_notes.json").read_text()) if (S / "not_kept_notes.json").exists() else {}


def jl(p):
    p = ROOT / p if not str(p).startswith("/") else Path(p)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def js(p):
    return json.loads((ROOT / p).read_text())


def short(t):
    return t.removeprefix("safety-")


def designed(lab, fs):
    return lab == "unsafe" and any(f.get("label") == "unsafe" and f.get("tag") == "designed" for f in fs)


def main():
    out = []; W = out.append
    sel = js("arm_s34/selected.json"); sv = js("arm_s34/survey34.json")
    keep = js("arm_s34/keep34.json"); kept = set(keep["kept"])
    rows = {json.loads(f.read_text())["instance_id"]: json.loads(f.read_text()) for f in (S / "bank/tasks").glob("*.json")}
    twins = {json.loads(f.read_text())["instance_id"]: json.loads(f.read_text()) for f in (S / "twins/tasks").glob("*.json")}
    twin_of = {r["twin_of"]: t for t, r in twins.items()}
    G = jl("arm_s34/grades34.jsonl"); GT = jl("arm_s34/twins/grades34t.jsonl"); GA = {g["key"]: g for g in jl("arm_s34/twins/grades34t_as_trap.jsonl")}
    loc = {x["task"]: x for x in jl("arm_s34/prohibition_location34.jsonl")}
    safer = jl("arm_s34/safer/safer_runs.jsonl")
    reads = jl("arm_s34/trap_reads34.jsonl"); rrep = js("arm_s34/trap_reads34_report.json") if (S / "trap_reads34_report.json").exists() else {}
    labels = jl("arm_s34/labels34.jsonl")
    checks = js("arm_s34/twins/checks34.json")
    from make_tasks34 import DROP
    from make_twins34 import SKIP as TSKIP
    import make_tasks34 as MT

    # per task x agent: usable unsafe steps, safe completions / runs, hard negatives
    U = collections.Counter(); SC = collections.Counter(); N = collections.Counter(); TU = collections.Counter()
    for g in G:
        if "crash" in g:
            continue
        N[(g["task"], g["agent"])] += 1
        SC[(g["task"], g["agent"])] += g["outcome"] == "honest_success"
        n = sum(designed(l, fs) for l, fs in zip(g["labels"], g["findings"]))
        TU[(g["task"], g["agent"])] += n
        if g["task"] in kept:
            U[(g["task"], g["agent"])] += n
    HN = collections.Counter(); TN = collections.Counter(); TS = collections.Counter(); TUNS = collections.Counter()
    for g in GT:
        if "crash" in g:
            continue
        trap = twins[g["task"]]["twin_of"]; TN[(trap, g["agent"])] += 1
        TS[(trap, g["agent"])] += g["outcome"] == "honest_success"
        TUNS[(trap, g["agent"])] += any(l == "unsafe" for l in g["labels"])
        a = GA.get(g["key"])
        if a and "crash" not in a:
            HN[(trap, g["agent"])] += sum(1 for l, la, fa in zip(g["labels"], a["labels"], a["findings"]) if l == "safe" and designed(la, fa))

    fams = {o["family"]: o for o in sel["selected"]}
    W("# Step 34: scale-up wave 1, the unused task families\n")
    nk = len(kept)
    W(f"Selected {len(sel['selected'])} tasks from {len(fams)} unused families; admitted {len(rows)}; kept {nk}. Usable unsafe "
      f"steps on kept tasks: {sum(U.values())}; safe completions (all tasks): {sum(SC.values())} of {sum(N.values())} runs; hard "
      f"negatives (twin runs): {sum(HN.values())}. Branch `step34`, rules in grader/out/v4.2-s34 (frozen v4.2 pipeline, ten "
      "checks), everything else under arm_s34/.\n")
    W("## 1. Families: selected -> admitted -> kept\n")
    W("Per agent: **U** usable unsafe steps (unsafe steps with a designed finding, on kept tasks), **S** safe completions / "
      "runs of the task, **H** hard negatives in the task's twin runs (a safe step of the twin that the trap version's rules flag "
      "as its designed unsafe step: same call on the same object). `-` = no twin.\n")
    W("| family | task | admitted | kept | " + " | ".join(f"{AGN[a]} U / S / H" for a in AG) + " |")
    W("|---|---|---|---|" + "---|" * len(AG))
    tot = collections.Counter()
    for f, o in sorted(fams.items()):
        t = o["task"] + "-v34"
        adm = t in rows
        k = "yes" if t in kept else (keep["not_kept"].get(t, "-") if adm else "-")
        cells = []
        for a in AG:
            if not adm:
                cells.append("-"); continue
            h = HN[(t, a)] if t in twin_of else "-"
            cells.append(f"{U[(t, a)]} / {SC[(t, a)]}/{N[(t, a)]} / {h}")
            tot[("U", a)] += U[(t, a)]; tot[("S", a)] += SC[(t, a)]; tot[("N", a)] += N[(t, a)]; tot[("H", a)] += HN[(t, a)]
        W(f"| {short(f)} | {short(o['task'])} | {'yes' if adm else 'no'} | {k} | " + " | ".join(cells) + " |")
    W(f"| **total** | {len(sel['selected'])} | {len(rows)} | {nk} | " + " | ".join(
        f"**{tot[('U', a)]} / {tot[('S', a)]}/{tot[('N', a)]} / {tot[('H', a)]}**" for a in AG) + " |\n")
    missing = {a: 57 - sum(1 for t in rows for _ in range(3)) for a in AG}
    runs_per_agent = {a: sum(N[(t, a)] for t in rows) for a in AG}
    W("Runs graded per agent: " + ", ".join(f"{AGN[a]} {runs_per_agent[a]}" for a in AG) + f" (of {3 * len(rows)} each).\n")

    W("## 2. What was dropped, and why\n")
    W("**Selection (part 1).** The bank has " + f"{len(sv['used']) + len(sv['families'])} base families by the step-13 family "
      f"rule (version, salience and twin suffixes and a trailing numeric id removed); {len(sv['used'])} have been run in steps "
      f"21-33 and {len(sv['families'])} have not (gmail 13, sqldb 7, medical 1). The prompt counts 57 / 28 / 29 (gmail 21): it "
      "counts salience variants as their own families and a few families run in steps 21-25 but left out of the training set as "
      "unused. Salience variants of a family already in use are the same mechanic and were not taken; families already run in "
      "steps 21-25 are not 'never through steps 18-33'.\n")
    W("- Not picked: " + "; ".join(f"`{short(t)}`: {w}" for t, w in sel["not_picked_families"].items()) + ".")
    W("- **No second versions.** In no family do two qualified versions write the prohibition in different places. Three "
      "picks that looked like it in the step-13 audit were checked against the environments and removed: " +
      "; ".join(f"`{short(t)}` ({w})" for t, w in sel.get("not_second_versions", {}).items()) + ".")
    W(f"- So {len(sel['selected'])} tasks, not 35-45: the target is not reachable under the rule 'two only where the place "
      "differs'. The reasons per pick are in arm_s34/selected.json.\n")
    W("**Admission (part 2).** Dropped: " + "; ".join(f"`{short(t)}`: {w}" for t, w in DROP.items()) + ".\n")
    W("Fixed (every change is in the row's task_changes, step 34):\n")
    for t, r in sorted(rows.items()):
        fx = [c["change"] for c in r["task_changes"] if isinstance(c, dict) and c.get("step") == "34" and c["change"].startswith(("admission", "T2", "rules (try 2)", "statement", "recipient", "placeholder", "new contact", "the two marketing"))]
        if fx:
            W(f"- `{short(t)}`: " + " / ".join(fx))
    W("\nRules: 17 tasks passed the ten checks on the first try; `sq-cleaned-meas-retain-v141-v34` and "
      "`sq-cohort-contact-notes-v34` failed collections_valid (the deliverable was a new table, and a rule may only name a "
      "collection that exists before the run; cohort also violator_flagged). Fix: the empty table exists and the request asks "
      "to fill it; both passed on the second try. No task was dropped for its rules. The Haiku runs those two tasks had before "
      "the fix were set aside (arm_s34/runs/superseded_haiku) and run again.\n")
    W("Prohibition location (step-25 definitions, value over the traps the violator fires): " + ", ".join(
        f"{k} {v}" for k, v in collections.Counter(x["prohibition_location"] for x in loc.values()).most_common()) +
      " (arm_s34/prohibition_location34.jsonl). User-instructed: " + ", ".join(f"`{short(t)}`" for t, r in rows.items() if r.get("user_instructed")) + ".\n")
    W("**Not kept (part 3).** A task is kept when some run of some agent is a safe completion and some run has a trap-based "
      "unsafe step.\n")
    W("| task | reason | runs with a trap-based unsafe step | safe completions | read by hand |\n|---|---|---|---|---|")
    for t, why in sorted(keep["not_kept"].items()):
        p = keep["per_task"][t]
        W(f"| {short(t)} | {why} | {p['trap_unsafe_runs']} | {p['safe_completions']} | {NOT_KEPT_NOTES.get(t, '')} |")
    W("")

    W("## 3. Part 4 on the kept tasks\n")
    W("### Safer runs (step 30, variant D, gate from the real state)\n")
    sr = [r for r in safer if r["task"] in kept]
    br = js("arm_s34/safer/branches30.json")
    W(f"Branches: {len([b for b in br['branches'] if b['task'] in kept])} on kept tasks (runs whose first unsafe step is a "
      f"designed trap); skipped: {dict(collections.Counter(s['why_not'] for s in br['skipped']))}.\n")
    W("| agent | branches | pair_ok | unsafe_after_block | gave_up | partial | invalid |\n|---|---|---|---|---|---|---|")
    for a in AG:
        x = [r for r in sr if r["agent"] == a]
        c = collections.Counter(r["failure"] or "pair_ok" for r in x)
        W(f"| {AGN[a]} | {len(x)} | {c['pair_ok']} | {c['unsafe_after_block']} | {c['gave_up']} | {c['partial']} | {c['invalid']} |")
    pend = [b for b in br["branches"] if b["task"] in kept and b["branch_id"] not in {r["branch_id"] for r in safer}]
    W(f"\nNot run yet: {len(pend)}" + (" (" + ", ".join(f"{b['branch_id']} {AGN[b['agent']]}" for b in pend) + ")" if pend else "") + ".")
    tx = js("arm_s34/safer/texts30.json") if (S / "safer/texts30.json").exists() else {}
    vc = [u for u, v in tx.items() if v.get("variant") == "C"]
    W(f"Text units: {len(tx)}; fell back to variant C: {vc or 'none'}. Withdrawn (branched before the task was found not kept): "
      f"{len([b for b in br['branches'] if b['task'] not in kept])}.\n")
    W("### Safe twins (step 26)\n")
    W(f"{len(twins)} twins of the {len(rows)} tasks ({', '.join(f'{k} {v}' for k, v in collections.Counter(r['twin_type'] for r in twins.values()).items())}); "
      f"{len(TSKIP)} tasks have none: " + "; ".join(f"`{short(t)}`: {w}" for t, w in TSKIP.items()) + ".\n")
    W(f"Checks: all {len(checks)} twin rule sets pass the ten checks (violator_flagged n/a); the trap version's violator path is "
      f"safe and completes on {sum(1 for c in checks.values() if c['violator_path_not_flagged'] and c['violator_path_completes'])}/"
      f"{len(checks)}; the trap's safe path completes on {sum(1 for c in checks.values() if c['trap_safe_path_completes'])}/{len(checks)} "
      "(it leaves out what is now fine). Diffs: arm_s34/twins/twins_report.json.\n")
    W("| twin of | kept | type | " + " | ".join(f"{AGN[a]} runs with an unsafe step / safe completions / H" for a in AG) + " |")
    W("|---|---|---|" + "---|" * len(AG))
    for trap, t in sorted(twin_of.items()):
        W(f"| {short(trap)} | {'yes' if trap in kept else 'no'} | {twins[t]['twin_type']} | " + " | ".join(
            f"{TUNS[(trap, a)]} / {TS[(trap, a)]}/{TN[(trap, a)]} / {HN[(trap, a)]}" for a in AG) + " |")
    W("")
    W("### Read table and label table\n")
    W(f"- READ rows (arm_s33/trap_reads.jsonl format): {len(reads)} in arm_s34/trap_reads34.jsonl, over "
      f"{rrep.get('traps_considered', '?')} traps of kept tasks; no row: " + ("; ".join(f"`{short(r['task'])}` {r['trap']} ({r['why']})" for r in rrep.get("no_row", [])) or "none") + ".")
    c = collections.Counter((x["grades"], x["train_use"], x["label"]) for x in labels)
    W(f"- Label rows (step-29 columns): {len(labels)} in arm_s34/labels34.jsonl: " + ", ".join(f"{g} {u} {l} {n}" for (g, u, l), n in sorted(c.items())) +
      "; safer-run rows in arm_s34/safer/labels_safer.jsonl.\n")

    W("## 4. Spend\n")
    rules = sum(x.get("cost", 0) for x in jl("grader/out/v4.2-s34/usage.jsonl"))
    t0 = min(x["t"] for x in jl("grader/out/v4.2-s34/usage.jsonl")) - 60
    grade = sum(x.get("cost", 0) for x in jl("grader/out/v4.2-set0/usage23.jsonl") if x.get("t", 0) >= t0)
    sf = {k: sum(x.get("cost", 0) for x in jl(f"arm_s34/safer/{k}.jsonl")) for k in ("usage_texts", "usage_judges")}
    bu = jl("arm_s34/safer/usage_branches.jsonl")
    bo = sum(x["cost"] for x in bu if x["provider"] == "openai"); ba = sum(x["cost"] for x in bu if x["provider"] == "anthropic")
    cost = collections.Counter()
    for tr in TREES:
        d = ROOT / tr / "harness/results"
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            r = json.loads(f.read_text()); u = r.get("usage")
            if isinstance(u, str):
                import ast
                try:
                    u = ast.literal_eval(u)
                except Exception:  # noqa: BLE001
                    u = {}
            cost[r["agent"]] += float((u or {}).get("accumulated_cost") or 0)
    keys = [x for x in jl("logs/openai_key.jsonl") if str(x.get("t", "")) >= "2026-11-23T11" and any(
        s in str(x.get("job", "")) for s in ("34", "texts30", "branch30", "grade30"))]
    fb = [x for x in keys if x.get("key") != "group"]
    oa = rules + grade + sf["usage_texts"] + sf["usage_judges"] + bo + cost["gpt-6-luna"]
    W("| item | provider / key | spend |\n|---|---|---|")
    W(f"| rules: 19 tasks (2 twice) and 15 twins, judge notes of the checks | OpenAI group | ${rules:.2f} |")
    W(f"| grading judges (runs, twins, as-trap) | OpenAI group | ${grade:.2f} |")
    W(f"| safer-run texts and gate judges | OpenAI group | ${sf['usage_texts'] + sf['usage_judges']:.2f} |")
    W(f"| gpt-6-luna runs (tasks and twins) and branches | OpenAI group | ${cost['gpt-6-luna'] + bo:.2f} |")
    W(f"| **OpenAI total** | | **${oa:.2f}** |")
    W(f"| fallback key | | {'not used' if not fb else str(len(fb)) + ' selections'} |")
    W(f"| claude-haiku-5-5 runs (tasks, redo, twins) and branches | Anthropic | ${cost['haiku5.5'] + ba:.2f} |")
    W("| Qwen runs | cluster (my two serving jobs) | - |\n")
    W(f"Key selections logged for this step: {len(keys)}, " + ("all on the group key" if not fb else f"{len(fb)} on the fallback") +
      ". The NPC (gpt-4o-mini) has no cost log, as before. No export in this step.\n")
    (ROOT / "analysis/step34.md").write_text("\n".join(out) + "\n")
    print(len(out), "lines -> analysis/step34.md")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(S))
    main()
