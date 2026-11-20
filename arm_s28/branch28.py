"""Step 28 part 2: blocked-call branches on the step-21 harness (harness/v16b/oas_agentdojo16b.py, arm_s21/bank), no
change to the harness, the image or the agent.

How: a normal harness run whose agent LLM base URL points at a replay proxy in this process (arm_s14/branch.py's method).
  - LLM calls 0 .. K-1 (the responses that produced the steps before the blocked one, from the stored history grouped by
    llm_response_id) are answered with the recorded response; the tools really execute, so the environment reaches the
    prefix state. A recorded response whose calls include the blocked call and earlier calls is split: the earlier calls
    first, then the blocked call alone; calls after it in the same response are dropped.
  - call K answers with the recorded response that made the blocked call, its tool name replaced by
    `blocked_by_safety_monitor`. No tool has that name, so the SDK does not execute it: it records the call and an error
    result (stored history: an ActionEvent without action + AgentErrorEvent; the graded steps show it as a rejected call,
    no state change). The agent's own call (arguments, id, thinking) is otherwise as it was made.
  - calls K+1 .. : before the request is forwarded to the real model, the proxy puts the original tool name back on that
    call and replaces its tool result with the monitor message (OpenAI chat: the tool message; Anthropic: the tool_result
    block, is_error dropped). So on the wire the model sees its own call and, as that call's result, the monitor message.
    The message is never in the stored history (the SDK keeps its error text) and the branch meta carries
    strip_from_monitor_input = true.
Agents: gpt-6-luna (OpenAI chat completions, API defaults) and claude-haiku-5-5 (Anthropic messages, API defaults;
summarized thinking display and the thinking-binding beta as step 14, so replayed thinking blocks that no longer bind are
dropped instead of failing). NPC gpt-4o-mini as in step 21.
Jobs: arm_s28/jobs28.json (step x condition x run), bid = <step no>*100 + <condition index 1-4>*10 + <run 1-3>.
Resumable: a job with a final result is skipped; a job without one is run again in a fresh folder (up to 2 retries).
Spend: arm_s28/usage_branches.jsonl (provider, model, cost); stops when OpenAI (texts + branches + judges) passes $4 or
Anthropic passes $4.
  .venv/bin/python arm_s28/branch28.py --jobs-only
  .venv/bin/python arm_s28/branch28.py [--bids 111,112] [--workers 4]"""
import argparse, collections, copy, json, os, re, subprocess, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s28"; BR = S / "branches"
sys.path[:0] = [str(ROOT / "arm_s14"), str(ROOT / "arm_s16c"), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT / "arm_v08"),
                str(ROOT)]
import run_harness16c as H  # noqa: E402
B = H.B
BANK = ROOT / "arm_s21/bank"
PORT = int(os.environ.get("S28_PROXY_PORT", "18828"))
BLOCKED = "blocked_by_safety_monitor"
PRICE = {"gpt-6-luna": (0.10, 0.01, 0.50), "claude-haiku-5-5": (0.10, 0.01, 0.50)}   # in, cached in, out ($/M)
CAPS = {"openai": 4.0, "anthropic": 4.0}
MODEL = {"gpt-6-luna": "gpt-6-luna", "haiku5.5": "claude-haiku-5-5"}
CONDS = "ABCD"
LOCK = threading.Lock(); HLOCK = threading.Lock()
USAGE = S / "usage_branches.jsonl"


def spent():
    s = collections.Counter()
    for o in map(json.loads, USAGE.read_text().splitlines()) if USAGE.exists() else []:
        s[o["provider"]] += o["cost"]
    for f in (S / "usage.jsonl", S / "usage_fallback.jsonl", S / "usage_judges.jsonl", S / "usage_judges_fallback.jsonl"):
        for o in map(json.loads, f.read_text().splitlines()) if f.exists() else []:
            s["openai"] += o["cost"]
    return s


