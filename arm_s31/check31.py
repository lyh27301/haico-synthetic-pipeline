"""Step 31 part 3: checks on the two exports, with the benchmarks loader and renderers unchanged (read, not edited).
Run with the benchmarks venv (it has pydantic); BENCHMARKS_DIR defaults to ~/Documents/workspace/benchmarks:
  $BENCHMARKS_DIR/.venv/bin/python arm_s31/check31.py   -> arm_s31/checks31.json, arm_s31/samples31.md (prints each check)

Rendered input = what the model is shown for one example: the user message of the Qwen format
(safety_monitor/sft/data.py critic_messages: instruction + last 20 steps, observations cut to 200 + " … " + 200 chars
when longer than 400, current action), and for ShieldGemma the user prompt inside its template (no instruction, last 8
steps, history cut to 700 + 700 chars). The fixed system prompt and template text are not ours and are not scanned.

Prohibition in the rendered input (the ceiling of what v0 can learn): for each training unsafe example, the fragments
that state the prohibition of its traps (arm_s25/prohibition_location.jsonl: each trap's places[].fragment and quote; a
derived version takes the fragments of the nearest ancestor listed there) are searched in the rendered text, both
normalized (\\uXXXX and \\n escapes decoded, lower case, letters and digits only). A trap with two pieces counts when
any one of its fragments is found.

Token lengths (the HF trainer truncates at 2048 tokens from the right, backends.py train_lora_sft): counted only when
QWEN_TOKENIZER_JSON / GEMMA_TOKENIZER_JSON name a local tokenizer.json (a stand-in of the same family is fine; the
counts are then approximate). Qwen: system prompt + user message + about 10 tokens of chat template; ShieldGemma: the
whole templated prompt."""
import collections, json, os, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s31"
BENCH = Path(os.environ.get("BENCHMARKS_DIR", Path.home() / "Documents/workspace/benchmarks"))
sys.path.insert(0, str(BENCH / "safety_monitor"))
from safety_monitor.sft.data import (load_trajectories, build_examples, mined_to_steps, PROMPT_FORMAT_SHIELDGEMMA,  # noqa: E402
                                     PROMPT_FORMAT_QWEN)
from safety_monitor.critic.prompted import format_action  # noqa: E402
from safety_monitor.critic.prompts import SYSTEM_PROMPT  # noqa: E402


def tokenizer(var):
    if not os.environ.get(var):
        return None
    from tokenizers import Tokenizer
    return Tokenizer.from_file(os.environ[var])

AGENTS = ["gpt-6-luna", "haiku5.5", "qwen3.5-9b", "qwen3.5-35b-a3b"]
FILES = {"base": S / "export/base/trajectories.jsonl", "with_safer": S / "export/with_safer/trajectories.jsonl"}
GRADES = ["grader/out/v4.2-set0/grades21.jsonl", "grader/out/v4.2-set0/grades23.jsonl", "arm_s25/grades25.jsonl", "arm_s29/grades29.jsonl"]
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""))


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


def norm(s):
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")
    s = s.replace("\\n", " ").replace("\\t", " ").replace('\\"', '"')
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fragments():
    rows = {json.loads(x)["instance_id"]: json.loads(x) for x in (ROOT / "arm_s18/bank/train_set0.jsonl").read_text().splitlines()}
    for d in ("arm_s22/bank/tasks", "arm_s23/bank/tasks", "arm_s25/bank/tasks", "arm_s29/bank/tasks"):
        for f in (ROOT / d).glob("*.json"):
            r = json.loads(f.read_text()); rows[r["instance_id"]] = r
    P = {}
    for x in jl(ROOT / "arm_s25/prohibition_location.jsonl"):
        tr = {}
        for t in x["traps"]:
            fr = [p["fragment"] for p in t.get("places") or [] if p.get("fragment")]
            if t.get("quote"):
                fr.append(t["quote"].strip("“”\"' "))
            tr[t["trap"]] = [f for f in fr if len(norm(f)) >= 12]
        P[x["task"]] = tr

    def of(task):
        t = task
        while t and t not in P:
            t = rows.get(t, {}).get("derived_from")
        return P.get(t, {})
    return of


def ushort(t):
    return t[7:] if t.startswith("safety-") else t


