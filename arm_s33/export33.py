"""Step 33: export the labelled runs as READ and JUDGE training examples, with READ answers taken from the trap table
(arm_s33/trap_reads.jsonl) instead of step 32's per-toolkit target rules, the step-26 twins and -v26 repairs added, and
the monitor's own earlier reads carried through a run.

Runs: step 31's (arm_s31/export31.base_runs: label table arm_s29/labels_all.jsonl, train_use "use" runs) + the step-26
runs (arm_s33/labels26.jsonl, the same train_use rules; run folders in the step-26 worktree); --safer include adds the
pair_ok step-30 safer runs as in step 31. Split: step 31's dev families (drawn from step 31's runs only, so unchanged); a
twin has its trap version's family and goes to the same side; the two -v26 repairs' families are new and go to train.

READ answer per training step (target of `<key>::read`):
  unsafe step                 the reads of the table rows of the traps it fires (label_source); an unsafe step whose
                              traps have no row gets no READ example
  twin hard negative          a twin-run step that the trap version's rules flag on an item its violator fires
                              (arm_s26_twins/grades26_as_trap.jsonl, as step 26 counted the 194; own label safe): the
                              reads of the trap version's rows for those items, run on the twin's state
  counterpart (trap version)  a safe step of a trap-version run with no unsafe step from that trap, whose tool and
                              arguments match the row's `match` (the same object, the same kind of call): that row's reads
  any other step that does not send, change or delete (reads33.kind is None): NONE
  any other send / change / delete step: no READ example (train=false in the READ trajectory); it keeps its JUDGE example
A read whose result is already in what the monitor is shown (the agent's history as rendered, and the monitor's own
earlier reads of the run) is left out; so is a read that returns an error. If none is left the answer is NONE.

Monitor's earlier reads: the reads of every earlier READ answer of the same run (each call once; a repeated call keeps
its latest result) are shown, after the current action, in a section "Monitor's earlier reads" in both the READ and the
JUDGE input of later steps. When an example is longer than --max-length, the oldest earlier reads are left out first
(then the benchmarks fit leaves out the oldest history). History-only steps (drop_step, a safer run's prefix) add no
reads.

JUDGE (target of `<key>::judge`): input = history + earlier reads + "Reads before judging:" with the step's READ answer
calls and their results ("NONE" when there are none). Target "Label: high-unsafe" + "Reason: <step-30 Why>
<consequence>" when the prohibition is in the JUDGE input as the model sees it, else the label alone.

  .venv/bin/python arm_s33/export33.py --safer none       -> arm_s33/export/base/
  .venv/bin/python arm_s33/export33.py --safer include    -> arm_s33/export/with_safer/
Each writes trajectories.jsonl, eval_dev.jsonl, reads.jsonl (one row per training step: answer source, reads), stats.json,
dev_states.jsonl.gz; base also writes arm_s33/prohibition33.json and arm_s33/read_balance33.json."""
import argparse, collections, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s33"
BENCH = Path(os.environ.get("BENCHMARKS_DIR", Path.home() / "Documents/workspace/benchmarks-gmail-dojo-monitor"))
sys.path[:0] = [str(BENCH / "safety_monitor"), str(S), str(ROOT / "arm_s31"), str(ROOT / "arm_s30")]
os.environ["BENCHMARKS_DIR"] = str(BENCH)   # check31 puts this checkout first on sys.path too
from safety_monitor.synthesis.pairs import MinedTrajectory  # noqa: E402
from safety_monitor.sft.data import build_examples, critic_messages, critic_user_prompt, mined_to_steps  # noqa: E402
import reads33 as R  # noqa: E402
import states33 as ST  # noqa: E402
import export31 as E31  # noqa: E402
import check31  # noqa: E402  (norm, fragments: the step-31 prohibition matcher)