def log_usage(provider, model, u):
    if not u:
        return
    p = PRICE[model]
    if provider == "anthropic":
        i, c = (u.get("input_tokens") or 0) + 1.25 * (u.get("cache_creation_input_tokens") or 0), u.get("cache_read_input_tokens") or 0
    else:
        c = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0); i = (u.get("prompt_tokens") or 0) - c
    o = u.get("completion_tokens") or u.get("output_tokens") or 0
    import openai_key
    with LOCK, open(USAGE, "a") as fh:
        fh.write(json.dumps({"t": time.time(), "provider": provider, "model": model, "key": openai_key.which() if provider == "openai" else None,
                             "cost": (i * p[0] + c * p[1] + o * p[2]) / 1e6}) + "\n")


# ---------- jobs ------------------------------------------------------------------------------------------------------
def jobs():
    T = json.loads((S / "texts28.json").read_text())
    out = []
    for sid, t in sorted(T.items()):
        if not t["gate"]["passed"]:
            continue
        n = int(sid[1:])
        for ci, c in enumerate(CONDS):
            for r in (1, 2, 3):
                out.append({"bid": n * 100 + (ci + 1) * 10 + r, "step_id": sid, "condition": c, "run": r, **{k: t["step"][k] for k in
                            ("task", "agent", "key", "step", "tool", "tree")}, "message": t["messages"][c]})
    return out


# ---------- recorded responses (copied from arm_s14/branch.py, unchanged) -------------------------------------------
def recorded(hist):
    """The trajectory's LLM responses in order: [{"events": [...], "tool_calls": [...], "text", "thinking_blocks",
    "reasoning"}], and for each ActionEvent its response index."""
    out, idx, cur = [], {}, None
    for e in hist:
        k = e.get("kind")
        if k not in ("ActionEvent", "MessageEvent", "AgentErrorEvent") or e.get("source") not in ("agent", None):
            continue
        if k == "MessageEvent" and e.get("source") != "agent":
            continue
        rid = e.get("llm_response_id") or f"msg-{len(out)}"
        if cur is None or cur["id"] != rid:
            cur = {"id": rid, "tool_calls": [], "text": "", "thinking_blocks": [], "reasoning": None, "kinds": []}
            out.append(cur)
        cur["kinds"].append(k)
        if k == "ActionEvent":
            tc = e.get("tool_call") or {}
            cur["tool_calls"].append({"id": tc.get("id"), "name": tc.get("name"), "arguments": tc.get("arguments") or "{}"})
            th = e.get("thought") or []
            if isinstance(th, list) and th and not cur["text"]:
                cur["text"] = " ".join(x.get("text", "") for x in th if isinstance(x, dict))
            if e.get("thinking_blocks") and not cur["thinking_blocks"]:
                cur["thinking_blocks"] = [b for b in e["thinking_blocks"] if isinstance(b, dict)]
            if e.get("reasoning_content") and e["reasoning_content"] != "None" and not cur["reasoning"]:
                cur["reasoning"] = e["reasoning_content"]
            idx[tc.get("id")] = len(out) - 1
        elif k == "MessageEvent":
            c = (e.get("llm_message") or {}).get("content") or []
            cur["text"] = " ".join(x.get("text", "") for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c)
            rc = (e.get("llm_message") or {}).get("reasoning_content")
            if rc and rc != "None":
                cur["reasoning"] = rc
        else:
            cur["error"] = True
    return out, idx


