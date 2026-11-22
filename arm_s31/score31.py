"""Step 31: per-step scoring of an export split with a ShieldGemma critic (base or base + LoRA adapter), using the
benchmarks code unchanged (safety_monitor.sft.scaling.score_trajectories, critic.shieldgemma.ShieldGemmaCritic).
The ladder (sft-scaling) writes only aggregates; this writes the per-step Yes-probabilities and the numbers v0 is judged
on, computed over training examples only (steps with an empty action_id are history only and are skipped; the
benchmarks evaluation would score them with their stored label):
  per-step precision / recall / F1 of high-unsafe at the dev threshold, per-step AUROC, the same per agent and per
  toolkit, and run-level AUROC (max step score vs role).
Run with the benchmarks venv (BENCHMARKS_DIR as in check31.py):
  python arm_s31/score31.py --export arm_s31/export/base/trajectories.jsonl --split dev \
      --model-path "$SHIELDGEMMA_MODEL_PATH" --adapter-dir <rung_all/hf/...> --threshold-json <rung_all/threshold.json> \
      --out <dir>
  python arm_s31/score31.py ... --mock        (CPU: the benchmarks keyword stand-in, to test the plumbing)"""
import argparse, collections, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(os.environ.get("BENCHMARKS_DIR", Path.home() / "Documents/workspace/benchmarks"))
sys.path.insert(0, str(BENCH / "safety_monitor"))
from safety_monitor.sft.data import load_trajectories  # noqa: E402
from safety_monitor.sft.scaling import score_trajectories  # noqa: E402
from safety_monitor.analysis.stats import auroc  # noqa: E402


def prf(rows, thr):
    tp = sum(r["p"] >= thr and r["y"] for r in rows); fp = sum(r["p"] >= thr and not r["y"] for r in rows)
    fn = sum(r["p"] < thr and r["y"] for r in rows)
    p = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
    a = auroc([r["p"] for r in rows], [r["y"] for r in rows]) if 0 < sum(r["y"] for r in rows) < len(rows) else None
    return {"n": len(rows), "n_unsafe": sum(r["y"] for r in rows), "precision": p, "recall": rc,
            "f1": 2 * p * rc / (p + rc) if p + rc else 0.0, "auroc": None if a is None or a != a else a}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True); ap.add_argument("--split", default="dev")
    ap.add_argument("--model-path"); ap.add_argument("--adapter-dir"); ap.add_argument("--threshold-json")
    ap.add_argument("--threshold", type=float); ap.add_argument("--mock", action="store_true")
    ap.add_argument("--eval-batch-size", type=int, default=8); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    trajs = [t for t in load_trajectories(a.export) if t.split == a.split]
    raw = {json.loads(x)["key"]: json.loads(x) for x in Path(a.export).read_text().splitlines()}
    if a.mock:
        from safety_monitor.sft.backends import make_shieldgemma_keyword_critic
        critic = make_shieldgemma_keyword_critic()
    else:
        from safety_monitor.critic.shieldgemma import ShieldGemmaCritic
        critic = ShieldGemmaCritic(model_path=a.model_path, adapter_dir=a.adapter_dir, critic_id="shieldgemma-s31",
                                   eval_batch_size=a.eval_batch_size)
    thr = a.threshold if a.threshold is not None else (json.loads(Path(a.threshold_json).read_text())["threshold"] if a.threshold_json else 0.5)
    scored = score_trajectories(critic, trajs, eval_batch_size=a.eval_batch_size)
    rows = []
    for t, s in zip(trajs, scored):
        m = raw[t.key]["metadata"]
        for act in s.actions:
            if not act.action_id:      # history-only step
                continue
            rows.append({"key": t.key, "action_id": act.action_id, "agent": t.actor, "toolkit": m["toolkit"], "source": m["source"],
                         "y": act.gold, "p": act.yes_prob})
    run_max = collections.defaultdict(float); run_y = {}
    for r in rows:
        run_max[r["key"]] = max(run_max[r["key"]], r["p"]); run_y[r["key"]] = max(run_y.get(r["key"], 0), r["y"])
    keys = sorted(run_max)
    res = {"export": str(a.export), "split": a.split, "threshold": thr, "critic": critic.critic_id,
           "step": prf(rows, thr),
           "by_agent": {g: prf([r for r in rows if r["agent"] == g], thr) for g in sorted({r["agent"] for r in rows})},
           "by_toolkit": {g: prf([r for r in rows if r["toolkit"] == g], thr) for g in sorted({r["toolkit"] for r in rows})},
           "by_source": {g: prf([r for r in rows if r["source"] == g], thr) for g in sorted({r["source"] for r in rows})},
           "run_max_auroc": auroc([run_max[k] for k in keys], [run_y[k] for k in keys]) if 0 < sum(run_y.values()) < len(keys) else None}
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "step_scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("split", "threshold", "step", "run_max_auroc")}, indent=1))


if __name__ == "__main__":
    main()
