"""Step 25: write analysis/step25.md from the grades (grades21 / grades23 of v4.2-set0, arm_s25/grades25.jsonl), the relabel
(arm_s25/prohibition_location.jsonl, b_steps.jsonl, b_offdesign.jsonl), the task report (arm_s25/tasks_report.json), the
step-25 rules (grader/out/v4.2-s25), the off_design groups (arm_s25/offdesign_groups.json), the run results, the key log
and arm_s25/report_extra.json (hand-written text). No model call.   .venv/bin/python arm_s25/report25.py"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s25"; SET = ROOT / "grader/out/v4.2-set0"
sys.path.insert(0, str(ROOT / "arm_s23"))
from report23 import cls, agent_table, AG  # noqa: E402
X = json.loads((S / "report_extra.json").read_text())
s = lambda t: t.removeprefix("safety-")
jl = lambda p: [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
REPLACED = {"safety-sq-active-studies-changelog": "sq-active-studies-changelog-v25", "safety-sq-partner-grant-v12": "sq-partner-grant-v12-v25"}
NFT = "safety-sq-partner-grant-v12"
LOCS = ["instruction", "object", "destination", "related_context", "unrelated", "common_sense", "none"]
CASES = ["in_trajectory", "common_sense", "object_or_destination", "related_context_only", "not_reachable"]


def task_agent_table(w, G, tasks, mark=lambda t: ""):
    w("| task | toolkit | " + " | ".join(AG) + " | all |\n|---|---|" + "---|" * (len(AG) + 1))
    for t in tasks:
        g = [x for x in G if x["task"] == t]
        cells = []
        for a in AG:
            ga = [x for x in g if x["agent"] == a]
            cells.append(f"{sum('unsafe' in x['labels'] for x in ga)}/{len(ga)}" if ga else "queued")
        tk = g[0]["toolkit"] if g else ""
        w(f"| {s(t)}{mark(t)} | {tk} | " + " | ".join(cells) + f" | {sum('unsafe' in x['labels'] for x in g)}/{len(g)} |")
    w("")


def main():
    G21 = [x for x in jl(SET / "grades21.jsonl") if "crash" not in x]
    G23 = [x for x in jl(SET / "grades23.jsonl") if "crash" not in x]
    G25 = [x for x in jl(S / "grades25.jsonl") if "crash" not in x]
    reruns = [x for x in G23 if x["tree"].startswith("arm_s21")]
    new23 = [x for x in G23 if not x["tree"].startswith("arm_s21")]
    A = jl(S / "prohibition_location.jsonl"); A24 = {o["task"]: o for o in jl(ROOT / "arm_s24/prohibition_location.jsonl")}
    B = jl(S / "b_steps.jsonl"); OFF = jl(S / "b_offdesign.jsonl")
    L = []; w = L.append
    w("# Step 25: missing Qwen runs, prohibition locations relabelled, two tasks repaired, off_design groups\n")
    w("Date: 2026-11-19. " + X["intro"] + "\n")

    # ---------------------------------------------------------------- part 1
    w("## 1. The Qwen runs that never started\n"); w(X["part1_why"] + "\n"); w(X["part1_what"] + "\n")
    w("**Step 23 tables, rewritten with what is graded now** (rules as in step 23: v4.2-set0 for the step-22 versions, "
      "v4.2-s23 for the two cm-firmware-lock versions). Qwen cells read `queued` until the cluster jobs run.\n")
    agent_table(w, new23, f"**Graded step-23 runs** ({len(new23)} of 60; `grader/out/v4.2-set0/grades23.jsonl`):")
    t23 = sorted({x["task"] for x in jl(SET / "grades23.jsonl") if not x.get("tree", "").startswith("arm_s21")} |
                 set((ROOT / "arm_s23/bank/tasks.txt").read_text().split()))
    w("**Per task and agent** (runs of 3 with an unsafe step):\n")
    task_agent_table(w, new23, t23)
    w("**The two 9B payroll r2 re-runs:** " + ("; ".join(f"{s(x['task'])} r{x['run']}: {cls(x).replace('_', ' ')}" for x in reruns)
                                               if reruns else "queued (the 9B job runs them first).") + "\n")
    agent_table(w, G21 + G23 + G25, f"**Per agent, all graded runs of steps 21, 23 and 25** ({len(G21 + G23 + G25)} runs; the "
                "old sq-active-studies-changelog and sq-partner-grant-v12 runs are included here and marked replaced below):")

    # ---------------------------------------------------------------- part 2
    w("## 2. Branch step24 merged\n"); w(X["part2"] + "\n")

    # ---------------------------------------------------------------- part 3
    w("## 3. prohibition_location relabelled\n"); w(X["part3_intro"] + "\n")
    w("### A. Tasks whose value changed\n")
    w("Old = step 24's task value (nearest place over all traps) and, in brackets, step 24's value over the traps the "
      "violator reference fires. New = step 25 (rule c: over the traps the violator fires).\n")
    w("| task | old | new | why |\n|---|---|---|---|")
    for o in A:
        o24 = A24.get(o["task"])
        if not o24:
            continue
        old, oldv = o24["prohibition_location"], o24["value_of_traps_violator_triggers"]
        if old != o["prohibition_location"] or (not o["control"] and oldv != o["prohibition_location"]):
            w(f"| {s(o['task'])} | {old} [{oldv or 'no designed trap'}] | **{o['prohibition_location']}** | {X['why'].get(s(o['task']), '')} |")
    w("")
    w("**Count per location** (48 tasks of step 24; the two repaired versions are counted apart):\n")
    w("| location | tasks, step 25 (rule c) | of them controls | tasks, step 24 (nearest over all traps) | traps, step 25 (each trap's own value) | traps, step 24 |")
    w("|---|---|---|---|---|---|")
    old48 = [o for o in A if o["task"] in A24]
    c25 = collections.Counter(o["prohibition_location"] for o in old48); c24 = collections.Counter(o["prohibition_location"] for o in A24.values())
    tc25 = collections.Counter(x["value"] for o in old48 for x in o["traps"]); tc24 = collections.Counter(x["value"] for o in A24.values() for x in o["traps"])
    cc = collections.Counter(o["prohibition_location"] for o in old48 if o["control"])
    for k in LOCS:
        w(f"| {k} | {c25[k]} | {cc[k]} | {c24[k]} | {tc25[k] if k != 'none' else ''} | {tc24[k] if k != 'none' else ''} |")
    w(f"| total | {len(old48)} | {sum(cc.values())} | {len(A24)} | {sum(tc25.values())} | {sum(tc24.values())} |")
    w("")
    w("`none` = the violator reference fires no designed trap (its unsafe step is off_design only), so rule c gives no value; "
      "their value over all traps is in the jsonl (`value_over_all_traps`). Controls have no violator reference and keep the "
      "value over all traps.\n")
    w("**Repaired versions:** " + "; ".join(f"`{s(o['task'])}` → {o['prohibition_location']} ({o['basis']})" for o in A if o["task"] not in A24) + ".\n")
    w("**Two-piece prohibitions (rule a), both pieces recorded:**\n")
    w("| task | trap | value | restriction (nearest place) | fact (nearest place) |\n|---|---|---|---|---|")
    for o in A:
        for x in o["traps"]:
            if x.get("two_piece"):
                pc = {p["role"]: p for p in x["pieces"]}
                w(f"| {s(o['task'])} | {x['trap']} | {x['value']} | {pc['restriction']['value']} | {pc['fact']['value']} |")
    w("")
    w("**States, not prohibitions (rule b):** " + "; ".join(f"{s(o['task'])} {x['trap']} `{p['where'].split(' ', 1)[-1]}`: {p['reason']}"
                                                         for o in A for x in o["traps"] for p in x["places"] if p.get("state")) + ".\n")
    low = [(o, x) for o in A for x in o["traps"] if x["violator_triggers"] and x["confidence"] == "low"]
    w(f"**Low confidence** (traps the violator fires; {len(low)}): " + "; ".join(f"{s(o['task'])} {x['trap']} ({x['value']})" for o, x in low) + ".\n")

    w("### B. Per unsafe step (step-21, step-23 and step-25 graded runs)\n"); w(X["part3_b"] + "\n")
    flag = lambda o: o.get("not_for_training") or o.get("replaced")
    def ctab(rows, key, keys):
        w(f"| {key} | trap steps | " + " | ".join(CASES) + " | off_design steps |\n|---|---|" + "---|" * (len(CASES) + 1))
        for k in keys:
            r = [o for o in rows if (o["agent"] if key == "agent" else o["task"]) == k]
            of = [o for o in OFF if (o["agent"] if key == "agent" else o["task"]) == k]
            c = collections.Counter(o["case"] for o in r)
            name = k if key == "agent" else s(k) + (" ‡" if k == NFT else " †" if k in REPLACED else "")
            w(f"| {name} | {len(r)} | " + " | ".join(f"{c[x]} ({c[x] / len(r):.0%})" if r and c[x] else "0" for x in CASES) + f" | {len(of)} |")
        r, of = rows, OFF
        c = collections.Counter(o["case"] for o in r)
        w(f"| all | {len(r)} | " + " | ".join(f"{c[x]} ({c[x] / max(len(r), 1):.0%})" for x in CASES) + f" | {len(of)} |")
        w("")
    w("**Per agent:**\n"); ctab(B, "agent", AG)
    tasks = sorted({o["task"] for o in B} | {o["task"] for o in OFF})
    w("**Per task** († replaced by a step-25 version; ‡ the old sq-partner-grant-v12: replaced, and its unsafe steps are "
      "**not for training (no stated reason)**):\n"); ctab(B, "task", tasks)
    w("**Usable unsafe steps per monitor version**:\n")
    w("- v0 = trap steps with the prohibition already in the trajectory + common_sense trap steps + off_design steps;\n"
      "- v1 = v0 + reachable by reading the object or destination (or the file the instruction points to: one read);\n"
      "- later = v1 + related_context.\n")
    w("| set of steps | unsafe steps | v0 | v1 | later | not reachable |\n|---|---|---|---|---|---|")
    def vrow(name, b, off):
        c = collections.Counter(o["case"] for o in b); n = len(b) + len(off)
        v0 = c["in_trajectory"] + c["common_sense"] + len(off); v1 = v0 + c["object_or_destination"]; v2 = v1 + c["related_context_only"]
        pc = lambda v: f"{v} ({v / max(n, 1):.0%})"
        w(f"| {name} | {n} | {pc(v0)} | {pc(v1)} | {pc(v2)} | {pc(c['not_reachable'])} |")
    vrow("all graded steps", B, OFF)
    keep = lambda o: not flag(o)
    vrow("without replaced versions and not-for-training steps", [o for o in B if keep(o)], [o for o in OFF if keep(o)])
    vrow("only the replaced / not-for-training steps", [o for o in B if flag(o)], [o for o in OFF if flag(o)])
    for a in AG:
        vrow(f"{a} (without replaced)", [o for o in B if keep(o) and o["agent"] == a], [o for o in OFF if keep(o) and o["agent"] == a])
    w("")
    nft = [o for o in OFF if o.get("not_for_training")]
    w(f"**The old sq-partner-grant-v12 steps marked not for training (no stated reason):** {len(nft)} off_design steps "
      f"(" + ", ".join(f"{o['agent']} r{o['run']} step {o['step']}" for o in nft) + "). They stay on disk and in the grade files.\n")
    w("### What still does not fit\n"); w(X["part3_nofit"] + "\n")

    # ---------------------------------------------------------------- parts 4 and 5
    TR = json.loads((S / "tasks_report.json").read_text())
    I = json.loads((ROOT / "grader/out/v4.2-s25/set.json").read_text())["tasks"]
    for part, t, title in ((4, "safety-sq-active-studies-changelog-v25", "Repair sq-active-studies-changelog"),
                           (5, "safety-sq-partner-grant-v12-v25", "Repair sq-partner-grant-v12")):
        w(f"## {part}. {title}\n"); w(X[f"part{part}"] + "\n")
        r = TR[t]
        for k, d in r["diff"].items():
            w(f"`{k}` (old → `{s(t)}`):\n\n```diff\n{d}\n```\n")
        v = r["validate"]
        w(f"References played on the new version: safe {v['safe_reference']['steps']} steps, {len(v['safe_reference']['errors'])} errors, "
          f"changes {v['safe_reference']['changes']}; violator {v['violator_reference']['steps']} steps, "
          f"{len(v['violator_reference']['errors'])} errors, changes {v['violator_reference']['changes']}. Other fields changed: "
          f"{', '.join(r['other_fields_changed']) or 'none'}.\n")
        d = json.loads((ROOT / I[t]["rule_file"]).read_text()); c = d["checks"]; rg = d.get("regenerations") or {}
        w(f"Rules (`grader/gen_rules_s25.py`, v4.2 pipeline unchanged, `grader/out/v4.2-s25/`, outside the tag): ten checks "
          f"{'all passed' if not c.get('failed') else 'failed: ' + ', '.join(c['failed'])}; regenerations step 1 {rg.get('step1', 0)}, "
          f"safety {rg.get('safety', 0)}, completion {rg.get('completion', 0)}. " + X[f"part{part}_rules"] + "\n")
        g = [x for x in G25 if x["task"] == t]
        w(f"**Runs** ({len(g)} of 12 graded; `arm_s25/grades25.jsonl`):\n")
        w("| agent | run | outcome | unsafe steps (finding) |\n|---|---|---|---|")
        for x in sorted(g, key=lambda x: (AG.index(x["agent"]), x["run"])):
            us = [f"step {i} `{x['tools'][i]}`: " + ", ".join(f"{f.get('rule')} {f.get('tag')} {f.get('item') or f.get('harm') or ''}".strip()
                                                         for f in fs if f.get("label") == "unsafe")
                  for i, (lb, fs) in enumerate(zip(x["labels"], x["findings"])) if lb == "unsafe"]
            w(f"| {x['agent']} | r{x['run']} | {cls(x).replace('_', ' ')} | {'; '.join(us) or '-'} |")
        for a in AG:
            if not any(x["agent"] == a for x in g):
                w(f"| {a} | r1-r3 | queued | |")
        w("")
        old = REPLACED and [k for k, v in REPLACED.items() if v == s(t)][0]
        go = [x for x in G21 if x["task"] == old]
        w(f"**Old version `{s(old)}` (step-21 runs, marked replaced; on disk, not re-graded):** runs with an unsafe step per agent: " +
          ", ".join(f"{a} {sum('unsafe' in x['labels'] for x in go if x['agent'] == a)}/{sum(1 for x in go if x['agent'] == a)}" for a in AG) +
          f"; unsafe steps {sum(x['labels'].count('unsafe') for x in go)}.\n")
        w(X[f"part{part}_note"] + "\n")
    w("**Per task and agent, the two repaired versions** (runs of 3 with an unsafe step):\n")
    task_agent_table(w, G25, sorted(I))

    # ---------------------------------------------------------------- part 6
    D = json.loads((S / "offdesign_groups.json").read_text())
    w("## 6. off_design unsafe steps, grouped\n"); w(X["part6"] + "\n")
    w("| task | collection | kind | object | runs | agents | example call | the expected events rest on (for excluding it) | note |")
    w("|---|---|---|---|---|---|---|---|---|")
    for gr in D["groups"]:
        ex = gr["example"]; ex_s = f"{ex['tool']} `{ex['args'][:140].replace('|', '/').replace(chr(10), ' ')}`"
        sent, note = gr["exclude_reading"]
        coll = gr["collection"].replace("databases.research_db.", "").replace(".rows", "")
        w(f"| {s(gr['task'])}{' ‡' if gr['task'] == NFT else ''} | {coll} | {gr['kind']} | `{gr['object'][:60]}` | {gr['runs']} | "
          f"{', '.join(gr['agents'])} | {ex_s} | {sent.replace('|', '/')} | {note.replace('|', '/')} |")
    w("")
    multi = [gr for gr in D["groups"] if len(gr["agents"]) >= 2]
    w(f"**Groups done by 2 or more agents ({len(multi)}):**\n")
    for gr in multi:
        w(f"- {s(gr['task'])}: {gr['kind']} {gr['collection'].replace('databases.research_db.', '').replace('.rows', '')} "
          f"`{gr['object'][:60]}`: {gr['runs']} runs, {', '.join(gr['agents'])}")
    w("")
    w(f"**Rule sets whose step-1 NOTES say the request is ambiguous or does not enumerate / specify something "
      f"({len(D['notes_ambiguous'])}):**\n")
    for a in D["notes_ambiguous"]:
        w(f"- `{s(a['rule_set'])}`: " + " ".join(f"“{x}”" for x in a["sentences"]))
    w("")
    w(X["part6_note"] + "\n")

    # ---------------------------------------------------------------- waiting, spend, notes
    w("## Still waiting\n"); w(X["waiting"] + "\n")
    w("## Spend\n")
    fbsum = lambda p: sum(o.get("cost", 0) for o in jl(p))
    rules_g, rules_fb = fbsum(ROOT / "grader/out/v4.2-s25/usage.jsonl"), fbsum(ROOT / "grader/out/v4.2-s25/usage_fallback.jsonl")
    gr_g = fbsum(SET / "usage23.jsonl") + fbsum(SET / "usage25.jsonl")
    luna = haiku = 0.0
    for f in (S / "runs/harness/results").glob("*.json"):
        r = json.loads(f.read_text()); cost = (r.get("usage") or {}).get("accumulated_cost") or 0
        luna += cost if r["agent"] == "gpt-6-luna" else 0; haiku += cost if r["agent"] == "haiku5.5" else 0
    w("| what | key / account | spend |\n|---|---|---|")
    w(f"| rules for the 2 repaired versions | OpenAI group | ${rules_g:.2f} |")
    w(f"| rules | OpenAI fallback | ${rules_fb:.2f} |")
    w(f"| grading judges (step-25 runs; every judge answer came from the cache) | OpenAI group | ${gr_g:.2f} |")
    w(f"| gpt-6-luna agent, 6 runs | OpenAI group | ${luna:.2f} |")
    w(f"| Haiku 5.5 agent, 6 runs | Anthropic | ${haiku:.2f} |")
    w(f"| **OpenAI total** | group ${rules_g + gr_g + luna:.2f} + fallback ${rules_fb:.2f} | **${rules_g + gr_g + luna + rules_fb:.2f}** (cap $2) |")
    w(f"| **Anthropic total** | | **${haiku:.2f}** (cap $1) |")
    w("")
    w(X["spend_note"] + "\n")
    w("## Notes\n"); w(X["notes"] + "\n")
    (ROOT / "analysis/step25.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step25.md")


if __name__ == "__main__":
    main()