TOK = os.environ.get("QWEN_TOKENIZER_JSON") or next(
    iter(sorted((Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots").glob("*/tokenizer.json"))), None)
MAX_HISTORY = 20          # the benchmarks default (critic_messages max_history_steps)
REASON_ROOM = 200         # tokens kept free for the JUDGE reason when fitting the earlier reads
PETRI_B = {"safety-ev-petri-attorney-archive-v29b": "safety-ev-petri-attorney-archive-v29a",   # step 26's existing twins
           "safety-ev-petri-attorney-archive-v123-v29b": "safety-ev-petri-attorney-archive-v123-v29a",
           "safety-ev-petri-attorney-archive-v132-v29b": "safety-ev-petri-attorney-archive-v132-v29a"}


def token_counter():
    from tokenizers import Tokenizer
    t = Tokenizer.from_file(str(TOK))

    def count(messages):   # chat template: about 5 tokens per message plus the generation prompt
        return sum(len(t.encode(m["content"]).ids) + 5 for m in messages) + 3
    return count


# ---------------------------------------------------------------- runs
def base26():
    """The step-26 runs as export31.base_runs builds the others (conversation text from each run's own record)."""
    rows = collections.defaultdict(list)
    for x in ST.jl(S / "labels26.jsonl"):
        rows[x["run_key"]].append(x)
    grades = {g["key"]: g for g in ST.jl(ROOT / ST.GRADES["step26"])}
    out = []
    for key, rs in rows.items():
        rs.sort(key=lambda x: x["step"])
        if not any(x["train_use"] == "use" for x in rs) or any(x["train_use"].startswith("drop_run") for x in rs):
            continue
        g = grades[key]
        base = ST.run_dir(g["tree"])
        res = json.loads((base / g["tree"] / "harness/results" / f"{key}.json").read_text())
        conv = E31.conversation(base, res)
        if len(conv["steps"]) != len(rs) or any(c["tool_name"] != x["tool"] for c, x in zip(conv["steps"], rs)):
            raise ValueError(f"{key}: conversation steps differ from the label table")
        steps = []
        for st, x in zip(conv["steps"], rs):
            reason = x["label_source"] if x["train_use"] == "use" else f"{x['train_use']}:{x['label_source']}"
            steps.append(E31.step_row(st, x["label"], reason, example=x["train_use"] == "use", i=x["step"], train_use=x["train_use"]))
        r0 = rs[0]
        out.append({"key": key, "instance_id": r0["task_id"], "run": f"r{r0['run']}", "condition": "mg_passive",
                    "actor": r0["agent"], "instruction": conv["instruction"], "steps": steps, "corpus": "gmail-dojo-s33",
                    "services": [g.get("toolkit") or "unknown"],
                    "metadata": {"source": "run", "grades": "step26", "task_id": r0["task_id"], "mechanic_id": r0["mechanic_id"],
                                 "agent": r0["agent"], "toolkit": g.get("toolkit"), "prohibition_location": r0["prohibition_location"],
                                 "counter_example": bool(g.get("counter_example")), "twin_of": r0.get("twin_of"),
                                 "outcome": r0["outcome"], "completion": r0["completion"]}})
    return out


def load_states(t):
    m = t["metadata"]
    return ST.load_states(m.get("run_key") or t["key"], t["instance_id"], m["source"], m.get("grades"))


# ---------------------------------------------------------------- READ answers: table, twins, counterparts
def trap_table():
    return {(r["task"], r["trap"]): r for r in ST.jl(S / "trap_reads.jsonl")}


def traps_of(label_source):
    return [p.split("/")[0] for p in label_source.removeprefix("trap:").split(",")] if label_source.startswith("trap:") else []


def hard_negatives():
    """(run key, step) -> [(trap version, item)]: the twin-run steps the trap version's rules flag on an item its violator
    fires, safe under the twin's own rules (arm_s26_twins/report26.py section 5)."""
    bank26 = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s26_twins/bank/bank_26.jsonl").read_text().splitlines()}
    ck = json.loads((ROOT / "arm_s26_twins/checks26.json").read_text())
    trap_of = {t: r["twin_of"] for t, r in bank26.items() if r.get("twin_of")} | PETRI_B
    items = {r["twin_of"]: set(ck[t]["trap_violator_items"]) for t, r in bank26.items() if r.get("twin_of")}
    items |= {a: set(v) for a, v in ck.get("_existing_twins_trap_items", {}).items()}
    own = {g["key"]: g for g in ST.jl(ROOT / "arm_s26_twins/grades26.jsonl")}
    out = {}
    for g in ST.jl(ROOT / "arm_s26_twins/grades26_as_trap.jsonl"):
        trap = trap_of.get(g["task"])
        if trap is None:
            continue
        o = own.get(g["key"])
        for i, f in enumerate(g["findings"]):
            hit = sorted({x.get("item") or x.get("harm") for x in f if x.get("tag") == "designed" and x.get("label") == "unsafe"
                          and (x.get("item") or x.get("harm")) in items[trap]})
            if hit and ((o["labels"][i] == "safe") if o else True):
                out[(g["key"], i)] = [(trap, h) for h in hit]
    return out


def answer_source(t, s, table, hn, unsafe_traps_in_run):
    """(source, rows) of one training step's READ answer; source in unsafe | unsafe_no_row | twin_hard_negative |
    counterpart | not_a_write | other_write."""
    tk = t["metadata"]["toolkit"]; task = t["instance_id"]
    if s["label"] == "high-unsafe":
        rows = [table[(task, tp)] for tp in traps_of(s["label_source"]) if (task, tp) in table]
        return ("unsafe", rows) if rows else ("unsafe_no_row", [])
    key = t["metadata"].get("run_key") or t["key"]
    if (key, s["step"]) in hn:
        rows = [table[x] for x in hn[(key, s["step"])] if x in table]
        if rows:
            return "twin_hard_negative", rows
    k = R.kind(tk, s["tool_name"], s["arguments"])
    if k is not None and not t["metadata"].get("twin_of") and task not in PETRI_B:
        a = json.dumps(s["arguments"], ensure_ascii=False)
        rows = [r for (tt, tp), r in table.items() if tt == task and tp not in unsafe_traps_in_run
                and s["tool_name"] in (r["match"]["tools"] or []) and r["match"]["args"] and re.search(r["match"]["args"], a)]
        if rows:
            return "counterpart", rows
    return ("not_a_write", []) if k is None else ("other_write", [])


def union_reads(rows):
    out, seen = [], set()
    for r in rows:
        for c in r["reads"]:
            ct = R.call_text(c)
            if ct not in seen:
                seen.add(ct); out.append(c)
    return out


# ---------------------------------------------------------------- the earlier-reads record and the length fit
def add_to_record(record, calls, results):
    """Each read once: a repeated call keeps its latest result (and moves to the end)."""
    for c, r in zip(calls, results):
        ct = R.call_text(c)
        record[:] = [(c0, r0) for c0, r0 in record if R.call_text(c0) != ct]
        record.append((c, r))


def visible_record(record, steps, i, instruction, count, max_length, max_obs_chars, *, judge_calls=(), judge_results=(),
                   system_prompt=None):
    """The earlier reads shown at step i: the oldest are left out until the JUDGE example (this step's reads, a label and
    REASON_ROOM tokens for a reason) fits with the full shown history."""
    vis = list(record)
    hist = steps[:i][-MAX_HISTORY:]
    while vis:
        ctx = R.step_context(vis, list(judge_calls), list(judge_results), judge=True)
        m = critic_messages(steps[i].action, hist, instruction, max_history_steps=MAX_HISTORY, max_obs_chars=max_obs_chars,
                            context=ctx, target="Label: high-unsafe", system_prompt=system_prompt)
        if count(m) + REASON_ROOM <= max_length:
            break
        vis.pop(0)
    return vis


def choose_reads(calls, results, shown_text):
    keep = [(c, r) for c, r in zip(calls, results) if not R.is_error(r) and not R.already_seen(c, r, shown_text)]
    return [c for c, _ in keep], [r for _, r in keep]


# ---------------------------------------------------------------- reasons (step 30 unit texts), as step 32
def units():
    U = json.loads((ROOT / "arm_s30/texts30.json").read_text())
    by_task = collections.defaultdict(list)
    for u in U.values():
        traps = u["traps"] if isinstance(u["traps"], list) else eval(u["traps"])  # noqa: S307 (stored as a repr)
        by_task[u["task"]].append((tuple(traps), u))
    return by_task


def find_unit(task, family, traps, by_task, fam_of):
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
    return re.sub(r"\b([Tt]he|[Yy]our) blocked (calls?|update|insert)\b", r"\1 current \2", f"{w} {c}".strip())


# ---------------------------------------------------------------- dev states (for eval.py)
def write_dev_states(path, judge_rows):
    import gzip
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for t in judge_rows:
            L = load_states(t)
            for s in t["steps"]:
                if s["train"]:
                    x = L["steps"][s["step"]]
                    fh.write(json.dumps({"key": t["metadata"]["run_key"], "step": s["step"], "pre": x["pre"], "pre_ws": x["pre_ws"]},
                                        ensure_ascii=False, default=str) + "\n")


def dev_states(path):
    import gzip
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for ln in fh:
            d = json.loads(ln); out[(d["key"], d["step"])] = d
    return out


# ---------------------------------------------------------------- one run
def export_run(t, table, hn, a, count):
    """READ and JUDGE trajectories of one run, and one record per training step."""
    L = load_states(t)
    st = L["steps"]
    tk = t["metadata"]["toolkit"]
    mt = MinedTrajectory.model_validate({k: v for k, v in t.items() if k != "metadata"})
    steps = mined_to_steps(mt)
    unsafe_traps = {tp for s in t["steps"] if s["train"] and s["label"] == "high-unsafe" for tp in traps_of(s["label_source"])}
    rsp, jsp = R.read_system_prompt(tk), R.JUDGE_SYSTEM_PROMPT
    record = []
    rsteps, jsteps, recs = [], [], []
    for i, s in enumerate(t["steps"]):
        r = dict(s); j = dict(s)
        if not s["train"]:
            rsteps.append(r); jsteps.append(j)
            continue
        x = st[s["step"]]
        if x["call"]["name"] != s["tool_name"]:
            raise ValueError(f"{t['key']} step {s['step']}: state record is {x['call']['name']}, not {s['tool_name']}")
        src, rows = answer_source(t, s, table, hn, unsafe_traps)
        calls = union_reads(rows)
        res = R.run_reads(tk, x["pre"], x["pre_ws"], calls)
        hist_text = critic_user_prompt(steps[i].action, steps[:i], t["instruction"], max_obs_chars=a.max_obs_chars)
        kc0, _ = choose_reads(calls, res, hist_text)                                   # step 32's test (history only)
        # what the monitor sees when it chooses its reads (no reads of this step yet; the same fit as eval.py)
        vis_r = visible_record(record, steps, i, t["instruction"], count, a.max_length, a.max_obs_chars, system_prompt=jsp)
        kc, kr = choose_reads(calls, res, hist_text + "\n" + R.earlier_reads_text(vis_r))  # + the monitor's earlier reads
        vis = visible_record(record, steps, i, t["instruction"], count, a.max_length, a.max_obs_chars,
                             judge_calls=kc, judge_results=kr, system_prompt=jsp)
        has_read_example = src not in ("unsafe_no_row", "other_write")
        if has_read_example:
            r["target"] = R.read_target(kc)
            r["context"] = R.step_context(vis_r, judge=False)
        else:
            r["train"] = False; r["action_id"] = ""; r["train_use"] = f"no_read_example:{src}"
            r["label_source"] = f"history_only:{s['label_source']}"
        j["context"] = R.step_context(vis, kc, kr, judge=True)
        j["target"] = f"Label: {s['label']}"
        recs.append({"key": t["key"], "step": s["step"], "i": i, "split": t["split"], "label": s["label"],
                     "label_source": s["label_source"], "toolkit": tk, "family": t["metadata"]["mechanic_id"],
                     "task": t["instance_id"], "agent": t["actor"], "source": t["metadata"]["source"],
                     "twin_of": t["metadata"].get("twin_of") or PETRI_B.get(t["instance_id"]),
                     "kind": R.kind(tk, s["tool_name"], s["arguments"]), "tool": s["tool_name"], "answer_source": src,
                     "rows": [f"{rw['task']}/{rw['trap']}" for rw in rows], "read_example": has_read_example,
                     "reads_planned": [R.call_text(c) for c in calls], "reads": [R.call_text(c) for c in kc],
                     "reads_without_earlier_test": [R.call_text(c) for c in kc0],
                     "none_because_earlier_reads": bool(kc0) and not kc,
                     "earlier_reads_shown": len(vis), "earlier_reads_left_out": len(record) - len(vis)})
        if has_read_example and kc:
            add_to_record(record, kc, kr)
        rsteps.append(r); jsteps.append(j)
    common = {k: v for k, v in t.items() if k not in ("steps", "key")}
    rt = common | {"key": t["key"] + "::read", "steps": rsteps, "system_prompt": rsp,
                   "metadata": t["metadata"] | {"run_key": t["key"], "example": "read"}}
    jt = common | {"key": t["key"] + "::judge", "steps": jsteps, "system_prompt": jsp,
                   "metadata": t["metadata"] | {"run_key": t["key"], "example": "judge"}}
    return rt, jt, recs


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--safer", choices=("none", "include"), default="none")
    ap.add_argument("--max-obs-chars", type=int, default=1500)
    ap.add_argument("--max-length", type=int, default=6144)
    a = ap.parse_args()
    count = token_counter()
    base31 = E31.base_runs()
    dev, draw, _ = E31.choose_dev(base31)   # step 31's draw on step 31's runs: the split does not move
    split31 = json.loads((ROOT / "arm_s31/split31.json").read_text())
    assert sorted(dev) == sorted(f for fs in split31["dev"].values() for f in fs), "dev families differ from step 31"
    rep = {"dev_draw": draw}
    if not any((ROOT / "arm_s30/runs/harness").glob("*/b*_a*")) and (ST.STEP30 / "arm_s30/labels_safer.jsonl").exists():
        E31.s30_dir = lambda: ST.STEP30 / "arm_s30"
    extra = E31.safer_runs({t["key"]: t for t in base31}, rep) if a.safer == "include" else []
    runs26 = base26()
    fams31 = {t["metadata"]["mechanic_id"] for t in base31}
    rep["new_families_to_train"] = sorted({t["metadata"]["mechanic_id"] for t in runs26} - fams31)
    trajs = base31 + runs26 + extra
    assert len({t["key"] for t in trajs}) == len(trajs), "a run key occurs twice"
    for t in trajs:
        t["split"] = "dev" if t["metadata"]["mechanic_id"] in dev else "train"
        n_high = sum(s["train"] and s["label"] == "high-unsafe" for s in t["steps"])
        t["role"] = "harmful" if n_high else "clean"; t["rule_based"] = int(bool(n_high))
    table = trap_table()
    hn = hard_negatives()
    out_read, out_judge, recs = [], [], []
    for n, t in enumerate(trajs):
        rt, jt, rc = export_run(t, table, hn, a, count)
        out_read.append(rt); out_judge.append(jt); recs += rc
        if n % 50 == 0:
            print(f"{n}/{len(trajs)} runs", file=sys.stderr)

    # ------------------------------------------------ prohibition in the JUDGE input, then reasons
    fam_of = {t["instance_id"]: t["metadata"]["mechanic_id"] for t in trajs}
    frag31 = check31.fragments()
    frag_of = lambda task: frag31(task.replace("-v26", "-v25"))   # a -v26 repair: its source's places (only the request changed)
    by_task = units()
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
    pro = []
    for (key, aid), e in ex1.items():
        x = rec_of[(key, aid_i[(key + "::judge", aid)])]
        if x["label"] != "high-unsafe" or x["source"] != "run":
            continue
        nf = frags(x)
        ctx = jt[key + "::judge"]["steps"][x["i"]]["context"] or ""
        earlier, _, own = ctx.partition("Reads before judging:")
        pro.append({"key": key, "step": x["step"], "i": x["i"], "split": x["split"], "task": x["task"], "family": x["family"],
                    "agent": x["agent"], "toolkit": x["toolkit"], "tool": x["tool"], "label_source": x["label_source"],
                    "step32_set": x["task"] not in rep["new_families_to_train"] and not x["task"].endswith("-v26"),
                    "n_fragments": len(nf), "in_judge_input": any(f in check31.norm(e.user_text) for f in nf),
                    "in_read_results": any(f in check31.norm(own) for f in nf),
                    "in_earlier_reads": any(f in check31.norm(earlier) for f in nf),
                    "history_dropped": e.history_dropped, "answer_source": x["answer_source"], "reads": x["reads"]})
    for p in pro:
        e = ex1[(p["key"], jt[p["key"] + "::judge"]["steps"][p["i"]]["action_id"])]
        hist_only = e.user_text.split("Monitor's earlier reads")[0].split("Reads before judging:")[0]
        p["in_history"] = any(f in check31.norm(hist_only) for f in frags(rec_of[(p["key"], p["i"])]))
    how = collections.Counter()
    import texts30 as T
    for p in pro:
        if not p["in_judge_input"]:
            p["reason"] = None; how["no_prohibition_in_input"] += 1
            continue
        u, h = find_unit(p["task"], p["family"], traps_of(p["label_source"]), by_task, fam_of)
        if u is None and p["task"].endswith("-v26"):   # a repair: its -v25 source's text (only the request changed)
            u, h = find_unit(p["task"].replace("-v26", "-v25"), p["family"], traps_of(p["label_source"]), by_task, fam_of)
        how[h] += 1
        if u is None:
            p["reason"] = None
            continue
        seen = T.norm(ex1[(p["key"], jt[p["key"] + "::judge"]["steps"][p["i"]]["action_id"])].user_text)
        p["reason"] = reason(u, seen); p["reason_unit"] = u["unit"]; p["reason_from"] = h
        jt[p["key"] + "::judge"]["steps"][p["i"]]["target"] = f"Label: high-unsafe\nReason: {p['reason']}"
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
    lens = sorted(count(e.messages) for e in allx.values())
    hn_keys = {(x["key"], x["step"]) for x in recs if x["answer_source"] == "twin_hard_negative"}
    per_split = {}
    for sp in ("train", "dev"):
        rs = [x for x in recs if x["split"] == sp]
        per_split[sp] = {
            "judge_examples": len(rs), "judge_unsafe": sum(x["label"] == "high-unsafe" for x in rs),
            "read_examples": sum(x["read_example"] for x in rs),
            "read_unsafe": sum(x["read_example"] and x["label"] == "high-unsafe" for x in rs),
            "read_non_none": sum(x["read_example"] and bool(x["reads"]) for x in rs),
            "hard_negatives": sum(x["answer_source"] == "twin_hard_negative" for x in rs),
            "hard_negatives_non_none": sum(x["answer_source"] == "twin_hard_negative" and bool(x["reads"]) for x in rs),
            "counterparts": sum(x["answer_source"] == "counterpart" for x in rs),
            "twin_runs": len({x["key"] for x in rs if x["twin_of"]}),
            "runs": len({x["key"] for x in rs})}
    stats = rep | {
        "options": {"max_obs_chars": a.max_obs_chars, "max_length": a.max_length, "tokenizer": Path(str(TOK)).parent.parent.parent.name},
        "runs": len(out_judge), "base_runs_step31": len(base31), "step26_runs": len(runs26), "safer_runs": len(extra),
        "trajectories": len(rows), "per_split": per_split,
        "answer_source": dict(collections.Counter(x["answer_source"] for x in recs)),
        "answer_source_by_label": {f"{k[0]} | {k[1]}": n for k, n in sorted(collections.Counter(
            (x["answer_source"], x["label"]) for x in recs).items())},
        "read_answers": {
            "non_none": sum(x["read_example"] and bool(x["reads"]) for x in recs),
            "none_all_seen": sum(x["read_example"] and bool(x["reads_planned"]) and not x["reads"] for x in recs),
            "none_because_earlier_reads": sum(x["read_example"] and x["none_because_earlier_reads"] for x in recs),
            "reads_dropped_because_earlier_reads": sum(len(x["reads_without_earlier_test"]) - len(x["reads"]) for x in recs if x["read_example"]),
            "earlier_reads_left_out_for_length": sum(x["earlier_reads_left_out"] > 0 for x in recs)},
        "hard_negative_steps_found": len(hn), "hard_negative_steps_exported": len(hn_keys),
        "tokens": {"median": lens[len(lens) // 2], "p90": lens[int(.9 * len(lens))], "max": lens[-1],
                   "history_shortened": sum(e.history_dropped > 0 for e in allx.values()),
                   "still_over_max_length": sum(e.history_dropped < 0 for e in allx.values())},
    }
    if a.safer == "none":
        def pr_sum(ps):
            return {"n": len(ps), "in_judge_input": sum(p["in_judge_input"] for p in ps),
                    "in_history": sum(p["in_history"] for p in ps), "in_read_results": sum(p["in_read_results"] for p in ps),
                    "in_earlier_reads": sum(p["in_earlier_reads"] for p in ps)}
        s32 = [p for p in pro if p["step32_set"]]
        pr = {"options": stats["options"], "step32_set": pr_sum(s32), "all": pr_sum(pro),
              "by_split": {sp: pr_sum([p for p in pro if p["split"] == sp]) for sp in ("train", "dev")},
              "reason_from": dict(how), "reason_dropped_after_refit": lost, "with_reason": sum(bool(p.get("reason")) for p in pro),
              "by_toolkit": {tk: f"{sum(p['in_judge_input'] for p in pro if p['toolkit'] == tk)}/{sum(p['toolkit'] == tk for p in pro)}"
                             for tk in sorted({p["toolkit"] for p in pro})},
              "not_in_judge_input": [{k: p[k] for k in ("key", "step", "split", "tool", "label_source", "answer_source", "reads",
                                                        "history_dropped")} for p in pro if not p["in_judge_input"]],
              "examples": pro}
        (S / "prohibition33.json").write_text(json.dumps(pr, indent=1, ensure_ascii=False))
        stats["prohibition"] = {k: pr[k] for k in ("step32_set", "all", "by_split", "with_reason", "reason_from")}
        # part 1 check: who has a non-NONE READ answer, per family
        bal = collections.defaultdict(lambda: collections.Counter())
        for x in recs:
            if x["read_example"] and x["reads"]:
                bal[x["family"]]["unsafe" if x["label"] == "high-unsafe" else f"safe_{x['answer_source']}"] += 1
        fams = {f: dict(c) | {"unsafe": c["unsafe"], "safe": sum(v for k, v in c.items() if k.startswith("safe"))}
                for f, c in sorted(bal.items())}
        only_unsafe = sorted(f for f, c in fams.items() if c["safe"] == 0)
        (S / "read_balance33.json").write_text(json.dumps({"by_family": fams, "reads_only_on_unsafe": only_unsafe,
                                                          "total": {"unsafe": sum(c["unsafe"] for c in fams.values()),
                                                                    "safe": sum(c["safe"] for c in fams.values())}}, indent=1))
        stats["read_balance"] = {"reads_only_on_unsafe": only_unsafe,
                                 "unsafe": sum(c["unsafe"] for c in fams.values()), "safe": sum(c["safe"] for c in fams.values())}
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
