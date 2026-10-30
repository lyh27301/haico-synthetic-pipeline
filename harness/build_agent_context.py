"""instance_id -> the driver's agent role text (profile.agent_system(env) / AGENT_SYSTEM) for every v0.4 row, so the
harness prompt's `## Environment` section carries the same role framing the driver's system prompt does instead
of the raw env YAML.  python harness/build_agent_context.py -> harness/agent_context.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402

man = json.loads((ROOT / "arm_hf/out_v04/manifest.json").read_text())
out = {}
for t, v in man["tasks"].items():
    d = ROOT / v["dir"]; prof = driver.profile_for(d)
    env = prof.load_environment(d / "environment.yaml")
    out[t] = prof.agent_system(env) if hasattr(prof, "agent_system") else prof.AGENT_SYSTEM
(ROOT / "harness/agent_context.json").write_text(json.dumps(out, indent=1))
print(len(out), "rows;", len(set(out.values())), "distinct texts")
