"""Step 13i: apply the norm-grounding audit (arm_s13/norm_audit.jsonl, from arm_s13/norm_audit.py).
  bank      arm_v08/bank_v08.jsonl gets `qualified` (true / false / null for pending) and `qualified_status`
            (qualified | unqualified | pending) on every row; nothing else in a row changes, no row is removed;
  pilot     arm_s13/pilot13i_drop.json (pilot v2 tasks to replace: unqualified + class iii) and
            arm_s13/pilot13i_exclude.json (never used as a replacement: unqualified, pending, class iii);
  tables    arm_s13/norm13i.json: counts by toolkit and family, the ungrounded list, the candidate list.
  .venv/bin/python arm_s13/norm13i.py bank | pilot | tables"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"; BANK = ROOT / "arm_v08/bank_v08.jsonl"


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def audit():
    return {o["task"]: o for o in jl(S13 / "norm_audit.jsonl")}


def bank():
    A = audit(); out = []
    for ln in BANK.read_text().splitlines():
        r = json.loads(ln); st = A[r["instance_id"]]["status"]
        # pending (empirical candidate) -> null; repaired tasks stay false until their re-roll is graded (step 13j)
        r["qualified"] = {"qualified": True, "unqualified": False, "removed": False, "repaired_pending_check": False,
                          "repaired_failed": False}.get(st)
        r["qualified_status"] = st
        out.append(json.dumps(r, ensure_ascii=False))
    BANK.write_text("\n".join(out) + "\n")
    print(collections.Counter(json.loads(l)["qualified_status"] for l in out))


def pilot():
    A = audit(); ex = json.loads((S13 / "exposure13h.json").read_text())
    iii = set(ex["class_iii"]) | {t for t in A if "dedupe-cas-preserve-control" in t and
                                   (ex["exposure_by_task"].get(t) or {}).get("class") == "iii"}
    unq = {t for t, o in A.items() if o["status"] == "unqualified"}
    pend = {t for t, o in A.items() if o["status"] == "pending"}
    (S13 / "pilot13i_drop.json").write_text(json.dumps(sorted(unq | iii), indent=1))
    (S13 / "pilot13i_exclude.json").write_text(json.dumps(sorted(unq | pend | iii), indent=1))
    print(len(unq | iii), "drop;", len(unq | pend | iii), "exclude")


def tables():
    A = audit()
    tk = collections.defaultdict(collections.Counter); fam = collections.defaultdict(lambda: collections.Counter())
    for o in A.values():
        tk[o["toolkit"]][o["source_type"]] += 1; tk[o["toolkit"]][o["status"]] += 1
        fam[o["family"]][o["status"]] += 1
    res = {"by_toolkit": {k: dict(v) for k, v in sorted(tk.items())},
           "status": dict(collections.Counter(o["status"] for o in A.values())),
           "source_type": dict(collections.Counter(o["source_type"] for o in A.values())),
           "instructed_harm": sum(o["instructed_harm"] for o in A.values()),
           "instructed_by_source": dict(collections.Counter(o["source_type"] for o in A.values() if o["instructed_harm"])),
           "families": {f: dict(c) for f, c in sorted(fam.items())},
           "mixed_families": {f: dict(c) for f, c in sorted(fam.items()) if len(c) > 1},
           "ungrounded": [{k: o[k] for k in ("task", "family", "toolkit", "instructed_harm", "convention", "harm_action",
                                             "status", "empirical")} for o in A.values() if not o["grounded"]],
           "candidates": [o["task"] for o in A.values() if o["status"] == "pending"]}
    (S13 / "norm13i.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("status", "source_type", "instructed_harm", "instructed_by_source")}))


if __name__ == "__main__":
    {"bank": bank, "pilot": pilot, "tables": tables}[sys.argv[1]]()
