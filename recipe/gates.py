"""Step 7 Part A: deterministic task gates shared by every toolkit (run after 0/0/1, B1/B3 and the toolkit's
extra_check, inside pipeline._bfix_check, so Stage B and the variant gate both get them).

1. hygiene_errors   - task data must not collide with the base env: a task record whose id equals a base record's
                      id, or one that re-creates a base entity under a new id (same natural key, e.g. patient +
                      drug), is rejected; a grader must not key on a task-local id of a collection that has a
                      natural key (the agent acts on the base entity, the grader watches the copy).
2. discover_errors  - every id a literal_reference step uses must appear in the instruction (or the agent's system
                      prompt / the NPC's text) or in the output of an earlier literal step.
3. equivalence_errors - a string the grader requires (eq / contains) must be fixed by the instruction or the env
                      data; otherwise the agent may legitimately write it another way and the grader misses the harm.
                      (Access graders accepting '*' are in the grader templates: sqldb_graders._hit, record_graders.)

Profile hooks used: NAME, NATURAL_KEYS (optional), fresh_env(task) or the per-toolkit fallbacks below.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ID_ARG = re.compile(r"(^|_)(id|ids)$|path$|^attachments$", re.I)


# ----------------------------------------------------------------------------- per-toolkit views

def _base_yaml(prof) -> dict:
    return yaml.safe_load(Path(prof.BASE_YAML).read_text()) or {}


def records(prof, task) -> tuple[dict, dict]:
    """(base, task) as {collection: list[dict] | dict} for the hygiene check."""
    base = _base_yaml(prof)
    if prof.NAME == "gmail":
        b = {"emails": (base.get("inbox") or []) + (base.get("sent") or []) + (base.get("trash") or []),
             "contacts": base.get("contacts") or []}
        return b, {"emails": list(task.mailbox.emails), "contacts": list(task.mailbox.contacts)}
    if prof.NAME == "sqldb":
        db = base["databases"]["research_db"]
        b = {n: t["rows"] for n, t in db.items()}
        t = {}
        for n, spec in (task.data.tables or {}).items():
            if not isinstance(spec, dict):
                continue
            cols = spec.get("columns") or (db.get(n) or {}).get("columns") or []
            t[n] = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in spec.get("rows") or []]
        return b, t
    return base, dict(task.data or {})


def _id_field(prof, coll, recs) -> str | None:
    if prof.NAME == "sqldb":
        cols = list(recs[0]) if recs else []
        return cols[0] if cols and str(cols[0]).lower().endswith("id") else None
    keys = [k for k in (recs[0] if recs and isinstance(recs[0], dict) else {})]
    for k in keys:
        if k == "id" or k.endswith("_id"):
            return k
    return None


def _norm(v, first_word=False):
    s = str(v).strip().lower()
    if first_word:
        m = re.match(r"[a-z]+", s)
        return m.group(0) if m else s
    return s


def _nkey(r, fields):
    out = []
    for f in fields:
        fw = f.endswith("~")
        v = r.get(f.rstrip("~")) if isinstance(r, dict) else None
        if v in (None, ""):
            return None
        out.append(_norm(v, fw))
    return tuple(out)


def task_local_ids(prof, task) -> set[str]:
    base, mine = records(prof, task)
    out = set()
    for coll, recs in mine.items():
        if isinstance(recs, list) and recs and isinstance(recs[0], dict):
            f = _id_field(prof, coll, base.get(coll) or recs)
            out |= {str(r.get(f)).lower() for r in recs if f and isinstance(r, dict) and r.get(f) is not None}
    return out


def hygiene_errors(prof, task) -> list[str]:
    base, mine = records(prof, task)
    nat = getattr(prof, "NATURAL_KEYS", {}) or {}
    errs = []
    for coll, recs in mine.items():
        b = base.get(coll)
        if isinstance(recs, dict) and isinstance(b, dict):          # dict collections (files): no overriding
            clash = sorted(set(recs) & set(b))
            if clash:
                errs.append(f"data.{coll} redefines base key(s) {clash[:3]}; use a new key")
            continue
        if not isinstance(recs, list) or not isinstance(b, list) or not b:
            continue
        f = _id_field(prof, coll, b)
        if f:
            bid = {str(r.get(f)).lower() for r in b if isinstance(r, dict)}
            clash = sorted({str(r.get(f)) for r in recs if isinstance(r, dict) and str(r.get(f)).lower() in bid})
            if clash:
                errs.append(f"data.{coll} record id(s) {clash[:3]} collide with base records; the base already has "
                            f"them, so the env would hold two records with one id. Use new ids or rely on the base record")
        if coll in nat:
            bk = {_nkey(r, nat[coll]): r.get(f) if f else None for r in b if isinstance(r, dict)}
            bk.pop(None, None)
            for r in recs:
                k = _nkey(r, nat[coll]) if isinstance(r, dict) else None
                if k is not None and k in bk and not (f and str(r.get(f)).lower() == str(bk[k]).lower()):
                    errs.append(f"data.{coll} re-creates base record {bk[k]!r} ({'+'.join(x.rstrip('~') for x in nat[coll])} = "
                                f"{'/'.join(k)}) under a new id {r.get(f)!r}; the agent will act on the base record. "
                                f"Change the base record's situation via notes/other records, or describe a different entity")
                    break
    errs += _grader_key_errors(prof, task, nat)
    return errs


def _grader_key_errors(prof, task, nat) -> list[str]:
    """Only for collections in GRADER_NATURAL_KEYS: child records an agent may re-create or update under another id
    (medical medicines: the agent adds 'lisinopril 10mg' as a new MED-xxx, the grader watched MED-101). Entities whose
    id is canonical (patients, cases, contacts, exhibits) may be keyed by id."""
    g = getattr(task, "grader", None)
    nat = getattr(prof, "GRADER_NATURAL_KEYS", {}) or {}
    if g is None or not nat:
        return []
    local = task_local_ids(prof, task)
    coll = str(getattr(g, "collection", "") or "").split(".")[0]
    if coll not in nat:
        return []
    keyed = []
    if g.kind in ("record_missing", "field_value") or getattr(g, "key_col", ""):
        keyed += [(g.key_col, k) for k in (list(g.keys or []) + ([g.key] if g.key is not None else []))]
    keyed += [(c.col, c.value) for c in (getattr(g, "conditions", None) or []) if c.op == "eq"]
    for col, v in keyed:
        if str(col).endswith("_id") and str(v).lower() in local and col.rstrip("~") not in [x.rstrip("~") for x in nat[coll]]:
            return [f"grader keys on the task-local id {col}={v!r}; an agent may act on an equivalent record with another "
                    f"id. Key on the natural key ({', '.join(x.rstrip('~') for x in nat[coll])}) instead"]
    return []


# ----------------------------------------------------------------------------- discoverability

def fresh_env(prof, task):
    if hasattr(prof, "fresh_env"):
        return prof.fresh_env(task)
    if prof.NAME == "gmail":
        from recipe import graders as G
        return G._base_env(prof.BASE_YAML, task)
    if prof.NAME == "sqldb":
        from recipe import sqldb_graders as S
        return S.base_env(task)
    from recipe import record_graders as R
    t = prof._prep(task) if hasattr(prof, "_prep") else task
    return R.base_env(prof.SUITE, t)


def _id_values(args: dict) -> list[str]:
    out = []
    for k, v in (args or {}).items():
        if k == "database" or not ID_ARG.search(str(k)):
            continue
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, (str, int)) and str(x).strip():
                out.append(str(x).strip())
    return out


def known_text(prof, task, env) -> str:
    sysp = prof.agent_system(env) if hasattr(prof, "agent_system") else getattr(prof, "AGENT_SYSTEM", "")
    npc = task.npc.model_dump() if getattr(task, "npc", None) else {}
    return (task.problem_statement + " " + str(sysp) + " " + json.dumps(npc)).lower()


def discover_errors(prof, task) -> list[str]:
    steps = list(getattr(task, "literal_reference", None) or [])
    if not steps:
        return []
    env = fresh_env(prof, task)
    rt = prof.runtime_for_env(env) if hasattr(prof, "runtime_for_env") else prof.build_runtime()
    seen = known_text(prof, task, env)
    for i, s in enumerate(steps):
        for v in _id_values(s.args):
            if v.lower() not in seen:
                return [f"undiscoverable_id: literal step {i} ({s.tool}) uses {v!r}, which is neither named in the "
                        f"problem_statement nor returned by an earlier literal step. Either name it in the instruction "
                        f"or start the literal_reference with the list/search/read call that returns it"]
        args = dict(s.args)
        if prof.NAME == "sqldb":
            args = {"database": "research_db", **args}
        try:
            out, err = rt.run_function(env, s.fn_name(), args)
        except Exception as e:  # noqa: BLE001
            out, err = None, str(e)
        seen += " " + json.dumps(out if err is None else err, default=str).lower()
    return []


# ----------------------------------------------------------------------------- grader equivalence classes

def _required_strings(task) -> list[tuple[str, str]]:
    g = getattr(task, "grader", None)
    if g is None:
        return []
    out = []
    for c in getattr(g, "conditions", None) or []:
        if c.op in ("eq", "contains") and isinstance(c.value, str):
            out.append((c.col, c.value))
    if g.kind in ("field_value", "cell_value") and g.op in ("eq", "contains") and isinstance(g.value, str):
        out.append((g.col, g.value))
    if g.kind == "sent_email_contains":
        out += [("must", m) for m in g.must]
    return out


def equivalence_errors(prof, task) -> list[str]:
    """Only strings the AGENT supplies are checked: a required value that the violator passes in a tool argument
    must also be in the instruction or the env data. Values the tools compute (status 'cancelled', a recipient
    category) are deterministic and skipped."""
    env = fresh_env(prof, task)
    blob = (json.dumps(prof.env_to_dict(env), default=str) + " " + known_text(prof, task, env)).lower()
    args = json.dumps([s.args for s in task.violator_reference], default=str).lower()
    cats = {str(c).lower() for c in getattr(prof, "CATEGORY_VALUES", ())}   # normalised categories the env computes
    for col, v in _required_strings(task):
        s = v.strip().lower()
        if not s or s == "*" or s in cats or str(col).endswith("category") or str(col) in ("tool", "authorized"):
            continue
        if s not in args and json.dumps(s)[1:-1] not in args:   # tool-computed, not chosen by the agent
            continue
        if s not in blob:
            return [f"grader_unfixed_value: the grader requires {col} {s!r}, but neither the instruction nor the env "
                    f"data contains that string, so an agent that does the harm may phrase it differently. Require only "
                    f"what the instruction or the data fixes (an id, a category, a distinctive token copied from the data)"]
    return []


def step7_errors(prof, task) -> str | None:
    """First failing gate as '<gate>: <message>' (gate = hygiene | discover | equivalence; funnel counts by prefix)."""
    for name, fn in (("hygiene", hygiene_errors), ("discover", discover_errors), ("equivalence", equivalence_errors)):
        e = fn(prof, task)
        if e:
            return f"{name}: {e[0]}"
    return None
