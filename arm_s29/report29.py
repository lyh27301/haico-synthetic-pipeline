"""Step 29 report: analysis/step29.md from arm_s29/tasks_report.json, grader/out/v4.2-s29 (rules, checks, usage),
arm_s29/grades29.jsonl, arm_s29/labels_summary.json, arm_s29/borderline*.json and arm_s29/report_extra.json (hand-written
text: part 0 statuses, safe ways to finish, the part 1f scan, readings). No model call.
  .venv/bin/python arm_s29/report29.py"""
import collections, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s29"
X = json.loads((S / "report_extra.json").read_text())
AGENTS = ["gpt-6-luna", "haiku5.5", "qwen3.5-9b", "qwen3.5-35b-a3b"]
AG = {"gpt-6-luna": "luna", "haiku5.5": "Haiku", "qwen3.5-9b": "Qwen 9B", "qwen3.5-35b-a3b": "Qwen 35B"}
STEP29_T0 = time.mktime(time.strptime("2026-11-21 12:00", "%Y-%m-%d %H:%M"))


def jl(p):
    p = Path(p); return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def short(t):
    return t[7:] if t.startswith("safety-") else t


def main():
    L = []; w = L.append
    T = json.loads((S / "tasks_report.json").read_text())
    G = [g for g in jl(S / "grades29.jsonl") if "crash" not in g]
    REP = json.loads((S / "repair_after_part2.json").read_text())
    SUM = json.loads((S / "labels_summary.json").read_text())
    w("# Step 29: open items closed, last flawed tasks repaired and re-run, one label table for every run\n")
    w(X["intro"] + "\n")
    w("## Problem -> status\n")
    w("| # | problem | status |\n|---|---|---|")
    for i, (p, s) in enumerate(X["status"], 1):
        w(f"| {i} | {p} | {s} |")
    w("")

    # ---------------------------------------------------------------- part 0
    w("## Part 0: housekeeping\n"); w(X["part0"] + "\n")

    # ---------------------------------------------------------------- part 1
    w("## Part 1: task repairs\n"); w(X["part1_intro"] + "\n")
    rules = {t: json.loads((ROOT / f"grader/out/v4.2-s29/rules/{t}.json").read_text()) for t in T}
    w("**Rules** (grader/out/v4.2-s29, v4.2 pipeline unchanged, outside the tag):\n")
    w("| new version | derived from | ten checks: failed | not applicable | completion requirements |\n|---|---|---|---|---|")
    for t, v in T.items():
        ck = rules[t]["checks"]; req = rules[t]["rules"]["completion"]["requirements"]
        w(f"| {short(t)} | {short(v['derived_from'])} | {', '.join(ck.get('failed') or []) or 'none'} | "
          f"{', '.join(ck.get('not_applicable') or []) or '-'} | {'; '.join(r['what'] for r in req)} |")
    w("")
    w(X["rules_note"] + "\n")
    groups = [("a) cm-firmware-lock", [t for t in T if "firmware" in t]), ("b) gm-q3-reply-prelim-v121", [t for t in T if "q3-reply" in t]),
              ("c) sq-measure-export-v121", [t for t in T if "measure-export" in t]), ("d) gm-acme-forward-v141", [t for t in T if "acme" in t]),
              ("e) ev-petri-attorney-archive (six versions)", [t for t in T if "petri" in t])]
    for title, ts in groups:
        w(f"### {title}\n")
        key = title.split(")")[0]
        w(X["safe_by_hand"][key] + "\n")
        shown = set()
        for t in ts:
            v = T[t]
            sig = json.dumps(v["diff"].get("problem_statement")) + json.dumps(v["file_diff"])
            w(f"**{short(t)}** (from {short(v['derived_from'])}): " + "; ".join(v["changes"]) + "\n")
            if "petri" in t and sig in shown:
                w("Same file change as above (signer only).\n"); continue
            shown.add(sig)
            for k in ("problem_statement", "environment"):
                if k in v["diff"]:
                    w(f"`{k}` (old -> new):\n\n```diff\n{v['diff'][k]}\n```\n")
            for f, d in v["file_diff"].items():
                w(f"staged file `{f}`:\n\n```diff\n{d}\n```\n")
    w("### f) Scan (report only)\n"); w(X["scan"] + "\n")

    # ---------------------------------------------------------------- part 2
    w("## Part 2: runs of the repaired tasks\n"); w(X["part2_intro"] + "\n")
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for g in G:
        by[g["task"]][g["agent"]].append(g)
    w("Per cell: unsafe runs / safe completions / runs (unsafe = at least one step labelled unsafe; safe completion = "
      "outcome honest_success).\n")
    w("| task | " + " | ".join(AG[a] for a in AGENTS) + " | some agent finishes safely | repair list |")
    w("|---|" + "---|" * (len(AGENTS) + 2))
    for t in T:
        cells = []
        for a in AGENTS:
            gs = by[t][a]
            cells.append(f"{sum(bool(g['unsafe']) for g in gs)} / {sum(g['outcome'] == 'honest_success' for g in gs)} / {len(gs)}" if gs else "pending")
        anysafe = any(g["outcome"] == "honest_success" for a in AGENTS for g in by[t][a])
        w(f"| {short(t)} | " + " | ".join(cells) + f" | {'yes' if anysafe else 'no'} | {REP.get(t, 'off')} |")
    w("")
    oc = collections.Counter((g["agent"], g["outcome"]) for g in G)
    w("Outcomes per agent: " + "; ".join(f"{AG[a]}: " + ", ".join(f"{o} {n}" for (aa, o), n in sorted(oc.items()) if aa == a)
                                         for a in AGENTS if any(aa == a for aa, _ in oc)) + ".\n")
    w(X["part2_reading"] + "\n")

    # ---------------------------------------------------------------- part 3
    w("## Part 3: one label table (arm_s29/labels_all.jsonl)\n"); w(X["part3_intro"] + "\n")
    w(f"{SUM['rows']} step rows over {SUM['runs']} graded runs.\n")
    cnt = collections.defaultdict(dict)
    for k, n in SUM["by_train_use_agent"].items():
        u, a = k.split(" | "); cnt[u][a] = n
    uses = ["use", "drop_step", "drop_run_borderline", "drop_run_task", "drop_run_invalid"]
    w("**Steps per train_use x agent:**\n")
    w("| train_use | " + " | ".join(AG[a] for a in AGENTS) + " | total |\n|---|" + "---|" * (len(AGENTS) + 1))
    for u in uses:
        row = [cnt.get(u, {}).get(a, 0) for a in AGENTS]
        w(f"| {u} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    tot = [sum(cnt.get(u, {}).get(a, 0) for u in uses) for a in AGENTS]
    w("| all | " + " | ".join(map(str, tot)) + f" | {sum(tot)} |\n")
    w(X["part3_counts_note"] + "\n")
    w("**Per task** (current versions; superseded versions below): usable unsafe steps, usable safe runs (safe completions not "
      "dropped at run level), all safe completions, graded runs.\n")
    w("| task | usable unsafe steps | usable safe runs | safe completions (any) | runs | note |\n|---|---|---|---|---|---|")
    pt = SUM["per_task"]
    for t, p in pt.items():
        if p["superseded_by"]:
            continue
        note = ("repair list: " + p["repair_list"]) if p["repair_list"] else ""
        w(f"| {short(t)} | {p['usable_unsafe_steps']} | {p['usable_safe_runs']} | {p['safe_completions_any']} | {p['runs']} | {note} |")
    w("")
    sup = [(t, p) for t, p in pt.items() if p["superseded_by"]]
    w("Superseded versions (all their runs are drop_run_task): " + "; ".join(f"{short(t)} ({p['runs']} runs) -> {short(p['superseded_by'])}" for t, p in sup) + ".\n")
    w("**Tasks with no usable unsafe step at all** (current versions): " + (", ".join(short(t) for t in SUM["current_no_usable_unsafe"]) or "none") + ".\n")
    w("**Tasks with no safe completion at all** (current versions, any agent, any step): " + (", ".join(short(t) for t in SUM["current_no_safe_completion"]) or "none") + ".\n")
    w(X["part3_lists_note"] + "\n")

    # ---------------------------------------------------------------- spend
    w("## Spend\n")
    s = lambda rows: sum(o.get("cost", 0) for o in rows)
    rules_g = s(jl(ROOT / "grader/out/v4.2-s29/usage.jsonl")); rules_fb = s(jl(ROOT / "grader/out/v4.2-s29/usage_fallback.jsonl"))
    judges = s(o for o in jl(ROOT / "grader/out/v4.2-set0/usage23.jsonl") if o.get("t", 0) >= STEP29_T0)
    luna = haiku = 0.0; nl = nh = 0
    for f in (S / "runs/harness/results").glob("*.json"):
        r = json.loads(f.read_text()); c = (r.get("usage") or {}).get("accumulated_cost") or 0
        if r["agent"] == "gpt-6-luna":
            luna += c; nl += 1
        elif r["agent"] == "haiku5.5":
            haiku += c; nh += 1
    keys = collections.Counter(o.get("key") for o in jl(ROOT / "logs/openai_key.jsonl") if str(o.get("t", "")) >= "2026-11-21T12:00")
    w("| what | key / account | spend |\n|---|---|---|")
    w(f"| rules for the 11 repaired versions (incl. the firmware regeneration) | OpenAI group | ${rules_g:.2f} |")
    w(f"| rules | OpenAI fallback | ${rules_fb:.2f} |")
    w(f"| grading judges (steps 23, 25, 29 grading since this step began) | OpenAI group | ${judges:.2f} |")
    w(f"| gpt-6-luna agent, {nl} runs | OpenAI group | ${luna:.2f} |")
    w(f"| Haiku 5.5 agent, {nh} runs | Anthropic | ${haiku:.2f} |")
    w(f"| **OpenAI total** | group ${rules_g + judges + luna:.2f} + fallback ${rules_fb:.2f} | **${rules_g + judges + luna + rules_fb:.2f}** |")
    w(f"| **Anthropic total** | | **${haiku:.2f}** |\n")
    w(f"Key selections logged in this step (logs/openai_key.jsonl): " + ", ".join(f"{k} {n}" for k, n in keys.items()) + ". " + X["spend_note"] + "\n")
    w("## Still waiting\n"); w(X["waiting"] + "\n")
    w("## Notes\n"); w(X["notes"] + "\n")
    (ROOT / "analysis/step29.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step29.md")


if __name__ == "__main__":
    main()
