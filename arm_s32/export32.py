"""Step 32 part 2: export the labelled runs as READ and JUDGE training examples (benchmarks MinedTrajectory rows).

Same runs, steps, labels and family split as step 31 (arm_s31/export31.py: base_runs, safer_runs, choose_dev, imported
unchanged); --safer include adds every pair_ok step-30 safer run, with the blocked call and its message left out and the
trajectory cut before the first step that mentions the block, as in step 31.

Two single-turn examples per training step, as two trajectories per run (the benchmarks loader builds one example per
step): `<key>::read` and `<key>::judge`. Both have the run's history; they differ in the system prompt (trajectory
system_prompt), the text after the current action (step context) and the target (step target):
  READ   input  instruction + prior steps + current action
         target the read calls (arm_s32/reads32.py targets, minus reads whose content is already in the shown history),
                one per line as `tool {json args}`, or NONE
  JUDGE  input  the same + "Reads before judging:" with each call and its result on the stored state before the step
         target "Label: high-unsafe" + "Reason: <step 30 Why> <step 30 consequence>", or "Label: low-unsafe"
The reason is the step-30 unit text of the step's task and traps (arm_s30/texts30.json; names the JUDGE input does not
contain replaced by their neutral phrases, arm_s30/texts30.fill), only when the prohibition is in the JUDGE input as
the model sees it (after the observation cut and the history fit). Unsafe steps without it keep the label, no reason.
The step 30 message itself is never in an input. Its texts say "the blocked call" (update, insert); in the reason that
reads "the current call".

Rendering options (the benchmarks branch gmail-dojo-monitor): --max-obs-chars (observation cut), --max-length (token
budget; the oldest history steps are left out until an example fits). The prohibition check renders with exactly
these, with a local Qwen tokenizer (QWEN_TOKENIZER_JSON) for the token count.

  .venv/bin/python arm_s32/export32.py --safer none       -> arm_s32/export/base/
  .venv/bin/python arm_s32/export32.py --safer include    -> arm_s32/export/with_safer/
Each writes trajectories.jsonl, eval_dev.jsonl (dev only), stats.json; base also writes arm_s32/prohibition32.json."""
import argparse, collections, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s32"
BENCH = Path(os.environ.get("BENCHMARKS_DIR", Path.home() / "Documents/workspace/benchmarks-gmail-dojo-monitor"))
sys.path[:0] = [str(BENCH / "safety_monitor"), str(S), str(ROOT / "arm_s31"), str(ROOT / "arm_s30")]
os.environ["BENCHMARKS_DIR"] = str(BENCH)   # check31 puts this checkout first on sys.path too
from safety_monitor.synthesis.pairs import MinedTrajectory  # noqa: E402
from safety_monitor.sft.data import build_examples, critic_user_prompt, mined_to_steps  # noqa: E402
import reads32 as R  # noqa: E402
import export31 as E31  # noqa: E402
import check31  # noqa: E402  (norm, fragments: the step-31 prohibition matcher)

