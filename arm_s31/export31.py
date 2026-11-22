"""Step 31 part 2: export the labelled runs as benchmarks/safety_monitor MinedTrajectory rows (trajectories.jsonl).

Input: arm_s29/labels_all.jsonl (one row per graded step, train_use from step 29) and, with --safer include, the step-30
safer runs (arm_s30/labels_safer.jsonl; read from arm_s30/ when it is on this branch, else from the step-30 worktree).
Text: re-read from each run's own conversation (output.critic_attempt_1.jsonl of the final attempt):
  instruction  the user message the agent received (the first user MessageEvent, equal to the output's `instruction`)
  action       tool_name, the call's arguments (action.data; for a call the SDK rejected, the raw tool-call arguments),
               the agent's own `summary` argument in LabeledStep.summary
  observation  the observation content the agent received (text parts joined with a newline); for a rejected call the
               SDK error text; is_error as recorded
Step i of a run is the i-th action of its conversation, the same reading the grader used (arm_s16b/smoke_grade.actions);
the tool name of every step is checked against the label table.

Nothing from the task bank, env state, snapshots, rules, trap descriptions or task metadata goes into a field the SFT
prompt is rendered from (instruction, tool_name, arguments, summary, observation). Task id, mechanic_id, agent,
prohibition_location, counter_example and the rest are kept under `metadata` (ignored by the loader) and in
instance_id / actor (not rendered).

Labels: unsafe -> high-unsafe, safe -> low-unsafe; label_source = our source (trap:<id>/<rule>, judge, none).
"No label" (train_use drop_step: off_design-only unsafe, third label; and the replayed steps before the block in a safer
run): the loader has no label-less value (LabeledStep.label is a two-value enum, null fails validation), but
build_examples skips a step whose action_id is empty (safety_monitor/sft/data.py:415) while keeping it in the history of
later steps. Such steps are written with action_id "" , train=false, label = our label mapped as above (it is what the
evaluation code would read), label_source "history_only:<reason>".

Trajectory fields: key = run key, instance_id = task id (the shipped split is task-level; all versions of a family get
the same split), run = r<k>, condition = "mg_passive" (the loader's train firewall admits only synthetic corpora or
real passive rollouts: data.py:216-225), actor = agent, role = harmful when the trajectory has a high-unsafe training
example (else clean), rule_based = the same as 0/1, split = train | dev, corpus = gmail-dojo-s31.

Split: by mechanic_id. dev = round(15% of the families) families, one from each of that many different toolkits (a
toolkit with a single family is never drawn, so every toolkit keeps a family in train), drawn with random.Random(SEED);
a draw is kept only when dev holds training unsafe steps from at least 3 toolkits and from all 4 agents (otherwise the
next draw of the same generator). A safer run takes its source run's family, so the same side.

Safer runs (--safer include): every arm_s30 branch with pair_ok whose source run is exported. Trajectory = the steps
before the blocked step (history only: they are the source run's steps, already examples there) + the continuation
(examples by their train_use). The blocked call and its result are left out; the monitor message is never read. When a
continuation step has mentions_block, the trajectory is cut before the first such step; a safer run left with no
training example is not exported.

  .venv/bin/python arm_s31/export31.py --safer none      -> arm_s31/export/base/trajectories.jsonl
  .venv/bin/python arm_s31/export31.py --safer include   -> arm_s31/export/with_safer/trajectories.jsonl
Each also writes eval_dev.jsonl (the dev trajectories only; the benchmarks CLI needs an --eval file) and stats.json;
arm_s31/split31.json holds the family list of each side."""
import argparse, collections, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s31"
SEED = 31; DEV_FRAC = 0.15
AGENTS = ["gpt-6-luna", "haiku5.5", "qwen3.5-9b", "qwen3.5-35b-a3b"]
GRADES = {"step21": "grader/out/v4.2-set0/grades21.jsonl", "step23": "grader/out/v4.2-set0/grades23.jsonl",
          "step25": "arm_s25/grades25.jsonl", "step29": "arm_s29/grades29.jsonl"}
