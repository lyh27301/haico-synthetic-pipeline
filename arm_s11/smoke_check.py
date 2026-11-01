"""Step 11b smoke checks for Qwen runs, from run_infer's conversation_event stream (harness/logs/*.log) + results:
  (a) tool calls parse: no raw <tool_call> / <function= text in agent messages, no AgentErrorEvent for a malformed or
      unknown tool call;
  (b) the run completed (graded, no error);
  (c) the grade (unsafe);
  (d) the watchdog's token regex sees non-zero cache_read_tokens (vLLM --enable-prompt-tokens-details);
plus wall time (invocation) and total tokens (usage.json).
  .venv/bin/python arm_s11/smoke_check.py [--tag smoke_] [--ids arm_s11/ids_smoke.txt]"""
import argparse, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S11 = ROOT / "arm_s11"; H = S11 / "harness"
sys.path.insert(0, str(S11))
TOK = re.compile(r'prompt_tokens\\?":\s*(\d+).*?completion_tokens\\?":\s*(\d+).*?cache_read_tokens\\?":\s*(\d+)')
RAW = re.compile(r"<tool_call>|<function=|</tool_call>")


def events(log, inst):
    for ln in open(log, errors="replace"):
        if ln.startswith("{") and f'"instance_id": "{inst}"' in ln and "conversation_event" in ln:
            try:
                o = json.loads(ln)
                yield o, json.loads(o.get("event") or "{}")
            except ValueError:
                continue


def check(t, k, tag):
    res = json.loads((H / "results" / f"{t}__qwen3.5-9b__r{k}.json").read_text())
    logs = sorted(glob.glob(str(H / "logs" / f"qwen3.5-9b_{tag}r{k}.log")))
    raw, errs, n_act, cache, last_tok = 0, [], 0, 0, None
    for log in logs:
        for o, e in events(log, t):
            kind = e.get("kind", "")
            if kind == "ActionEvent":
                n_act += 1
            if kind == "MessageEvent" and e.get("source") == "agent" and RAW.search(json.dumps(e.get("llm_message", e))):
                raw += 1
            if kind in ("AgentErrorEvent", "ConversationErrorEvent"):
                errs.append(str(e.get("error") or e.get("detail"))[:200])
            for p, c, cr in TOK.findall(o.get("event", "")):
                cache = max(cache, int(cr)); last_tok = (int(p), int(c), int(cr))
    inv = [json.loads(x) for f in glob.glob(str(H / "qwen3.5-9b" / f"{tag}r{k}" / "invocations.jsonl"))
           for x in open(f)]
    u = (res.get("usage") or {}).get("token_usage") or {}
    return {"run": k, "graded": res["graded"], "unsafe": res["unsafe"], "error": res["error"], "rerun": res["rerun"],
            "actions": n_act, "raw_tool_call_text": raw, "agent_errors": errs, "max_cache_read_tokens": cache,
            "last_event_tokens(prompt,completion,cache_read)": last_tok,
            "wall_s": round(sum(i["end"] - i["start"] for i in inv)),
            "tokens": {"prompt": u.get("prompt_tokens"), "completion": u.get("completion_tokens"),
                       "cache_read": u.get("cache_read_tokens"), "reasoning": u.get("reasoning_tokens")}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="smoke_")
    ap.add_argument("--ids", default=str(S11 / "ids_smoke.txt")); ap.add_argument("--runs", default="1,2,3")
    a = ap.parse_args()
    out = []
    for t in Path(a.ids).read_text().split():
        for k in map(int, a.runs.split(",")):
            out.append({"task": t, **check(t, k, a.tag)})
    ok = {"a_tool_calls_parse": all(r["raw_tool_call_text"] == 0 and not any("tool" in e.lower() for e in r["agent_errors"])
                                    for r in out),
          "b_all_complete": all(r["graded"] for r in out),
          "c_any_unsafe": any(r["unsafe"] for r in out),
          "d_cache_tokens_seen": any(r["max_cache_read_tokens"] > 0 for r in out)}
    (S11 / f"smoke_{a.tag}.json").write_text(json.dumps({"checks": ok, "runs": out}, indent=1))
    print(json.dumps({"checks": ok, "runs": out}, indent=1))


if __name__ == "__main__":
    main()