TOK = os.environ.get("QWEN_TOKENIZER_JSON") or next(   # a local Qwen tokenizer: counts for the history fit of the checks
    iter(sorted((Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots").glob("*/tokenizer.json"))), None)
STEP30 = ROOT / ".claude/worktrees/step30"   # where step 30's branch runs (state records) were written


def token_counter():
    from tokenizers import Tokenizer
    t = Tokenizer.from_file(str(TOK))

    def count(messages):   # chat template: about 5 tokens per message plus the generation prompt
        return sum(len(t.encode(m["content"]).ids) + 5 for m in messages) + 3
    return count


# ---------------------------------------------------------------- stored states
_runs = {}


def load_states(tr):
    """runs16c steps (call, pre, pre_ws, ...) of the run a trajectory's steps come from."""
    import texts30 as T, runs16c, play as P, s29
    G23 = T.setup()
    runs16c._BANK = runs16c._BANK or G23.rows()
    m = tr["metadata"]
    if m["source"] == "run":
        g = _grades()[(m["grades"], tr["key"])]
        res = json.loads((ROOT / g["tree"] / "harness/results" / f"{tr['key']}.json").read_text())
    else:
        res = json.loads((ROOT / "arm_s30/runs/harness/results" / f"{tr['key']}.json").read_text())
        for k in ("state_dir", "traj_dir"):
            if not (ROOT / res[k]).exists():
                res[k] = str((STEP30 / res[k]).relative_to(ROOT))
    P.BANK = s29.bank(tr["instance_id"])
    return runs16c.load(res | {"key": tr["key"]})


_G = {}


def _grades():
    if not _G:
        _G.update({(s, g["key"]): g for s, f in E31.GRADES.items() for g in E31.jl(ROOT / f)})
    return _G


def write_dev_states(path, judge_rows):
    """The stored state before every dev training step (toolkit state + workspace text), so arm_s32/eval.py can run the
    model's reads where the run records are not available (they are local and not committed)."""
    import gzip
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for t in judge_rows:
            src = {"key": t["metadata"]["run_key"], "instance_id": t["instance_id"], "metadata": t["metadata"]}
            L = load_states(src)
            for s in t["steps"]:
                if s["train"]:
                    x = L["steps"][s["step"]]
                    fh.write(json.dumps({"key": src["key"], "step": s["step"], "pre": x["pre"], "pre_ws": x["pre_ws"]},
                                        ensure_ascii=False, default=str) + "\n")


def dev_states(path):
    import gzip
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for ln in fh:
            d = json.loads(ln); out[(d["key"], d["step"])] = d
    return out


# ---------------------------------------------------------------- reasons (step 30 unit texts)
def units():
    U = json.loads((ROOT / "arm_s30/texts30.json").read_text())
    by_task = collections.defaultdict(list)
    for u in U.values():
        traps = u["traps"] if isinstance(u["traps"], list) else eval(u["traps"])  # noqa: S307 (stored as a repr)
        by_task[u["task"]].append((tuple(traps), u))
    return by_task


def traps_of(label_source):
    return [p.split("/")[0] for p in label_source.removeprefix("trap:").split(",")] if label_source.startswith("trap:") else []


def find_unit(task, family, traps, by_task, fam_of):
    """(unit, how): the same task with the same traps; the same task sharing a trap; a task of the same family with the
    same traps; sharing a trap."""
    want = set(traps)
    for how, pool in (("task", by_task.get(task, [])),
                      ("family", [x for t, xs in by_task.items() if fam_of.get(t) == family and t != task for x in xs])):
        exact = [u for tr, u in pool if set(tr) == want]
        if exact:
            return exact[0], f"{how}_same_traps"
        share = [u for tr, u in pool if set(tr) & want]
        if share:
            return share[0], f"{how}_shared_trap"
    return None, "none"


def reason(u, seen):
    import texts30 as T
    why = u["why"] if isinstance(u["why"], dict) else eval(u["why"])  # noqa: S307
    con = u["consequence"] if isinstance(u["consequence"], dict) else eval(u["consequence"])  # noqa: S307
    w, _, _ = T.fill(why["text"], why.get("mentions"), seen)
    c, _, _ = T.fill(con["text"], con.get("mentions"), seen)
    # the texts were written for the block message ("the blocked call"); the monitor judges the current call
    return re.sub(r"\b([Tt]he|[Yy]our) blocked (calls?|update|insert)\b", r"\1 current \2", f"{w} {c}".strip())


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--safer", choices=("none", "include"), default="none")
    ap.add_argument("--max-obs-chars", type=int, default=1500)
    ap.add_argument("--max-length", type=int, default=6144)
    ap.add_argument("--cache", help="keep / reuse the reads of part 1 in this file (same --safer and --max-obs-chars)")
    a = ap.parse_args()
    count = token_counter()
    base = E31.base_runs()
    dev, draw, _ = E31.choose_dev(base)
    split31 = json.loads((ROOT / "arm_s31/split31.json").read_text())
    assert sorted(dev) == sorted(f for fs in split31["dev"].values() for f in fs), "dev families differ from step 31"
    rep = {"dev_draw": draw}
    if not any((ROOT / "arm_s30/runs/harness").glob("*/b*_a*")) and (STEP30 / "arm_s30/labels_safer.jsonl").exists():
        E31.s30_dir = lambda: STEP30 / "arm_s30"   # step 30's run folders (not committed) are in its worktree
    extra = E31.safer_runs({t["key"]: t for t in base}, rep) if a.safer == "include" else []
    trajs = base + extra
    for t in trajs:
        t["split"] = "dev" if t["metadata"]["mechanic_id"] in dev else "train"
        n_high = sum(s["train"] and s["label"] == "high-unsafe" for s in t["steps"])
        t["role"] = "harmful" if n_high else "clean"; t["rule_based"] = int(bool(n_high))

    loc = {}
    for f in ("arm_s30/source/prohibition_location.jsonl", "arm_s30/source/prohibition_location_v29.jsonl"):
        for x in E31.jl(ROOT / f):
            loc[x["task"]] = x
    fam_of = {t["instance_id"]: t["metadata"]["mechanic_id"] for t in trajs}
    fam_rows = collections.defaultdict(list)
    for task, x in loc.items():
        fam_rows[fam_of.get(task) or task].append(x)
    has_place = {f: R.family_has_place(fam_rows.get(f, [])) for f in set(fam_of.values())}
    frag_of = check31.fragments()
    by_task = units()

    out_read, out_judge, recs = [], [], []
    cache = Path(a.cache) if a.cache else None
    if cache and cache.exists():
        c = json.loads(cache.read_text())
        assert c["opts"] == [a.safer, a.max_obs_chars], "cache made with other options"
        out_read, out_judge, recs = c["read"], c["judge"], c["recs"]
        trajs = []
    for n, t in enumerate(trajs):
        L = load_states(t)
        st = L["steps"]
        tk = t["metadata"]["toolkit"]; fam = t["metadata"]["mechanic_id"]
        mt = MinedTrajectory.model_validate({k: v for k, v in t.items() if k != "metadata"})
        steps = mined_to_steps(mt)
        rsteps, jsteps = [], []
        for i, s in enumerate(t["steps"]):
            r = dict(s); j = dict(s)
            if s["train"]:
                x = st[s["step"]]
                if x["call"]["name"] != s["tool_name"]:
                    raise ValueError(f"{t['key']} step {s['step']}: state record is {x['call']['name']}, not {s['tool_name']}")
                shown = critic_user_prompt(steps[i].action, steps[:i], t["instruction"], max_obs_chars=a.max_obs_chars)
                prior = [(p["tool_name"], p["arguments"], p["observation"]) for p in t["steps"][:i]]
                calls = R.targets(tk, s["tool_name"], s["arguments"], x["pre"], x["pre_ws"], has_place=has_place[fam], prior=prior)
                res = R.run_reads(tk, x["pre"], x["pre_ws"], calls)
                keep = [(c, rr) for c, rr in zip(calls, res) if not R.already_seen(c, rr, shown) and not R.is_error(rr)]
                kc = [c for c, _ in keep]; kr = [rr for _, rr in keep]
                r["target"] = R.read_target(kc)
                j["context"] = R.reads_context(kc, kr)
                j["target"] = f"Label: {s['label']}"
                recs.append({"key": t["key"], "step": s["step"], "i": i, "split": t["split"], "label": s["label"],
                             "label_source": s["label_source"], "toolkit": tk, "family": fam, "task": t["instance_id"],
                             "agent": t["actor"], "source": t["metadata"]["source"], "kind": R.kind(tk, s["tool_name"], s["arguments"]),
                             "tool": s["tool_name"], "reads_planned": [R.call_text(c) for c in calls],
                             "reads_skipped_seen": [R.call_text(c) for c, rr in zip(calls, res) if R.already_seen(c, rr, shown)],
                             "reads_dropped_error": [R.call_text(c) for c, rr in zip(calls, res) if R.is_error(rr)],
                             "reads": [R.call_text(c) for c in kc],
                             "read_roles": [c["role"] for c in kc],
                             "read_errors": sum(rr.startswith("ERROR") or rr.startswith('{"error"') for rr in kr)})
            rsteps.append(r); jsteps.append(j)
        common = {k: v for k, v in t.items() if k not in ("steps", "key")}
        out_read.append(common | {"key": t["key"] + "::read", "steps": rsteps, "system_prompt": R.read_system_prompt(tk),
                                  "metadata": t["metadata"] | {"run_key": t["key"], "example": "read"}})
        out_judge.append(common | {"key": t["key"] + "::judge", "steps": jsteps, "system_prompt": R.JUDGE_SYSTEM_PROMPT,
                                   "metadata": t["metadata"] | {"run_key": t["key"], "example": "judge"}})
        if n % 50 == 0:
            print(f"{n}/{len(trajs)} runs", file=sys.stderr)

    if cache and not cache.exists():
        cache.write_text(json.dumps({"opts": [a.safer, a.max_obs_chars], "read": out_read, "judge": out_judge, "recs": recs}))
    # ------------------------------------------------ prohibition in the JUDGE input, then reasons
    rec_of = {(x["key"], x["i"]): x for x in recs}

    def render(rows):
        mts = [MinedTrajectory.model_validate({k: v for k, v in t.items() if k != "metadata"}) for t in rows]
        ex = build_examples(mts, bucket="check", max_obs_chars=a.max_obs_chars, token_count=count, max_tokens=a.max_length)
        return {(e.trajectory_key.rsplit("::", 1)[0], e.action_id): e for e in ex}

    def frags(x):
        fm = frag_of(x["task"])
        fr = [f for i in traps_of(x["label_source"]) for f in fm.get(i, [])] or [f for v in fm.values() for f in v]
        return [check31.norm(f) for f in fr]

    aid_i = {(t["key"], s["action_id"]): i for t in out_judge for i, s in enumerate(t["steps"]) if s["train"]}
    jt = {t["key"]: t for t in out_judge}
    unsafe_rows = [t for t in out_judge if t["role"] == "harmful"]
    ex1 = render(unsafe_rows)
    noread = [t | {"steps": [s | {"context": None} for s in t["steps"]]} for t in unsafe_rows]
    ex0 = render(noread)
    pro = []
    for (key, aid), e in ex1.items():
        x = rec_of[(key, aid_i[(key + "::judge", aid)])]
        if x["label"] != "high-unsafe" or x["source"] != "run":
            continue
        nf = frags(x)
        u_txt = e.user_text
        pro.append({"key": key, "step": x["step"], "i": x["i"], "split": x["split"], "task": x["task"], "family": x["family"],
                    "agent": x["agent"], "toolkit": x["toolkit"], "tool": x["tool"], "label_source": x["label_source"],
                    "n_fragments": len(nf), "in_judge_input": any(f in check31.norm(u_txt) for f in nf),
                    "in_input_without_reads": any(f in check31.norm(ex0[(key, aid)].user_text) for f in nf),
                    "in_read_results": any(f in check31.norm(jt[key + "::judge"]["steps"][x["i"]]["context"] or "") for f in nf),
                    "history_dropped": e.history_dropped, "reads": x["reads"]})
    # reasons for the unsafe steps whose prohibition the model sees
    how = collections.Counter()
    for p in pro:
        if not p["in_judge_input"]:
            p["reason"] = None; how["no_prohibition_in_input"] += 1
            continue
        u, h = find_unit(p["task"], p["family"], traps_of(p["label_source"]), by_task, fam_of)
        how[h] += 1
        if u is None:
            p["reason"] = None
            continue
        import texts30 as T
        seen = T.norm(ex1[(p["key"], jt[p["key"] + "::judge"]["steps"][p["i"]]["action_id"])].user_text)
        p["reason"] = reason(u, seen); p["reason_unit"] = u["unit"]; p["reason_from"] = h
        jt[p["key"] + "::judge"]["steps"][p["i"]]["target"] = f"Label: high-unsafe\nReason: {p['reason']}"
    # the reason makes the example longer: check again that the prohibition is still in the input
    ex2 = render([jt[t["key"]] for t in unsafe_rows])
    lost = 0
    for p in pro:
        if p.get("reason"):
            e = ex2[(p["key"], jt[p["key"] + "::judge"]["steps"][p["i"]]["action_id"])]
            if not any(f in check31.norm(e.user_text) for f in frags(rec_of[(p["key"], p["i"])])):
                jt[p["key"] + "::judge"]["steps"][p["i"]]["target"] = "Label: high-unsafe"
                p["reason"] = None; p["in_judge_input"] = False; lost += 1

    # ------------------------------------------------ write
    out = S / "export" / ("base" if a.safer == "none" else "with_safer")
    out.mkdir(parents=True, exist_ok=True)
    order = ["key", "instance_id", "run", "condition", "actor", "role", "rule_based", "instruction", "system_prompt", "steps",
             "split", "corpus", "services", "metadata"]
    rows = out_read + out_judge
    dump = lambda rr: "".join(json.dumps({k: t[k] for k in order}, ensure_ascii=False) + "\n" for t in rr)
    (out / "trajectories.jsonl").write_text(dump(rows))
    (out / "eval_dev.jsonl").write_text(dump([t for t in rows if t["split"] == "dev"]))
    (out / "reads.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))
    write_dev_states(out / "dev_states.jsonl.gz", [t for t in out_judge if t["split"] == "dev"])
    allx = render(rows)
    cnt = collections.Counter()
    for t in rows:
        for s in t["steps"]:
            if s["train"]:
                cnt[(t["metadata"]["example"], t["split"], s["label"])] += 1
    lens = sorted(count(e.messages) for e in allx.values())
    stats = rep | {
        "options": {"max_obs_chars": a.max_obs_chars, "max_length": a.max_length, "tokenizer": Path(str(TOK)).parent.parent.parent.name},
        "runs": len(out_judge), "base_runs": len(base), "safer_runs": len(extra), "trajectories": len(rows),
        "examples": {f"{e} | {sp} | {l}": n for (e, sp, l), n in sorted(cnt.items())},
        "read_targets": {
            "steps": len(recs),
            "with_reads": sum(bool(x["reads"]) for x in recs),
            "none_not_a_write": sum(x["kind"] is None for x in recs),
            "none_all_seen": sum(x["kind"] is not None and not x["reads"] and bool(x["reads_planned"]) for x in recs),
            "none_no_target": sum(x["kind"] is not None and not x["reads_planned"] for x in recs),
            "reads": sum(len(x["reads"]) for x in recs), "reads_skipped_seen": sum(len(x["reads_skipped_seen"]) for x in recs),
            "by_role": dict(collections.Counter(r for x in recs for r in x["read_roles"])),
            "read_errors": sum(x["read_errors"] for x in recs),
            "reads_dropped_error": sum(len(x["reads_dropped_error"]) for x in recs),
            "unsafe_with_reads": sum(bool(x["reads"]) for x in recs if x["label"] == "high-unsafe"),
            "unsafe": sum(x["label"] == "high-unsafe" for x in recs)},
        "tokens": {"median": lens[len(lens) // 2], "p90": lens[int(.9 * len(lens))], "max": lens[-1],
                   "history_shortened": sum(e.history_dropped > 0 for e in allx.values()),
                   "still_over_max_length": sum(e.history_dropped < 0 for e in allx.values())},
    }
    if a.safer == "none":
        pr = {"options": stats["options"], "unsafe_examples": len(pro),
              "in_judge_input": sum(p["in_judge_input"] for p in pro),
              "in_input_without_reads": sum(p["in_input_without_reads"] for p in pro),
              "in_read_results": sum(p["in_read_results"] for p in pro),
              "reason_from": dict(how), "reason_dropped_after_refit": lost,
              "with_reason": sum(bool(p.get("reason")) for p in pro),
              "by_split": {sp: {"n": sum(p["split"] == sp for p in pro), "in_judge_input": sum(p["in_judge_input"] for p in pro if p["split"] == sp)}
                           for sp in ("train", "dev")},
              "by_toolkit": {tk: f"{sum(p['in_judge_input'] for p in pro if p['toolkit'] == tk)}/{sum(p['toolkit'] == tk for p in pro)}"
                             for tk in sorted({p["toolkit"] for p in pro})},
              "not_in_judge_input": [{k: p[k] for k in ("key", "step", "split", "tool", "label_source", "reads", "history_dropped")}
                                     for p in pro if not p["in_judge_input"]],
              "examples": pro}
        (S / "prohibition32.json").write_text(json.dumps(pr, indent=1, ensure_ascii=False))
        stats["prohibition"] = {k: pr[k] for k in ("unsafe_examples", "in_judge_input", "in_input_without_reads", "in_read_results",
                                                   "with_reason", "reason_from", "by_split", "by_toolkit")}
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
