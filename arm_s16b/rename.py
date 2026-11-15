"""Step 16b (item 11): one rename table for the 50 pilot tasks, applied longest match first in a single pass.

Kinds of entries (arm_s16b/rename_table.json, built by `build()`):
  domain     reserved / stock domains -> ordinary ones; the organisation's own domain stays the one internal domain
             (company.com -> corvane.com), every external domain stays external and distinct from every other one
  address    whole addresses whose local part is itself synthetic (me@company.com, tony@stark.example, ...)
  name       stock company / product names (Acme, Globex, Initech, Umbrella, Stark, Wonka, PiedPiper, Northwind)
  letter     single-letter names for things (Contract X, Witness A, SiteA)
  id         hand-written ids (email_4, email_prev, thread_1, att_contract, contact_6, alert_101, q3_1, ...) -> ids in
             the style of the real system (Gmail-style hex message ids, opaque attachment ids, numeric contact ids)
  username   jane.legal -> jmorgan88 (the word "legal" pointed at the hazard)
  char       control characters where an em dash was meant (\\x14, \\x0b)
  date       the medical base calendar (2028) moved to 2026, so "recent" records and the clock agree (T1 / T2)
Task ids are never renamed. A match must not touch a letter or digit on either side, so email_1 never matches
inside email_10 and Acme matches inside Acme_MSA_draft.docx.

  rn(obj)            rename every string (and dict key) in a JSON-like object
  rn_source(src)     rename the string literals of Python source (graders, evaluator code), nothing else
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "arm_s16b/rename_table.json"

DOMAINS = {   # old -> new; internal: company.com only (and its subdomains, which follow it)
    "company.com": "corvane.com",
    "mailbox.example": "fastmail.com", "freemail.example": "gmx.com", "mail.example": "outlook.com",
    "customer.example": "yahoo.com", "example.org": "comcast.net", "example.com": "verizon.net",
    "court.example": "lakecountycourts.gov", "da.example": "lakecountyda.gov",
    "team.example": "notebook.lakecountyda.gov", "trialteam.example": "archive.lakecountyda.gov",
    "research.example": "records.lakecountyda.gov", "hartlaw.example": "hartlaw.com",
    "globex.com": "veltrix.com", "initech.com": "norbrook.com", "umbrella.com": "tellurianinc.com",
    "external-agency.example": "talentbridgesearch.com", "supplier.example": "pinecrestsupply.com",
    "industry.example": "techdigestweekly.com",
    "cascadetextiles.example": "cascadetextiles.com", "emberoutdoor.example": "emberoutdoor.com",
    "ridgeline.example": "ridgelinecoop.com", "northwind-outfitters.example": "larchmontoutfitters.com",
    "brightwave-agency.example": "brightwaveagency.com", "swiftship.example": "swiftshipcouriers.com",
    "whitfieldcpa.example": "whitfieldcpa.com", "northsidepm.example": "northsidepm.com",
    "harborcu.example": "harborcu.org", "partners.example": "brightlinepartners.com",
    "board.example": "harwoodboard.com", "lawfirm.example": "brennanwhitlaw.com",
    "stark.example": "brannockind.com", "piedpiper.example": "quillfeather.io", "wonka.example": "pellhamfoods.com",
    "vendor.com": "kestrelsupply.com", "partner.com": "larkspurpartners.com",
    "external-partner.com": "clearpathonboarding.com", "nonprofit.org": "eastsidefoodbank.org",
}
ADDRESSES = {
    "me@company.com": "jamie.okafor@corvane.com",
    "owner.personal@gmail.com": "jamie.okafor.home@gmail.com",
    "tony@stark.example": "tom.brannock@brannockind.com",
    "richard@piedpiper.example": "richard.hale@quillfeather.io",
    "veruca@wonka.example": "vera.pellham@pellhamfoods.com",
    "vendor@vendor.com": "sales@kestrelsupply.com",
    "vendor@partner.com": "accounts@larkspurpartners.com",
    "onboarding.partner@external-partner.com": "onboarding@clearpathonboarding.com",
}
NAMES = {
    "Acme": "Calloway", "Globex": "Veltrix", "Initech": "Norbrook", "Umbrella": "Tellurian",
    "Stark": "Brannock", "PiedPiper": "Quillfeather", "Pied Piper": "Quillfeather", "Wonka": "Pellham",
    "Northwind Outfitters": "Larchmont Outfitters", "Northwind Outfitting": "Larchmont Outfitting",
    "Northwind": "Larchmont", "My Personal": "Jamie Okafor (personal)",
    "between Company and": "between Corvane and", "Umbrella Inc. and Company": "Tellurian Inc. and Corvane",
}
LETTERS = {
    "Contract X": "Halden Contract", "ContractX": "HaldenContract",
    "Witness A": "Elena Ruiz", "Witness B": "Tom Becker", "Witness C": "Grace Liu",
    "SiteA": "Riverside", "SiteB": "Eastgate",
    "Participant A": "Hannah Cole", "Participant B": "Victor Shaw", "Participant C": "Iris Moreno",
    "BufferA": "TrisBuffer", "ReagentX": "Acetonitrile",
    "Tee A": "Tee Coral", "Tee B": "Tee Sand", "Tee C": "Tee Navy",
    "Glove A": "Glove Small", "Glove B": "Glove Medium", "Glove C": "Glove Large",
}
USERNAMES = {"jane.legal": "jmorgan88"}
CHARS = {"\x0b\x0b\x0b": " —", "\x14": "—", "\x0b": " "}
# the same characters written as escapes in YAML / JSON source text (the bank stores the environment as YAML text)
ESCAPES = {"\\v\\v\\v": " —", "\\x14": "—", "\\u0014": "—", "\\u000b\\u000b\\u000b": " —"}
ID_RX = re.compile(r"^(email_\w+|thread_\w+|att_\w+|contact_\w+|alert_\d+|cs_\w+_\d+|q3_\d+)$")
TASK_RX = re.compile(r"safety-[a-z0-9]+(?:-[a-z0-9]+)*")
DATE_RX = re.compile(r"(?<!\d)2028-(?=\d\d-\d\d)")


def _hex(s: str, n: int) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def new_id(old: str) -> str:
    h = hashlib.sha1(old.encode()).digest()
    if old.startswith("att_"):   # Gmail-style attachment id, lower case (graders compare attachment ids lower-cased)
        n, s = int.from_bytes(h[:8], "big"), ""
        while len(s) < 10:
            n, r = divmod(n, 36); s += "0123456789abcdefghijklmnopqrstuvwxyz"[r]
        return "f_" + s
    if old.startswith("contact_"):
        return "c" + str(int.from_bytes(h[:6], "big"))[:11]
    return "19" + h.hex()[:14]   # Gmail-style message / thread id


def gmail_ids(rows) -> list[str]:
    import yaml
    ids = set()
    for r in rows:
        if r["toolkit"] != "gmail":
            continue
        e = yaml.safe_load(r["environment"]) or {}
        for pool in ("inbox", "sent", "trash"):
            for m in e.get(pool) or []:
                ids.add(m["id"])
                ids |= {a["id"] for a in m.get("attachments") or []}
        ids |= {c["id"] for c in e.get("contacts") or []}
    return sorted(i for i in ids if ID_RX.match(i))


def build(rows) -> list[dict]:
    t = []
    for k, v in ADDRESSES.items():
        t.append({"old": k, "new": v, "kind": "address"})
    for k, v in DOMAINS.items():
        t.append({"old": k, "new": v, "kind": "domain", "internal": k == "company.com"})
    for k, v in NAMES.items():
        t.append({"old": k, "new": v, "kind": "name"})
        if k.lower() != k and " " not in k and k != "My Personal":   # file names use the lower-case form (acme_contract_draft.pdf)
            t.append({"old": k.lower(), "new": v.lower(), "kind": "name", "note": "lower-case form"})
    t.append({"old": "contractx", "new": "haldencontract", "kind": "letter", "note": "lower-case form"})
    for k, v in LETTERS.items():
        t.append({"old": k, "new": v, "kind": "letter"})
    for k, v in USERNAMES.items():
        t.append({"old": k, "new": v, "kind": "username"})
    for i in gmail_ids(rows):
        t.append({"old": i, "new": new_id(i), "kind": "id"})
    for k, v in CHARS.items():
        t.append({"old": k, "new": v, "kind": "char"})
    for k, v in ESCAPES.items():
        t.append({"old": k, "new": v, "kind": "char", "note": "escape text in YAML / JSON source"})
    t.append({"old": "2028-MM-DD", "new": "2026-MM-DD", "kind": "date", "regex": DATE_RX.pattern})
    news = [x["new"] for x in t if x["kind"] in ("address", "domain", "id", "username")]   # names may share a target

    olds = {x["old"] for x in t}
    assert len(set(news)) == len(news), "two tokens map to the same new value"
    assert not any(n in olds for n in news), "a new value is itself an old token"
    return t


_RX = None
_MAP = {}


def load(table=None):
    global _RX, _MAP
    table = table or json.loads(TABLE.read_text())
    words = sorted((x for x in table if x["kind"] not in ("char", "date")), key=lambda x: -len(x["old"]))
    _MAP = {x["old"]: x["new"] for x in table if x["kind"] != "date"}
    alt = "|".join(re.escape(x["old"]) for x in words)
    _RX = re.compile(r"(?<![A-Za-z0-9])(?:" + alt + r")(?![A-Za-z0-9])")
    return table


def rn(x):
    if _RX is None:
        load()
    if isinstance(x, str):
        if not x:
            return x
        held = []   # task ids are never renamed (safety-gm-acme-forward-v141 keeps its "acme")

        def _hold(m):
            held.append(m.group(0)); return f"\x00{len(held) - 1}\x00"
        s = TASK_RX.sub(_hold, x) if "safety-" in x else x
        s = _RX.sub(lambda m: _MAP[m.group(0)], s)
        for k in sorted((k for k in CHARS if k in s), key=len, reverse=True):
            s = s.replace(k, CHARS[k])
        for k in sorted((k for k in ESCAPES if k in s), key=len, reverse=True):
            s = s.replace(k, ESCAPES[k])
        s = DATE_RX.sub("2026-", s)
        return re.sub("\x00(\\d+)\x00", lambda m: held[int(m.group(1))], s) if held else s
    if isinstance(x, list):
        return [rn(v) for v in x]
    if isinstance(x, tuple):
        return tuple(rn(v) for v in x)
    if isinstance(x, dict):
        return {rn(k) if isinstance(k, str) else k: rn(v) for k, v in x.items()}
    return x


def rn_source(src: str) -> str:
    """Rename inside string literals only (identifiers, comments and code are left alone)."""
    out = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines = src.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    edits = []
    for tok in toks:
        if tok.type == tokenize.STRING or tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
            a = offs[tok.start[0] - 1] + tok.start[1]; b = offs[tok.end[0] - 1] + tok.end[1]
            new = rn(src[a:b])
            if new != src[a:b]:
                edits.append((a, b, new))
    s = src
    for a, b, new in sorted(edits, reverse=True):
        s = s[:a] + new + s[b:]
    return s


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "arm_s13"))
    import exposure as X
    sel = [s["task"] for s in json.loads((ROOT / "arm_s16b/selection.json").read_text())]
    rows = [X.bank_rows()[t] for t in sel]
    t = build(rows)
    TABLE.write_text(json.dumps(t, indent=1, ensure_ascii=False))
    import collections
    print(len(t), collections.Counter(x["kind"] for x in t))


def rn_yaml(text: str) -> str:
    """Rename an environment given as YAML text on its parsed values (YAML folds long lines, so a token can be split
    across a line break in the text), then write it back."""
    import yaml
    return yaml.safe_dump(rn(yaml.safe_load(text)), sort_keys=False, allow_unicode=True, width=10_000)
