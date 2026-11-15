"""Step 16b item 12: regression test for the rename. The stored trajectories, states and environments of the 50
pilot tasks, and every rule that reads them (task evaluator, grader v2 / v3 / v5 string literals, utility specs,
exposure matchers, probes, grounding quotes, toolkit constants), are passed through the same rename table, then
re-graded with the step-16a pipeline (arm_s16/regrade.py `_one`, utility16.utility5, exposure, outcome). Every verdict
must equal the verdict of the same pipeline on the original data:
  per step: label_v5, label_v5p, sub_reason, the (tag, rule) findings; per run: unsafe_v5, intent_v5, utility_v5,
  exposed, outcome_v5.
Two passes, so a difference can be attributed: `control` (no rename, today's code) and `renamed`. Both are compared with
the stored step-16a results; control vs 16a isolates code changes made since 16a, renamed vs control is the rename.
No model calls.   .venv/bin/python arm_s16b/regress_rename.py [--workers 8]"""
import argparse, collections, importlib, importlib.util, json, sys, types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S16, S16B = ROOT / "arm_s16", ROOT / "arm_s16b"
sys.path[:0] = [str(ROOT), str(ROOT / "harness"), str(ROOT / "arm_s13"), str(S16), str(S16B)]
import rename as RN  # noqa: E402

MODE = None
TOOLKIT_MODULES = ("gmail_suite.environment", "gmail_suite.tools", "evidence_suite.tools", "commerce_suite.tools",
                   "commerce_suite.environment", "medical_suite.tools", "finance_suite.tools", "sqldb_suite.tools")


def _renamed_module(name: str):
    """Import `name` from its source with its string literals renamed, and register it before anyone imports it."""
    spec = importlib.util.find_spec(name)
    src = Path(spec.origin).read_text()
    mod = types.ModuleType(name); mod.__file__ = spec.origin
    sys.modules[name] = mod
    exec(compile(RN.rn_source(src), spec.origin, "exec"), mod.__dict__)
    return mod


def _rename_constants(mod):
    for k, v in list(vars(mod).items()):
        if k.startswith("__") or callable(v) or isinstance(v, types.ModuleType):
            continue
        if isinstance(v, (str, tuple, list, dict)):
            try:
                setattr(mod, k, RN.rn(v))
            except Exception:  # noqa: BLE001
                pass


def init(mode):
    global MODE, G, UT, OUT, X, EXPO
    MODE = mode
    RN.load()
    if mode == "renamed":
        for m in ("grader_v2", "grader_v4", "grader_v3", "grader_v5"):
            _renamed_module(m)
        for m in TOOLKIT_MODULES:
            _rename_constants(importlib.import_module(m))
    import regrade as G   # noqa: PLC0415
    import utility16 as UT   # noqa: PLC0415
    import outcomes as OUT   # noqa: PLC0415
    import exposure as X   # noqa: PLC0415
    import replay as RP   # noqa: PLC0415
    f = RN.rn if mode == "renamed" else (lambda o: o)
    G.init()
    G.BANK = {t: (f(r) | ({"environment": RN.rn_yaml(r["environment"])} if mode == "renamed" else {}))
              for t, r in G.BANK.items()}
    G.NORM = {t: f(o) for t, o in G.NORM.items()}
    G.CTX = {t: f(c) for t, c in G.CTX.items()}
    js0, jl0, hist0 = G.js, RP.jl, RP.history
    G.js = lambda p: f(js0(p))
    RP.jl = lambda p: f(jl0(p))
    G.R.jl = RP.jl
    G.R.history = lambda d, t: f(hist0(d, t))
    G.specs_of = lambda t: [f(s) for s in _specs16a(js0, t)]
    pr0 = G.probe_spec
    G.probe_spec = lambda t: f(pr0(t))
    G.S16 = S16B / "regress" / mode
    G.STEPS_DIR = "steps"
    EXPO = {t: f(json.loads((ROOT / "arm_s13/exposure" / f"{t}.json").read_text()))
            for t in G.BANK if (ROOT / "arm_s13/exposure" / f"{t}.json").exists()}
    globals().update(G=G, UT=UT, OUT=OUT, X=X, F=f, JS0=js0)


def _specs16a(js0, t):
    out = []
    for p in (ROOT / "arm_s13/utility" / f"{t}.json", S16 / "utility" / f"{t}.json"):
        d = js0(p)
        if d and d.get("requirements"):
            out.append({"requirements": [r for r in d["requirements"] if "any_of" not in r] +
                        [x for r in d["requirements"] if "any_of" in r for x in r["any_of"]]})
    return out


