"""Step 27 part 5: what the agent said after the warning, from the branch proxy logs (live responses only: the calls
the real model answered after the warning was put on the wire). Haiku 5.5 responses carry summarized reasoning
("thinking"); gpt-4o-mini responses carry no reasoning, only text and tool calls. No model calls.
  .venv/bin/python arm_s27/said27.py   -> arm_s27/said27.json"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S14 = ROOT / "arm_s14"
TREE = {"v1": S14 / "branches", "v2": S14 / "r2/branches", "v2-noalt": S14 / "r2/branches", "v2-continue": S14 / "r2b/branches"}


def responses(cond, bid) -> list:
    f = TREE[cond] / "proxy" / f"b{bid}.jsonl"
    out = []
    for o in map(json.loads, f.read_text().splitlines()) if f.exists() else []:
        if o.get("mode") != "live":
            continue
        r = o.get("response") or {}
        parts = []
        for c in r.get("content") or []:
            if c.get("type") == "thinking":
                parts.append({"reasoning": c.get("thinking") or ""})
            elif c.get("type") == "text" and (c.get("text") or "").strip():
                parts.append({"text": c["text"]})
            elif c.get("type") == "tool_use":
                parts.append({"call": c.get("name"), "args": c.get("input")})
        for ch in r.get("choices") or []:
            m = ch.get("message") or {}
            if (m.get("content") or "").strip():
                parts.append({"text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    a = fn.get("arguments")
                parts.append({"call": fn.get("name"), "args": a})
        out.append(parts)
    return out


def main():
    g = [json.loads(l) for l in (ROOT / "arm_s27/grades27.jsonl").read_text().splitlines()]
    out = []
    for x in g:
        if x["condition"] == "original":
            continue
        out.append({"condition": x["condition"], "bid": x["bid"], "key": x["key"], "agent": x["agent"],
                    "responses": responses(x["condition"], x["bid"])})
    (ROOT / "arm_s27/said27.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(out), "branches;", sum(bool(o["responses"]) for o in out), "with live responses")


if __name__ == "__main__":
    main()