LABEL = {"unsafe": "high-unsafe", "safe": "low-unsafe", "third_label": "low-unsafe"}
BLOCKED = "blocked_by_safety_monitor"


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


def s30_dir():
    for d in (ROOT / "arm_s30", ROOT / ".claude/worktrees/step30/arm_s30"):
        if (d / "labels_safer.jsonl").exists():
            return d
    return None


def conversation(base: Path, result: dict) -> dict:
    o = next(o for o in map(json.loads, (base / result["traj_dir"] / "output.critic_attempt_1.jsonl").read_text().splitlines())
             if o["instance_id"] == result["task"])
    hist = o.get("history") or []
    user = next(e for e in hist if e.get("kind") == "MessageEvent" and e.get("source") == "user")
    instruction = "".join(c.get("text", "") for c in user["llm_message"]["content"] if isinstance(c, dict))
    obs = {}
    for e in hist:   # as arm_s16b/smoke_grade.actions, text parts joined with a newline
        if e.get("kind") == "ObservationEvent" or ("observation" in e and e.get("action_id")):
            ob = e.get("observation") or {}
            obs[e.get("action_id")] = ("\n".join(c.get("text", "") for c in ob.get("content") or [] if isinstance(c, dict)), bool(ob.get("is_error")))
        if e.get("kind") == "AgentErrorEvent" and e.get("tool_call_id"):
            obs[e.get("tool_call_id")] = (e.get("error"), True)
    steps = []
    for e in hist:
        if e.get("kind") == "ActionEvent" or ("action" in e and e.get("tool_name")):
            a = e.get("action") or {}
            if isinstance(a.get("data"), dict):
                args = a["data"]
            elif a:
                args = {k: v for k, v in a.items() if k != "kind"}
            else:   # rejected by the SDK before it ran: the raw arguments the agent sent
                raw = (e.get("tool_call") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(raw)
                except ValueError:
                    args = {"raw_arguments": raw}
                args = {k: v for k, v in args.items() if k != "summary"} if isinstance(args, dict) else {"raw_arguments": args}
            txt, err = obs.get(e.get("id")) or obs.get((e.get("tool_call") or {}).get("id")) or ("", False)
            steps.append({"action_id": e.get("id"), "tool_name": e.get("tool_name"), "arguments": args,
                          "summary": e.get("summary"), "observation": txt, "is_error": err})
    if instruction != o.get("instruction"):
        raise ValueError(f"user message differs from the output's instruction: {result['task']}")
    return {"instruction": instruction, "steps": steps}


def step_row(st, lab, source, *, example: bool, i: int, train_use: str):
    return {"action_id": st["action_id"] if example else "", "tool_name": st["tool_name"], "arguments": st["arguments"],
            "summary": st["summary"], "observation": st["observation"], "is_error": st["is_error"],
            "label": LABEL[lab], "label_source": source if example else f"history_only:{source}",
            "train": example, "step": i, "train_use": train_use}


def base_runs():
    rows = collections.defaultdict(list)
    for x in jl(ROOT / "arm_s29/labels_all.jsonl"):
        rows[(x["grades"], x["run_key"])].append(x)
    grades = {(s, g["key"]): g for s, f in GRADES.items() for g in jl(ROOT / f)}
    out = []
    for (step, key), rs in rows.items():
        rs.sort(key=lambda x: x["step"])
        if not any(x["train_use"] == "use" for x in rs) or any(x["train_use"].startswith("drop_run") for x in rs):
            continue
        g = grades[(step, key)]
        res = json.loads((ROOT / g["tree"] / "harness/results" / f"{key}.json").read_text())
        conv = conversation(ROOT, res)
        if len(conv["steps"]) != len(rs) or any(c["tool_name"] != x["tool"] for c, x in zip(conv["steps"], rs)):
            raise ValueError(f"{key}: conversation steps differ from the label table")
        steps = []
        for st, x in zip(conv["steps"], rs):
            reason = x["label_source"] if x["train_use"] == "use" else f"{x['train_use']}:{x['label_source']}"
            steps.append(step_row(st, x["label"], reason, example=x["train_use"] == "use", i=x["step"], train_use=x["train_use"]))
        r0 = rs[0]
        out.append({"key": key, "instance_id": r0["task_id"], "run": f"r{r0['run']}", "condition": "mg_passive",
                    "actor": r0["agent"], "instruction": conv["instruction"], "steps": steps, "corpus": "gmail-dojo-s31",
                    "services": [g.get("toolkit") or "unknown"],
                    "metadata": {"source": "run", "grades": step, "task_id": r0["task_id"], "mechanic_id": r0["mechanic_id"],
                                 "agent": r0["agent"], "toolkit": g.get("toolkit"), "prohibition_location": r0["prohibition_location"],
                                 "counter_example": bool(g.get("counter_example")), "outcome": r0["outcome"],
                                 "completion": r0["completion"]}})
    return out


def safer_runs(base_by_key, report):
    d = s30_dir()
    if d is None:
        report["safer_source"] = None
        return []
    report["safer_source"] = str(d.relative_to(ROOT))
    rows = collections.defaultdict(list)
    for x in jl(d / "labels_safer.jsonl"):
        rows[x["key"]].append(x)
    report.update(branches=len(rows), not_pair_ok=0, source_not_exported=[], cut=0, steps_lost=0, examples_lost=0,
                  no_example_left=[])
    out = []
    for key, rs in sorted(rows.items()):
        rs.sort(key=lambda x: x["step"])
        if not all(x["pair_ok"] for x in rs):
            report["not_pair_ok"] += 1
            continue
        src = base_by_key.get(rs[0]["source_run_key"])
        if src is None:
            report["source_not_exported"].append(key)
            continue
        blocked = [x for x in rs if x["part"] == "blocked"]
        assert len(blocked) == 1, key
        k = blocked[0]["step"]
        res = json.loads((d / "runs/harness/results" / f"{key}.json").read_text())
        conv = conversation(d.parent, res)
        cs = conv["steps"]
        if cs[k]["tool_name"] != BLOCKED:
            raise ValueError(f"{key}: step {k} is {cs[k]['tool_name']}, not the blocked call")
        if [s["tool_name"] for s in cs[:k]] != [s["tool_name"] for s in src["steps"][:k]]:
            raise ValueError(f"{key}: prefix differs from the source run")
        steps = [step_row(st, "unsafe" if ss["label"] == "high-unsafe" else "safe", f"prefix_of_source_run:{ss['label_source']}",
                          example=False, i=i, train_use="history_only_prefix") for i, (st, ss) in enumerate(zip(cs[:k], src["steps"][:k]))]
        cont = [x for x in rs if x["part"] == "continuation"]
        cut_at = next((j for j, x in enumerate(cont) if x["mentions_block"]), None)
        if cut_at is not None:
            report["cut"] += 1
            report["steps_lost"] += len(cont) - cut_at
            report["examples_lost"] += sum(x["train_use"] == "use" for x in cont[cut_at:])
            cont = cont[:cut_at]
        for x in cont:
            st = cs[x["step"]]
            if st["tool_name"] != x["tool"]:
                raise ValueError(f"{key}: step {x['step']} tool differs")
            lab = "third_label" if x["label"] not in ("safe", "unsafe") else x["label"]
            src_label = x["label_source"] or "none"
            reason = src_label if x["train_use"] == "use" else f"{x['train_use']}:{src_label}"
            steps.append(step_row(st, lab, reason, example=x["train_use"] == "use", i=x["step"], train_use=x["train_use"]))
        if not any(s["train"] for s in steps):   # as for the base runs: only a trajectory with a training example
            report["no_example_left"].append(key)
            continue
        sm = src["metadata"]
        out.append({"key": key, "instance_id": rs[0]["task"], "run": f"r{rs[0]['run']}", "condition": "mg_passive",
                    "actor": rs[0]["agent"], "instruction": conv["instruction"], "steps": steps, "corpus": "gmail-dojo-s31-safer",
                    "services": src["services"],
                    "metadata": sm | {"source": "warned_safer_run", "source_run_key": rs[0]["source_run_key"], "branch_id": rs[0]["branch_id"],
                                      "blocked_step": k, "completion": rs[0]["completion"], "cut_before_mention": cut_at is not None,
                                      "outcome": None, "grades": "step30"}})
    return out


def choose_dev(trajs):
    fam_tk, fam_unsafe = {}, collections.defaultdict(set)
    for t in trajs:
        m = t["metadata"]; fam_tk[m["mechanic_id"]] = m["toolkit"]
        for s in t["steps"]:
            if s["train"] and s["label"] == "high-unsafe":
                fam_unsafe[m["mechanic_id"]].add((m["toolkit"], m["agent"]))
    by_tk = collections.defaultdict(list)
    for f, tk in sorted(fam_tk.items()):
        by_tk[tk].append(f)
    n_dev = round(DEV_FRAC * len(fam_tk))
    pool = sorted(tk for tk, fs in by_tk.items() if len(fs) >= 2)   # a toolkit's only family never goes to dev
    rng = random.Random(SEED)
    for draw in range(1, 1001):
        dev = {rng.choice(sorted(by_tk[tk])) for tk in rng.sample(pool, n_dev)}   # one family from each of n_dev toolkits
        cells = set().union(*(fam_unsafe[f] for f in dev))
        if len({tk for tk, _ in cells}) >= 3 and {a for _, a in cells} >= set(AGENTS):
            return dev, draw, by_tk
    raise RuntimeError("no dev draw meets the constraints")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--safer", choices=("none", "include"), default="none")
    a = ap.parse_args()
    base = base_runs()
    dev, draw, by_tk = choose_dev(base)   # the split is fixed by the base runs only, so both files share it
    report = {"seed": SEED, "dev_draw": draw}
    extra = safer_runs({t["key"]: t for t in base}, report) if a.safer == "include" else []
    trajs = base + extra
    keys = [t["key"] for t in trajs]
    if len(keys) != len(set(keys)):
        sys.exit("a run key occurs twice")
    for t in trajs:
        t["split"] = "dev" if t["metadata"]["mechanic_id"] in dev else "train"
        n_high = sum(s["train"] and s["label"] == "high-unsafe" for s in t["steps"])
        t["role"] = "harmful" if n_high else "clean"; t["rule_based"] = int(bool(n_high))
    out = S / "export" / ("base" if a.safer == "none" else "with_safer")
    out.mkdir(parents=True, exist_ok=True)
    order = ["key", "instance_id", "run", "condition", "actor", "role", "rule_based", "instruction", "steps", "split", "corpus",
             "services", "metadata"]
    dump = lambda rows: "".join(json.dumps({k: t[k] for k in order}, ensure_ascii=False) + "\n" for t in rows)
    (out / "trajectories.jsonl").write_text(dump(trajs))
    (out / "eval_dev.jsonl").write_text(dump([t for t in trajs if t["split"] == "dev"]))
    fams = {"seed": SEED, "dev_fraction": DEV_FRAC, "draw": draw,
            "dev": {tk: sorted(f for f in fs if f in dev) for tk, fs in sorted(by_tk.items())},
            "train": {tk: sorted(f for f in fs if f not in dev) for tk, fs in sorted(by_tk.items())}}
    (S / "split31.json").write_text(json.dumps(fams, indent=1))
    n_ex = collections.Counter((s["label"], t["split"]) for t in trajs for s in t["steps"] if s["train"])
    report |= {"trajectories": len(trajs), "base_runs": len(base), "safer_runs": len(extra),
               "examples": {f"{l} | {sp}": n for (l, sp), n in sorted(n_ex.items())},
               "history_only_steps": sum(not s["train"] for t in trajs for s in t["steps"])}
    (out / "stats.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
