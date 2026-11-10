"""Re-render arm_s13/pilot_blind/ with the full transcript, so a human can judge each step in context. The 50
trajectories of arm_s13/pilot_manifest.jsonl, same step numbers as arm_s13/steps/, no labels. A file that already holds
annotations is left as it is; one no longer selected moves to arm_s13/pilot_annotated_dropped/.

Every turn is shown in history order: agent messages, the agent's reasoning_content (marked), user-sim replies, tool
calls with args and results. Only a single field longer than CLIP_OVER chars is collapsed (first CLIP_TO chars and a
marker). Attachment contents come from the task environment, because download_attachment only returns a path. Left out:
the system prompt and the first user message (its task and role are at the top, the rest is harness boilerplate), and
the NPC briefs (goal, strategy_hint, extra_info), which state the task's intended harm; the NPC profile stays.
  .venv/bin/python arm_s13/pilot_blind_full.py  ->  arm_s13/pilot_blind/*.md"""
import json, re, sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(S13))
import replay as R  # noqa: E402
from pilot13b import DEFINITION  # noqa: E402

CLIP_OVER, CLIP_TO = 2000, 1500
PASTE_MARK = re.compile(r"\x1b?\[\?2004[lh]")


class Dump(yaml.SafeDumper):
    pass


Dump.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))


def clip(v):
    if isinstance(v, str):
        return v if len(v) <= CLIP_OVER else v[:CLIP_TO] + f" [… {len(v) - CLIP_TO} more chars]"
    if isinstance(v, dict):
        return {k: clip(x) for k, x in v.items()}
    return [clip(x) for x in v] if isinstance(v, list) else v


def fence(text):
    n = max([3] + [len(m) + 1 for m in re.findall(r"`{3,}", text)])
    return ["`" * n + "text", text.rstrip("\n"), "`" * n, ""]


def body(v):
    """A dict or list as readable YAML, a string as it is (JSON text is parsed first), each long field collapsed."""
    if isinstance(v, str):
        v = PASTE_MARK.sub("", v)
        try:
            p = json.loads(v)
        except ValueError:
            p = None
        if not isinstance(p, (dict, list)):
            return clip(v) or "(no output)"
        v = p
    return yaml.dump(clip(v), Dumper=Dump, allow_unicode=True, sort_keys=False, width=10 ** 6)


def attachments(env):
    """id and name -> attachment, over every email in the task environment."""
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("attachments"), list):
                for a in o["attachments"]:
                    if isinstance(a, dict):
                        out[a.get("id")] = a; out[a.get("name")] = a
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(env)
    return out


def text_of(msg):
    return "\n".join(c.get("text", "") for c in msg.get("content") or [] if isinstance(c, dict)).strip()


def reasoning(e):
    return (e.get("reasoning_content") or "").strip()


def tag(name, text):
    return [f"**[{name}]**", ""] + fence(text) if text else []


def step_block(s, args, atts):
    L = [f"### step {s['step']} · `{s['tool']}` ({s['kind']})", "", "- args:", ""] + fence(body(args))
    L += ["- result (NPC reply):" if s["kind"] == "npc" else "- result:", ""] + fence(body(s["observation"]))
    ids = (args.get("attachment_ids") or []) if s["tool"] == "download_attachment" else \
        (args.get("attachments") or []) if s["tool"] == "send_email" and isinstance(args, dict) else []
    for a in ids if isinstance(ids, list) else []:
        x = atts.get(a) if isinstance(a, str) else None
        if x:
            why = "the download returned only a path" if s["tool"] == "download_attachment" else \
                "what this send attaches; the agent may or may not have read it"
            L += [f"- attachment contents, `{x.get('name')}` (from the task environment; {why}):", ""] + \
                fence(clip(str(x.get("content", ""))))
    return L + ["- gold: ", ""]


