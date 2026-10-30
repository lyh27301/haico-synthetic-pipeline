"""Step 7 Part E: 2 variants of every good task in the repaired bank (analysis/bank.good(): steps 3-6 after Part A2
plus the Part C/D batches), with the Part A rules (frozen base values, one axis per variant, axis alternated between
the two: recipe/variants.make_variant one_axis=True). Gate = the full Stage-B gate + structure checks. Then
5 x gpt-4o-mini and 5 x gpt-5-mini on the extremes.

Sources: one per mechanic. A good task that is itself a variant (step-5 salience `-sal-`, step-6 `-vNN`) is used
only when no good task of the same mechanic is a source, so no variant-of-a-variant is made of a mechanic that is
already covered (decide-and-record).

  python arm_step7/run_variants.py gen | roll
"""
import collections, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
ARM = ROOT / "arm_s7_variants"; ARM.mkdir(exist_ok=True); (ARM / "eval").mkdir(exist_ok=True)
MODE = sys.argv[1] if len(sys.argv) > 1 else "gen"
os.environ["GEN_MODEL"] = "gpt-5-mini"
os.environ.setdefault("USAGE_LOG", str(ARM / ("gen_usage.jsonl" if MODE == "gen" else "eval/usage.jsonl")))
import driver, run_batch  # noqa: E402
from recipe import variants as V  # noqa: E402
from bank import good  # noqa: E402

SEED, N = 7, 2
LOCK = threading.Lock()
VAR = re.compile(r"-(v\d\d|sal-\w+)$")


def mechanic(t, d):
    sc = json.loads((Path(d) / "scenario.json").read_text())
    return sc.get("axes", {}).get("mechanic_id") or VAR.sub("", t)


def sources():
    g = {t: v for t, v in good().items() if v["set"] != "arm_s7_variants"}
    by = collections.defaultdict(list)
    for t, v in g.items():
        by[mechanic(t, v["dir"])].append(t)
    out = {}
    for m, ts in by.items():
        orig = [t for t in ts if not VAR.search(t)]
        for t in (orig or ts[:1]):
            out[t] = g[t]
    return out


def manifest_row(rec):
    tdir = Path(rec["dir"]); prof = driver.profile_for(tdir)
    task = prof.TASK_SCHEMA.model_validate_json((tdir / "scenario.json").read_text())
    return {"task": task.instance_id, "dir": str(tdir), "toolkit": prof.NAME, "seed": "variant",
            "seed_id": rec["source"], "hook": task.axes.get("hook"), "outcome": task.axes.get("outcome"),
            "cue_salience": task.axes.get("cue_salience"), "cue_ids": prof.cue_ids(task)}


def run_gen():
    src = sources()
    (ARM / "sources.json").write_text(json.dumps(src, indent=1))
    print(f"{len(src)} sources", collections.Counter(v["toolkit"] for v in src.values()), flush=True)
    log = ARM / "variants.jsonl"
    done = {json.loads(x)["variant"] for x in log.read_text().splitlines()} if log.exists() else set()

    def gen(job):
        s, k = job
        vid = f"{s}-v{SEED}{k}"
        if vid in done:
            return
        d = Path(src[s]["dir"])
        try:
            rec = V.make_variant(d, SEED, k, ARM)
        except Exception as e:  # noqa: BLE001
            rec = {"source": s, "variant": vid, "status": "failed", "err": f"crash: {type(e).__name__}: {e}"[:300],
                   "trail": [], "toolkit": driver.profile_for(d).NAME}
        rec["source_set"] = src[s]["set"]; rec["source_buckets"] = src[s].get("buckets")
        with LOCK:
            with open(log, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        print(f"  {vid}: {rec['status']} {rec.get('axis')} {(rec.get('err') or '')[:150]}", flush=True)

    (ARM / "gen_done").unlink(missing_ok=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(gen, [(s, k) for s in sorted(src) for k in range(1, N + 1)]))
    (ARM / "gen_done").write_text(time.strftime("%H:%M:%S"))
    print("GEN DONE", flush=True)


def run_roll():
    os.environ["USAGE_TAG"] = "rollout_4omini"
    out, started = ARM / "eval", set()
    with ThreadPoolExecutor(6) as ex:
        while True:
            fin = (ARM / "gen_done").exists()
            log = ARM / "variants.jsonl"
            recs = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
            for rec in recs:
                if rec["status"] == "passed" and rec["variant"] not in started:
                    started.add(rec["variant"])
                    ex.submit(run_batch.run_task, manifest_row(rec), "4omini", out, 1800)
            if fin:
                break
            time.sleep(20)
    res = run_batch.results(out)
    recs = [json.loads(x) for x in (ARM / "variants.jsonl").read_text().splitlines()]
    man = [manifest_row(r) for r in recs if r["status"] == "passed"]
    extreme = [m for m in man if run_batch.bucket([r for r in res if r["task"] == m["task"] and r["agent"] == "4omini"])
               in ("all_safe", "all_unsafe")]
    print(f"5-mini on {len(extreme)} extremes", flush=True)
    os.environ["USAGE_TAG"] = "rollout_5mini"
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda m: run_batch.run_task(m, "5mini", out, 1800), extreme))
    print("ROLL DONE", flush=True)


if __name__ == "__main__":
    run_gen() if MODE == "gen" else run_roll()
