"""Step 23: write analysis/step23.md from the grades (grader/out/v4.2-set0/grades21.jsonl, grades23.jsonl), the task
report (arm_s23/tasks_report.json), the step-23 rules (grader/out/v4.2-s23), the run results (arm_s23 trees, the 9B r2
re-runs), the blind-batch manifest (arm_s23/pilot_v4_manifest.jsonl), the key log (logs/openai_key.jsonl), the usage
files and arm_s23/report_extra.json (hand-written text). No model calls.   .venv/bin/python arm_s23/report23.py"""
import collections, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s23"; SET = ROOT / "grader/out/v4.2-set0"
X = json.loads((S / "report_extra.json").read_text())
AG = ["gpt-6-luna", "haiku5.5", "qwen3.5-9b", "qwen3.5-35b-a3b"]
s = lambda t: t.removeprefix("safety-")
jl = lambda p: [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def cls(x):
    u = "unsafe" in x["labels"] or x["unsafe"]
    return ("unsafe_succeeded" if x["completion"] else "unsafe_failed") if u else ("safe_completion" if x["completion"] else "failed_safely")


def agent_table(w, G, title):
    w(f"{title}\n")
    w("| agent | runs | runs with an unsafe step | safe completion | unsafe and succeeded | failed safely | unsafe and failed | "
      "third-label steps (runs) | steps | unsafe steps |\n|---|---|---|---|---|---|---|---|---|---|")
    for a in AG + ["all"]:
        g = [x for x in G if a in ("all", x["agent"])]
        if not g:
            w(f"| {a} | 0 | | | | | | | | |"); continue
        c = collections.Counter(map(cls, g))
        w(f"| {a} | {len(g)} | {sum('unsafe' in x['labels'] for x in g)} ({sum('unsafe' in x['labels'] for x in g) / len(g):.0%}) | "
          f"{c['safe_completion']} | {c['unsafe_succeeded']} | {c['failed_safely']} | {c['unsafe_failed']} | "
          f"{sum(x['labels'].count('intent') for x in g)} ({sum(x['intent'] for x in g)}) | {sum(x['n_steps'] for x in g)} | "
          f"{sum(x['labels'].count('unsafe') for x in g)} |")
    w("")


def main():
    G21 = [x for x in jl(SET / "grades21.jsonl")]
    G23 = jl(SET / "grades23.jsonl")
    crash = [x for x in G21 + G23 if "crash" in x]
    G21 = [x for x in G21 if "crash" not in x]; G23 = [x for x in G23 if "crash" not in x]
    reruns = [x for x in G23 if x["tree"].startswith("arm_s21")]
    new = [x for x in G23 if not x["tree"].startswith("arm_s21")]
    ALL = G21 + G23
    L = []; w = L.append
    w("# Step 23: step-21 runs graded with the frozen v4.2 rules, a task fix, the missing runs, a blind batch\n")
    w("Date: 2026-11-19. " + X["intro"] + "\n")
    # part 0
    w("## 0. Backup OpenAI key\n"); w(X["part0"] + "\n")
    log = jl(ROOT / "logs/openai_key.jsonl")
    w("Jobs of this step and the key each used (`logs/openai_key.jsonl`; only the choice is logged, never a key):\n")
    w("| time | job | key |\n|---|---|---|")
    for o in log:
        w(f"| {o['t']} | `{o['job']}` | {o['key']} |")
    w("")
    # part 1
    w("## 1. Freeze\n"); w(X["part1"] + "\n")
    # part 2
    w("## 2. The step-21 runs graded\n"); w(X["part2_engine"] + "\n")
    agent_table(w, G21, f"**Per agent** ({len(G21)} runs: the 516 of step 21 minus the 2 invalid 9B payroll r2 runs). "
                "Classes: unsafe = at least one step the rules call unsafe (or harm in the final state; that never happened "
                "without an unsafe step); done = the rules' completion check. Third-label steps are counted apart; their "
                "runs are in the class their unsafe / done values give.")
    # per task x agent (step-21 runs + the re-runs + the new runs)
    w("**Per task and agent:** runs (of 3) with at least one unsafe step. Rows marked † are step-23 runs (part 4); the "
      "two 9B payroll cells include the r2 re-run (part 4). `-` = not run.\n")
    w("| task | toolkit | " + " | ".join(AG) + " | all |\n|---|---|" + "---|" * (len(AG) + 1))
    tasks = sorted({x["task"] for x in ALL}, key=lambda t: (t in {x["task"] for x in new}, t))
    none_u, all_u = [], []
    for t in tasks:
        g = [x for x in ALL if x["task"] == t]
        cells = []
        for a in AG:
            ga = [x for x in g if x["agent"] == a]
            cells.append(f"{sum('unsafe' in x['labels'] for x in ga)}/{len(ga)}" if ga else "-")
        n_u = sum('unsafe' in x['labels'] for x in g)
        w(f"| {s(t)}{' †' if t in {x['task'] for x in new} else ''} | {g[0]['toolkit']} | " + " | ".join(cells) + f" | {n_u}/{len(g)} |")
        if t not in {x["task"] for x in new}:
            (none_u if n_u == 0 else all_u if n_u == len(g) else []).append(t)
    w("")
    w(f"**Step-21 tasks where no run of any agent has an unsafe step ({len(none_u)}):** " + (", ".join(f"`{s(t)}`" for t in none_u) or "none") + ".\n")
    w(f"**Step-21 tasks where every run has an unsafe step ({len(all_u)}):** " + (", ".join(f"`{s(t)}`" for t in all_u) or "none") + ".\n")
    # controls
    ctl = [x for x in ALL if x["counter_example"]]
    fl = [x for x in ctl if any(l != "safe" for l in x["labels"])]
    w(f"**Controls** (ev-petri b versions, {len({x['task'] for x in ctl})} tasks, {len(ctl)} runs): "
      f"{len(fl)} runs with a flagged step" + (":" if fl else ".") + "\n")
    for x in fl:
        for i, (l, f) in enumerate(zip(x["labels"], x["findings"])):
            if l != "safe":
                w(f"- {s(x['task'])} {x['agent']} r{x['run']}, step {i} (`{x['tools'][i]}`): {l}; " +
                  "; ".join(f"{q.get('rule')} {q.get('coll') or q.get('item') or q.get('harm') or ''}" for q in f if q.get("label") != "safe"))
    if fl:
        w("")
    # toolkit and user_instructed
    w("**Share of runs with an unsafe step, by toolkit and for user_instructed tasks** (step-21 runs):\n")
    w("| group | " + " | ".join(AG) + " | all |\n|---|" + "---|" * (len(AG) + 1))
    groups = [(f"toolkit {k}", lambda x, k=k: x["toolkit"] == k) for k in sorted({x["toolkit"] for x in G21})] + \
        [("user_instructed", lambda x: x["user_instructed"]), ("not user_instructed", lambda x: not x["user_instructed"])]
    for name, f in groups:
        cells = []
        for a in AG + ["all"]:
            g = [x for x in G21 if f(x) and a in ("all", x["agent"])]
            cells.append(f"{sum('unsafe' in x['labels'] for x in g) / len(g):.0%} ({sum('unsafe' in x['labels'] for x in g)}/{len(g)})" if g else "-")
        w(f"| {name} | " + " | ".join(cells) + " |")
    w("")
    pend = sum(len(x.get("judge_pending_steps") or []) for x in ALL)
    w(f"**Judge pending:** {pend} steps (the judges answered every call; OpenAI was reachable through the fallback key). "
      f"Crashed gradings: {len(crash)}.\n")
    w(X.get("part2_notes", "") + "\n")
    # part 3
    w("## 3. Task fix: cm-firmware-lock-60071 and -v122\n"); w(X["part3"] + "\n")
    TR = json.loads((S / "tasks_report.json").read_text())
    for t, r in TR.items():
        w(f"### `{s(t)}` (from `{s(r['derived_from'])}`)\n")
        for k, d in r["diff"].items():
            w(f"`{k}`:\n\n```diff\n{d}\n```\n")
        v = r["validate"]
        w(f"Replay: safe reference {v['safe_reference']['steps']} steps, {len(v['safe_reference']['errors'])} errors; violator "
          f"reference {v['violator_reference']['steps']} steps, {len(v['violator_reference']['errors'])} errors (same state "
          f"changes as the old version). Other fields changed: {', '.join(r['other_fields_changed']) or 'none'}.\n")
    I = json.loads((ROOT / "grader/out/v4.2-s23/set.json").read_text())["tasks"]
    w("Rules (v4.2 pipeline unchanged, `grader/gen_rules_s23.py` → `grader/out/v4.2-s23/`, outside the tag):\n")
    w("| task | checks | step 1 regen | safety regen | completion regen |\n|---|---|---|---|---|")
    for t in I:
        d = json.loads((ROOT / I[t]["rule_file"]).read_text()); c = d["checks"]; rg = d.get("regenerations") or {}
        w(f"| {s(t)} | {'passes all' if not c.get('failed') else 'fails ' + ', '.join(c['failed'])} | {rg.get('step1', 0)} | "
          f"{rg.get('safety', 0)} | {rg.get('completion', 0)} |")
    w("")
    # part 4
    w("## 4. Missing runs\n"); w(X["part4"] + "\n")
    w("| agent | tree | runs asked | final | retried | failed |\n|---|---|---|---|---|---|")
    for a, tree in X["part4_trees"]:
        rs = [json.loads(f.read_text()) for f in (ROOT / tree / "harness/results").glob(f"*__{a}__r*.json")] \
            if (ROOT / tree / "harness/results").exists() else []
        if tree.startswith("arm_s21"):
            ids = (S / "rerun9b_ids.txt").read_text().split()
            rs = [r for r in rs if r["task"] in ids and r["run"] == 2]
            asked = 2
        else:
            asked = 15
        w(f"| {a} | `{tree}` | {asked} | {sum(1 for r in rs if r.get('final'))} | "
          f"{sum(1 for r in rs if len(r.get('attempts') or []) > 1)} | {sum(1 for r in rs if r.get('failed'))} |")
    w("")
    agent_table(w, new, f"**Graded step-23 runs** ({len(new)} runs; rules: v4.2-set0 for the step-22 versions, v4.2-s23 for "
                "the two new versions; `grader/out/v4.2-set0/grades23.jsonl`):")
    if reruns:
        w("**The two 9B payroll r2 re-runs:** " + "; ".join(
            f"{s(x['task'])} r{x['run']}: {cls(x).replace('_', ' ')}, labels {x['labels']}" for x in reruns) + ".\n")
    agent_table(w, G21 + G23, f"**Per agent, step-21 and step-23 runs together** ({len(G21 + G23)} runs):")
    # part 5
    w("## 5. Blind annotation batch (pilot v4)\n"); w(X["part5"] + "\n")
    M = jl(S / "pilot_v4_manifest.jsonl")
    c = collections.Counter
    w("| | count |\n|---|---|")
    for k, v in [("files", len(M)), ("with an unsafe step (rules) / none", f"{sum(m['picked_as'] == 'unsafe' for m in M)} / {sum(m['picked_as'] == 'none' for m in M)}"),
                 ("outside the trial-task families / inside", f"{sum(m['group'] == 'other' for m in M)} / {sum(m['group'] == 'trial_family' for m in M)}"),
                 ("different tasks", len({m['task'] for m in M})), ("controls", sum(m['counter_example'] for m in M)),
                 ("third-label runs", sum(m['intent'] for m in M))]:
        w(f"| {k} | {v} |")
    for k in ("agent", "toolkit"):
        w(f"| per {k} | " + ", ".join(f"{a} {n}" for a, n in sorted(c(m[k] for m in M).items())) + " |")
    w("| unsafe / none by group | " + ", ".join(f"{g} {sum(m['picked_as'] == 'unsafe' and m['group'] == g for m in M)} / "
                                            f"{sum(m['picked_as'] == 'none' and m['group'] == g for m in M)}" for g in ("other", "trial_family")) + " |")
    w("")
    # waiting, spend
    w("## Waiting for OpenAI\n"); w(X["waiting"] + "\n")
    w("## Spend\n")
    fb = lambda p: sum(o["cost"] for o in jl(p))
    grade_fb, grade_g = fb(SET / "usage23_fallback.jsonl"), fb(SET / "usage23.jsonl")
    rules_fb, rules_g = fb(ROOT / "grader/out/v4.2-s23/usage_fallback.jsonl"), fb(ROOT / "grader/out/v4.2-s23/usage.jsonl")
    luna = 0.0; haiku = 0.0
    for tree in ("arm_s23/runs",):
        for f in (ROOT / tree / "harness/results").glob("*.json"):
            r = json.loads(f.read_text())
            cost = (r.get("usage") or {}).get("accumulated_cost") or 0
            if r["agent"] == "gpt-6-luna":
                luna += cost
            elif r["agent"] == "haiku5.5":
                haiku += cost
    w("| what | key / account | spend |\n|---|---|---|")
    w(f"| grading judges (note judge, third-label judge) | OpenAI fallback | ${grade_fb:.2f} |")
    w(f"| grading judges | OpenAI group | ${grade_g:.2f} |")
    w(f"| rules for the 2 new versions | OpenAI fallback | ${rules_fb:.2f} |")
    w(f"| rules | OpenAI group | ${rules_g:.2f} |")
    w(f"| gpt-6-luna agent, 15 runs (final attempts) | OpenAI fallback | ${luna:.2f} |")
    w(f"| Haiku 5.5 agent, 15 runs (final attempts) | Anthropic | ${haiku:.2f} |")
    w(f"| **OpenAI total** | group ${grade_g + rules_g:.2f} + fallback ${grade_fb + rules_fb + luna:.2f} | "
      f"**${grade_g + rules_g + grade_fb + rules_fb + luna:.2f}** (cap $2) |")
    w(f"| **Anthropic total** | | **${haiku:.2f}** (cap $2) |")
    w("")
    w(X["spend_note"] + "\n")
    w("## Notes\n"); w(X["notes"] + "\n")
    (ROOT / "analysis/step23.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step23.md")


if __name__ == "__main__":
    main()
