"""Shared LLM client wrapper: 240s timeout, 3 retries with exponential backoff on
timeout / APIConnectionError / 5xx / rate-limit. Returns (message, error); callers
wrap so a final failure marks that one item 'error' and moves on. Used by gates,
task gen, review, driver rollouts, and Petri wiring."""
from __future__ import annotations
import json, os, random, time
from openai import OpenAI
try:
    from openai import APIConnectionError, APITimeoutError, RateLimitError, APIStatusError
except Exception:  # pragma: no cover
    APIConnectionError = APITimeoutError = RateLimitError = APIStatusError = Exception

TIMEOUT = 240.0
RETRIES = 3

def _client():
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=TIMEOUT, max_retries=0)

def _retryable(e) -> bool:
    if isinstance(e, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    code = getattr(e, "status_code", None)
    return isinstance(code, int) and (code == 429 or 500 <= code < 600)

def chat(model, messages, json_mode=True, retries=RETRIES, **kw):
    last = None
    for i in range(retries + 1):
        try:
            args = {"model": model, "messages": messages, **kw}
            if json_mode:
                args["response_format"] = {"type": "json_object"}
            r = _client().chat.completions.create(**args)
            return r.choices[0].message, None
        except Exception as e:  # noqa: BLE001
            last = e
            if not _retryable(e) and i == 0 and not isinstance(e, Exception):
                break
            if not _retryable(e):
                # non-retryable (e.g. 400) -> stop early
                return None, f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(min(2 ** i + random.random(), 30))
    return None, f"{type(last).__name__}: {str(last)[:120]}"

def complete_json(model, system, user, retries=RETRIES):
    m, err = chat(model, [{"role": "system", "content": system},
                          {"role": "user", "content": user}], True, retries)
    if err:
        return None, err
    try:
        return json.loads(m.content), None
    except Exception as e:  # noqa: BLE001
        return None, f"jsonparse: {str(e)[:80]}"
