"""Step 6 Part C: 2 variants per usable task, gated, then 5 gpt-4o-mini (temp 1.0) rollouts per passing variant.

Sources = every step-3..5 task whose class is good (mixed under either agent) or all_unsafe (all_unsafe under every
agent run on it). Variant generation (seed 1, k = 1, 2) and rollouts run concurrently; every variant record is a
line in variants.jsonl and every rollout an atomic file in eval/results (run_batch.run_task), so the run resumes and
a partial run still reports.

  python arm_variants/run_c.py gen    # variant generation + gate   (usage -> gen_usage.jsonl)
  python arm_variants/run_c.py roll   # rollouts, polling variants.jsonl until gen is done (usage -> eval/usage.jsonl)
Two processes so token usage is attributed cleanly.
"""
import collections, glob, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent; sys.path.insert(0, str(ROOT))
MODE = sys.argv[1] if len(sys.argv) > 1 else "gen"
os.environ.setdefault("USAGE_LOG", str(HERE / ("gen_usage.jsonl" if MODE == "gen" else "eval/usage.jsonl")))
(HERE / "eval").mkdir(exist_ok=True)
import driver, run_batch  # noqa: E402
from recipe import variants as V  # noqa: E402

EVALS = {"step3": "arm_eval3/results", "gmail": "arm_gmail_c/eval/results", "sqldb": "arm_sqldb_d/eval/results",
         "evidence": "arm_evidence_c/eval/results", "medical": "arm_medical_c/eval/results"}
SEED, N = 1, 2
LOCK = threading.Lock()


def classes():
    out = {}
    for grp, d in EVALS.items():
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        for f in glob.glob(str(ROOT / d / "*.json")):
            r = json.loads(Path(f).read_text())
            if r.get("unsafe") != "":
                by[r["task"]][r["agent"]].append(int(r["unsafe"]))
        for t, ag in by.items():
            b = {a: ("all_unsafe" if all(u) else "all_safe" if not any(u) else "mixed") for a, u in ag.items()}
            cls = ("good" if "mixed" in b.values() else "all_unsafe" if set(b.values()) == {"all_unsafe"}
                   else "all_safe" if set(b.values()) == {"all_safe"} else "split")
            out[t] = {"group": grp, "class": cls, "buckets": b,
                      "rate_4o": round(sum(ag["4omini"]) / len(ag["4omini"]), 2) if ag.get("4omini") else None}
    return out


def source_dirs():
    dirs = {m["task"]: ROOT / m["dir"] for m in json.loads((ROOT / "analysis/step3_manifest.json").read_text())}
    for arm in ("arm_gmail_c", "arm_sqldb_d", "arm_evidence_c", "arm_medical_c"):
        for d in (ROOT / arm / "tasks").iterdir():
            dirs[d.name] = d
    return dirs


def manifest_row(rec):
    tdir = Path(rec["dir"]); prof = driver.profile_for(tdir)
    task = prof.TASK_SCHEMA.model_validate_json((tdir / "scenario.json").read_text())
    return {"task": task.instance_id, "dir": str(tdir), "toolkit": prof.NAME, "seed": "variant",
            "seed_id": rec["source"], "hook": task.axes.get("hook"), "outcome": task.axes.get("outcome"),
            "cue_salience": task.axes.get("cue_salience"), "cue_ids": prof.cue_ids(task)}


def run_gen():
    cls = classes(); dirs = source_dirs()
    sources = sorted(t for t, c in cls.items() if c["class"] in ("good", "all_unsafe") and t in dirs)
    (HERE / "sources.json").write_text(json.dumps({t: {**cls[t], "dir": str(dirs[t])} for t in sources}, indent=1))
    print(f"{len(sources)} sources", collections.Counter(cls[t]["class"] for t in sources), flush=True)
    log = HERE / "variants.jsonl"
    done = {json.loads(x)["variant"] for x in log.read_text().splitlines()} if log.exists() else set()

    def gen(job):
        src, k = job
        vid = f"{src}-v{SEED}{k}"
        if vid in done:
            return
        V.tag_source(dirs[src])
        try:
            rec = V.make_variant(dirs[src], SEED, k, HERE)
        except Exception as e:  # noqa: BLE001
            rec = {"source": src, "variant": vid, "status": "failed", "err": f"crash: {type(e).__name__}: {e}"[:300],
                   "trail": [], "toolkit": driver.profile_for(dirs[src]).NAME}
        rec["source_class"] = cls[src]["class"]
        with LOCK:
            with open(log, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        print(f"  {vid}: {rec['status']} {(rec.get('err') or '')[:150]}", flush=True)

    (HERE / "gen_done").unlink(missing_ok=True)
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(gen, [(s, k) for s in sources for k in range(1, N + 1)]))
    (HERE / "gen_done").write_text(time.strftime("%H:%M:%S"))
    print("GEN DONE", flush=True)


def run_roll():
    os.environ["USAGE_TAG"] = "rollout_4omini"
    out = HERE / "eval"; started = set()
    with ThreadPoolExecutor(6) as ex:
        while True:
            fin = (HERE / "gen_done").exists()
            log = HERE / "variants.jsonl"
            recs = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
            for rec in recs:
                if rec["status"] == "passed" and rec["variant"] not in started:
                    started.add(rec["variant"])
                    ex.submit(run_batch.run_task, manifest_row(rec), "4omini", out, 1800)
            if fin:
                break
            time.sleep(20)
    print("ROLL DONE", flush=True)


def main():
    run_gen() if MODE == "gen" else run_roll()


if __name__ == "__main__":
    main()
