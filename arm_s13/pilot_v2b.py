"""Pilot v2, part B: 10 tasks x 2 trajectories from the v0.8 re-roll (arm_v08/ids_v08.txt), on the new runs
(arm_v08/analysis/outcomes_v08.jsonl, from arm_v08/analyze_v08.py). Added to the folders of part A; part A's files and
manifest lines are never rewritten (the manifest is appended to, and an existing file is never overwritten).
  - groups: finance, evidence, attachment carrier (gmail), fixed-tool re-rolls (arm_s13/reroll13g.json; tasks whose
    runs hit a toolkit row fixed in step 13g), as evenly as the eligible tasks allow; at most one task per mechanic and
    none whose mechanic is already in part A;
  - per task one honest_success and one unsafe run, same agent where possible; agents balanced;
  - hard cases (manifest only) top up part A toward the 25-task targets: unsafe_failed 5, attempt_wrong_* 4,
    honest_success with an attempted or reverted harm 3, v2/v3 disagreement 3;
  - not picked: runs over MAX_STEPS steps, runs whose replay does not reproduce the stored verdict (verdict_mismatch)
    or does not line up with calls.jsonl.
  .venv/bin/python arm_s13/pilot_v2b.py   ->  arm_s13/pilot_v2{,_blind}/ (new files), pilot_v2_manifest.jsonl (appended),
                                              utility_pilot_v2b_review.md (part B; part A's review is left as is), pilot_v2b.json"""
import collections, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"; V = ROOT / "arm_v08"; AN = V / "analysis"
sys.path[:0] = [str(S13), str(V)]
import pilot_blind_full as PB  # noqa: E402
import pilot13c as PC  # noqa: E402
import replay as R  # noqa: E402
import pilot_v2a as A  # noqa: E402

N_TASKS, MAX_STEPS = 10, 60
TOTAL = {"unsafe_failed": 5, "attempt_wrong": 4, "hs_attempted_harm": 3, "v2_v3_disagree": 3}
GROUPS = ("finance", "evidence", "attachment", "fixed_tool")


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def group(o, rr):
    if o["toolkit"] in ("finance", "evidence"):
        return o["toolkit"]
    if o["carrier"] == "attachment":
        return "attachment"
    return "fixed_tool" if o["task"] in rr else None


def load():
    rr = set(json.loads((S13 / "reroll13g.json").read_text())["extra_tasks"])
    car = {o["task"]: o["carrier"] for o in jl(S13 / "outcomes_record.jsonl")}
    var = {v["variant"]: v["mechanic"] for v in jl(ROOT / "arm_s12/variants.jsonl")}
    a_mech = {m["mechanic"] for m in jl(S13 / "pilot_v2_manifest.jsonl") if m["part"] == "A"}
    runs = collections.defaultdict(list)
    for o in jl(AN / "outcomes_v08.jsonl"):
        if "crash" in o or o.get("slot") or not o.get("outcome") or o["n_steps"] > MAX_STEPS \
                or {"verdict_mismatch", "call_alignment", "no_history"} & set(o["issues"]):
            continue
        o = o | {"carrier": car[o["task"]]}
        g = group(o, rr)
        if g is None or var.get(o["task"], o["task"]) in a_mech:
            continue
        hs_harm = o["outcome"] == "honest_success" and (o["attempt_wrong_id"] or o["attempt_wrong_type"]
                                                        or o["n_unsafe_v2"] > 0 or o["n_unsafe_v3"] > 0)
        o |= {"group": g, "tags": [t for t, on in (
            ("unsafe_failed", o["outcome"] == "unsafe_failed"), ("attempt_wrong_id", o["attempt_wrong_id"]),
            ("attempt_wrong_type", o["attempt_wrong_type"]), ("hs_attempted_harm", hs_harm),
            ("v2_v3_disagree", bool(o["v2_v3_disagree_steps"]))) if on]}
        runs[o["task"]].append(o)
    return runs, var


