"""Step 16b item 19: the task admission checklist (docs/RULES.md §9) as an automatic lint over the 50 pilot tasks.

Checks (one per checklist item; a task passes an item when every check of it passes):
  1 completion_checkable   the task has a v6 completion check; the safe reference passes it; doing nothing fails it
                           (rule gates, arm_s16b/rules/<task>.json)
  2 hazard_on_path         an exposure rule exists and is valid, and stored rollouts were exposed on at least one agent
                           (exposure rate > 0); the per-agent rates are reported
  3 prohibition_has_source every protected item of the v6 rules quotes text that occurs verbatim in the task (statement,
                           environment, staged files, role, NPC) or is marked "common sense"
  4 role_matches_requester the step-13j role audit is not "mismatch" (or the task was repaired)
  5 nothing_synthetic      no reserved / stock token (.example / .test / .invalid domains, example.com/org, company.com,
                           Acme, Globex, Initech, Umbrella, Hooli, Stark, Wonka, Pied Piper, John / Jane Doe), no
                           single-letter names (Contract X, Witness A), no hand-written ids (email_4, thread_1,
                           att_contract, contact_6, alert_101, email_prev), no control characters, no record dated after
                           the task's current date unless it is a deadline / schedule field, no record whose own text
                           reports a later date than its timestamp, and no test-like harness header
  6 tools_usable           every operation the statement asks for has a tool (forward -> forward_email, zip / archive /
                           compress -> create_archive, merge / combine / bundle into one PDF -> merge_pdfs, convert ->
                           flagged for a decision); a task that depends on "today" has a current date; the completion
                           check looks at content (some requirement has a condition beyond recipient / existence)
  7 multi_agent            stored rollouts exist for at least two agents, one of them strong (haiku5.5 or sonnet5.5)
Writes arm_s16b/lint.json.   .venv/bin/python arm_s16b/lint.py"""
import collections, json, re, sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
sys.path[:0] = [str(S16B), str(ROOT / "harness"), str(ROOT / "arm_s13")]
import play as P  # noqa: E402

STOCK = re.compile(r"(?i)\b[\w.-]+\.(example|test|invalid)\b|\bexample\.(com|org|net)\b|\bcompany\.com\b|"
                   r"\b(Acme|Globex|Initech|Umbrella Corp|Hooli|Stark Industries|Wonka|Pied ?Piper|John Doe|Jane Doe)\b")
SINGLE = re.compile(r"\b(Contract|Project|Witness|Device|Protocol|Lab|Client|Patient|Company|Vendor|Site|Study|Product|"
                    r"Participant|Supplier|Partner|Exhibit|Document|Tee|Glove|Buffer|Reagent) ?[A-Z]\b(?![a-z])")
HANDID = re.compile(r"\b(email_\d+|email_prev|email_c\d+|thread_\d+|att_[a-z_0-9]+|contact_\d+|alert_\d+|q3_\d+|cs_\w+_\d+)\b")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DEADLINE = re.compile(r"(?i)(due|deadline|until|through|expires?|embargo|availability|schedul|reminder|appointment|"
                      r"payment_date|next_|start|end_date|effective|valid)")
HEADER_BAD = ("THE AGENT COMPANY", "the-agent-company", "NEVER ASK FOR HUMAN HELP", "This is AUTONOMOUS", "theagentcompany",
              "NPC COMMUNICATION", "Available NPCs", "/utils/common.py")
OPS = {"forward": (r"\bforward", "forward_email"), "archive": (r"\b(zip|archive|compress)", "create_archive"),
       "merge": (r"\b(merge|combine|bundle\w*)\b.*\bpdf|\bpdf\b.*\b(merge|combine|bundle)", "merge_pdfs"),
       "convert": (r"\bconvert\w*\b", None)}
DATE_DEP = re.compile(r"(?i)\b(today|recent|older than|last week|overdue|within \d+ days|upcoming|this week|yesterday)")


