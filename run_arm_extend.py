"""Extend an arm with extra seeds (step 5): Stage A on the new seeds with the arm's gated scenarios as prior
(novelty / mechanic / diversity gates see them), then Stage B on the new scenarios only, until the arm reaches
--target emitted tasks. Results are merged into the arm's candidates / gated_scenarios / funnel (the new
scenarios get idx after the existing ones, so run_batch's seed mapping still works); the extension's own
funnel is kept in <arm>/ext_<tag>/funnel.json.

  python run_arm_extend.py --arm arm_evidence_c --seeds arm_evidence_c/seeds_ext --toolkit evidence --target 10
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe import pipeline, profiles  # noqa: E402
from run_arm import load_seeds  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True); ap.add_argument("--seeds", required=True)
    ap.add_argument("--toolkit", required=True); ap.add_argument("--target", type=int, required=True)
    ap.add_argument("--k", type=int, default=3); ap.add_argument("--tag", default="1")
    a = ap.parse_args()
    pipeline.PROFILE = profiles.get(a.toolkit)
    arm = Path(a.arm); ext = arm / f"ext_{a.tag}"; ext.mkdir(exist_ok=True)
    main_f = json.loads((arm / "funnel.json").read_text())
    prior = [json.loads(x) for x in (arm / "gated_scenarios.jsonl").read_text().splitlines() if x.strip()]
    have = sum(1 for r in main_f.get("tasks", []) if r.get("dir"))
    seeds = load_seeds(Path(a.seeds))
    print(f"extension {a.tag}: {len(seeds)} seeds, prior gated {len(prior)}, emitted {have}/{a.target}", flush=True)
    stage_b_model = pipeline.GEN_MODEL
    pipeline.GEN_MODEL = os.environ.get("STAGEA_GEN_MODEL", "gpt-4o-mini")   # scenarios: same model as the main run
    new = pipeline.run_stage_a(seeds, ext, k=a.k, prior_gated=prior)
    pipeline.GEN_MODEL = stage_b_model
    print(f"stage A passed: {len(new)} new scenarios", flush=True)
    with open(arm / "gated_scenarios.jsonl", "a") as fh:
        fh.writelines(json.dumps(g) + "\n" for g in new)
    with open(arm / "candidates.jsonl", "a") as fh:
        fh.write((ext / "candidates.jsonl").read_text())
    f = pipeline.run_stage_b(new, arm, target=max(0, a.target - have), profile=pipeline.PROFILE,
                             idx_offset=len(prior), funnel_path=ext / "funnel.json")
    main_f = json.loads((arm / "funnel.json").read_text())
    main_f.setdefault("extensions", []).append({"tag": a.tag, "seeds": [s["seed_id"] for s in seeds],
                                                "scenario_funnel": f.get("scenario_funnel"),
                                                "task_funnel": f["task_funnel"]})
    for k, v in (f.get("scenario_funnel") or {}).items():
        main_f["scenario_funnel"][k] = main_f["scenario_funnel"].get(k, 0) + v
    for k, v in f["task_funnel"].items():
        if k != "scenarios":
            main_f["task_funnel"][k] = main_f["task_funnel"].get(k, 0) + v
    main_f["task_funnel"]["scenarios"] = len(prior) + len(new)
    main_f["tasks"] = main_f.get("tasks", []) + f["tasks"]
    (arm / "funnel.json").write_text(json.dumps(main_f, indent=2))
    print("TASK FUNNEL (merged)", json.dumps(main_f["task_funnel"]), flush=True)


if __name__ == "__main__":
    main()