def one(x):
    try:
        r = G._one(x)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"key": (x["task"], x["agent"], x["run"], x["source"]), "crash": f"{type(e).__name__}: {e}"[:300],
                "tb": traceback.format_exc()[-600:]}
    t = x["task"]
    sd = Path(x["state_dir"])
    pre, post = F(JS0(sd / "pre.json")), F(JS0(sd / "post.json"))
    fin = G.S16 / "final_states" / x["source"] / f"{t}__{x['agent']}__r{x['run']}.json"
    if r.get("g6_patch") and fin.exists():
        post = json.loads(fin.read_text())
    wpre = F(JS0(sd / "workspace_pre.json")); wpost = F(JS0(sd / "workspace_post.json")) | (r.get("g6_patch") or {})
    spec = F(OUT.spec_new(t))
    u, _ = UT.utility5(spec, pre | {"workspace": wpre}, post | {"workspace": wpost},
                       task_text=G.BANK[t]["problem_statement"]) if spec else (None, {})
    steps = F(JS0(Path(x["steps_path"]))) or []
    rule = EXPO.get(t)
    ex = X.exposure(steps, [m["string"] if isinstance(m, dict) else m for m in rule.get("matchers") or []]) if rule else {"exposed": None}
    o = OUT.outcome(r["unsafe_v5"], r["intent_v5"], u, ex["exposed"], (rule or {}).get("valid"))
    labs = json.loads((G.S16 / "steps" / x["source"] / f"{t}__{x['agent']}__r{x['run']}.json").read_text())
    return {"key": (t, x["agent"], x["run"], x["source"]), "unsafe_v5": r["unsafe_v5"], "intent_v5": r["intent_v5"],
            "utility_v5": u, "exposed": ex["exposed"], "outcome": o, "issues": r.get("issues"),
            "steps": [(s["label_v5"], s["label_v5p"], s.get("sub_reason"),
                       sorted((f.get("tag"), f.get("rule")) for f in s["findings"])) for s in labs]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=8); a = ap.parse_args()
    sel = {s["task"] for s in json.loads((S16B / "selection.json").read_text())}
    runs = [json.loads(l) for l in (S16 / "runs.jsonl").read_text().splitlines() if l.strip()]
    runs = [r for r in runs if r["task"] in sel and "crash" not in r and "unsafe_v5" in r]
    keep = ("task", "agent", "run", "source", "state_dir", "traj_dir", "steps_path", "of_record", "qualified", "pilot")
    xs = [{k: r.get(k) for k in keep} for r in runs]
    print(len(xs), "runs of the 50 tasks", flush=True)
    res = {}
    for mode in ("control", "renamed"):
        with ProcessPoolExecutor(a.workers, initializer=init, initargs=(mode,)) as ex:
            res[mode] = {tuple(o["key"]): o for o in ex.map(one, xs, chunksize=4)}
        print(mode, "done; crashed", sum("crash" in o for o in res[mode].values()), flush=True)
    # the stored step-16a verdicts
    o5 = {(o["task"], o["agent"], o["run"], o["source"]): o for o in map(json.loads, (S16 / "outcomes_v5.jsonl").read_text().splitlines())}
    base = {}
    for x in xs:
        k = (x["task"], x["agent"], x["run"], x["source"])
        st = json.loads((S16 / "steps" / x["source"] / f"{x['task']}__{x['agent']}__r{x['run']}.json").read_text())
        o = o5.get(k, {})
        base[k] = {"unsafe_v5": o.get("unsafe_v5"), "intent_v5": o.get("intent_v5"), "utility_v5": o.get("utility_v5"),
                   "exposed": o.get("exposed"), "outcome": o.get("outcome_v5"),
                   "steps": [(s["label_v5"], s["label_v5p"], s.get("sub_reason"),
                              sorted((f.get("tag"), f.get("rule")) for f in s["findings"])) for s in st]}

    def cmp(A, B, name):
        diffs = []
        for k in sorted(A):
            a, b = A[k], B.get(k)
            if b is None or "crash" in a or "crash" in b:
                diffs.append({"key": k, "what": "crash_or_missing", "a": a.get("crash"), "b": (b or {}).get("crash")}); continue
            for f in ("unsafe_v5", "intent_v5", "utility_v5", "exposed", "outcome"):
                if a[f] != b[f]:
                    diffs.append({"key": k, "what": f, "a": a[f], "b": b[f]})
            if len(a["steps"]) != len(b["steps"]):
                diffs.append({"key": k, "what": "n_steps", "a": len(a["steps"]), "b": len(b["steps"])})
            for i, (sa, sb) in enumerate(zip(a["steps"], b["steps"])):
                if json.dumps(sa) != json.dumps(sb):
                    diffs.append({"key": k, "what": "step", "step": i, "a": sa, "b": sb})
        return {"pair": name, "runs": len(A), "runs_differing": len({d["key"] for d in diffs}),
                "by_field": dict(collections.Counter(d["what"] for d in diffs)), "diffs": diffs}
    rep = {"n_runs": len(xs), "n_steps": sum(len(b["steps"]) for b in base.values()),
           "control_vs_16a": cmp(res["control"], base, "control_vs_16a"),
           "renamed_vs_control": cmp(res["renamed"], res["control"], "renamed_vs_control"),
           "renamed_vs_16a": cmp(res["renamed"], base, "renamed_vs_16a")}
    (S16B / "regression.json").write_text(json.dumps(rep, indent=1, default=str))
    for k in ("control_vs_16a", "renamed_vs_control", "renamed_vs_16a"):
        print(k, {kk: rep[k][kk] for kk in ("runs", "runs_differing", "by_field")})


if __name__ == "__main__":
    main()
