"""Step 18 Part B: scan the whole 16b bank (arm_s16b/bank/bank_16b.jsonl, 50 tasks; read only) for the problems found in
steps 17 / 17b. Code finds candidates; categories that need judgment are confirmed by reading (arm_s18/scan_review.json,
written by hand) and the report says which is which.
  1 produce_vs_send     the statement names one file to produce and a different file to send
  2 user_instructed     the unsafe action is exactly what the user explicitly asked for (candidate: the violator's
                        pivotal call targets a recipient / file / record the statement names)
  3 ids_for_content     a record of ids stands in for an export / archive and no real content moves (candidate: the
                        statement asks for an archive / bundle / export, the task has no staged files, and the pivotal
                        violator call writes only a text row)
  4 no_tool             the statement asks for an operation no tool of the toolkit can do (send / email / notify in a
                        toolkit with no send tool; grader/toolkit_events.py)
  5 safe_copy           a ready-made safe copy in the environment or the staged files (redacted / sanitized / reviewed /
                        anonymized / clean / public / safe / summary-only variant of another item)
  6 synthetic           555 numbers, neat sequential ids, placeholder / simulated content (arm_s18/lib.synthetic)
  .venv/bin/python arm_s18/scan.py  ->  arm_s18/scan.json"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "arm_s18"), str(ROOT / "grader")]
import lib as L  # noqa: E402
import toolkit_events as TE  # noqa: E402

FILE = re.compile(r"[\w.-]+\.(?:csv|pdf|xlsx|zip|docx|txt|json|png)\b", re.I)
PRODUCE = re.compile(r"(?i)\b(produce|create|build|generate|compile|prepare|make|write)\b")
SEND = re.compile(r"(?i)\b(send|email|forward|share|upload|attach|deliver)\b")
SENDWORD = re.compile(r"(?i)\b(send|email|e-mail|notify|message|reply|forward)\b")
ARCH = re.compile(r"(?i)\b(archive|bundle|export|package|zip)\b")
SAFE = re.compile(r"(?i)(redact|saniti|reviewed|anonymi|deidentif|de-identif|_clean|clean_|_public|public_|_safe\b|summary_only|_external)")


def files_of(r):
    return [s.split("/workspace/", 1)[1] for s in r.get("workspace_files") or []]


def main():
    ev = TE.build()
    rows = L.old_rows()
    res = {k: [] for k in ("produce_vs_send", "user_instructed", "ids_for_content", "no_tool", "safe_copy", "synthetic")}
    for t, r in sorted(rows.items()):
        st = r["problem_statement"]
        names = sorted(set(FILE.findall(st)))
        if len(names) >= 2 and PRODUCE.search(st) and SEND.search(st):
            res["produce_vs_send"].append({"task": t, "files": names})
        piv = next((s for s in r.get("violator_reference") or [] if s.get("pivotal")), None)
        if piv:
            a = json.dumps(piv.get("args"), ensure_ascii=False)
            named = [x for x in re.findall(r"[\w.+-]+@[\w.-]+|[\w.-]+\.(?:csv|pdf|xlsx|zip|docx|txt)|\b[A-Z]{1,5}-?\d{2,6}\b", a)
                     if x in st]
            if named:
                res["user_instructed"].append({"task": t, "pivotal_tool": piv["tool"], "named_in_statement": sorted(set(named))})
        if ARCH.search(st) and not r.get("workspace_files") and piv and (
                "insert" in json.dumps(piv.get("args")).lower() or "export" in piv["tool"].lower()):
            res["ids_for_content"].append({"task": t, "pivotal_tool": piv["tool"]})
        tk = r["toolkit"]
        if SENDWORD.search(st) and not ev[tk]["events"].get("send"):
            res["no_tool"].append({"task": t, "toolkit": tk, "phrase": SENDWORD.search(st).group(0)})
        fs = files_of(r)
        envtxt = r["environment"]
        hits = sorted({f for f in fs if SAFE.search(f)} | set(m.group(0) for m in re.finditer(
            r"[\w./-]*(?:redact|saniti|anonymi|reviewed)[\w./-]*", envtxt, re.I)))
        if hits:
            res["safe_copy"].append({"task": t, "items": hits[:8]})
        rr = dict(r); rr["_files"] = {p: (ROOT / "arm_s16b/bank" / s).read_bytes() for p, s in zip(fs, r.get("workspace_files") or [])
                                      if (ROOT / "arm_s16b/bank" / s).exists()}
        syn = L.synthetic(rr)
        if any(syn.values()):
            res["synthetic"].append({"task": t, **{k: v for k, v in syn.items() if v}})
    (ROOT / "arm_s18/scan.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    for k, v in res.items():
        print(k, len(v), [x["task"].removeprefix("safety-") for x in v][:60])


if __name__ == "__main__":
    main()
