"""Step 11: tag every v0.6 task with harm_carrier in {attachment, body, action, other} = where the harm travels, so
Part D can stratify unsafe rates by carrier (smoke: Qwen "forwards" by writing new emails without `attachments`, so
attachment-carried harm never leaves; that should not blur the overall rate). Deterministic rules, no LLM:
  - Gmail send graders (a new external email carries all MUST terms): attachment if every MUST term occurs in some
    attachment (content or name) of the initial mailbox and none occurs in any email subject/body; else body;
  - Gmail falsified-revenue reply grader: body; sensitive-attachment-downloaded grader: attachment;
    staged-message-gone grader: action;
  - "protected record gone" graders and sqldb retention graders (CONSTANT_IDS / CONSTANTS): action;
  - other record/row/field graders (commerce, finance, medical, evidence, sqldb), by the task's outcome axis:
    falsification / private_data_exposure / credential_exposure -> body (the harm is the content written in the tool
    arguments); data_loss / security_weakening / policy_violation -> action (the harm is the state change itself);
  - anything else -> other.
  .venv/bin/python arm_s11/harm_carrier.py -> arm_s11/harm_carrier.json"""
import ast, collections, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]; S11 = ROOT / "arm_s11"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis"))
from bank import bank  # noqa: E402

CONTENT = {"falsification", "private_data_exposure", "credential_exposure"}
STATE = {"data_loss", "security_weakening", "policy_violation"}


def emails(node):
    """Every dict in the env that looks like an email (has subject/body or attachments)."""
    if isinstance(node, dict):
        if ("subject" in node or "body" in node) and ("sender" in node or "recipients" in node or "attachments" in node):
            yield node
        for v in node.values():
            yield from emails(v)
    elif isinstance(node, list):
        for v in node:
            yield from emails(v)


def gmail_send_carrier(code, env_yaml):
    m = re.search(r"^MUST = (\[.*?\])", code, re.M)
    must = [x.lower() for x in ast.literal_eval(m.group(1))] if m else []
    if not must:
        return "body", "send grader without MUST terms"
    env = yaml.safe_load(env_yaml)
    in_text = in_att = False
    for e in emails(env):
        txt = (str(e.get("subject", "")) + " " + str(e.get("body", ""))).lower()
        att = " ".join(str(a.get("content", "")) + " " + str(a.get("name", "")) for a in e.get("attachments") or []
                       if isinstance(a, dict)).lower()
        in_text |= any(t in txt for t in must)
        in_att |= all(t in att for t in must) or any(t in att for t in must)
    if in_att and not in_text:
        return "attachment", f"MUST {must} only inside attachments"
    return "body", f"MUST {must} in subject/body" + (" (also in attachments)" if in_att else "")


def tag(t, row, outcome):
    code, tk = row["evaluator_code"], row["toolkit"]
    harm = (re.findall(r'"""HARM: (.*?)"""', code, re.S) or [""])[0]
    if tk == "gmail":
        if "newly sent email" in harm:
            return gmail_send_carrier(code, row["environment"])
        if "REVENUE_TOKENS" in code:
            return "body", "falsified figure in the reply body"
        if "attachment was downloaded" in harm:
            return "attachment", "sensitive attachment downloaded"
        if "gone from inbox" in harm:
            return "action", "staged message deleted/moved"
        return "other", "unrecognised gmail grader"
    if "is gone afterwards" in harm or "CONSTANT_IDS" in code or code.lstrip().startswith(("CONSTANTS", '"""')) and "CONSTANTS = {" in code:
        return "action", "protected record removed"
    if outcome in CONTENT:
        return "body", f"{outcome}: content written in tool arguments"
    if outcome in STATE:
        return "action", f"{outcome}: state change"
    return "other", f"outcome {outcome}"


def main():
    b = bank()
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (S11 / "bank_v06.jsonl").read_text().splitlines()}
    out = {}
    for t, row in rows.items():
        sc = Path(b[t]["dir"]) / "scenario.json"
        outcome = (json.loads(sc.read_text()).get("axes") or {}).get("outcome") if sc.exists() else None
        c, why = tag(t, row, outcome)
        out[t] = {"harm_carrier": c, "toolkit": row["toolkit"], "outcome": outcome, "why": why}
    (S11 / "harm_carrier.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(collections.Counter(v["harm_carrier"] for v in out.values())))
    print(json.dumps(collections.Counter((v["toolkit"], v["harm_carrier"]) for v in out.values()).most_common()))


if __name__ == "__main__":
    main()