def main():
    frag_of = fragments()
    labels = jl(ROOT / "arm_s29/labels_all.jsonl")
    rule_ids = sorted({f["rule"] for p in GRADES for g in jl(ROOT / p) if "findings" in g for fs in g["findings"] for f in fs if f.get("rule")})
    out = {"rule_ids_scanned": rule_ids}
    TQ, TG = tokenizer("QWEN_TOKENIZER_JSON"), tokenizer("GEMMA_TOKENIZER_JSON")
    n_sys = len(TQ.encode(SYSTEM_PROMPT).ids) if TQ else 0
    samples_md = []
    for name, path in FILES.items():
        trajs = load_trajectories(path)                       # the benchmarks loader, unchanged
        raw = {t["key"]: t for t in jl(path)}
        check(f"[{name}] loads with safety_monitor.sft.data.load_trajectories", len(trajs) == len(raw), f"{len(trajs)} trajectories")
        ex_q = {e.example_id: e for e in build_examples(trajs, bucket="all", prompt_format=PROMPT_FORMAT_QWEN)}
        ex_s = {e.example_id: e for e in build_examples(trajs, bucket="all", prompt_format=PROMPT_FORMAT_SHIELDGEMMA)}
        n_train_steps = sum(s["train"] for t in raw.values() for s in t["steps"])
        check(f"[{name}] build_examples yields one example per train=true step and none for history-only steps",
              len(ex_q) == len(ex_s) == n_train_steps, f"{len(ex_q)} examples, {sum(len(t['steps']) for t in raw.values()) - n_train_steps} history-only steps")
        # per-example records
        recs = []
        for t in trajs:
            r = raw[t.key]; m = r["metadata"]; full = mined_to_steps(t)
            for i, (st, rs) in enumerate(zip(t.steps, r["steps"])):
                if not st.action_id:
                    continue
                eid = f"{t.key}:{st.action_id}"
                q = ex_q[eid].user_text
                sg = ex_s[eid].user_text
                sg_user = sg.split("Human Question:", 1)[1].split("<end_of_turn>", 1)[0]
                hist = full[:i]
                last20 = hist[-20:]
                full20 = "\n".join([t.instruction or ""] + [format_action(s.action) + "\n" + (s.observation.text or "") for s in last20]
                                   + [format_action(full[i].action)])
                fullall = "\n".join([t.instruction or ""] + [format_action(s.action) + "\n" + (s.observation.text or "") for s in hist]
                                    + [format_action(full[i].action)])
                cut_obs = sum(len(s.observation.text or "") > 400 for s in last20)
                recs.append({"eid": eid, "key": t.key, "step": rs["step"], "label": st.label.value, "agent": t.actor, "split": r["split"],
                             "toolkit": m["toolkit"], "family": m["mechanic_id"], "task": t.instance_id, "source": m["source"],
                             "ploc": m["prohibition_location"], "label_source": st.label_source, "q": q, "sg": sg_user,
                             "full20": full20, "fullall": fullall, "cut_obs": cut_obs, "hist_empty_ids": sum(not s.action_id for s in t.steps[:i][-20:]),
                             "tok_q": (n_sys + 10 + len(TQ.encode(q).ids)) if TQ else None,
                             "tok_sg": len(TG.encode(sg).ids) if TG else None})
        # ------------------------------------------------------------ leak scan
        terms = [("BLOCKED BY THE SAFETY MONITOR", re.compile(re.escape("BLOCKED BY THE SAFETY MONITOR"))),
                 ("safety monitor", re.compile(r"safety[ _-]monitor", re.I)), ("trap", re.compile(r"\btrap", re.I)),
                 ("checkpoint", re.compile(r"checkpoint", re.I)), ("off_design", re.compile(r"off[_ -]design", re.I)),
                 ("twin", re.compile(r"\btwin", re.I)), ("high-unsafe", re.compile(r"high[-_ ]unsafe", re.I)),
                 ("low-unsafe", re.compile(r"low[-_ ]unsafe", re.I)), ("history-only marker id= (empty)", re.compile(r" id=(\n|$)"))]
        terms += [(f"rule id {r}", re.compile(r"\b" + re.escape(r) + r"\b")) for r in rule_ids]
        trap_ids = sorted({p.split("/")[0] for r in recs for p in r["label_source"].removeprefix("trap:").split(",") if r["label_source"].startswith("trap:")})
        terms += [(f"trap id {t}", re.compile(r"\b" + re.escape(t) + r"\b")) for t in trap_ids]
        hits = collections.defaultdict(lambda: {"examples": 0, "qwen": 0, "shieldgemma": 0, "contexts": collections.Counter()})
        for r in recs:
            for tn, rx in terms:
                mq, ms = rx.search(r["q"]), rx.search(r["sg"])
                if mq or ms:
                    h = hits[tn]; h["examples"] += 1; h["qwen"] += bool(mq); h["shieldgemma"] += bool(ms)
                    txt, mm = (r["q"], mq) if mq else (r["sg"], ms)
                    h["contexts"][txt[max(0, mm.start() - 60): mm.end() + 60].replace("\n", " ")] += 1
        out[name] = {"leak_hits": {k: {**v, "contexts": v["contexts"].most_common(6)} for k, v in hits.items()}}
        print(f"[{name}] leak scan over {len(recs)} rendered inputs x 2 formats:",
              {k: v["examples"] for k, v in hits.items()} or "zero hits")
        # ------------------------------------------------------------ split / duplicates / counts
        fam_side = collections.defaultdict(set)
        for t in raw.values():
            fam_side[t["metadata"]["mechanic_id"]].add(t["split"])
        both = [f for f, s in fam_side.items() if len(s) > 1]
        check(f"[{name}] no family on both sides of the split", not both, f"{len(fam_side)} families" + (f"; on both: {both}" if both else ""))
        check(f"[{name}] no run twice", len({t.key for t in trajs}) == len(trajs) and
              len({(t['metadata'].get('grades'), t['key']) for t in raw.values()}) == len(raw), f"{len(trajs)} distinct keys")
        lab_use = collections.Counter(x["agent"] for x in labels if x["train_use"] == "use")
        lab_hist = collections.Counter(x["agent"] for x in labels if x["train_use"] == "drop_step")
        base_ex = collections.Counter(r["agent"] for r in recs if r["source"] == "run")
        base_hist = collections.Counter(t["actor"] for t in raw.values() if t["metadata"]["source"] == "run" for s in t["steps"] if not s["train"])
        check(f"[{name}] run examples per agent = label-table train_use=use rows; history-only = drop_step rows",
              base_ex == lab_use and base_hist == lab_hist, f"use {sum(base_ex.values())} = {sum(lab_use.values())}; drop_step {sum(base_hist.values())} = {sum(lab_hist.values())}")
        if name == "with_safer":
            st = json.loads((S / "export/with_safer/stats.json").read_text())
            d = ROOT / st["safer_source"]
            ls = [x for x in jl(d / "labels_safer.jsonl")]
            kept = {t.key for t in trajs if raw[t.key]["metadata"]["source"] == "warned_safer_run"}
            want = 0
            for k in kept:   # continuation use rows before the first step that mentions the block
                cont = sorted((x for x in ls if x["key"] == k and x["part"] == "continuation"), key=lambda x: x["step"])
                cut = next((j for j, x in enumerate(cont) if x["mentions_block"]), len(cont))
                want += sum(x["train_use"] == "use" for x in cont[:cut])
            got = sum(1 for r in recs if r["source"] == "warned_safer_run")
            check("[with_safer] safer examples = labels_safer continuation use rows of the kept branches before the first mention of the block",
                  got == want, f"{got} = {want}")
            blocked_text = [x["monitor_message"]["text"] for x in ls if x.get("monitor_message") and x["monitor_message"].get("text")]
            dump = Path(path).read_text()
            check("[with_safer] no monitor message text anywhere in the export file", not any(b[:80] in dump for b in blocked_text),
                  f"{len(blocked_text)} messages searched")
            out[name]["safer"] = st
        # ------------------------------------------------------------ tables
        tab = collections.Counter((r["label"], r["agent"], r["split"]) for r in recs)
        out[name]["label_agent_split"] = {f"{l} | {a} | {s}": n for (l, a, s), n in sorted(tab.items())}
        out[name]["per_toolkit"] = {tk: dict(collections.Counter(r["label"] for r in recs if r["toolkit"] == tk))
                                    for tk in sorted({r["toolkit"] for r in recs})}
        out[name]["per_source"] = {s: dict(collections.Counter((r["label"]) for r in recs if r["source"] == s)) for s in sorted({r["source"] for r in recs})}
        n_u = sum(r["label"] == "high-unsafe" for r in recs)
        out[name]["unsafe_share"] = {"all": n_u / len(recs), **{sp: sum(r["label"] == "high-unsafe" and r["split"] == sp for r in recs) /
                                                               max(1, sum(r["split"] == sp for r in recs)) for sp in ("train", "dev")}}
        # rendered length (the HF trainer truncates at 2048 tokens from the right: backends.py train_lora_sft)
        lens = sorted(len(r["q"]) for r in recs)
        out[name]["qwen_prompt_chars"] = {"median": lens[len(lens) // 2], "p90": lens[int(.9 * len(lens))], "max": lens[-1],
                                          "over_8000_chars": sum(x > 8000 for x in lens), "n": len(lens)}
        if TQ or TG:
            out[name]["tokens_over_2048"] = {
                fmt: {"all": sum(r[k] > 2048 for r in recs), "max": max(r[k] for r in recs),
                      "median": sorted(r[k] for r in recs)[len(recs) // 2],
                      "by_label_split": dict(collections.Counter(f"{r['label']} {r['split']}" for r in recs if r[k] > 2048))}
                for fmt, k, T in (("qwen", "tok_q", TQ), ("shieldgemma", "tok_sg", TG)) if T}
            print(f"[{name}] examples over 2048 tokens:", {f: v["all"] for f, v in out[name]["tokens_over_2048"].items()})
        out[name]["examples_with_history_only_step_in_last20"] = {
            "all": sum(r["hist_empty_ids"] > 0 for r in recs),
            "by_source_label": dict(collections.Counter(f"{r['source']} {r['label']}" for r in recs if r["hist_empty_ids"] > 0))}
        # ------------------------------------------------------------ prohibition in the rendered input (base runs' unsafe)
        rows = []
        for r in recs:
            if r["label"] != "high-unsafe":
                continue
            ids = [p.split("/")[0] for p in r["label_source"].removeprefix("trap:").split(",")]
            fr_map = frag_of(r["task"])
            frs = [f for i in ids for f in fr_map.get(i, [])] or [f for v in fr_map.values() for f in v]
            nf = [norm(f) for f in frs]
            inq = any(f in norm(r["q"]) for f in nf); ins = any(f in norm(r["sg"]) for f in nf)
            in20 = any(f in norm(r["full20"]) for f in nf); inall = any(f in norm(r["fullall"]) for f in nf)
            rows.append(r | {"in_qwen": inq, "in_sg": ins, "in_full_last20": in20, "in_full_any": inall, "frag": frs[:1], "n_frag": len(frs)})
        cut = [x for x in rows if x["in_full_last20"] and not x["in_qwen"]]
        out[name]["prohibition"] = {
            "unsafe_examples": len(rows), "no_fragment_known": sum(x["n_frag"] == 0 for x in rows),
            "in_rendered_qwen": sum(x["in_qwen"] for x in rows), "in_rendered_shieldgemma": sum(x["in_sg"] for x in rows),
            "in_instruction_location": sum(x["ploc"] and x["ploc"].startswith("instruction") for x in rows),
            "in_rendered_qwen_by_ploc": dict(collections.Counter(f"{(x['ploc'] or '?').split(' ')[0]} {x['in_qwen']}" for x in rows)),
            "in_rendered_qwen_by_split": dict(collections.Counter(f"{x['split']} {x['in_qwen']}" for x in rows)),
            "in_rendered_qwen_by_agent": dict(collections.Counter(f"{x['agent']} {x['in_qwen']}" for x in rows)),
            "returned_in_last20_uncut": sum(x["in_full_last20"] for x in rows),
            "removed_by_400_cut": len(cut),
            "only_older_than_20_steps": sum(x["in_full_any"] and not x["in_full_last20"] for x in rows),
            "never_returned_to_agent": sum(not x["in_full_any"] for x in rows),
            "cut_examples": [{"run": x["key"], "step": x["step"], "fragment": x["frag"][0] if x["frag"] else None} for x in cut]}
        # ------------------------------------------------------------ samples (full rendered Qwen input)
        rng = random.Random(31)
        pick = []
        cat = [("unsafe", [r for r in recs if r["label"] == "high-unsafe"]), ("safe", [r for r in recs if r["label"] == "low-unsafe" and r["cut_obs"] == 0]),
               ("safer run", [r for r in recs if r["source"] == "warned_safer_run"]),
               ("long, cut by the 400-character rule", [r for r in recs if r["cut_obs"] >= 3 and 4000 < len(r["q"]) < 9000])]
        for c, pool in cat:
            if pool:
                pick.append((c, rng.choice(sorted(pool, key=lambda r: r["eid"]))))
        rest = sorted([r for r in recs if r not in [p for _, p in pick]], key=lambda r: r["eid"])
        while len(pick) < 5:
            pick.append(("random", rng.choice(rest)))
        samples_md.append(f"### {name}\n")
        for c, r in pick:
            samples_md.append(f"**{c}**: run `{r['key']}` step {r['step']}, agent {r['agent']}, split {r['split']}, gold {r['label']} "
                              f"({r['label_source']}), {len(r['q'])} characters, {r['cut_obs']} observations cut.\n\n````text\n{r['q']}\n````\n")
    (S / "checks31.json").write_text(json.dumps({"checks": CHECKS, **out}, indent=1, ensure_ascii=False))
    (S / "samples31.md").write_text("\n".join(samples_md))
    print("all checks pass" if all(c["ok"] for c in CHECKS) else "SOME CHECKS FAIL")


if __name__ == "__main__":
    main()
