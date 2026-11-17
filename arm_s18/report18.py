"""Step 18: assemble analysis/step18.md from the family notes (arm_s18/notes/*.md), the Part B scan
(arm_s18/scan.json + the hand review arm_s18/scan_review.json), the chat_npc finding and the Part C change.
No model calls.   .venv/bin/python arm_s18/report18.py"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S18 = ROOT / "arm_s18"
sys.path.insert(0, str(S18))
ORDER = ["sq-embargo-archive", "ev-petri-attorney-archive", "gm-deploy-key-zip", "fn-venmo-anonymity", "fn-consolidate-vendors",
         "sq-dedupe-cas", "md-jonathan-medlist", "cm-legacy-draft-delete", "md-maria-lopez", "sq-petri-grant-wildcard-access",
         "fn-payroll-reroute"]
CAT = {"produce_vs_send": "Requests that name one file to produce and a different one to send",
       "user_instructed": "Unsafe action exactly what the user explicitly asked for (to be tagged user_instructed)",
       "ids_for_content": "A record of ids stands in for an export or archive; no real content moves",
       "no_tool": "Asks for an operation no tool can do",
       "safe_copy": "A ready-made safe copy in the environment",
       "synthetic": "Remaining synthetic traces (555 numbers, sequential ids, placeholder / simulated content)"}


def main(extra: dict):
    L = []; w = L.append
    tasks = sorted(p.stem for p in (S18 / "bank/tasks").glob("*.json"))
    w("# Step 18: task fixes for the 12 trial tasks' families, bank scan, canned user reply\n")
    w("Date: 2026-11-17. This step changes tasks and writes the changes up for review. No agent was run, no grader rule "
      "was written, no API was called. Old versions are kept unchanged in `arm_s16b/bank`; the new versions are in "
      f"`arm_s18/bank/tasks/` ({len(tasks)} tasks) with their staged files in `arm_s18/bank/files/`, and "
      "`arm_s18/bank/bank_18.jsonl` / `bank_18_harness.jsonl` / `agent_context_18.json` hold the 50 old rows plus the new "
      "ones (built by `arm_s18/lib.py build()`). Every new row has `task_version` 0.18, `derived_from` and a step-18 entry "
      "per change in `task_changes`. Both references of every new task were played on the real toolkit with no tool error "
      "(`lib.validate`), and `lib.synthetic` is clean on every new task unless the family notes say otherwise.\n")
    w("How the work was done: one worker per toolkit group (sqldb; evidence; gmail / commerce / medical; finance) under a "
      "common brief (`arm_s18/BRIEF.md`), all with the same helper (`arm_s18/lib.py`). I reviewed their notes and spot-checked "
      "the rows; the notes below are theirs, unedited except where marked. Build scripts: `arm_s18/scripts/`, "
      "`arm_s18/notes/*_build.py`.\n")
    w("## Summary\n")
    w(extra.get("summary", "") + "\n")
    w("## Harness changes made in this step\n")
    w(extra.get("harness", "") + "\n")
    w("## Part A: changed tasks\n")
    w("New task ids:\n")
    w("\n".join(f"- `{t}`" for t in tasks) + "\n")
    for fam in ORDER:
        f = S18 / "notes" / f"{fam}.md"
        w(f"### {fam}\n")
        if not f.exists():
            w("(no notes file: see Open problems)\n"); continue
        txt = f.read_text().strip()
        lines = txt.splitlines()
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        w("\n".join(("##" + l if l.startswith("#") else l) for l in lines).strip() + "\n")
    w("## chat_npc (item 10)\n")
    w(extra.get("chat_npc", "") + "\n")
    w("## Part B: bank scan (report only, nothing changed)\n")
    s = json.loads((S18 / "scan.json").read_text()); rv = json.loads((S18 / "scan_review.json").read_text())
    w("Scope: the 50 tasks of `arm_s16b/bank/bank_16b.jsonl` (the old versions; the new versions are fixed by Part A where "
      "they are in the 11 families). Candidates come from code (`arm_s18/scan.py`); categories that need judgment were "
      "confirmed by reading each candidate (`arm_s18/scan_review.json`).\n")
    for k, title in CAT.items():
        rows = s[k]
        if k in rv:
            conf = [t for t, (ok, _) in rv[k].items() if ok]
            w(f"**{title}**: {len(conf)} confirmed of {len(rows)} candidates.\n")
            w("| task | confirmed | reason |\n|---|---|---|")
            for t, (ok, why) in sorted(rv[k].items()):
                w(f"| {t.removeprefix('safety-')} | {'yes' if ok else 'no'} | {why} |")
            w("")
        elif k == "safe_copy":
            fp = rv.get("safe_copy_false_positives", {})
            real = [x for x in rows if x["task"] not in fp]
            w(f"**{title}**: {len(real)} tasks (code; {len(fp)} false positive removed by reading).\n")
            w("| task | item |\n|---|---|")
            for x in real:
                w(f"| {x['task'].removeprefix('safety-')} | {', '.join(sorted(set(i.rsplit('/', 1)[-1] for i in x['items'])))[:160]} |")
            for t, why in fp.items():
                w(f"| ~~{t.removeprefix('safety-')}~~ | not a safe copy: {why} |")
            w("")
        else:
            w(f"**{title}**: {len(rows)} tasks (code).\n")
            w("| task | 555 numbers | sequential ids | placeholder |\n|---|---|---|---|")
            for x in rows:
                seq = "; ".join(f"{p}: {v[:5]}" for p, v in (x.get("sequential ids") or {}).items())
                w(f"| {x['task'].removeprefix('safety-')} | {len(x.get('555 number') or [])} | {seq[:120]} | "
                  f"{', '.join(x.get('placeholder') or [])[:80]} |")
            w("")
    w("## Part C: canned user reply\n")
    w(extra.get("part_c", "") + "\n")
    w("## Could not fix under the rules / open problems\n")
    w(extra.get("open", "") + "\n")
    (ROOT / "analysis/step18.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/step18.md", len("\n".join(L)))


if __name__ == "__main__":
    main(json.loads((S18 / "report_extra.json").read_text()))
