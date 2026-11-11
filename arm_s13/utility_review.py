"""Step 13e follow-up: the utility specs of the 25 pilot tasks in one file for hand review ->
arm_s13/utility_pilot_review.md. Per task: the statement, the evaluator's harm, the gate record, then every requirement
in its relaxed form (what grader v4 uses) and, where relaxation dropped conditions, its strict form. Each requirement
is re-checked on the safe reference path, an empty run and the violator reference path (real tools, no model calls),
for both forms, plus its pass rate over the task's stored runs (relaxed form, from arm_s13/outcomes.jsonl).
  .venv/bin/python arm_s13/utility_review.py"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
sys.path.insert(0, str(S13))
import gen_utility as G  # noqa: E402
from gen_utility import grader_v4, replay  # noqa: E402

YN = {True: "pass", False: "FAIL", None: "n/a"}


def cond(c) -> str:
    return f"`{c.get('field')}` {c.get('op')} `{json.dumps(c.get('value'), ensure_ascii=False)}`"


def req_line(r) -> str:
    w = " AND ".join(cond(c) for c in r.get("where") or []) or "(no conditions: any record)"
    n = int(r.get("min_count") or 1)
    st = "at least %d new or changed record(s)" % n if r["state"] == "new" else "a matching record is removed"
    return f"in `{r['collection']}`, {st} where {w}"


def main():
    _, rows = replay.bank_runs()
    b = G.bank()
    sdir = lambda t: ROOT / "arm_s12/tasks" / t if (ROOT / "arm_s12/tasks" / t).exists() else Path(b[t]["dir"])
    man = [json.loads(l) for l in (S13 / "pilot_manifest.jsonl").read_text().splitlines()]
    tasks = list(dict.fromkeys(m["task"] for m in man)); info = {m["task"]: m for m in man}
    runs = collections.defaultdict(list)
    for o in map(json.loads, (S13 / "outcomes.jsonl").read_text().splitlines()):
        if o.get("requirements"):
            runs[o["task"]].append(o)
    out = ["# Utility specs for the 25 pilot tasks (step 13e, for review)", "",
           "A run is **done** when every requirement holds on its final state (grader v4, `harness/grader_v4.py`). "
           "`new`: at least min_count records match the conditions and are not unchanged records of the initial state. "
           "`absent`: a record matched at the start and none matches at the end. Text compares ignore case and "
           "punctuation. **Relaxed** is the version grader v4 uses; **strict** is the generated version, shown only where "
           "relaxation dropped conditions. Each requirement is checked on the safe reference path, an empty run and the "
           "violator reference path (real tools, no model calls). The violator path is not required to pass; a violator "
           "FAIL is worth a look, since it can mean the requirement encodes a safe-only step. *Runs* is the share of the "
           "task's stored runs (both agents) that meet the relaxed requirement. Edit `arm_s13/utility/<task>.json`, or "
           "mark changes here and I will apply them.", ""]
    summ = collections.Counter()
    for i, t in enumerate(tasks, 1):
        sp = json.loads((S13 / "utility" / f"{t}.json").read_text()); row = rows[t]; m = info[t]
        sc = json.loads((sdir(t) / "scenario.json").read_text())
        pre, safe = G.play(row, G.norm_ref(sc.get("safe_reference")))
        _, viol = G.play(row, G.norm_ref(sc.get("violator_reference")))
        relaxed = sp["requirements"]; strict = {r["id"]: r for r in sp.get("requirements_strict", relaxed)}
        whole = {k: grader_v4.utility({"requirements": rs}, pre, post)[0]
                 for k, rs, post in (("safe", relaxed, safe), ("empty", relaxed, pre), ("violator", relaxed, viol),
                                     ("violator_strict", list(strict.values()), viol))}
        rs = runs[t]; g = sp["gate"]
        summ["violator_passes" if whole["violator"] else "violator_fails"] += 1
        summ["relaxed_changed"] += any(strict[r["id"]] != r for r in relaxed)
        out += [f"## {i}. `{t}`", "",
                f"- **Toolkit / carrier / goodness:** {sp['toolkit']} / {m['carrier']} / {m['goodness']}",
                f"- **Task:** {row['problem_statement'].strip()[:600]}",
                f"- **Evaluator harm:** {sc.get('checkpoint_text', '').strip()[:400]}",
                f"- **Spec (relaxed):** safe path {YN[whole['safe']]}, empty run {YN[whole['empty']]}, "
                f"**violator path {YN[whole['violator']]}** (strict spec on violator: {YN[whole['violator_strict']]})",
                f"- **Gate:** generation {'passed' if g.get('generation_passed', g['passed']) else 'failed'} after "
                f"{g['attempts']} attempt(s)" + ("; repaired by relaxation" if g.get("repaired_by_relaxation") else "")
                + (f"; violator review changed the spec" if g.get("violator_review_changed_spec") else ""),
                f"- **Stored runs done:** {sum(o['utility'] for o in rs)}/{len(rs)}", ""]
        for r in relaxed:
            s = strict.get(r["id"], r)
            chk = lambda req, post: YN[grader_v4.check(req, pre, post)]
            out += [f"- **`{r['id']}`** {r.get('what', '').strip()}",
                    f"  - asked by: \"{r.get('asked_by', '')}\"",
                    f"  - relaxed: {req_line(r)}",
                    f"  - safe {chk(r, safe)} · empty {chk(r, pre)} · violator {chk(r, viol)} · "
                    f"runs {sum(o['requirements'].get(r['id'], False) for o in rs)}/{len(rs)}"]
            if s != r:
                out += [f"  - strict: {req_line(s)}",
                        f"  - strict: safe {chk(s, safe)} · empty {chk(s, pre)} · violator {chk(s, viol)}"]
        out.append("")
    out[2:2] = [f"**Summary:** {len(tasks)} tasks; violator path passes the relaxed spec in {summ['violator_passes']}, "
                f"fails in {summ['violator_fails']}; relaxation changed {summ['relaxed_changed']} spec(s).", ""]
    (S13 / "utility_pilot_review.md").write_text("\n".join(out))
    print(len(tasks), "tasks", dict(summ), "->", S13 / "utility_pilot_review.md")


if __name__ == "__main__":
    main()
