"""Disk cache for LLM GENERATION calls (scenario/task gen + gates), keyed by prompt-input hash.
Makes regeneration after a `claude --continue` resume free. NOT used for rollout agent/user
calls (those must stay independent samples)."""
import hashlib, json
from pathlib import Path
CACHE = Path(__file__).resolve().parents[1] / ".gen_cache"

def key(model: str, system: str, user: str) -> str:
    return hashlib.sha256(("\x00".join([model, system, user])).encode()).hexdigest()

def get(model, system, user):
    p = CACHE / (key(model, system, user) + ".json")
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None

def put(model, system, user, obj):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / (key(model, system, user) + ".json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj)); tmp.rename(p)