def walk_dates(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from walk_dates(v, path + (str(k),))
            if isinstance(k, str) and re.match(r"20\d\d-\d\d-\d\d", k):
                yield k, path + (k,), "<key>"
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from walk_dates(v, path + (str(i),))
    elif isinstance(x, str):
        for d in re.findall(r"\b(20\d\d-\d\d-\d\d)", x):
            yield d, path, x


def main():
    rows = [json.loads(l) for l in (S16B / "bank/bank_16b.jsonl").read_text().splitlines()]
    ctx = json.loads((S16B / "bank/agent_context.json").read_text())
    tmpl = (ROOT / "harness/v16b/prompt.j2").read_text()
    roles = {o["task"]: o for o in map(json.loads, (ROOT / "arm_s13/role_audit.jsonl").read_text().splitlines())}
    o5 = [json.loads(l) for l in (ROOT / "arm_s16/outcomes_v5.jsonl").read_text().splitlines()]
    expo = collections.defaultdict(lambda: collections.defaultdict(list))
    for o in o5:
        if o.get("of_record") and o.get("exposed") is not None:
            expo[o["task"]][o["agent"]].append(bool(o["exposed"]))
    out = {}
    for r in rows:
        t = r["instance_id"]; res = {}
        rf = json.loads((S16B / "rules" / f"{t}.json").read_text()) if (S16B / "rules" / f"{t}.json").exists() else {}
        g = rf.get("gates") or {}; R = rf.get("rules") or {}
        env = yaml.safe_load(r["environment"]) or {}
        _, ws = P.initial(r)
        text = " ".join([r["problem_statement"], r["environment"], ctx.get(t, ""), json.dumps(r.get("agent_profiles")),
                         json.dumps(r.get("agent_scenarios"))] + list(ws.values()))
        # 1
        res["1_completion_checkable"] = {"ok": bool((R.get("completion") or {}).get("requirements")) and
                                         bool(g.get("safe_completes")) and bool(g.get("empty_fails")),
                                         "safe_completes": g.get("safe_completes"), "empty_fails": g.get("empty_fails")}
        # 2
        ef = ROOT / "arm_s13/exposure" / f"{t}.json"
        ev = json.loads(ef.read_text()) if ef.exists() else {}
        rates = {a: round(sum(v) / len(v), 2) for a, v in expo[t].items() if v}
        res["2_hazard_on_path"] = {"ok": bool(ev.get("valid")) and any(x > 0 for x in rates.values()),
                                   "rule_valid": ev.get("valid"), "exposure_rate": rates,
                                   "note": "exposure rule and rates are from the pre-rename runs (13h rule renamed for 16b)"}
        # 3
        norm = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower()
        bad = [p.get("id") for p in R.get("protected") or [] if not (str(p.get("quote", "")).lower().startswith("common sense")
               or norm(p.get("quote", "")) in norm(text))]
        res["3_prohibition_has_source"] = {"ok": bool(R.get("protected") or R.get("harm_states")) and not bad,
                                           "unverified_quotes": bad, "n_protected": len(R.get("protected") or [])}
        # 4
        ro = roles.get(t, {})
        res["4_role_matches_requester"] = {"ok": ro.get("verdict") != "mismatch" or bool(ro.get("repaired_13j")),
                                           "verdict": ro.get("verdict")}
        # 5
        hits = sorted({m.group(0) for m in STOCK.finditer(text)})
        single = sorted({m.group(0) for m in SINGLE.finditer(text)} - {"Part D"})
        hid = sorted({m.group(0) for m in HANDID.finditer(text)})
        ctrl = bool(CTRL.search(text))
        cur = str(r.get("current_date") or env.get("current_date") or "")[:10]
        late = sorted({(d, "/".join(p[-2:])) for d, p, s in walk_dates(env) if cur and d > cur
                       and not DEADLINE.search("/".join(p[-3:]) + " " + str(s)[:120])})
        rep = []
        for d, p, s in walk_dates(env):
            if p and p[-1] in ("timestamp", "uploaded_at", "created_at", "date", "recorded_at") and isinstance(s, str):
                pass
        for coll in ("inbox", "evidence", "clinical_documents"):
            for rec in env.get(coll) or []:
                ts = str(rec.get("timestamp") or rec.get("uploaded_at") or rec.get("date") or "")[:10]
                body = json.dumps({k: v for k, v in rec.items() if k not in ("timestamp", "uploaded_at", "date")})
                later = [d for d in re.findall(r"\b(20\d\d-\d\d-\d\d)", body) if ts and d > ts and not DEADLINE.search(body[max(0, body.find(d) - 40):body.find(d)])]
                if later:
                    rep.append((rec.get("id") or rec.get("evidence_id") or rec.get("document_id"), ts, later[:3]))
        hdr = [b for b in HEADER_BAD if b.lower() in tmpl.lower()]
        res["5_nothing_synthetic"] = {"ok": not (hits or single or hid or ctrl or late or rep or hdr), "stock": hits,
                                      "single_letter": single, "handwritten_ids": hid[:10], "control_chars": ctrl,
                                      "dated_after_today": late[:10], "content_later_than_timestamp": rep[:10],
                                      "header": hdr}
        # 6
        _, _, rt = P.load_env(r)
        ps = r["problem_statement"]
        missing, convert = [], False
        for op, (rx, tool) in OPS.items():
            if re.search(rx, ps, re.I | re.S):
                if r["toolkit"] == "sqldb" and op == "archive":   # an "archive record" in a table: done with SQL
                    continue
                if tool is None:
                    convert = True
                elif tool not in rt.functions:
                    missing.append(tool)
        needs_date = bool(DATE_DEP.search(ps))
        content = any(any(c.get("field") not in ("recipients", "to", "cc", "bcc", "recipient", "recipient_org", "grantee",
                                                  "destination", "folder", "case_id")
                          for c in q.get("where") or []) for q in (R.get("completion") or {}).get("requirements") or [])
        res["6_tools_usable"] = {"ok": not missing and not convert and (not needs_date or bool(cur)) and content,
                                 "missing_tools": missing, "convert": convert, "date_dependent": needs_date,
                                 "current_date": cur, "completion_checks_content": content}
        # 7
        ag = {a for a in expo[t]}
        res["7_multi_agent"] = {"ok": len(ag) >= 2 and bool(ag & {"haiku5.5", "sonnet5.5"}), "agents": sorted(ag),
                                "note": "rollouts of the pre-16b version; the 16b version has only the smoke run"}
        res["passed"] = all(v["ok"] for k, v in res.items() if k[0].isdigit())
        out[t] = res
    summ = {k: sum(v[k]["ok"] for v in out.values()) for k in next(iter(out.values())) if k[0].isdigit()}
    summ["all"] = sum(v["passed"] for v in out.values())
    (S16B / "lint.json").write_text(json.dumps({"summary": summ, "tasks": out}, indent=1, default=str))
    print(json.dumps(summ, indent=1))
    for t, v in out.items():
        f = [k for k in v if k[0].isdigit() and not v[k]["ok"]]
        if f:
            print(t, f)


if __name__ == "__main__":
    main()
