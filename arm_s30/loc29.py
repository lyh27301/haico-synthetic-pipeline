"""Prohibition locations of step 29's -v29 tasks for the step-30 texts (no model call).
A -v29 version keeps the trap of the version it was derived from (step 29: "The trap is unchanged in every task"), so
its row is that version's row of arm_s30/source/prohibition_location.jsonl (step 25's labels), followed along the
derived_from chain of arm_s29/bank/bank_29.jsonl, marked inherited_from. Every quoted prohibition (each piece of a
multi-part quote) is checked to be present, word for word, in the -v29 task row or its staged files; a missing piece
stops the script. Tasks still on the repair list after step 29 part 2 (arm_s29/repair_after_part2.json) are not
branched and are left out.
  .venv/bin/python arm_s30/loc29.py   -> arm_s30/source/prohibition_location_v29.jsonl"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S = ROOT / "arm_s30"


def main():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_s29/bank/bank_29.jsonl").read_text().splitlines()}
    P = {json.loads(l)["task"]: json.loads(l) for l in (S / "source/prohibition_location.jsonl").read_text().splitlines()}
    repair = json.loads((ROOT / "arm_s29/repair_after_part2.json").read_text())
    out, bad = [], []
    for t, r in sorted(rows.items()):
        if t in repair:
            continue
        s = r["derived_from"]
        while s not in P:
            s = rows[s]["derived_from"]
        blob = json.dumps(r, ensure_ascii=False).replace('\\"', '"').replace("\\n", "\n")
        d = ROOT / "arm_s29/bank/files" / t
        if d.exists():
            blob += "".join(f.read_text(errors="ignore") for f in d.rglob("*") if f.is_file())
        for x in P[s]["traps"]:
            q = x["quote"].strip('“”"')
            if q.startswith("common sense") or x["quote"].startswith("(description quote)"):
                continue
            bad += [(t, x["trap"], p) for p in re.split(r'"; "|; ', q) if p not in blob]
        out.append(P[s] | {"task": t, "inherited_from": s})
    if bad:
        sys.exit(f"quote pieces not found in the -v29 environment: {bad}")
    (S / "source/prohibition_location_v29.jsonl").write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out))
    print(len(out), "rows -> arm_s30/source/prohibition_location_v29.jsonl; every quote piece found")


if __name__ == "__main__":
    main()
