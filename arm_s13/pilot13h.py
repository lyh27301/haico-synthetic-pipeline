"""Step 13h item 5: exposure in the annotation pilots (pilot v1: arm_s13/pilot_blind + pilot_manifest.jsonl; pilot v2:
arm_s13/pilot_v2_blind + pilot_v2_manifest.jsonl). Reads arm_s13/outcomes_v2_13h.jsonl (arm_s13/exposure13h.py).
  1. every blind file with no filled `gold:` line gets an empty `exposed:` line at the top (for the annotator: yes / no);
     a file with a filled `gold:` line is never touched, it is listed instead (checked right before each write);
  2. pairs whose safe side is no longer honest_success under outcome_v2 (safe_unexposed) get a replacement, written as
     NEW files (blind + labeled copy) in the same pilot's folders:
       - same task, when an exposed honest success exists (4o-mini / Qwen runs, as in the pilots; same agent as the
         unsafe side first, then the closest in length): a new safe side;
       - otherwise the task is swapped within its stratum (toolkit x harm carrier): a new task with an exposed honest
         success and an unsafe run (same agent first), whose mechanic is in neither pilot: a new pair;
     no existing file is overwritten or deleted; old manifest lines are kept and annotated (outcome_v2, exposed,
     superseded_by), new lines are appended (part "13h", replaces).
  Second pass (--pass2): pilot v2 only, after the exposure rules were simplified (safe side only, self-describing
  names). The exposed line is not touched again; pairs already superseded are skipped; a mechanic may appear in up to
  --mech-cap tasks across both pilots (counted over every task in either manifest, superseded ones included).
  .venv/bin/python arm_s13/pilot13h.py [--dry] [--pass2 --mech-cap 2]   ->  arm_s13/pilot13h.json / pilot13h_pass2.json"""
import argparse, collections, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"; V8 = ROOT / "arm_v08"
sys.path[:0] = [str(S13), str(V8)]
import pilot_blind_full as PB  # noqa: E402
import pilot13c as PC  # noqa: E402
import replay as R  # noqa: E402
import pilot_v2a as A  # noqa: E402
import pilot_v2b as B  # noqa: E402

PILOTS = {"v1": (S13 / "pilot_blind", S13 / "pilot", S13 / "pilot_manifest.jsonl"),
          "v2": (S13 / "pilot_v2_blind", S13 / "pilot_v2", S13 / "pilot_v2_manifest.jsonl")}
WEAK = ("4omini", "qwen3.5-9b")
FILLED = re.compile(r"^- gold: *\S", re.M)
EXPOSED_LINE = "exposed: "


def mech(t, var) -> str:
    """A task's mechanic family: the variant table's mechanic, with variant / salience suffixes stripped."""
    return re.sub(r"(-v\d+|-sal-(quiet|medium|loud))+$", "", var.get(t, t))


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def annotated(f: Path) -> bool:
    return bool(FILLED.search(f.read_text()))


def add_exposed(f: Path, dry=False) -> str:
    """'annotated' (untouched), 'has_line', or 'added'. The gold check runs right before the write."""
    txt = f.read_text()
    if FILLED.search(txt):
        return "annotated"
    if txt.startswith("exposed:"):
        return "has_line"
    if not dry:
        cur = f.read_text()
        if cur != txt or FILLED.search(cur):   # changed under us: leave it
            return "annotated" if FILLED.search(cur) else "changed"
        f.write_text(EXPOSED_LINE + "\n\n" + txt)
    return "added"


def pools():
    """Candidate runs (4o-mini / Qwen) with their outcome_v2: step-13f record runs (tasks not re-rolled) and v0.8 runs."""
    ox = {(o["task"], o["agent"], o["run"], o["source"]): o for o in jl(S13 / "outcomes_v2_13h.jsonl")}
    A.TOOLKITS = ("gmail", "sqldb", "commerce", "medical", "finance", "evidence")
    A.CARRIERS = ("action", "body", "attachment")
    B.group = lambda o, rr: o["toolkit"]
    ra, var = A.load(); rb, _ = B.load()
    out = collections.defaultdict(list)
    for src, pool in (("step13f", ra), ("v0.8", rb)):
        for t, rs in pool.items():
            for r in rs:
                x = ox.get((t, r["agent"], r["run"], src))
                if not x or r["agent"] not in WEAK or x["contaminated"] or not x["of_record"] or not x["rule_valid"]:
                    continue
                out[t].append(r | {"source": src, "outcome_v2": x["outcome_v2"], "exposed": x["exposed"],
                                   "exposure_step": x["exposure_step"]})
    return out, var


