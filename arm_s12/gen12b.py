"""Step 12b: variant layer. New tasks = one-axis variants (recipe/variants.make_variant: same mechanic; domain, data or
persona changed; base values frozen) of the v0.6 mechanics, through
  1. the variant gate (full Stage-B task gate: 0/0/1, B1/B3, toolkit checks, writer + blind literal path) and the
     variant structure checks, one regeneration on failure;
  2. the harness discoverability gate (recipe/discover_gate.check with the agent role text, NPC reply for NPC tasks),
     one repair (as arm_s9/run_gate.py);
then emitted as a bank row (arm_hf/build_bank.row) into arm_s12/bank_12b.jsonl, plus its role text in
harness/agent_context.json. The novelty gate is on mechanics only and every variant shares its source's mechanic, so
it does not apply.

Sources: one per v0.6 mechanic (50): the mechanic's original task (else its first v0.6 task), in its harness version
(arm_s10/arm_s9 npc_tasks / tasks repairs, else the bank dir). Candidates per mechanic per batch = weight:
  w = 1 + [Petri seed] + 2 * [action-borne harm (delete / overwrite / grant)] + [toolkit outside gmail / sqldb]
(step 11: action-borne mechanics transfer worst between agents; commerce / evidence / finance / medical are thin).
Axis of candidate k: domain / data / persona in turn, from a per-source offset. Batch b uses seed 11 + b (ids
<source>-v<seed><k>).
  USAGE_LOG=arm_s12/gen_usage.jsonl .venv/bin/python arm_s12/gen12b.py --batch 1 [--workers 6] [--max N]
Outputs: arm_s12/variants.jsonl (one record per candidate, incl. gates), arm_s12/tasks/<id>/ (gated variants, with a
repaired instruction if the discoverability gate repaired it), arm_s12/bank_12b.jsonl, arm_s12/ids_b<batch>.txt."""
import argparse, collections, json, os, re, shutil, sys, threading, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S12 = ROOT / "arm_s12"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "arm_hf"))
os.environ.setdefault("USAGE_LOG", str(S12 / "gen_usage.jsonl"))
os.environ["GEN_MODEL"] = "gpt-5-mini"
import driver  # noqa: E402
from recipe import variants as V, discover_gate as D, gates  # noqa: E402
from bank import bank  # noqa: E402
from seed_source import seed_map, root  # noqa: E402
from build_bank import row  # noqa: E402

AXES12 = ("domain", "data", "persona")
SMALL = {"commerce", "evidence", "finance", "medical"}
VAR = re.compile(r"-(v\d\d\d?|sal-\w+)$")
LOCK = threading.Lock()
TASKS = S12 / "tasks"; LOG = S12 / "variants.jsonl"; BANK = S12 / "bank_12b.jsonl"
CTX_F = ROOT / "harness/agent_context.json"


def harness_dir(t: str, d: str) -> Path:
    for p in (ROOT / "arm_s10/npc_tasks" / t, ROOT / "arm_s10/tasks" / t, ROOT / "arm_s9/npc_tasks" / t,
              ROOT / "arm_s9/tasks" / t):
        if p.exists():
            return p
    return Path(d)


def sources() -> dict:
    b, sm = bank(), seed_map()
    hc = json.loads((ROOT / "arm_s11/harm_carrier.json").read_text())
    by = collections.defaultdict(list)
    for t in (ROOT / "arm_s11/ids_v06.txt").read_text().split():
        sc = json.loads((Path(b[t]["dir"]) / "scenario.json").read_text())
        by[sc.get("axes", {}).get("mechanic_id") or VAR.sub("", t)].append(t)
    out = {}
    for m, ts in sorted(by.items()):
        t = next((x for x in ts if x == m), None) or next((x for x in ts if not VAR.search(x)), ts[0])
        seed = sm.get(root(t)) or sm.get(t) or "unknown"
        tk, carrier = hc[t]["toolkit"], hc[t]["harm_carrier"]
        w = 1 + (seed == "Petri") + 2 * (carrier == "action") + (tk in SMALL)
        out[t] = {"mechanic": m, "dir": str(harness_dir(t, b[t]["dir"])), "toolkit": tk, "carrier": carrier,
                  "seed_source": seed, "weight": w, "v06_tasks": ts}
    return out


def axis12(src_id: str, k: int) -> str:
    return AXES12[(zlib.crc32(src_id.encode()) + k - 1) % len(AXES12)]


V.axis_for = axis12   # step 12: domain / data / persona only (no wording-only variants)


def role_text(d: Path, prof, task) -> str:
    env = prof.load_environment(d / "environment.yaml")
    return prof.agent_system(env) if hasattr(prof, "agent_system") else prof.AGENT_SYSTEM


