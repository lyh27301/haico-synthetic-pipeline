"""Step 27 part 4: code checks on every warning text of the 76 branches (v1, v2, v2-noalt, v2-continue). No model calls.
  - self-contradiction candidates: the alternative (v2's last line; the other conditions have none) names a trap object:
    an identifier of the original unsafe action (attachment ids and file names, item / payment / patient / evidence ids,
    file paths) or a trap identifier of the v4.2-s27 rule set (gen_rules42.trap_mentions: protected ids, names, paths,
    identifier values of harm states). Each candidate is listed with its sentence; whether it asks for the forbidden
    object or only names it as the thing to avoid is decided by reading (arm_s27/review27.json "contradiction").
  - hindsight candidates: a sentence that states the unsafe action's effect as already done (past or perfect tense of
    the action verbs; "after ...ing ... to sent"; "now showing / now shows / is now"). Each is checked against the branch
    point: does the prefix (steps before the branch point, as graded) already contain that effect? Decided by reading.
  - exits: "ask ..." (the user, Legal, a named person, whether ...), "get approval / confirm with / check with / wait for /
    escalate", and optional wording ("if <x> is needed", "if necessary", "if possible", "if one is available", "can then",
    "could then", "optionally"). Listed for a reader; which of them offer a way out of the task is decided by reading.
  - third person: occurrences of "the agent" (and "the assistant") in the text.
  - v2 alternative source: arm_s14/rationales_pilot.jsonl "matched" (true: the alternative was written from the round-1
    branch that completed; false: from the task's safe reference). The path is graded with the v4.2-s27 rules: the
    round-1 branch from arm_s27/grades27.jsonl (condition v1), the safe reference by playing it on the old row.
  .venv/bin/python arm_s27/warnings27.py   -> arm_s27/warnings27.json"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S14 = ROOT / "arm_s14"
sys.path[:0] = [str(ROOT / "arm_s27"), str(ROOT / "grader"), str(ROOT / "arm_s16c"), str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT)]

HIND = re.compile(r"(?i)\b(this|it|that|which|the agent|this email|the message)\s+(?:also\s+|has\s+|have\s+)?(sent|moved|deleted|"
                  r"uploaded|granted|approved|added|updated|changed|set|removed|shared|forwarded|exposed|released|overwrote|replaced|"
                  r"attached|archived|published|refunded|went)\b"
                  r"|\b(?:has|have|was|were)\s+(?:been\s+)?(sent|moved|deleted|uploaded|granted|approved|added|updated|changed|"
                  r"removed|shared|forwarded|exposed|released|overwritten|replaced|attached|archived|published|refunded)\b"
                  r"|\bafter\s+\w+ing\b[^.]{0,80}\bto\s+sent\b|\bnow\s+(?:showing|shows|holds|contains|has|in)\b|\bis\s+now\b")
EXIT = re.compile(r"(?i)\b(ask(?:ing)?\b(?!ed)[^.;]{0,60}|get(?:ting)?\s+(?:\w+\s+)?approval|seek(?:ing)?\s+approval|"
                  r"confirm(?:ing)?\s+with|check(?:ing)?\s+with|wait(?:ing)?\s+for|escalat\w+|if\s+(?:\w+\s+){0,2}(?:is\s+|are\s+)?needed|"
                  r"if\s+necessary|if\s+possible|if\s+required|if\s+one\s+is\s+available|can\s+then|could\s+then|optionally)")
THIRD = re.compile(r"(?i)\bthe\s+(agent|assistant)\b")


def sentences(t: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", t or "") if s.strip()]


def ids_of(tool, args) -> set:
    out = set()
    for k, v in (args or {}).items():
        if k in ("summary", "security_risk", "body", "subject", "message", "description", "notes", "query"):
            continue
        for x in (v if isinstance(v, list) else [v]):
            x = str(x)
            if k in ("to", "cc", "bcc", "action", "category", "evidence_type", "quantity", "database", "folder"):
                continue
            if len(x) >= 3:
                out.add(x); out.add(x.rstrip("/").rsplit("/", 1)[-1])
    q = str((args or {}).get("query") or "")
    out |= set(re.findall(r"'([^']{3,})'", q))
    return {x for x in out if len(x) >= 3}


def alternative_line(w: str) -> str:
    m = re.search(r"(?m)^You must take a different approach, such as: (.*)$", w or "")
    return m.group(1) if m else ""


def main():
    import gen_rules42 as G42
    r2 = json.loads((S14 / "r2/jobs_r2.json").read_text()); r2b = json.loads((S14 / "r2b/jobs_r2b.json").read_text())
    v1w = {j["bid"]: j["warning"] for j in json.loads((S14 / "branch_jobs.json").read_text())}
    rat = {r["key"]: r for r in map(json.loads, (S14 / "rationales_pilot.jsonl").read_text().splitlines())}
    S = json.loads((ROOT / "grader/out/v4.2-s27/set.json").read_text())["tasks"]
    grades = [json.loads(l) for l in (ROOT / "arm_s27/grades27.jsonl").read_text().splitlines()]
    gk = {(g["condition"], g["key"]): g for g in grades}
    items = []
    for j in r2:
        items.append((j["condition"], j["bid"], j))
    for j in r2b:
        items.append(("v2-continue", j["bid"], j))
    for j in r2:
        if j["condition"] == "v2":
            items.append(("v1", j["v1_bid"], j | {"warning": v1w[j["v1_bid"]]}))
    out = []
    for cond, bid, j in items:
        w = j["warning"]
        rules = json.loads((ROOT / S[j["task"]]["rule_file"]).read_text())["rules"]
        forb = ids_of(j["orig_tool"], j["orig_args"]) | {str(x) for x in G42.trap_mentions(rules) if len(str(x)) >= 3}
        alt = alternative_line(w)
        contra = [{"token": t, "sentence": s} for s in sentences(alt) for t in sorted(forb) if t.lower() in s.lower()]
        hind = [{"match": m.group(0), "sentence": s} for s in sentences(w) for m in HIND.finditer(s)]
        exits = [{"match": m.group(0), "sentence": s} for s in sentences(alt) for m in EXIT.finditer(s)] if alt else []
        third = len(THIRD.findall(w))
        g = gk.get((cond, j["key"]))
        prefix = [{"i": i, "tool": g["tools"][i], "args": g["args"][i], "error": g["errors"][i]} for i in range(j["step"])] if g else None
        out.append({"condition": cond, "bid": bid, "key": j["key"], "task": j["task"], "branch_step": j["step"],
                    "forbidden_tokens": sorted(forb), "self_contradiction_candidates": contra, "hindsight_candidates": hind,
                    "exits": exits, "third_person": third, "prefix": prefix, "warning": w})
    # v2: the path the alternative was written from, graded with the new rules
    import play as P, bank27, yaml, engine4 as E
    P.staged = bank27.staged
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s27/bank/bank_27.jsonl").read_text().splitlines()}
    import grade27 as G27
    G27.init()
    src = []
    for j in r2:
        if j["condition"] != "v2":
            continue
        r = rat[j["key"]]
        if r["matched"]:
            g = gk[("v1", j["key"])]
            uns = [{"step": i, "tool": g["tools"][i], "args": g["args"][i],
                    "rules": sorted({f.get("rule") for f in g["findings"][i] if f.get("label") == "unsafe"} - {None})}
                   for i, lab in enumerate(g["labels"]) if lab == "unsafe" and i >= j["step"]]
            src.append({"key": j["key"], "source": f"round-1 branch b{j['v1_bid']} (completed)", "unsafe_steps": uns,
                        "completion": g["completion"]})
        else:
            row = rows[j["task"]]
            d = json.loads((ROOT / S[j["task"]]["rule_file"]).read_text())
            files = "\n".join(f"## {p}\n{v[:3000]}" for p, v in P.initial(row)[1].items()) or "(none)"
            R = {**d["rules"], "_note_env": row["environment"] + "\n\n# Files on disk at the start\n" + files}
            st = P.play(row, row["safe_reference"])
            Lr = E.label_run(R, st, (yaml.safe_load(row["environment"]) or {}).get("owner_email"))
            done, _ = E.completion(R, st[0]["pre"], st[-1]["post"], st[0]["pre_ws"], st[-1]["post_ws"])
            uns = [{"step": i, "tool": s["call"]["name"], "args": s["call"]["args"],
                    "rules": sorted({f.get("rule") for f in s["findings"] if f.get("label") == "unsafe"} - {None})}
                   for i, s in enumerate(Lr["steps"]) if s["label"] == "unsafe"]
            src.append({"key": j["key"], "source": "the task's safe reference", "unsafe_steps": uns, "completion": done,
                        "safe_completes_check": d["checks"].get("safe_completes"),
                        "safe_not_flagged_check": d["checks"].get("safe_not_flagged")})
    (ROOT / "arm_s27/warnings27.json").write_text(json.dumps({"warnings": out, "alternative_sources": src}, indent=1,
                                                             ensure_ascii=False, default=str))
    print(len(out), "warnings;", sum(bool(x["self_contradiction_candidates"]) for x in out), "with contradiction candidates;",
          sum(bool(x["hindsight_candidates"]) for x in out), "with hindsight candidates;", sum(bool(x["exits"]) for x in out),
          "with exits;", sum(x["third_person"] > 0 for x in out), "in third person;",
          sum(bool(s["unsafe_steps"]) for s in src), "v2 alternative sources with unsafe steps")


if __name__ == "__main__":
    main()
