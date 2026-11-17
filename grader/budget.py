"""Step 17 spend: every model call of the step (rule writing, note judge, third-label judge) is logged in
grader/out/v3/usage.jsonl; check() stops the step once spend passes the cap ($5, the step's limit)."""
import json, threading, time
from pathlib import Path

USAGE = Path(__file__).resolve().parent / "out" / "v3" / "usage.jsonl"
CAP = 5.0
LOCK = threading.Lock()


class OverBudget(SystemExit):
    pass


def spent() -> float:
    if not USAGE.exists():
        return 0.0
    return sum(json.loads(l)["cost"] for l in USAGE.read_text().splitlines() if l.strip())


def check():
    s = spent()
    if s >= CAP:
        raise OverBudget(f"spend ${s:.2f} passed the ${CAP:.2f} cap: stopping (step 17 limit)")


def cost(u, price) -> float:
    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    return ((u.input_tokens - cached) * price["in"] + cached * price["cached"] + u.output_tokens * price["out"]) / 1e6


def log(row: dict):
    with LOCK, open(USAGE, "a") as fh:
        fh.write(json.dumps(row | {"t": time.time()}) + "\n")