def main():
    if any(m["part"] == "B" for m in jl(S13 / "pilot_v2_manifest.jsonl")):
        sys.exit("part B already in the manifest")
    man_a = jl(S13 / "pilot_v2_manifest.jsonl")
    have = collections.Counter()
    for m in man_a:
        for t in m["hard_tags"]:
            have["attempt_wrong" if t.startswith("attempt_wrong") else t] += 1
    target = {k: max(0, v - have[k]) for k, v in TOTAL.items()}
    ag_a = collections.Counter(m["agent"] for m in man_a)
    runs, var = load()
    tasks = {t: p for t, rs in runs.items() if (p := A.pairs_for(rs))}
    grp = {t: p[0][0]["group"] for t, p in tasks.items()}
    sup = collections.Counter({g: len({var.get(t, t) for t in tasks if grp[t] == g}) for g in GROUPS})
    quota = {g: 0 for g in GROUPS}
    for _ in range(N_TASKS):   # spread evenly over the groups that still have mechanics
        open_ = [g for g in GROUPS if sup[g] > quota[g]]
        if not open_:
            break
        quota[min(open_, key=lambda g: quota[g])] += 1

    def score(sel):
        c = A.hard_counts(sel)
        ag = collections.Counter(r["agent"] for p in sel.values() for r in p) + ag_a
        s = sum(10 * min(c[k], v) - 2 * max(0, c[k] - v - 2) for k, v in target.items())
        s -= 4 * abs(ag["4omini"] - ag["qwen3.5-9b"]) + sum(p[0]["agent"] != p[1]["agent"] for p in sel.values())
        return s - 0.02 * sum(r["n_steps"] for p in sel.values() for r in p)
    rng = random.Random(20261112); best = None
    for _ in range(4000):
        order = list(tasks); rng.shuffle(order); sel, used, cnt = {}, set(), collections.Counter()
        for t in order:
            if var.get(t, t) in used or cnt[grp[t]] >= quota[grp[t]]:
                continue
            sel[t] = rng.choice(tasks[t]); used.add(var.get(t, t)); cnt[grp[t]] += 1
        if len(sel) < min(N_TASKS, sum(quota.values())):
            continue
        for t in list(sel):
            for p in tasks[t]:
                trial = dict(sel); trial[t] = p
                if score(trial) > score(sel):
                    sel = trial
        if best is None or score(sel) > score(best):
            best = sel
    assert best, "no selection"
    sel = best
    xs = {}
    for f in (V / "harness/results").glob("*.json"):
        r = json.loads(f.read_text())
        xs[(r["task"], r["agent"], int(r["run"]))] = r
    rows = A.R.bank_runs()[1] | {json.loads(l)["instance_id"]: json.loads(l) for l in (V / "bank_v08.jsonl").read_text().splitlines()}
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    new_man, tool_steps, steps_total = [], 0, 0
    for t in sorted(sel, key=lambda t: (grp[t], t)):
        u, s = sel[t]
        for r, side in ((u, "unsafe"), (s, "safe")):
            k = (t, r["agent"], r["run"]); name = f"{t}__{r['agent']}__r{r['run']}"
            if (A.BLIND / f"{name}.md").exists() or (A.LAB / f"{name}.md").exists():
                sys.exit(f"{name} exists; part A files are never overwritten")
            x = xs[k]; steps = json.loads((AN / "steps" / f"{name}.json").read_text())
            m = {"task": t, "agent": r["agent"], "run": r["run"], "part": "B", "label_side": side, "group": grp[t],
                 "outcome": r["outcome"], "unsafe": r["unsafe"], "utility": r["utility"], "toolkit": r["toolkit"],
                 "carrier": r["carrier"], "mechanic": var.get(t, t), "pair_same_agent": u["agent"] == s["agent"],
                 "n_steps": r["n_steps"], "hard_tags": r["tags"], "attempt_wrong_id_steps": r["attempt_wrong_id_steps"],
                 "attempt_wrong_type_steps": r["attempt_wrong_type_steps"], "v2_v3_disagree_steps": r["v2_v3_disagree_steps"],
                 "n_unsafe_v2": r["n_unsafe_v2"], "n_unsafe_v3": r["n_unsafe_v3"], "pivotal_step": r["pivotal_v2"],
                 "pivotal_step_v3": r["pivotal_v3"], "source": "v0.8 batch"}
            new_man.append(m)
            hist = R.history(ROOT / x["traj_dir"], t)
            blind_steps = [{q: st[q] for q in ("step", "tool", "kind", "args", "observation") if q in st} for st in steps]
            PB.render(A.BLIND / f"{name}.md", rows[t], ctx.get(t, ""), m, hist, blind_steps)
            txt = (A.BLIND / f"{name}.md").read_text().replace("## Transcript\n", A.INSTR + "\n\n## Transcript\n", 1)
            (A.BLIND / f"{name}.md").write_text(txt)
            tool_steps += len(re.findall(r"^- gold: *$", txt, re.M)); steps_total += len(steps)
            spec = json.loads((S13 / "probes" / f"{t}.json").read_text())
            rules = {q["id"]: q for v in spec["probes"].values() for q in v}
            v3 = {"episode_unsafe": r["unsafe"], "replay_flags": steps[-1]["flags"] if steps else {}}
            rec = {"task": t, "agent": r["agent"], "run": r["run"], "toolkit": r["toolkit"], "carrier": r["carrier"],
                   "goodness": "-", "pivotal_step": r["pivotal_v2"], "pivotal_step_v3": r["pivotal_v3"],
                   "pivotal_v3_source": [], "v3_rules": r["pivotal_v3_rules"], "v3_rules_hinted": [],
                   "v3_rules_v2_blind_spot": [q for q in r["pivotal_v3_rules"] if rules.get(q, {}).get("v2_blind_spot")],
                   "v2_safe_v3_unsafe": (not r["unsafe"]) and r["pivotal_v3"] is not None,
                   "why": f"part B ({grp[t]}), {side} side: {r['outcome']}; {r['n_steps']} steps"
                          + (f"; hard: {', '.join(r['tags'])}" if r["tags"] else "")}
            for st in steps:
                st |= {"label_v2": st["label"], "label_v3_nohint": st["label_v3"], "probe_rules": st["probe"]}
            PC.render(A.LAB / f"{name}.md", rows[t], ctx.get(t, ""), v3, rec, steps, rules)
    with open(A.MAN, "a") as fh:
        fh.writelines(json.dumps(m) + "\n" for m in new_man)
    A.utility_review(sel, rows, rec_rows=[o for o in jl(AN / "outcomes_v08.jsonl") if not o.get("slot") and "crash" not in o],
                     path=S13 / "utility_pilot_v2b_review.md",
                     title="# Utility specs for the pilot v2 tasks (part B: 10 tasks from the v0.8 re-roll)",
                     runs_note="*Runs* counts the task's v0.8 runs (slot runs excluded) that meet the relaxed requirement.")
    hc = A.hard_counts(sel)
    summ = {"part": "B", "tasks": len(sel), "trajectories": len(new_man), "steps": steps_total,
            "tool_call_steps_to_annotate": tool_steps, "quota": quota, "eligible_mechanics": dict(sup),
            "strata_toolkit_carrier_agent": {" / ".join(k): v for k, v in sorted(collections.Counter(
                (m["toolkit"], m["carrier"], m["agent"]) for m in new_man).items())},
            "by_group": dict(collections.Counter(m["group"] for m in new_man[::2])),
            "by_agent": dict(collections.Counter(m["agent"] for m in new_man)),
            "outcomes": dict(collections.Counter(m["outcome"] for m in new_man)),
            "hard_cases": {k: hc[k] for k in TOTAL}, "hard_targets_after_part_A": target,
            "hard_runs": [f"{m['task']}__{m['agent']}__r{m['run']}: {', '.join(m['hard_tags'])}" for m in new_man if m["hard_tags"]]}
    (S13 / "pilot_v2b.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
    return sel


if __name__ == "__main__":
    main()
