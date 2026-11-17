"""Step 17: read the hand-annotated pilot v3 files (arm_s16c/pilot_v3_gold/, read-only).
gold(file) -> {"task", "agent", "run", "steps": {i: (label, note)}}; label in safe / unsafe / intent."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "arm_s16c/pilot_v3_gold"
SKIP = {"safety-fn-consolidate-vendors-venmo-name-collision__haiku5.5__r1"}   # task flaw (COMPLETION_GOLD.md)
ADDED = {"safety-md-maria-lopez-med-update-v2__qwen3.5-9b__r5"}               # the Qwen file added after the blind 24
STEP = re.compile(r"^### step (\d+) ")
LINE = re.compile(r"^- gold:\s*(.*)$")


def norm(s: str) -> str:
    s = s.strip().lower()
    if s.startswith("unsafe-intent") or s.startswith("intent"):
        return "intent"
    if s.startswith("unsafe"):
        return "unsafe"
    if s.startswith("safe"):
        return "safe"
    return "?"


def parse(path: Path) -> dict:
    t, ag, r = path.stem.split("__")
    steps, cur = {}, None
    for ln in path.read_text().splitlines():
        m = STEP.match(ln)
        if m:
            cur = int(m.group(1)); continue
        m = LINE.match(ln)
        if m and cur is not None:
            raw = m.group(1).strip()
            note = re.search(r"\((.*)\)\s*$", raw)
            steps[cur] = (norm(raw), note.group(1) if note else "")
    return {"file": path.stem, "task": t, "agent": ag, "run": int(r.lstrip("r")), "steps": steps}


def files(include_added=True) -> list:
    out = []
    for p in sorted(GOLD.glob("safety-*.md")):
        if p.stem in SKIP or (p.stem in ADDED and not include_added):
            continue
        out.append(parse(p) | {"added": p.stem in ADDED})
    return out
