"""Step 14 pilot, item 7: analysis/step14_pilot.md (tables + every rationale in full) and arm_s14/examples.md
(5 complete examples). Reads arm_s14/selection.json, risk_notes.json, branch_outcomes.jsonl, rationales_pilot.jsonl,
usage.jsonl.
  .venv/bin/python arm_s14/report.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S14 = ROOT / "arm_s14"
OUTC = ["no_new_harm_completed", "no_new_harm_gave_up", "new_harm", "incomplete"]
SHORT = {"no_new_harm_completed": "completed", "no_new_harm_gave_up": "gave up", "new_harm": "new harm", "incomplete": "incomplete"}


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def table(rows, key):
    c = collections.defaultdict(collections.Counter)
    for r in rows:
        c[(key(r), r["condition"])][r["outcome"]] += 1
    out = ["| group | warning | n | " + " | ".join(SHORT[o] for o in OUTC) + " |", "|---|---|---|" + "---|" * len(OUTC)]
    for (g, cond), v in sorted(c.items()):
        out.append(f"| {g} | {cond} | {sum(v.values())} | " + " | ".join(str(v[o]) for o in OUTC) + " |")
    return "\n".join(out)


def main():
    sel = json.loads((S14 / "selection.json").read_text())
    car = {(c["task"]): c["carrier"] for c in sel["trajectories"]}
    oc = jl(S14 / "branch_outcomes.jsonl"); rows = jl(S14 / "rationales_pilot.jsonl")
    for o in oc:
        o["carrier"] = car.get(o["task"])
    usage = jl(S14 / "usage.jsonl") if (S14 / "usage.jsonl").exists() else []
    cost = collections.Counter()
    for u in usage:
        cost[(u["provider"], u["kind"])] += u["cost"]
    n = len(rows) or 1
    sp = [o for o in oc if o["condition"] == "specific"]
    gave = sum(o["outcome"] == "no_new_harm_gave_up" for o in sp)
    down = [r for r in rows if r["harm_downstream"]]
    down_ok = all(r["multi_unsafe"] and not r["last_unsafe"] for r in down)
    lp = sum(r.get("leakage_pass", False) for r in rows)
    fields = ("why_not_allowed", "harm_immediate", "harm_downstream", "alternative", "rationale")
    md = ["# Step 14 pilot: safe branches and rationales", "",
          f"{sel['tasks']} tasks, {len(rows)} unsafe steps ({sel['multi_step_trajectories']} trajectories with more than one "
          f"unsafe step, {sum(not r['harm_realized'] for r in rows)} attempts that did not take effect), {len(oc)} branches "
          "(specific and generic warning per step). Method: arm_s14/branch.py (prefix replay through a proxy, warning "
          "injected on the wire only), arm_s14/notes.py (Sonnet 5.5 writer, fixed fields, leakage check), "
          "arm_s14/outcomes.py (branch outcome from step labels after the branch point and grader-v4 utility).", "",
          "## Branch outcomes", "", "By agent:", "", table(oc, lambda r: r["agent"]), "",
          "By harm carrier:", "", table(oc, lambda r: r["carrier"]), "",
          f"- **Specific warning -> gave up:** {gave} of {len(sp)} branches.",
          f"- **Prefix replayed identically:** {sum(o['prefix_identical'] for o in oc)} of {len(oc)} branches.", "",
          "## Checks", "",
          f"- **Leakage check:** {lp} of {len(rows)} rows pass on every field; failures per field: "
          + ", ".join(f"{f} {sum(bool((r.get('leakage') or {}).get(f)) for r in rows)}" for f in fields) + ".",
          f"- **harm_downstream filled:** {len(down)} rows; every one is an earlier unsafe step of a multi-unsafe-step run: "
          f"{'yes' if down_ok else 'NO'}.",
          f"- **harm_realized = false:** {sum(not r['harm_realized'] for r in rows)} rows.",
          f"- **matched (the specific-warning branch succeeded and is the alternative):** {sum(r['matched'] for r in rows)} of {len(rows)}.",
          f"- **Grounding quote already seen by the agent before the step:** {sum(r.get('grounding_seen_in_prefix', False) for r in rows)} of {len(rows)}. "
          "In the other rows why_not_allowed cites a prohibition the agent had not read yet: true to the task, but not "
          "something a reader of the prefix alone could write. The leakage check allows the quote's tokens, because the "
          "field must cite it; this conflict between 'cite the grounding' and 'prediction only' is open.",
          "- **Leakage failures** (facts the agent had not seen): " + "; ".join(
              f"{r['task'].replace('safety-', '')} step {r['step']}: " + ", ".join(sorted({t for v in (r.get('leakage') or {}).values() for t in v}))
              for r in rows if not r.get("leakage_pass")) + ". They come from the environment diff (record fields the agent "
          "never displayed), from the safe reference used as the alternative, and from one quote not yet read.", "",
          "## Method notes", "",
          "- Written in the fixed field structure from the start: no risk note or branch existed in the earlier free-text "
          "form, so nothing was reused or redone. Three notes came out in the past tense and were regenerated before any "
          "branch used them.",
          "- Replay fixes found on the way (the affected branches were re-run): the agent SDK makes an auxiliary call without "
          "tools before the first turn (forwarded, not counted); a branch step that shares one LLM response with earlier "
          "parallel calls (that response is replayed cut to those calls); stored step numbers that count calls the "
          "framework rejected (the branch step is found by its call, not its position); empty tool output as an empty text "
          "block (sent as \"(no output)\" to the Anthropic API). After the fixes every prefix replays identically.",
          "- Finance tasks have an NPC: its replies in the prefix are regenerated; the agent's prefix actions are not.", "",
          "## Cost", "",
          f"- Branches: Anthropic ${cost[('anthropic', 'branch')]:.2f}, OpenAI ${cost[('openai', 'branch')]:.2f} (Qwen on Babel: no API cost).",
          f"- Writing (Sonnet 5.5): risk notes ${cost[('anthropic', 'risk_note')]:.2f}, alternatives ${cost[('anthropic', 'alternative')]:.2f}.",
          f"- **Per unsafe step:** ${sum(cost.values()) / n:.3f}.", "", "## All rationales", ""]
    for r in rows:
        md += [f"### {r['task']} · {r['agent']} · run {r['run']} · step {r['step']}", "",
               f"- rule: `{json.dumps(r['rule'].get('v3_probe_rules'), default=str)[:200]}`; harm_realized: {r['harm_realized']}; matched: {r['matched']}; "
               f"specific: {(r['branch_specific'] or {}).get('outcome')}; generic: {(r['branch_generic'] or {}).get('outcome')}; leakage pass: {r.get('leakage_pass')}",
               f"- **why_not_allowed:** {r['why_not_allowed']}", f"- **harm_immediate:** {r['harm_immediate']}",
               f"- **harm_downstream:** {r['harm_downstream'] or '—'}", f"- **alternative:** {r['alternative']}", ""]
    (ROOT / "analysis/step14_pilot.md").write_text("\n".join(md) + "\n")
    # five examples: one per toolkit where possible, matched first
    ex, seen = [], set()
    for r in sorted(rows, key=lambda r: (not r["matched"], not r.get("leakage_pass"), r["task"])):
        tk = r["task"].split("-")[1]
        if tk in seen:
            continue
        seen.add(tk); ex.append(r)
        if len(ex) == 5:
            break
    em = ["# Step 14 pilot: five worked examples", "",
          "Each example: what happened before the step, the unsafe step, the risk note (the specific warning), what the "
          "agent did after the warning, and the full rationale.", ""]
    for r in ex:
        sp = r["branch_specific"] or {}
        em += [f"## {r['task']} ({r['agent']}, run {r['run']}, step {r['step']})", "",
               f"**Prefix.** {r.get('prefix_summary') or ''}", "",
               f"**Unsafe step.** `{json.dumps(r.get('unsafe_action'), ensure_ascii=False)[:600]}`", "",
               f"**Risk note (specific warning).** {r['warning_specific']['text']}", "",
               f"**Branch step after the warning.** `{json.dumps(sp.get('branch_action'), ensure_ascii=False)[:600]}` — outcome: "
               f"{SHORT.get(sp.get('outcome'), sp.get('outcome'))}", "",
               f"**Full rationale.** {r['rationale']}", ""]
    (S14 / "examples.md").write_text("\n".join(em) + "\n")
    print("written")


if __name__ == "__main__":
    main()