def discover(d: Path, rec: dict) -> dict:
    """Harness discoverability gate + one repair (arm_s9/run_gate.py, arm_s9/gate_npc.py for NPC tasks)."""
    prof = driver.profile_for(d)
    task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
    env, role = str(d / "environment.yaml"), role_text(d, prof, task)
    instr = None
    sp = d / "scenarios.json"
    npc = json.loads(sp.read_text()) if sp.exists() else {}
    if npc.get("goal"):
        role += f"\n\n(Reply from {npc.get('name')} when messaged: {npc.get('strategy_hint')})"
        instr = re.sub(r"\s*\w+ is only reachable on chat.*?chat_npc\.", "", task.problem_statement)
    g = {"role": role}
    try:
        r1 = D.check(prof, task, env, role, instruction=instr)
    except Exception as e:  # noqa: BLE001
        r1 = {"ok": True, "reason": f"gate_crash {type(e).__name__}: {e}"}
    g["first"] = {k: r1.get(k) for k in ("ok", "reason", "targets", "found")}
    if r1["ok"]:
        g["status"] = "pass"; return g
    ps, fb = D.repair(prof, task, env, role, r1)
    r2 = D.check(prof, task, env, role, instruction=ps) if ps else {"ok": False, "reason": "repair_failed"}
    g.update(feedback=fb, repaired=ps, second={k: r2.get(k) for k in ("ok", "reason", "targets", "found")})
    t2 = prof.TASK_SCHEMA.model_validate({**json.loads(task.model_dump_json()), "problem_statement": ps}) if ps else None
    new_err = None
    if t2 is not None:
        before, after = gates.step7_errors(prof, task), gates.step7_errors(prof, t2)
        new_err = after if after and after != before else None
    g["step7_gate_after_repair"] = new_err
    if r2["ok"] and not new_err:
        g["status"] = "repaired"
        (d / "task.md").write_text(ps if ps.endswith("\n") else ps + "\n")
        sc = json.loads((d / "scenario.json").read_text()); sc["problem_statement"] = ps
        (d / "scenario.json").write_text(json.dumps(sc, indent=2))
    else:
        g["status"] = "undiscoverable"
    return g


def one(job, src):
    s, seed, k = job
    vid = f"{s}-v{seed}{k}"
    info = src[s]; d = Path(info["dir"])
    try:
        rec = V.make_variant(d, seed, k, S12)   # emit() writes <out>/tasks/<id>
    except Exception as e:  # noqa: BLE001
        rec = {"source": s, "variant": vid, "status": "failed", "err": f"crash: {type(e).__name__}: {e}"[:300], "trail": []}
    rec.update(mechanic=info["mechanic"], toolkit=info["toolkit"], carrier=info["carrier"],
               seed_source=info["seed_source"], batch=seed - 11)
    if rec["status"] == "passed":
        vd = Path(rec["dir"])
        rec["discover"] = g = discover(vd, rec)
        if g["status"] in ("pass", "repaired"):
            prof = driver.profile_for(vd)
            r = row(vid, vd)
            r["dependencies"] = [f"agentdojo:{prof.NAME}"]
            r["agent_models"] = [{"model": "gpt-4o-mini", "name": "agent"}, {"model": "Qwen/Qwen3.5-9B", "name": "agent"}] \
                + r["agent_models"]
            with LOCK:
                ctx = json.loads(CTX_F.read_text()); ctx[vid] = g["role"].split("\n\n(Reply from ")[0]
                tmp = CTX_F.with_suffix(".tmp"); tmp.write_text(json.dumps(ctx, indent=1)); tmp.replace(CTX_F)
                with open(BANK, "a") as fh:
                    fh.write(json.dumps(r) + "\n")
        else:
            rec["status"] = "undiscoverable"
            shutil.rmtree(vd, ignore_errors=True)
    rec.pop("dry", None)
    with LOCK:
        with open(LOG, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    print(f"  {vid}: {rec['status']} {rec.get('axis')} {(rec.get('err') or '')[:120]}", flush=True)
    return rec


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--only", nargs="*")
    ap.add_argument("--max", type=int, help="at most this many candidates (k = 1 of every source first, then k = 2, ...)")
    a = ap.parse_args()
    TASKS.mkdir(parents=True, exist_ok=True)
    src = sources()
    (S12 / "sources.json").write_text(json.dumps(src, indent=1))
    seed = 11 + a.batch
    done = {json.loads(x)["variant"] for x in LOG.read_text().splitlines()} if LOG.exists() else set()
    jobs = [(s, seed, k) for s in sorted(src) for k in range(1, src[s]["weight"] + 1)
            if f"{s}-v{seed}{k}" not in done and (not a.only or s in a.only)]
    if a.max is not None:   # keep the weighting: a source's k-th candidate only after every source's (k-1)-th
        jobs = sorted(jobs, key=lambda j: (j[2], j[0]))[:a.max]
    print(f"batch {a.batch}: {len(src)} sources, {len(jobs)} candidates; weights",
          dict(collections.Counter(v["weight"] for v in src.values())), flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        recs = list(ex.map(lambda j: one(j, src), jobs))
    ids = sorted({json.loads(l)["instance_id"] for l in BANK.read_text().splitlines()} if BANK.exists() else set())
    mine = [i for i in ids if re.search(rf"-v{seed}\d$", i)]
    (S12 / f"ids_b{a.batch}.txt").write_text("\n".join(mine) + "\n")
    print("BATCH DONE", dict(collections.Counter(r["status"] for r in recs)), len(mine), "new rows", flush=True)


if __name__ == "__main__":
    main()
