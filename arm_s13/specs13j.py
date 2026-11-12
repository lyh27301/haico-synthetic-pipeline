"""Step 13j item 1: regenerate and re-validate the specs of the 18 repaired tasks (task_version 0.10 in
arm_v08/bank_v08.jsonl, scenario copies in arm_s13j/tasks/). Each phase runs the step-13 generator on the repaired
bank row and scenario, with the generator's own deterministic gates:
  probes    arm_s13/gen_probes.py one(): union of rounds r1..r11 plus one new model round (monotone, as before);
            the round is also stored under arm_s13/probes_rounds/r12/;
  utility   arm_s13/gen_utility.py one(): safe reference path passes, empty run fails, schema / grounding gates;
  exposure  arm_s13/gen_exposure.py one() (+ self-describing names): fires on the safe reference path, not on an
            empty run, specific;
  audit     arm_s13/norm_audit.py: the 18 tasks re-audited (cached answers removed), then `reverify` for all;
  validate  every check in one table -> arm_s13/specs13j.json: utility safe passes / empty fails, grader v2 safe on the
            safe reference path and unsafe on the violator path, probe gate passed and no probe firing on the safe
            path, exposure rule valid, norm-audit class stated (string-verified quote) or common sense (and, for the three
            environment repairs, a quote from the added text).
OpenAI spend is logged by each generator to its usage log; this run's deltas are summed in `validate`.
  .venv/bin/python arm_s13/specs13j.py probes|utility|exposure|audit|validate"""
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"; NEW = ROOT / "arm_s13j/tasks"
for p in ("", "analysis", "arm_s10", "harness", "arm_s13"):
    sys.path.insert(0, str(ROOT / p))
if "OPENAI_API_KEY" not in os.environ:   # read from the repo's .env by this process only
    for ln in (ROOT / ".env").read_text().splitlines():
        ln = ln.strip().removeprefix("export ")
        if ln.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = ln.split("=", 1)[1].strip().strip('"').strip("'")


def rows():
    return {json.loads(l)["instance_id"]: json.loads(l) for l in (ROOT / "arm_v08/bank_v08.jsonl").read_text().splitlines()}


def tasks():
    sel = os.environ.get("TASKS")   # optional subset (comma list), e.g. the role-mismatch repairs
    return sorted(t for t, r in rows().items() if r.get("task_version") == "0.10" and (not sel or t in sel.split(",")))


def ctx():
    return json.loads((ROOT / "harness/agent_context.json").read_text())


def probes():
    import gen_probes as P
    P.BASE = P.spent(); P.BUDGET = 1.0
    for l in (S13 / "replay_runs.jsonl").read_text().splitlines():
        r = json.loads(l)
        if "episode_unsafe" in r and not r["episode_unsafe"] and not r["ever_flagged"]:
            P.SAFE_RUNS.setdefault(r["task"], []).append(r)
    for t, steps in (json.loads(P.HINT_FILE.read_text()) if P.HINT_FILE.exists() else {}).items():
        P.HINT_STEPS[t] = [{"agent": ag, "run": k, "step": st} for ag, k, st in steps]
    R, C = rows(), ctx(); rounds = [f"r{i}" for i in range(1, 12)]
    (S13 / "probes_rounds/r12").mkdir(exist_ok=True)
    for t in tasks():
        st = P.one(t, R[t], NEW / t, C, rounds, True)
        shutil.copy(P.OUT / f"{t}.json", S13 / "probes_rounds/r12" / f"{t}.json")
        print(*st, f"${P.spent() - P.BASE:.3f}", flush=True)


def utility():
    import gen_utility as U
    U.BUDGET = U.spent() + 1.0
    R, C = rows(), ctx()
    for t in tasks():
        print(*U.one(t, R[t], NEW / t, C), f"${U.spent():.3f}", flush=True)


def exposure():
    import gen_exposure as X
    import exposure as E
    X.BUDGET = X.spent() + 1.0
    R, C = rows(), ctx()
    for t in tasks():
        f = E.EXPO / f"{t}.json"
        if f.exists():
            f.unlink()
        print(*X.one(t, R[t], C, [], recheck=False, names=True), f"${X.spent():.3f}", flush=True)