def openai_response(r, model):
    msg = {"role": "assistant", "content": (r["text"] or "").strip() or None}
    if r["tool_calls"]:
        msg["tool_calls"] = [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t["arguments"]}}
                             for t in r["tool_calls"]]
    if r.get("reasoning"):
        msg["reasoning_content"] = r["reasoning"]
    return {"id": "replay-" + str(r["id"]), "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if r["tool_calls"] else "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


def anthropic_response(r, model):
    content = [{"type": "thinking", "thinking": b.get("thinking") or "", "signature": b.get("signature") or ""}
               for b in r["thinking_blocks"] if b.get("type") == "thinking"]
    if (r["text"] or "").strip():   # the API rejects empty / whitespace-only text blocks
        content.append({"type": "text", "text": r["text"].strip()})
    for t in r["tool_calls"]:
        try:
            inp = json.loads(t["arguments"]) if isinstance(t["arguments"], str) else t["arguments"]
        except ValueError:
            inp = {}
        content.append({"type": "tool_use", "id": t["id"], "name": t["name"], "input": inp})
    return {"id": "msg_replay_" + re.sub(r"\W", "", str(r["id"]))[:20], "type": "message", "role": "assistant",
            "model": model, "content": content, "stop_reason": "tool_use" if r["tool_calls"] else "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0}}



class Branch:
    def __init__(self, job, responses, K, block_id, orig_name, orig_args):
        self.job, self.responses, self.K = job, responses, K
        self.block_id, self.orig_name, self.orig_args = block_id, orig_name, orig_args
        self.provider = "anthropic" if job["agent"] == "haiku5.5" else "openai"
        self.model = MODEL[job["agent"]]; self.calls = 0; self.rewrites = collections.Counter()
        self.log = BR / "proxy" / f"b{job['bid']}.jsonl"; self.log.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def write(self, o):
        with open(self.log, "a") as fh:
            fh.write(json.dumps(o, ensure_ascii=False, default=str) + "\n")


BRANCHES = {}


def rewrite(br, body):
    """Put the original call back and make the monitor message its result (on the wire only)."""
    msg = br.job["message"]
    for m in body.get("messages") or []:
        if br.provider == "openai":
            for tc in m.get("tool_calls") or []:
                if tc.get("id") == br.block_id:
                    tc["function"]["name"] = br.orig_name; tc["function"]["arguments"] = br.orig_args
                    br.rewrites["call"] += 1
            if m.get("role") == "tool" and m.get("tool_call_id") == br.block_id:
                m["content"] = msg if isinstance(m.get("content"), str) else [{"type": "text", "text": msg}]
                br.rewrites["result"] += 1
        else:
            for c in m.get("content") if isinstance(m.get("content"), list) else []:
                if c.get("type") == "tool_use" and c.get("id") == br.block_id:
                    c["name"] = br.orig_name
                    try:
                        c["input"] = json.loads(br.orig_args)
                    except ValueError:
                        pass
                    br.rewrites["call"] += 1
                if c.get("type") == "tool_result" and c.get("tool_use_id") == br.block_id:
                    c["content"] = [{"type": "text", "text": msg}]; c.pop("is_error", None)
                    br.rewrites["result"] += 1
    return body


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send(200, {"data": [{"id": "replay"}]})

    def do_POST(self):
        m = re.match(r"/b/(\d+)(/.*)", self.path)
        br = BRANCHES.get(int(m.group(1))) if m else None
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if br is None:
            return self._send(404, {"error": "unknown branch"})
        if not body.get("tools"):
            return self._forward(br, body, k=None)
        with br.lock:
            k = br.calls; br.calls += 1
        if body.get("stream"):
            br.write({"call": k, "error": "stream requested"})
            return self._send(400, {"error": {"message": "streaming not supported by the replay proxy"}})
        if k <= br.K:
            r = br.responses[k]
            out = anthropic_response(r, br.model) if br.provider == "anthropic" else openai_response(r, br.model)
            br.write({"call": k, "mode": "replay" if k < br.K else "blocked", "n_messages": len(body.get("messages") or []), "response": out})
            return self._send(200, out)
        return self._forward(br, rewrite(br, copy.deepcopy(body)), k=k)

    def _forward(self, br, body, k):
        try:
            with LOCK:
                if spent()[br.provider] >= CAPS[br.provider]:
                    raise RuntimeError(f"step-28 {br.provider} cap reached")
            if br.provider == "anthropic":
                for m in body.get("messages") or []:
                    for c in m["content"] if isinstance(m.get("content"), list) else []:
                        if c.get("type") == "text" and not (c.get("text") or "").strip():
                            c["text"] = "(no output)"
                        if c.get("type") == "tool_result" and isinstance(c.get("content"), list):
                            for cc in c["content"]:
                                if cc.get("type") == "text" and not (cc.get("text") or "").strip():
                                    cc["text"] = "(no output)"
                th = body.get("thinking") or {"type": "adaptive"}
                th.update({"display": "summarized", "block_binding": {"prefix_mismatch_behavior": "drop_block"}})
                body["thinking"] = th
                beta = ",".join(x for x in [self.headers.get("anthropic-beta"), "thinking-binding-controls-2026-08-01"] if x)
                hdr = {"x-api-key": H.env_key("ANTHROPIC_API_KEY"), "anthropic-version": self.headers.get("anthropic-version") or "2023-06-01",
                       "anthropic-beta": beta, "content-type": "application/json"}
                url = "https://api.anthropic.com/v1/messages"
            else:
                body["model"] = br.model
                hdr = {"Authorization": f"Bearer {H.env_key('OPENAI_API_KEY')}", "content-type": "application/json"}
                url = "https://api.openai.com/v1/chat/completions"
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr, method="POST")
            with urllib.request.urlopen(req, timeout=900) as resp:
                out = json.loads(resp.read()); code = resp.status
            log_usage(br.provider, br.model, out.get("usage"))
        except urllib.error.HTTPError as e:
            out, code = json.loads(e.read() or b"{}"), e.code
        except Exception as e:  # noqa: BLE001
            out, code = {"error": {"message": str(e)}}, 500
        br.write({"call": k, "mode": "live" if k is not None else "aux", "status": code, "rewrites": dict(br.rewrites),
                  "n_messages": len(body.get("messages") or []), "response": out})
        self._send(code, out)

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------- one branch ------------------------------------------------------------------------------------------------
def plan(job):
    """(responses up to and including the blocked one, K, block id, original name, original arguments)."""
    import runs16c
    from smoke_grade import actions
    res = json.loads((ROOT / job["tree"] / "harness/results" / f"{job['key']}.json").read_text())
    with HLOCK:
        hist = runs16c.output_row(res).get("history") or []
    responses, idx = recorded(hist)
    acts = actions(hist)
    aid = acts[job["step"]][0]
    ev = next(e for e in hist if e.get("kind") == "ActionEvent" and e.get("id") == aid)
    tc = ev.get("tool_call") or {}
    K = idx[tc["id"]]
    calls = responses[K]["tool_calls"]; j = [t["id"] for t in calls].index(tc["id"])
    blocked = dict(responses[K], tool_calls=[dict(calls[j], name=BLOCKED)])
    if j > 0:
        responses = responses[:K] + [dict(responses[K], tool_calls=calls[:j], thinking_blocks=[])] + [blocked]
        K += 1
    else:
        responses = responses[:K] + [blocked]
    return responses, K, tc["id"], tc.get("name"), tc.get("arguments") or "{}", any(r.get("error") for r in responses[:K])


def run_branch(job):
    bid = job["bid"]; t, agent = job["task"], job["agent"]
    res_f = BR / "harness/results" / f"{t}__{agent}__r{bid}.json"
    if res_f.exists() and json.loads(res_f.read_text()).get("final"):
        return json.loads(res_f.read_text())
    responses, K, block_id, name, args, prefix_err = plan(job)
    rec = None
    for attempt in range(1, 4):
        if spent()["openai"] >= CAPS["openai"] or spent()["anthropic"] >= CAPS["anthropic"]:
            return {"bid": bid, "skipped": "spend cap"}
        br = Branch(job, responses, K, block_id, name, args); BRANCHES[bid] = br
        base = f"http://localhost:{PORT}/b/{bid}"
        if agent == "haiku5.5":
            cfg, extra = ".llm_config/openai.json", ["--anthropic", MODEL[agent], "--base-url", base]
        else:
            cfg, extra = ".llm_config/openai.json", ["--model", MODEL[agent], "--base-url", base + "/v1", "--api-key", "EMPTY"]
        out = BR / "harness" / agent / f"b{bid}_a{attempt}"; out.mkdir(parents=True, exist_ok=True)
        (out / "ids.txt").write_text(t + "\n")
        env = {**os.environ, "OPENHANDS_SUPPRESS_BANNER": "1", "OAS_WORKSPACE_ROOT": str(BANK),
               "OH16B_CONTEXT": str(BANK / "agent_context_21.json"), "ANTHROPIC_API_KEY": "unused-proxy-holds-the-key"}
        (BR / "harness/logs").mkdir(parents=True, exist_ok=True)
        with open(BR / "harness/logs" / f"b{bid}_a{attempt}.log", "a") as log:
            p = subprocess.run([str(B.PY), str(ROOT / "harness/v16b/oas_agentdojo16b.py"), cfg, *extra, "--dataset",
                                str(BANK / "bank_21_harness.jsonl"), "--split", "train", "--select", str(out / "ids.txt"),
                                "--output-dir", str(out), "--num-workers", "1", "--critic", "pass", "--max-attempts", "1"],
                               cwd=B.BENCH, env=env, stdout=log, stderr=subprocess.STDOUT)
        BRANCHES.pop(bid, None)
        got = B.outputs(out)
        meta = {"bid": bid, "step_id": job["step_id"], "condition": job["condition"], "run": job["run"], "task": t, "agent": agent,
                "orig_key": job["key"], "blocked_step": job["step"], "blocked_call": {"name": name, "arguments": args},
                "message": job["message"], "strip_from_monitor_input": True, "replayed_calls": K, "calls": br.calls,
                "rewrites": dict(br.rewrites), "prefix_rejected_call": prefix_err, "rc": p.returncode, "attempt": attempt}
        rec = H.record(t, agent, bid, *got[t], rerun=attempt > 1) if t in got else {
            "task": t, "agent": agent, "run": bid, "final": False, "error": "no output", "traj_dir": str(out.relative_to(ROOT))}
        live_ok = br.calls > K and br.rewrites.get("result", 0) > 0
        if rec.get("final") and not live_ok:
            rec.update(final=False, error=f"block not delivered (calls {br.calls}, K {K}, rewrites {dict(br.rewrites)})")
        rec["branch"] = meta
        if rec.get("final"):
            break
    B.write(res_f, rec)
    with LOCK, open(BR / "branches.jsonl", "a") as fh:
        fh.write(json.dumps({k: v for k, v in rec["branch"].items() if k != "message"} | {"final": rec.get("final"), "error": rec.get("error")}) + "\n")
    return rec


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=4); ap.add_argument("--bids")
    ap.add_argument("--jobs-only", action="store_true"); a = ap.parse_args()
    J = jobs()
    (S / "jobs28.json").write_text(json.dumps(J, indent=1, ensure_ascii=False))
    print(len(J), "jobs", collections.Counter((j["agent"], j["condition"]) for j in J))
    if a.jobs_only:
        return
    H.setup(BR)
    import openai_key
    openai_key.get("branch28")
    os.environ.update({"NPC_API_KEY": H.env_key("OPENAI_API_KEY"), "NPC_BASE_URL": "https://api.openai.com/v1", "NPC_MODEL": "gpt-4o-mini"})
    (BR / "harness/results").mkdir(parents=True, exist_ok=True)
    if a.bids:
        J = [j for j in J if str(j["bid"]) in a.bids.split(",")]
    serve()

    def safe(j):
        try:
            return run_branch(j)
        except Exception as e:  # noqa: BLE001
            import traceback
            return {"bid": j["bid"], "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-800:]}
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(safe, J):
            b = r.get("branch") or {}
            print(json.dumps({"bid": b.get("bid", r.get("bid")), "final": r.get("final"), "error": r.get("error"),
                              "calls": b.get("calls"), "rewrites": b.get("rewrites"), "tb": r.get("tb")}), flush=True)
    print("spend", dict(spent()))


if __name__ == "__main__":
    main()
