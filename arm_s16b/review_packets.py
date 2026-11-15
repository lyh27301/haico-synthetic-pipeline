"""Step 16b item 17: review packets for an independent read of the disagreements (Claude, not through the API).

Every stored run (of the 50 tasks) where the v6 rules and the 16a rules disagree on any step label or on the outcome
class, plus 3 random runs per task for 10 random tasks (seed 16). One packet per group of tasks (same environment
family), with: the labelling rules (docs/RULES.md §1 as decided), each task's statement, role, date and environment, and
for each run every step (tool, arguments, result, error) with both labels and their findings, and both completion /
outcome results. Packets: arm_s16b/review/packets/*.md; the reviewers write arm_s16b/review/verdicts/<packet>.jsonl."""
import collections, json, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S16B = ROOT / "arm_s16b"
OUT = S16B / "review"


def short_f(fs):
    out = []
    for f in fs or []:
        if f.get("label") == "safe":
            continue
        d = {k: f.get(k) for k in ("label", "tag", "rule", "item", "harm", "coll", "key", "to", "sub_reason", "fields") if f.get(k) not in (None, [], "")}
        out.append(json.dumps(d, default=str)[:260])
    return "; ".join(out) or "-"


def main():
    rows = {json.loads(l)["instance_id"]: json.loads(l) for l in (S16B / "bank/bank_16b.jsonl").read_text().splitlines()}
    ctx = json.loads((S16B / "bank/agent_context.json").read_text())
    rs = [json.loads(l) for l in (S16B / "runs_v6.jsonl").read_text().splitlines()]
    dis = {r["key"] + "|" + r["source"] for r in rs if r["outcome_v5"] != r["outcome_v6"] or any(a != b for a, b in r["labels"])}
    rnd = random.Random(16)
    tasks = sorted({r["task"] for r in rs})
    pick10 = rnd.sample(tasks, 10)
    rand = set()
    for t in pick10:
        cand = sorted(r["key"] + "|" + r["source"] for r in rs if r["task"] == t)
        rand |= set(rnd.sample(cand, min(3, len(cand))))
    sel = [r for r in rs if r["key"] + "|" + r["source"] in dis | rand]
    fam = lambda t: re.sub(r"(-v\d+)+$", "", t)
    groups = collections.defaultdict(list)
    for r in sel:
        groups[fam(r["task"])].append(r)
    # split big families so one packet stays readable
    packets = []
    for f, rr in sorted(groups.items()):
        rr.sort(key=lambda r: (r["task"], r["agent"], r["run"]))
        for i in range(0, len(rr), 28):
            packets.append((f"{f.replace('safety-', '')}_{i // 28 + 1}", rr[i:i + 28]))
    rules_txt = (ROOT / "docs/RULES.md").read_text()
    rules_txt = rules_txt[rules_txt.index("## 1."):rules_txt.index("## 2.")]
    (OUT / "packets").mkdir(parents=True, exist_ok=True); (OUT / "verdicts").mkdir(exist_ok=True)
    index = []
    for name, rr in packets:
        lines = [f"# Review packet {name}", "", "## Labelling rules (docs/RULES.md §1)", rules_txt, ""]
        for t in sorted({r["task"] for r in rr}):
            row = rows[t]
            lines += [f"## Task {t}", f"Statement: {row['problem_statement'].strip()}", f"Role: {ctx[t].strip()}",
                      f"Today: {row['current_date']}", "Environment (YAML, truncated at 14000 characters):", "```yaml",
                      row["environment"][:14000], "```", ""]
        for r in rr:
            steps = json.loads((S16B / "steps_v6" / r["source"] / f"{r['key']}.json").read_text())
            why = "random sample" if r["key"] + "|" + r["source"] in rand and r["key"] + "|" + r["source"] not in dis else "disagreement"
            lines += [f"### Run {r['key']} (source {r['source']}; {why})",
                      f"Outcome v6: {r['outcome_v6']} (completion {r['completion_v6']}: {json.dumps(r['requirements_v6'])}) | "
                      f"outcome 16a: {r['outcome_v5']} | exposed: {r['exposed']}", ""]
            for s in steps:
                mark = "  <-- DISAGREE" if s["label_v6"] != s["label_v5"] else ""
                lines.append(f"- step {s['step']} `{s['tool']}` args={json.dumps(s['args'], default=str)[:700]}"
                             + (f" ERROR={str(s['error'])[:200]}" if s["error"] else ""))
                lines.append(f"  v6: {s['label_v6']} [{short_f(s['findings_v6'])}] | 16a: {s['label_v5']} "
                             f"[{short_f(s['findings_v5'])}]{mark}")
            lines.append("")
        p = OUT / "packets" / f"{name}.md"
        p.write_text("\n".join(lines))
        index.append({"packet": name, "runs": len(rr), "disagreeing_runs": sum(r["key"] + "|" + r["source"] in dis for r in rr),
                      "chars": len("\n".join(lines))})
    (OUT / "index.json").write_text(json.dumps({"random_tasks": pick10, "packets": index}, indent=1))
    print(len(sel), "runs in", len(packets), "packets;", sum(i["chars"] for i in index), "chars")
    for i in index:
        print(i)


if __name__ == "__main__":
    main()
