"""Step 7 Part A2: mechanical hygiene / discoverability / equivalence repair of every task currently classified good
(steps 3-6, sources + variants). Originals are left untouched; repaired copies are emitted to arm_step7/a2/tasks/<id>
with the same instance id, and every decision is written to arm_step7/a2/repairs.json.

Repairs (the mechanic is never changed):
- hygiene, id collision, same entity (natural key / gmail contact email / title prefix match): drop the task record,
  the base record stands in (same id, nothing to repoint).
- hygiene, id collision, different entity: the base record shadowed the task record (lookups return the first
  match), so give the task record a fresh id (numeric part + 900) and rewrite that id everywhere in the task.
- hygiene, base entity re-created under a new id: drop the task record and repoint its id at the base record's id.
  If the dropped record carries the cue marker, the task is not repairable mechanically.
- discover: insert, before the failing literal step, the first list/search call (run in the state the literal path
  has reached) whose output contains the id. The instruction is not reworded.
- equivalence: loosen the required string to the token the instruction / data fixes (none among good tasks today).

  python arm_step7/a2/repair.py   -> arm_step7/a2/{repairs.json, tasks/}
"""
import copy, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(ROOT))
import driver  # noqa: E402
from recipe import gates, pipeline as P  # noqa: E402
from recipe.graders import dry_run_ok  # noqa: E402
from analysis.step7_regression import classes, dirs  # noqa: E402

OUT = HERE / "tasks"


def _paths(prof):
    """collection name -> path of the task-data list in the task JSON."""
    if prof.NAME == "gmail":
        return {"emails": ("mailbox", "emails"), "contacts": ("mailbox", "contacts")}
    if prof.NAME == "sqldb":
        raise NotImplementedError("sqldb hygiene repair")
    return None   # record stores: data.<coll>


def _get_list(tj, prof, coll):
    p = _paths(prof)
    if p is None:
        return tj.setdefault("data", {}).get(coll)
    return tj[p[coll][0]][p[coll][1]]


def _same_entity(prof, coll, tr, br, nat):
    if prof.NAME == "gmail" and coll == "contacts":
        return str(tr.get("email", "")).lower() == str(br.get("email", "")).lower()
    if nat:
        tk, bk = gates._nkey(tr, nat), gates._nkey(br, nat)
        if tk is not None and bk is not None:
            return all(a == b or b.startswith(a) or a.startswith(b) for a, b in zip(tk, bk))
    return False


def _sub(s, old, new):
    return re.sub(r"(?<![A-Za-z0-9_\-])" + re.escape(old) + r"(?![A-Za-z0-9_])", new, s)


def _fresh(old, taken):
    m = re.match(r"^(.*?)(\d+)$", old)
    n = 900
    while True:
        new = f"{m.group(1)}{int(m.group(2)) + n}" if m else f"{old}_t{n}"
        if new.lower() not in taken:
            return new
        n += 1


def _text(r):
    return json.dumps(r, default=str).lower()


def hygiene_repair(prof, task):
    base, mine = gates.records(prof, task)
    nat_all = getattr(prof, "NATURAL_KEYS", {}) or {}
    tj = json.loads(task.model_dump_json())
    cue = (getattr(task, "cue_marker", "") or "").lower()
    ops, renames, drops = [], [], []        # renames: (old, new) applied to the whole task JSON
    taken = {i for c in base.values() if isinstance(c, list) for r in c if isinstance(r, dict) for i in map(str, r.values())}
    taken = {x.lower() for x in taken} | gates.task_local_ids(prof, task)
    for coll, recs in mine.items():
        b = base.get(coll)
        if isinstance(recs, dict) and isinstance(b, dict):      # keyed directory: same key = same entity
            for k in sorted(set(recs) & set(b)):
                if cue and cue in _text(recs[k]) and cue not in _text(b[k]):
                    return None, [f"unrepairable: data.{coll}[{k}] redefines the base entry and carries the cue marker"]
                tj["data"][coll].pop(k, None); ops.append(f"drop data.{coll}[{k}] (base entry stands)")
            continue
        if not isinstance(recs, list) or not isinstance(b, list) or not b:
            continue
        f = gates._id_field(prof, coll, b)
        nat = nat_all.get(coll)
        bid = {str(r.get(f)).lower(): r for r in b if isinstance(r, dict)} if f else {}
        bnk = {gates._nkey(r, nat): r for r in b if isinstance(r, dict)} if nat else {}
        bnk.pop(None, None)
        for r in recs:
            if not isinstance(r, dict):
                continue
            rid = str(r.get(f)) if f else None
            if rid and rid.lower() in bid:
                br = bid[rid.lower()]
                if _same_entity(prof, coll, r, br, nat):
                    if cue and cue in _text(r) and cue not in _text(br):
                        return None, [f"unrepairable: {coll} {rid} duplicates the base record but carries the cue marker"]
                    drops.append((coll, r)); ops.append(f"drop {coll} {rid} (same entity as base {rid})")
                else:
                    new = _fresh(rid, taken); taken.add(new.lower())
                    renames.append((rid, new)); ops.append(f"rename {coll} {rid} -> {new} (different entity; base {rid} shadowed it)")
                continue
            k = gates._nkey(r, nat) if nat else None
            if k is not None and k in bnk:
                br = bnk[k]
                if cue and cue in _text(r) and cue not in _text(br):
                    return None, [f"unrepairable: {coll} {rid} re-creates base {br.get(f)} but carries the cue marker"]
                drops.append((coll, r)); renames.append((rid, str(br.get(f))))
                ops.append(f"drop {coll} {rid}, repoint -> base {br.get(f)} (re-created base entity)")
    if not ops:
        return task, []
    for coll, r in drops:
        lst = _get_list(tj, prof, coll)
        lst[:] = [x for x in lst if x is not r and x != r]
    s = json.dumps(tj)
    for old, new in renames:
        s = _sub(s, old, new)
    return prof.TASK_SCHEMA.model_validate_json(s), ops


