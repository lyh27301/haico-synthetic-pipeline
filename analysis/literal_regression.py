"""Step 5 Part B regression: would the literal-completion gate have rejected the existing tasks?

For every step-3 (incl. the 7 step-2 tasks) and step-4 (Gmail, SQL) task: a task-writer (gpt-4o-mini, the gate's
GEN_MODEL) writes `literal_reference` for the task as it stands, then the real dry run executes it and the task's
own grader scores it. Two writer views:
  blind    - sees only the instruction, the environment data and the tools (no violator / grader / cue);
  informed - sees the whole task JSON, as the pipeline's task-writer does when it emits literal_reference.
A task is REJECTED when the grader scores 0 on the literal path (harm_not_on_literal_path). Literal steps that fail
to execute get one retry with the error; if they still fail the task is counted as `exec_error`, not rejected.
Results joined with the step-3/4 rollout classes (all_safe = all_safe under every agent run on it).

  python analysis/literal_regression.py   ->  analysis/literal_regression.json
"""
import collections, glob, json, os, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.setdefault("USAGE_LOG", str(ROOT / "arm_step5" / "b_regression_usage.jsonl"))
import driver  # noqa: E402
from recipe import pipeline as P  # noqa: E402

GROUPS = {"step3": "arm_eval3/results", "gmail_step4": "arm_gmail_c/eval/results", "sqldb_step4": "arm_sqldb_d/eval/results"}


def classes(results_dir):
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in glob.glob(str(ROOT / results_dir / "*.json")):
        r = json.loads(Path(f).read_text())
        if r.get("unsafe") != "":
            by[r["task"]][r["agent"]].append(r["unsafe"])
    b = lambda u: "all_unsafe" if all(u) else "all_safe" if not any(u) else "mixed"  # noqa: E731
    out = {}
    for t, d in by.items():
        per = {ag: b(u) for ag, u in d.items()}
        vals = set(per.values())
        out[t] = "mixed" if "mixed" in vals else vals.pop() if len(vals) == 1 else "split"
    return out, by


def task_dirs():
    dirs = {}
    for m in json.loads((ROOT / "analysis/step3_manifest.json").read_text()):
        dirs[m["task"]] = ("step3", ROOT / m["dir"])
    for g, arm in (("gmail_step4", "arm_gmail_c"), ("sqldb_step4", "arm_sqldb_d")):
        for d in sorted((ROOT / arm / "tasks").iterdir()):
            dirs[d.name] = (g, d)
    return dirs


def ask(prof, task, view, err=None):
    if view == "blind":   # identical prompt to the pipeline's independent literal writer
        return P._chat_json(*P.blind_literal_prompt(task, prof, err), "task")
    sysmsg, _ = P.blind_literal_prompt(task, prof)
    user = "TASK JSON: " + task.model_dump_json(exclude={"literal_reference"})[:12000]
    if err:
        user += f"\n\nYour previous literal_reference failed to execute: {err}. Fix the arguments."
    return P._chat_json(sysmsg, user, "task")


def one(name, group, d):
    prof = driver.profile_for(d)
    P.PROFILE = prof
    task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
    row = {"task": name, "group": group, "toolkit": prof.NAME, "instruction": task.problem_statement}
    for view in ("blind", "informed"):
        err, lit, score = None, None, None
        for _ in range(2):
            try:
                raw = ask(prof, task, view, err)
                t2 = prof.TASK_SCHEMA.model_validate({**json.loads(task.model_dump_json()), "literal_reference": raw.get("literal_reference", [])})
            except Exception as e:  # noqa: BLE001
                err = f"schema: {type(e).__name__}: {str(e)[:300]}"; continue
            lit = [s.model_dump() for s in t2.literal_reference]
            e2, score = P._run_literal(task, prof, lit)
            if e2:
                err = e2[:400]; score = None; continue
            err = None; break
        row[view] = {"score": score, "error": err, "literal_reference": lit,
                     "verdict": "exec_error" if score is None else "rejected" if score == 0 else "passes",
                     "equals_violator": lit is not None and [(s["tool"], s["args"]) for s in lit]
                     == [(s.tool, s.args) for s in task.violator_reference]}
    return row


def main():
    cls = {}
    for g, rd in GROUPS.items():
        c, _ = classes(rd); cls.update(c)
    dirs = task_dirs()
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda kv: one(kv[0], *kv[1]), sorted(dirs.items())))
    for r in rows:
        r["class"] = cls.get(r["task"], "not_run")
        r["step2"] = (ROOT / "arm_step2" / "tasks" / r["task"]).exists()
    summ = {}
    for view in ("blind", "informed"):
        for grp in ("all", "all_safe", "mixed", "all_unsafe"):
            sel = [r for r in rows if grp == "all" or r["class"] == grp]
            c = collections.Counter(r[view]["verdict"] for r in sel)
            summ[f"{view}/{grp}"] = {"n": len(sel), **c}
        for g in ("step3", "gmail_step4", "sqldb_step4"):
            sel = [r for r in rows if r["group"] == g and r["class"] == "all_safe"]
            summ[f"{view}/all_safe/{g}"] = {"n": len(sel), **collections.Counter(r[view]["verdict"] for r in sel)}
    out = {"summary": summ, "rows": rows}
    (ROOT / "analysis" / "literal_regression.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(summ, indent=1))
    for r in rows:
        print(f"{r['task']:45s} {r['group']:12s} {r['class']:10s} blind={r['blind']['verdict']:10s} informed={r['informed']['verdict']}")


if __name__ == "__main__":
    main()
