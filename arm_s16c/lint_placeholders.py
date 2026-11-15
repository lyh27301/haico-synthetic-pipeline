"""Step 16c follow-up: lint the whole 16b bank for content that says it is simulated, a placeholder or a stand-in (the
kind of text deploy-key-zip's attachments had: "(PDF bytes simulated)").

Scanned, for every task of arm_s16b/bank/bank_16b.jsonl (what the agent or the NPC can see): the task statement, every
string in the environment (emails, attachments, records, files), the workspace / staged files under
arm_s16b/bank/files/<task>/ (text extracted with harness/filetext.py), the role text (agent_context.json) and the NPC
profiles / scenarios. Not scanned: references, evaluator code, selection notes (never shown).
Each hit is printed with its location and context; the verdict per hit (real placeholder or false alarm) is given by hand
in analysis/step16c.md (section "Follow-up"). Writes arm_s16c/lint_placeholders.json.
  .venv/bin/python arm_s16c/lint_placeholders.py"""
import json, re, sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]; C = ROOT / "arm_s16c"; BANK = ROOT / "arm_s16b/bank"
sys.path[:0] = [str(ROOT / "harness")]
import filetext  # noqa: E402

PAT = re.compile(r"(?i)("
                 r"simulat\w*|placeholder\w*|\bdummy\b|\bmock\w*|\bstub\w*|lorem ipsum|\bfiller\b|"
                 r"\b(sample|test|fake|synthetic|generated|example) (data|file|content|record|key|value|text|document)s?\b|"
                 r"\b(bytes?|binary|content|contents|data|image|attachment|file) (omitted|elided|simulated|not (shown|included)|"
                 r"goes here|here|truncated|redacted)\b|"
                 r"\((pdf|png|jpe?g|image|binary|file|zip|docx|xlsx)[^)]{0,40}\)|"
                 r"\[(insert|placeholder|redacted|todo|tbd|binary|image|attachment)[^\]]{0,40}\]|"
                 r"<(insert|placeholder|your|redacted)[^>]{0,40}>|"
                 r"\b(TODO|TBD|FIXME|XXX+)\b|"
                 r"\bexample[-.](com|org|net|project|bucket|key|corp)\w*|"
                 r"\bnot (a )?real\b|\bfor (testing|test purposes|demo(nstration)?( purposes)?)\b|\bdemo (data|account|key)\b|"
                 r"\b(abc|abcd|1234|0000)[0-9a-z]{0,12}(efgh|5678)\w*|"
                 r"rest[- ]of[- ][\w-]+|\b(pdf|file|document) content (start|end)\b|@example\b|"
                 r"\b(content|text|comments|notes|material|stories|body|details)(:)?\s*\.\.\.(?!\w)|:\s*\.\.\.\s"
                 r")")


def leaves(x, path=""):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from leaves(v, f"{path}[{i}]")


def hits(where, text):
    for m in PAT.finditer(text):
        a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
        yield {"where": where, "match": m.group(0), "context": text[a:b].replace("\n", " ")}


def main():
    ctx = json.loads((BANK / "agent_context.json").read_text())
    out = []
    for line in (BANK / "bank_16b.jsonl").read_text().splitlines():
        r = json.loads(line); t = r["instance_id"]
        src = [("problem_statement", r.get("problem_statement") or ""), ("role", ctx.get(t, ""))]
        src += [(f"environment.{p}", s) for p, s in leaves(yaml.safe_load(r["environment"]) or {})]
        src += [(f"agent_profiles.{p}", s) for p, s in leaves(r.get("agent_profiles") or [])]
        src += [(f"agent_scenarios.{p}", s) for p, s in leaves(r.get("agent_scenarios") or [])]
        src += [(f"workspace_files.{p}", s) for p, s in leaves(r.get("workspace_files") or {})]
        d = BANK / "files" / t
        for f in sorted(d.rglob("*")) if d.exists() else []:
            if f.is_file():
                src.append((f"file:{f.relative_to(d)}", filetext.extract(f.read_bytes(), f.name)))
        for where, s in src:
            for h in hits(where, s):
                out.append({"task": t, **h})
    (C / "lint_placeholders.json").write_text(json.dumps(out, indent=1))
    for h in out:
        print(f"{h['task'][7:]:45} {h['where'][:60]:60} [{h['match']}]  ...{h['context']}...")
    print(len(out), "hits in", len({h['task'] for h in out}), "tasks")


if __name__ == "__main__":
    main()
