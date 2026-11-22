"""Step 31 part 4: the benchmarks SFT entry points in mock mode (CPU, no weights) on both exports, far enough to show
data loading, prompt rendering, the class balance handling and the dev threshold fit with our files. The benchmarks code
is run as it is (from its own directory and venv); outputs go to $OUT (default: a temp dir), never into either repo.
Then arm_s31/score31.py --mock on dev. Summary -> arm_s31/dryrun31.json (paths shown as $REPO / $OUT).
  python3 arm_s31/dryrun31.py        (BENCHMARKS_DIR as in check31.py)"""
import json, os, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(os.environ.get("BENCHMARKS_DIR", Path.home() / "Documents/workspace/benchmarks"))
PY = str(BENCH / ".venv/bin/python")
OUT = Path(os.environ.get("OUT") or tempfile.mkdtemp(prefix="s31_dry_"))


def run(name, args, cwd):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=os.environ | {"PYTHONPATH": "."})
    log = (p.stdout + p.stderr).splitlines()
    shown = " ".join(a.replace(str(ROOT), "$REPO").replace(str(OUT), "$OUT").replace(PY, "python") for a in args)
    return {"command": f"cd $BENCHMARKS_DIR/safety_monitor && PYTHONPATH=. {shown}" if cwd != ROOT else shown,
            "exit": p.returncode, "log": [ln.replace(str(OUT), "$OUT").replace(str(ROOT), "$REPO") for ln in log
                                          if not ln.startswith("  ") and ln.strip()][-14:]}


def main():
    sm = BENCH / "safety_monitor"
    before = subprocess.run(["git", "status", "--short"], cwd=BENCH, capture_output=True, text=True).stdout
    res = {}
    for v in ("base", "with_safer"):
        tr, ev = str(ROOT / f"arm_s31/export/{v}/trajectories.jsonl"), str(ROOT / f"arm_s31/export/{v}/eval_dev.jsonl")
        o = OUT / f"scaling_{v}"
        r = run(f"sft-scaling {v}", [PY, "-m", "safety_monitor", "sft-scaling", "--backend", "mock", "--train", tr, "--eval", ev,
                                     "--rungs", "0,all", "--epochs", "1", "--seed", "42", "--out-dir", str(o)], sm)
        rr = json.loads((o / "results.json").read_text()) if (o / "results.json").exists() else {}
        r["written"] = sorted(str(p.relative_to(o)) for p in o.rglob("*") if p.is_file())
        r["split"] = {k: x for k, x in (rr.get("split") or {}).items() if k.startswith("n_")}
        r["rungs"] = {pr["rung"]: {"threshold": pr["threshold"],
                                   "threshold_selection": {k: pr["threshold_selection"].get(k) for k in ("dev_action_f1", "dev_max_vs_harmful_auroc", "n_dev_trajectories")},
                                   "train_stats": {k: pr["train_stats"].get(k) for k in ("backend", "n", "n_pos", "final_loss", "note")},
                                   "example_counts": {k: pr["example_counts"][k] for k in ("train", "synthetic_dev")},
                                   "dev_action": pr["metrics"]["synthetic_dev"]["action"]} for pr in rr.get("per_rung", [])}
        res[f"sft-scaling {v}"] = r
        o = OUT / f"run_qwen_{v}"
        r = run(f"sft-run {v}", [PY, "-m", "safety_monitor", "sft-run", "--backend", "mock", "--family", "qwen", "--use-shipped-splits",
                                 "--epochs", "1", "--train", tr, "--eval", ev, "--out-dir", str(o)], sm)
        m = json.loads((o / "metrics.json").read_text())
        r |= {"split": {k: x for k, x in m["split"].items() if k.startswith("n_") or k == "split_source"}, "example_counts": m["example_counts"],
              "train_stats": {k: m["train_stats"].get(k) for k in ("backend", "n", "n_pos", "final_loss", "note")},
              "after_sft_eval_action": m["metrics"]["after_sft"]["v3_eval"]["action"]}
        res[f"sft-run {v}"] = r
    thr = OUT / "scaling_base/rung_0/threshold.json"
    r = run("score31 mock", [PY, str(ROOT / "arm_s31/score31.py"), "--export", str(ROOT / "arm_s31/export/base/trajectories.jsonl"),
                             "--split", "dev", "--mock", "--threshold-json", str(thr), "--out", str(OUT / "score31_mock")], ROOT)
    r["summary"] = json.loads((OUT / "score31_mock/summary.json").read_text())
    r["summary"]["export"] = "$REPO/arm_s31/export/base/trajectories.jsonl"
    res["score31 mock"] = r
    after = subprocess.run(["git", "status", "--short"], cwd=BENCH, capture_output=True, text=True).stdout
    res["benchmarks_working_tree_unchanged"] = before == after
    (ROOT / "arm_s31/dryrun31.json").write_text(json.dumps(res, indent=1))
    for k, v in res.items():
        print(k, v if isinstance(v, bool) else f"exit {v['exit']}")


if __name__ == "__main__":
    main()
