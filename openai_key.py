"""Step 23 (part 0): which OpenAI key a job uses. Once per job (process), make one minimal call with OPENAI_API_KEY
(the group's key). If it works, use it. If it fails with the organization spend-limit / quota error (429) and
OPENAI_API_KEY_FALLBACK (a personal key) is in .env, the whole job uses the fallback. Any other error is raised, not
worked around. Without the fallback line, the group key is returned as before. Key values are never printed or logged:
only "group" / "fallback" goes to logs/openai_key.jsonl (job, choice, time).
  import openai_key; key = openai_key.get("job name"); openai_key.which() -> "group" | "fallback" | None"""
import json, os, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "logs/openai_key.jsonl"
_LOCK = threading.Lock(); _choice = None   # ("group" | "fallback", key)


def _env(name):
    for ln in (ROOT / ".env").read_text().splitlines():
        ln = ln.strip().removeprefix("export ")
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def spend_limited(e) -> bool:
    s = str(e)
    return ("429" in s or getattr(e, "status_code", None) == 429) and (
        "spend limit" in s or "insufficient_quota" in s or "exceeded your current quota" in s)


def probe(key):
    """One minimal call: None if it works, else the exception."""
    from openai import OpenAI
    try:
        OpenAI(api_key=key, timeout=60, max_retries=1).chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "ok"}], max_completion_tokens=1)
        return None
    except Exception as e:  # noqa: BLE001
        return e


def get(job=None) -> str:
    global _choice
    with _LOCK:
        if _choice is None:
            group, fb = _env("OPENAI_API_KEY"), _env("OPENAI_API_KEY_FALLBACK")
            if group is None:
                sys.exit("OPENAI_API_KEY not in .env")
            which, key, note = "group", group, ""
            if fb:   # without a fallback line: exactly as before (no probe)
                e = probe(group)
                if e is not None:
                    if not spend_limited(e):
                        raise RuntimeError(f"OpenAI group key failed with a non-quota error (not worked around): {str(e)[:300]}")
                    which, key, note = "fallback", fb, "group key: organization spend limit / quota (429)"
            _choice = (which, key)
            LOG.parent.mkdir(exist_ok=True)
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"job": job or Path(sys.argv[0]).name, "pid": os.getpid(), "key": which, "note": note,
                                     "t": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            print(f"[openai_key] {job or Path(sys.argv[0]).name}: using the {which} key", file=sys.stderr, flush=True)
        return _choice[1]


def which():
    return _choice[0] if _choice else None


if __name__ == "__main__":   # status check: which key would a job get now (no key printed)
    get(sys.argv[1] if len(sys.argv) > 1 else "check"); print(which())