def _candidates(prof, task, seen, v):
    """Discovery calls an agent could make from what it already knows."""
    if prof.NAME == "gmail":
        em = next((e for e in task.mailbox.emails if isinstance(e, dict) and str(e.get("id")) == v), None)
        words = [w for w in re.findall(r"[A-Za-z]{4,}", (em or {}).get("subject", "")) if w.lower() in seen]
        return [("SearchEmails", {"keywords": [w]}) for w in words] + [("SearchEmails", {})]
    if prof.NAME == "evidence":
        cases = sorted(set(re.findall(r"\bc\d{3,}\b", seen)))
        return ([("RetrieveEvidence", {"case_id": c}) for c in cases] + [("ListCases", {})]
                + [("ListWorkspaceFiles", {})])
    if prof.NAME == "medical":
        pids = sorted(set(re.findall(r"\bp-\d{3,}\b", seen)))
        out = []
        for p in pids:
            P_ = p.upper()
            out += [("epic_manage_clinical_documents", {"patient_id": P_, "action": "list"}),
                    ("epic_manage_clinical_documents", {"patient_id": P_, "action": "search"}),
                    ("epic_manage_diagnostic_reports", {"patient_id": P_, "action": "list"}),
                    ("epic_manage_diagnostic_reports", {"patient_id": P_, "action": "search"}),
                    ("epic_manage_appointments", {"patient_id": P_, "action": "list"}),
                    ("epic_get_patient_details", {"patient_id": P_})]
        return out + [("teladoc_manage_appointments", {"action": "view"}), ("teladoc_view_prescriptions", {}),
                      ("prescription_search_medicine", {"query": ""})]
    return []


def discover_repair(prof, task):
    ops = []
    for _ in range(4):
        e = gates.discover_errors(prof, task)
        if not e:
            return task, ops
        m = re.search(r"literal step (\d+) \((\w+)\) uses '([^']+)'", e[0])
        i, v = int(m.group(1)), m.group(3)
        env = gates.fresh_env(prof, task)
        rt = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
        seen = gates.known_text(prof, task, env)
        steps = list(task.literal_reference)
        for s in steps[:i]:
            out, err = rt.run_function(env, s.fn_name(), dict(s.args))
            seen += " " + json.dumps(out if err is None else err, default=str).lower()
        step_cls = type(steps[0])
        hit = None
        for tool, args in _candidates(prof, task, seen, v):
            st = step_cls(tool=tool, args=args)
            e2 = copy.deepcopy(env)
            try:
                out, err = rt.run_function(e2, st.fn_name(), dict(args))
            except Exception as ex:  # noqa: BLE001
                out, err = None, str(ex)
            if err is None and v.lower() in json.dumps(out, default=str).lower():
                hit = st; break
        if hit is None:
            return None, ops + [f"unrepairable: no list/search call returns {v!r} from what the agent knows"]
        task = task.model_copy(update={"literal_reference": steps[:i] + [hit] + steps[i:]})
        ops.append(f"literal: insert {hit.tool}({hit.args}) before step {i} to discover {v}")
    return None, ops + ["unrepairable: discover still failing after 4 inserts"]


def full_gate(prof, task):
    P.PROFILE = prof
    dry = prof.dry_run(task)
    if not dry_run_ok(dry):
        return f"dry_run {dry}"
    return P._bfix_check(task, prof)


def main():
    cls, D = classes(), dirs()
    good = sorted(t for t, c in cls.items() if c == "good" and t in D)
    rows = []
    for t in good:
        grp, d = D[t]; prof = driver.profile_for(d)
        task = prof.TASK_SCHEMA.model_validate_json((d / "scenario.json").read_text())
        flags = {n: (f(prof, task) or [None])[0] for n, f in (("hygiene", gates.hygiene_errors),
                 ("discover", gates.discover_errors), ("equivalence", gates.equivalence_errors))}
        row = {"task": t, "set": grp, "toolkit": prof.NAME, "src_dir": str(d), "flags": flags, "ops": []}
        if not any(flags.values()):
            row["status"] = "clean"; rows.append(row); continue
        t2, err = task, None
        if flags["hygiene"]:
            t2, ops = hygiene_repair(prof, t2); row["ops"] += ops
            if t2 is None:
                err = ops[-1]
        if t2 is not None and gates.discover_errors(prof, t2):
            t2, ops = discover_repair(prof, t2); row["ops"] += ops
            if t2 is None:
                err = ops[-1]
        if t2 is not None and gates.equivalence_errors(prof, t2):
            err = "unrepairable: equivalence (no mechanical loosening implemented)"; t2 = None
        if t2 is not None:
            try:
                err = full_gate(prof, t2)
            except Exception as ex:  # noqa: BLE001
                err = f"gate crash {type(ex).__name__}: {ex}"
        if t2 is not None and err is None:
            row["dir"] = prof.emit(t2, HERE); row["status"] = "repaired"
        else:
            row["status"] = "unrepairable"; row["err"] = str(err)[:400]
        print(f"{t:50s} {row['status']:12s} {'; '.join(row['ops'])[:200]} {row.get('err', '')[:200]}", flush=True)
        rows.append(row)
    (HERE / "repairs.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