def turns(hist, steps, atts):
    """The transcript. `steps` are arm_s13/steps records, consumed in the order replay.steps_of produced them."""
    rej_ids = {e.get("tool_call_id") for e in hist if e.get("kind") == "AgentErrorEvent"}
    it = iter(steps); L = []; users = 0; seen = set()

    def take(tool):
        s = next(it)
        assert s["tool"] == tool, (s["step"], s["tool"], tool)
        return s

    for e in hist:
        k = e.get("kind")
        if k == "MessageEvent" and e.get("source") == "user":
            users += 1
            if users > 1:
                L += tag("user-sim reply", text_of(e["llm_message"]))
        elif k == "MessageEvent" and e.get("source") == "agent":
            L += tag("reasoning: the model's internal reasoning, not an action", (e["llm_message"].get("reasoning_content") or "").strip())
            L += tag("agent message", text_of(e["llm_message"]))
            for r in R.rejected_calls.extract([e]):
                s = take(r["name"]); L += step_block(s, s["args"], atts)
        elif k == "ActionEvent":
            rid = e.get("llm_response_id")
            if rid not in seen:   # parallel calls of one response repeat its reasoning and text
                seen.add(rid)
                L += tag("reasoning: the model's internal reasoning, not an action", reasoning(e))
                L += tag("agent message", "\n".join(t.get("text", "") for t in e.get("thought") or []).strip())
            c = e.get("tool_call") or {}
            if c.get("id") not in rej_ids:
                s = take(c.get("name") or e.get("tool_name"))
                try:
                    args = json.loads(c.get("arguments") or "{}")   # as the agent sent it, with its summary field
                except ValueError:
                    args = s["args"]
                L += step_block(s, args, atts)
        elif k == "AgentErrorEvent":
            s = next(it); L += step_block(s, s["args"], atts)
    assert next(it, None) is None, "steps left over"
    return L


def render(path, row, ctx, m, hist, steps):
    L = [f"# {m['task']} · {m['agent']} · run {m['run']}", "", f"- toolkit **{m['toolkit']}**", "", "## Task", "",
         row["problem_statement"].strip(), ""]
    if ctx:
        L += ["**Agent role:** " + ctx.strip(), ""]
    for p in row.get("agent_profiles") or []:
        info = {k: v for k, v in (p.get("data") or {}).items() if v}
        L += [f"**NPC profile, {p.get('name')}:** " + "; ".join(f"{k}: {v}" for k, v in info.items()), ""]
    L += ["## Transcript", "",
          "Every turn in order. `[reasoning]` blocks are the model's internal reasoning, not something it did or said; "
          "`[agent message]` is what it said; `[user-sim reply]` is the simulated user. Only tool calls are labeled: "
          "write `safe` or `unsafe` on each `gold:` line. " + DEFINITION, ""]
    atts = attachments(yaml.safe_load(row["environment"]))
    path.write_text("\n".join(L + turns(hist, steps, atts)))


def main():
    man = [json.loads(l) for l in (S13 / "pilot_manifest.jsonl").read_text().splitlines()]
    xs, rows = R.bank_runs()
    X = {(x["task"], x["agent"], x["run"]): x for x in xs}
    ctx = json.loads((ROOT / "harness/agent_context.json").read_text())
    names = {f"{m['task']}__{m['agent']}__r{m['run']}.md" for m in man}
    annotated = lambda f: bool(re.search(r"^- gold: *\S", f.read_text(), re.M))
    for f in (S13 / "pilot_blind").glob("*.md"):   # no longer selected: an annotated file is moved, never deleted
        if f.name not in names:
            if annotated(f):
                (S13 / "pilot_annotated_dropped").mkdir(exist_ok=True); f.rename(S13 / "pilot_annotated_dropped" / f.name)
            else:
                f.unlink()
    for m in man:
        name = f"{m['task']}__{m['agent']}__r{m['run']}"
        if (S13 / "pilot_blind" / f"{name}.md").exists() and annotated(S13 / "pilot_blind" / f"{name}.md"):
            continue   # holds the annotator's labels
        x = X[(m["task"], m["agent"], m["run"])]
        steps = json.loads((S13 / "steps" / f"{name}.json").read_text())
        render(S13 / "pilot_blind" / f"{name}.md", rows[m["task"]], ctx.get(m["task"], ""), m,
               R.history(x["traj_dir"], x["task"]), steps)
    print(len(man), "trajectories")


if __name__ == "__main__":
    main()
