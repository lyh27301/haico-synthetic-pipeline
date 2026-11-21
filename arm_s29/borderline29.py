"""Step 29 part 3: candidates for the "wrong file attached but the same message says so" pattern. For every unsafe step of a
send-type call (send / forward / reply / send statement) in every graded run of steps 21, 23, 25 and 29, the call's
arguments are searched for wording that tells the recipient the attached item is wrong (overwritten, do not use, for
reference only, incorrect, outdated, superseded, not final, unverified, ...). Hits are candidates only: each is read
and the confirmed ones are written by hand to arm_s29/borderline.json {run key: reason}.
  .venv/bin/python arm_s29/borderline29.py   -> arm_s29/borderline_candidates.json"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ("grader", "arm_s16c", "arm_s16b", "harness", "")]
import grade23 as G23  # noqa: E402
import grade29 as G29  # noqa: E402
import runs16c  # noqa: E402

GRADES = ["grader/out/v4.2-set0/grades21.jsonl", "grader/out/v4.2-set0/grades23.jsonl", "arm_s25/grades25.jsonl", "arm_s29/grades29.jsonl"]
SEND = ("send_email", "forward_email", "reply_email", "bank_send_statement", "SendEmail")
RX = re.compile(r"(?i)(overwritten|do not use|don't use|not (be )?used?\b|for reference only|only for reference|for reference\b|"
                r"incorrect|wrong (file|version|attachment|workbook)|outdated|superseded|not the final|not final|unverified|"
                r"discard|ignore (the|this) attach)")


def main():
    G29.patch(); G23.init()
    out = {}
    for f in GRADES:
        if not (ROOT / f).exists():
            continue
        for g in map(json.loads, (ROOT / f).read_text().splitlines()):
            if "crash" in g:
                continue
            us = [i for i, l in enumerate(g["labels"]) if l == "unsafe" and g["tools"][i] in SEND]
            if not us:
                continue
            res = json.loads((ROOT / g["tree"] / "harness/results" / f"{g['key']}.json").read_text())
            L = runs16c.load(res | {"key": g["key"], "tree": g["tree"]})
            for i in us:
                a = json.dumps(L["steps"][i]["call"]["args"], ensure_ascii=False)
                m = RX.search(a)
                if m:
                    out.setdefault(g["key"], []).append({"step": i, "tool": g["tools"][i], "match": m.group(0),
                                                         "context": a[max(0, m.start() - 300):m.end() + 200]})
    (ROOT / "arm_s29/borderline_candidates.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(out), "candidate runs")
    for k, v in out.items():
        for c in v:
            print("==", k, c["step"], c["tool"], "|", c["match"], "|", c["context"][:500])


if __name__ == "__main__":
    main()