def audit():
    for t in tasks():
        f = S13 / "norm_audit" / f"{t}.json"
        if f.exists():
            f.unlink()
    py = str(ROOT / ".venv/bin/python")
    subprocess.run([py, str(S13 / "norm_audit.py"), "audit", "--tasks", ",".join(tasks())], check=True)
    subprocess.run([py, str(S13 / "norm_audit.py"), "reverify"], check=True)


ADDED = {"venmo-name-collision": "business payments only", "payroll-forward": "stays with payroll",
         "enrollment-placeholder-v121": "do not count as enrolled"}


def validate():
    import gen_utility as U
    import grader_v2, grader_v3
    import exposure as E
    R = rows(); out = {}
    for t in tasks():
        row, sc = R[t], json.loads((NEW / t / "scenario.json").read_text())
        u = json.loads((S13 / "utility" / f"{t}.json").read_text())
        pr = json.loads((S13 / "probes" / f"{t}.json").read_text())
        ex = json.loads((E.EXPO / f"{t}.json").read_text())
        na = json.loads((S13 / "norm_audit" / f"{t}.json").read_text())

        def run(ref):
            prof, env, rt = U.fresh(row); pre = U.replay.rt(prof.env_to_dict(env)); calls = []
            for s in U.norm_ref(ref):
                name = grader_v3.tool_name(s.get("tool"))
                if name in rt.functions:
                    res = rt.run_function(env, name, dict(s.get("args") or {}))
                    calls.append({"name": name, "args": dict(s.get("args") or {}),
                                  "result": res[0] if isinstance(res, tuple) else res})
            return pre, U.replay.rt(prof.env_to_dict(env)), calls
        pre, post_s, calls_s = run(sc.get("safe_reference"))
        _, post_v, calls_v = run(sc.get("violator_reference"))
        g_s = grader_v2.grade(row, pre, post_s, calls_s); g_v = grader_v2.grade(row, pre, post_v, calls_v)
        import grader_v4
        spec = {"requirements": u["requirements"]}   # replayed on the current scenario paths, not the gate's record
        u_safe, u_empty = grader_v4.utility(spec, pre, post_s)[0], grader_v4.utility(spec, pre, pre)[0]
        added = next((v for k, v in ADDED.items() if k in t), None)
        qs = [q["quote"] for q in na.get("quotes") or []]
        out[t] = {"utility_gate": u["gate"]["passed"], "utility_safe_passes": bool(u_safe),
                  "utility_empty_fails": not u_empty,
                  "v2_safe_path_safe": not g_s["unsafe"], "v2_violator_path_unsafe": bool(g_v["unsafe"]),
                  "probe_gate": pr["gate"]["passed"], "probe_coverage": pr.get("probe_coverage"),
                  "exposure_valid": ex["valid"], "exposure_safe_path_fires": ex["checks"].get("a_safe"),
                  "exposure_empty_fires": ex["checks"].get("c_empty_fires"), "exposure_failures": ex["failures"],
                  "norm_class": na["class"], "norm_quotes": qs,
                  "added_text_grounds": None if not added else any(added in E.norm(q) for q in qs)}
        o = out[t]
        o["all_pass"] = all([o["utility_gate"], o["utility_safe_passes"], o["utility_empty_fails"], o["v2_safe_path_safe"],
                             o["v2_violator_path_unsafe"], o["probe_gate"], o["exposure_valid"],
                             o["norm_class"] in ("stated", "common_sense"), o["added_text_grounds"] is not False])
    (S13 / "specs13j.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for t, o in out.items():
        print("PASS" if o["all_pass"] else "FAIL", t, {k: v for k, v in o.items() if v is False or (k == "norm_class" and v != "stated")})


if __name__ == "__main__":
    {"probes": probes, "utility": utility, "exposure": exposure, "audit": audit, "validate": validate}[sys.argv[1]]()
