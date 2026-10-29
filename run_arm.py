"""Run Stage A + B for an arm from a seeds dir of TOMLs."""
import json, sys, tomllib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe import pipeline

def load_seeds(seeds_dir: Path):
    out = []
    for p in sorted(seeds_dir.glob("*.toml")):
        d = tomllib.loads(p.read_text())
        trap = d.get("trap", {})
        out.append({"seed_id": d.get("seed_id", p.stem), "axes": d["axes"],
                    "setting": d.get("setting", {}), "incident": trap.get("incident", ""),
                    "forbid": trap.get("forbid", [])})
    return out

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--target", type=int, default=10)
    ap.add_argument("--no-mech", action="store_true")
    ap.add_argument("--toolkit", default="gmail")
    a = ap.parse_args()
    from recipe import profiles
    pipeline.PROFILE = profiles.get(a.toolkit)
    arm_dir = Path(a.arm)
    seeds = load_seeds(Path(a.seeds))
    print(f"stage A: {len(seeds)} seeds, k={a.k}")
    gated = pipeline.run_stage_a(seeds, arm_dir, k=a.k, mech_check=not a.no_mech)
    print(f"stage A passed: {len(gated)} scenarios")
    print("stage B...")
    f = pipeline.run_stage_b(gated, arm_dir, target=a.target, profile=pipeline.PROFILE)
    print("TASK FUNNEL", json.dumps(f["task_funnel"]))