def render(pilot, t, r, side, m, rows, ctx, X, xs8):
    blind, lab, _ = PILOTS[pilot]
    name = f"{t}__{r['agent']}__r{r['run']}"
    if (blind / f"{name}.md").exists() or (lab / f"{name}.md").exists():
        raise FileExistsError(name)
    if r["source"] == "step13f":   # v3 labels of step-13f runs live in action_labels_v3.jsonl
        steps = json.loads((S13 / "steps" / f"{name}.json").read_text()); hist = R.history(X[(t, r["agent"], r["run"])]["traj_dir"], t)
        lab3 = {o["step"]: o for o in map(json.loads, (S13 / "action_labels_v3.jsonl").open())
                if (o["task_id"], o["agent"], o["run"]) == (t, r["agent"], r["run"])}
        for st in steps:
            o = lab3.get(st["step"], {})
            st.setdefault("label_v3", o.get("label_v3")); st.setdefault("probe", o.get("probe_rules"))
    else:
        steps = json.loads((V8 / "analysis/steps" / f"{name}.json").read_text())
        hist = R.history(ROOT / xs8[(t, r["agent"], r["run"])]["traj_dir"], t)
    blind_steps = [{q: st[q] for q in ("step", "tool", "kind", "args", "observation") if q in st} for st in steps]
    PB.render(blind / f"{name}.md", rows[t], ctx.get(t, ""), m, hist, blind_steps)
    txt = (blind / f"{name}.md").read_text()
    if pilot == "v2":
        txt = txt.replace("## Transcript\n", A.INSTR + "\n\n## Transcript\n", 1)
    (blind / f"{name}.md").write_text(EXPOSED_LINE + "\n\n" + txt)
    spec = json.loads((S13 / "probes" / f"{t}.json").read_text())
    rules = {q["id"]: q for v in spec["probes"].values() for q in v}
    piv2 = next((st["step"] for st in steps if st.get("label") == "unsafe"), None)
    piv3 = next((st["step"] for st in steps if st.get("label_v3") == "unsafe"), None)
    v3 = {"episode_unsafe": r["unsafe"], "replay_flags": steps[-1].get("flags", {}) if steps else {}}
    rec = {"task": t, "agent": r["agent"], "run": r["run"], "toolkit": r["toolkit"], "carrier": r["carrier"],
           "goodness": "-", "pivotal_step": piv2, "pivotal_step_v3": piv3, "pivotal_v3_source": [], "v3_rules": [],
           "v3_rules_hinted": [], "v3_rules_v2_blind_spot": [], "v2_safe_v3_unsafe": (not r["unsafe"]) and piv3 is not None,
           "why": f"step 13h replacement, {side} side: {r['outcome']} / {r['outcome_v2']}; {r['n_steps']} steps"}
    for st in steps:
        st |= {"label_v2": st.get("label"), "label_v3_nohint": st.get("label_v3"), "label_v3": st.get("label_v3"),
               "probe_rules": st.get("probe") or {"probe_read": [], "probe_write": [], "probe_send": []}}
    PC.render(lab / f"{name}.md", rows[t], ctx.get(t, ""), v3, rec, steps, rules)
    return name, steps


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--pass2", action="store_true"); ap.add_argument("--mech-cap", type=int, default=1)
    ap.add_argument("--pass3", action="store_true", help="step 13i: drop pairs on --drop tasks, swap outside the stratum")
    ap.add_argument("--drop", help="json list: tasks whose pairs are replaced whatever their outcome")
    ap.add_argument("--exclude", help="json list: tasks never used as a replacement")
    a = ap.parse_args(); a.pass2 = a.pass2 or a.pass3
    todo = ("v2",) if a.pass2 else tuple(PILOTS); tag = "13i" if a.pass3 else "13h-2" if a.pass2 else "13h"
    drop = set(json.loads(Path(a.drop).read_text())) if a.drop else set()
    excl = set(json.loads(Path(a.exclude).read_text())) if a.exclude else set()
    phases = (0, 1, 2, 3) if a.pass3 else (0, 1)
    ox = {(o["task"], o["agent"], o["run"], o["source"]): o for o in jl(S13 / "outcomes_v2_13h.jsonl")}
    res = {"exposed_line": {}, "annotated_untouched": [], "pairs_flagged": [], "replacements": [], "unreplaced": [],
           "safe_side_rule_excluded": []}
    # 1. exposed line
    for p, (blind, _, _) in PILOTS.items():
        for f in sorted(blind.glob("*.md")) if not a.pass2 else []:
            st = add_exposed(f, a.dry)
            res["exposed_line"][f"{p}/{f.name}"] = st
            if st == "annotated":
                res["annotated_untouched"].append(f"{blind.name}/{f.name}")
    # 2. pairs
    pool, var = pools()
    used_runs = set(); used_tasks = set(); mech_tasks = collections.defaultdict(set)
    mans = {p: jl(PILOTS[p][2]) for p in PILOTS}
    for p, man in mans.items():
        for m in man:
            used_runs.add((m["task"], m["agent"], m["run"])); used_tasks.add(m["task"])
            mech_tasks[mech(m["task"], var)].add(m["task"])
    xs, rows = R.bank_runs(); X = {(x["task"], x["agent"], x["run"]): x for x in xs}
    rows |= {json.loads(l)["instance_id"]: json.loads(l) for l in (V8 / "bank_v08.jsonl").read_text().splitlines()}
    xs8 = {}
    for f in (V8 / "harness/results").glob("*.json"):
        r = json.loads(f.read_text()); xs8[(r["task"], r["agent"], int(r["run"]))] = r
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    car = {o["task"]: o["carrier"] for o in jl(S13 / "outcomes_record.jsonl")}
    new_lines = collections.defaultdict(list)
    for p, man in mans.items():
        if p not in todo:
            continue
        by = collections.defaultdict(dict)
        for m in man:
            by[m["task"]][m["label_side"]] = m
        for m in man:   # annotate every line with its exposure / outcome_v2
            src = m["source"] if str(m.get("part")).startswith("13h") else "v0.8" if m.get("part") == "B" else "step13f"
            x = ox.get((m["task"], m["agent"], m["run"], src)) or ox.get((m["task"], m["agent"], m["run"], "v0.8" if src == "step13f" else "step13f"))
            m.update(outcome_v2=x and x["outcome_v2"], exposed=x and x["exposed"], exposure_step=x and x["exposure_step"],
                     exposure_rule_valid=x and x["rule_valid"])
        # phase 0: same task, or a swap to a sibling variant of the same mechanic; phase 1: any task in the stratum
        # (so a pair with a sibling is not left without one because another pair took it first)
        # pass 3 adds phase 2: same toolkit, any carrier; phase 3: any task
        for phase, (t, pair) in [(ph, x) for ph in phases for x in sorted(by.items())]:
            s, u = pair.get("safe"), pair.get("unsafe")
            if not s or not u or s.get("superseded_by"):
                continue
            dropped = t in drop
            if s["exposure_rule_valid"] is False and not dropped:
                if phase == 0:
                    res["safe_side_rule_excluded"].append(f"{p}: {t}__{s['agent']}__r{s['run']}")
                continue
            if s["outcome_v2"] == "honest_success" and not dropped:
                continue
            old = f"{t}__{s['agent']}__r{s['run']}"
            if phase == 0:
                res["pairs_flagged"].append({"pilot": p, "task": t, "safe": old, "safe_outcome_v2": s["outcome_v2"],
                                             "reason": "task dropped (step 13i)" if dropped else "safe side not an exposed honest success",
                                             "unsafe": f"{t}__{u['agent']}__r{u['run']}", "stratum": [s["toolkit"], s["carrier"]]})
            ok = lambda r: r["outcome_v2"] == "honest_success" and r["exposed"] and r["n_steps"] <= A.MAX_STEPS \
                and (r["task"], r["agent"], r["run"]) not in used_runs
            cands = sorted((r for r in pool.get(t, []) if ok(r) and not dropped),
                           key=lambda r: (r["agent"] != u["agent"], abs(r["n_steps"] - u["n_steps"]), r["agent"], r["run"]))
            if cands:
                r = cands[0]; side_lines = [("safe", r)]; mode = "same_task"
            else:   # swap the task within the stratum
                mode = "swap"; best = None
                for t2, rs in sorted(pool.items()):
                    if t2 in used_tasks or t2 in excl or len(mech_tasks[mech(t2, var)]) >= a.mech_cap or not rs or \
                            (phase == 0 and mech(t2, var) != mech(t, var)):
                        continue
                    if phase <= 1 and (rs[0]["toolkit"], car.get(t2, rs[0].get("carrier"))) != (s["toolkit"], s["carrier"]):
                        continue
                    if phase == 2 and rs[0]["toolkit"] != s["toolkit"]:
                        continue
                    hs = [r for r in rs if ok(r)]
                    un = [r for r in rs if r["unsafe"] is True and r["n_steps"] <= A.MAX_STEPS
                          and (r["task"], r["agent"], r["run"]) not in used_runs]
                    prs = sorted(((x, y) for x in un for y in hs),
                                 key=lambda q: (q[0]["agent"] != q[1]["agent"], q[0]["n_steps"] + q[1]["n_steps"],
                                                q[0]["agent"], q[0]["run"], q[1]["run"]))
                    if prs and (best is None or (prs[0][0]["agent"] != prs[0][1]["agent"], prs[0][0]["n_steps"] + prs[0][1]["n_steps"], t2)
                                < (best[0]["agent"] != best[1]["agent"], best[0]["n_steps"] + best[1]["n_steps"], best[0]["task"])):
                        best = prs[0]
                if not best and phase < phases[-1]:
                    continue
                if not best:
                    res["unreplaced"].append({"pilot": p, "task": t, "safe": old, "why": "no exposed honest success on "
                                              "this task and no task in the stratum with an exposed honest success "
                                              f"whose mechanic has fewer than {a.mech_cap} tasks in the pilots"})
                    continue
                side_lines = [("unsafe", best[0]), ("safe", best[1])]
                mode = ["swap_sibling", "swap", "swap_toolkit", "swap_any"][phase]
            files = []
            for side, r in side_lines:
                r = r | {"carrier": car.get(r["task"], r.get("carrier"))}
                m = {"task": r["task"], "agent": r["agent"], "run": r["run"], "part": tag, "label_side": side,
                     "outcome": r["outcome"], "outcome_v2": r["outcome_v2"], "exposed": r["exposed"],
                     "exposure_step": r["exposure_step"], "exposure_rule_valid": True, "unsafe": r["unsafe"],
                     "utility": r["utility"], "toolkit": r["toolkit"], "carrier": r["carrier"],
                     "mechanic": var.get(r["task"], r["task"]), "n_steps": r["n_steps"], "source": r["source"],
                     "hard_tags": r.get("tags", []), "replaces": old if side == "safe" else f"{t}__{u['agent']}__r{u['run']}",
                     "replace_mode": mode, "pair_same_agent": len(side_lines) == 1 and r["agent"] == u["agent"]
                     or len(side_lines) == 2 and side_lines[0][1]["agent"] == side_lines[1][1]["agent"]}
                if not a.dry:
                    render(p, r["task"], r, side, m, rows, ctx, X, xs8)
                used_runs.add((r["task"], r["agent"], r["run"])); used_tasks.add(r["task"])
                mech_tasks[mech(r["task"], var)].add(r["task"])
                new_lines[p].append(m); files.append(f"{r['task']}__{r['agent']}__r{r['run']}")
            s["superseded_by"] = files[-1]
            if mode.startswith("swap"):
                u["superseded_by"] = files[0]
            res["replacements"].append({"pilot": p, "task": t, "old_safe": old, "mode": mode, "new_files": files})
    if not a.dry:
        for p, man in mans.items():
            if p in todo:
                PILOTS[p][2].write_text("".join(json.dumps(m) + "\n" for m in man + new_lines[p]))
    res["counts"] = {"blind_files": len(res["exposed_line"]), "exposed_line": dict(collections.Counter(res["exposed_line"].values())),
                     "pairs_flagged": len(res["pairs_flagged"]), "replaced_same_task": sum(r["mode"] == "same_task" for r in res["replacements"]),
                     "replaced_swap": sum(r["mode"] == "swap" for r in res["replacements"]),
                     "replaced_swap_sibling": sum(r["mode"] == "swap_sibling" for r in res["replacements"]),
                     "replaced_outside_stratum": sum(r["mode"] in ("swap_toolkit", "swap_any") for r in res["replacements"]), "unreplaced": len(res["unreplaced"]),
                     "new_files": sum(len(r["new_files"]) for r in res["replacements"])}
    name = "pilot13i" if a.pass3 else "pilot13h_pass2" if a.pass2 else "pilot13h"
    (S13 / (name + ("_dry.json" if a.dry else ".json"))).write_text(json.dumps(res, indent=1))
    print(json.dumps(res["counts"]))


if __name__ == "__main__":
    main()
