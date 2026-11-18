"""Step 18 helpers: write new task versions next to the old ones, stage their files, play their references.

Old tasks stay in arm_s16b/bank (never edited). A new version is one JSON row in arm_s18/bank/tasks/<new_id>.json with its
staged files under arm_s18/bank/files/<new_id>/workspace/..., written as real binaries (harness/filegen.py, as step 16b).
build() assembles arm_s18/bank/bank_18.jsonl (every 16b row unchanged + the new rows), bank_18_harness.jsonl (without
the analysis fields, as step 16b) and agent_context_18.json.

  import sys; sys.path.insert(0, "arm_s18"); import lib as L
  r = L.new_row("safety-sq-embargo-archive-v131", "safety-sq-embargo-archive-v131-v18", ["what changed", ...])
  r["problem_statement"] = "..."; r["environment"] = L.dump_env(env_dict)     # YAML text, as the bank keeps it
  L.set_files(r, {"blueprints/BP-4471.pdf": "text ..."}, keep=True, drop=["trial_notebook/witness_statements_redacted.zip"])
  L.save(r)                        # also keeps the role text (agent context) of the old task unless context= is given
  print(L.validate(r))             # plays safe_reference and violator_reference; returns errors and the changes made
  print(L.synthetic(r))            # 555 numbers, neat sequential ids, placeholder text, generic tool names
create_archive / merge_pdfs: during step 18 they were made available to sqldb inside validate() only, because step 19 had
to run on the step-16c harness; after step 19's runs, harness/file_tools.py registers them for sqldb (commerce is not
needed by any fix)."""
from __future__ import annotations

import copy, json, re, sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]; S18 = ROOT / "arm_s18"; OUT = S18 / "bank"
OLD = ROOT / "arm_s16b/bank"
sys.path[:0] = [str(ROOT / "arm_s16b"), str(ROOT / "harness"), str(ROOT), str(ROOT / "arm_s16c")]
import filegen  # noqa: E402
import file_tools  # noqa: E402

# step 18 end: harness/file_tools.py now registers create_archive / merge_pdfs for sqldb itself (after step 19's runs)
import play as P  # noqa: E402
import rules_engine7 as E  # noqa: E402

_ROWS = None


def old_rows() -> dict:
    global _ROWS
    if _ROWS is None:
        _ROWS = {json.loads(l)["instance_id"]: json.loads(l) for l in (OLD / "bank_16b.jsonl").read_text().splitlines()}
    return _ROWS


def old(task_id: str) -> dict:
    return copy.deepcopy(old_rows()[task_id])


def env(row: dict) -> dict:
    return yaml.safe_load(row["environment"])


def dump_env(d: dict) -> str:
    return yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=120)


def new_row(old_id: str, new_id: str, changes: list[str]) -> dict:
    r = old(old_id)
    r["instance_id"] = new_id
    r["task_version"] = "0.18"
    r["task_changes"] = list(r.get("task_changes") or []) + [{"step": "18", "change": c} for c in changes]
    r["derived_from"] = old_id
    r["_files"] = {}   # rel path -> bytes, filled by set_files (written by save)
    return r


def old_files(row_or_id) -> dict:
    """rel path under workspace/ -> bytes, for the old task's staged files."""
    r = old(row_or_id) if isinstance(row_or_id, str) else old(row_or_id.get("derived_from") or row_or_id["instance_id"])
    out = {}
    for spec in r.get("workspace_files") or []:
        p = OLD / spec
        if p.exists():
            out[spec.split("/workspace/", 1)[1]] = p.read_bytes()
    return out


def set_files(row: dict, files: dict, keep: bool = True, drop: list | None = None) -> None:
    """files: rel path under /workspace -> text (rendered by file type) or bytes. keep: start from the old task's files.
    drop: rel paths to remove."""
    cur = old_files(row) if keep else {}
    for d in drop or []:
        if d not in cur and d not in files:
            raise KeyError(f"drop: {d} is not a staged file")
        cur.pop(d, None)
    for rel, text in files.items():
        cur[rel] = filegen.render(rel, text)
    row["_files"] = cur
    row["has_workspace"] = bool(cur)
    row["workspace_files"] = [f"files/{row['instance_id']}/workspace/{rel}" for rel in sorted(cur)]


def save(row: dict, context: str | None = None) -> Path:
    t = row["instance_id"]
    if row.get("_files") is not None:
        base = OUT / "files" / t / "workspace"
        if base.exists():
            import shutil
            shutil.rmtree(base)
        for rel, data in (row.get("_files") or {}).items():
            p = base / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    elif row.get("workspace_files"):
        raise ValueError("call set_files (keep=True keeps the old files) so the new task owns its staged files")
    ctxs = json.loads((OLD / "agent_context.json").read_text())
    out = {k: v for k, v in row.items() if k != "_files"}
    out["_agent_context"] = context if context is not None else ctxs.get(row.get("derived_from"), "")
    f = OUT / "tasks" / f"{t}.json"; f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return f


def load(task_id: str) -> dict:
    return json.loads((OUT / "tasks" / f"{task_id}.json").read_text())


def _play(row, steps):
    P.BANK = OUT if (OUT / "tasks" / f"{row['instance_id']}.json").exists() else OLD
    try:
        return P.play(row, steps)
    finally:
        P.BANK = OLD


def validate(row: dict) -> dict:
    """Play both references on the real toolkit; report tool errors per step and the state changes each one makes."""
    if row.get("_files") is not None:
        save(row)
    res = {}
    for k in ("safe_reference", "violator_reference"):
        st = _play(row, row.get(k) or [])
        errs = [(i, s["call"]["name"], str(s["call"]["error"])[:200]) for i, s in enumerate(st) if s["call"]["error"]]
        ch = E.changes(st[0]["pre"], st[-1]["post"], st[0]["pre_ws"], st[-1]["post_ws"]) if st else []
        res[k] = {"steps": len(st), "errors": errs,
                  "changes": [f"{kind} {c} {key} fields={f}" for kind, c, key, rb, ra, f in ch][:40]}
    return res


SYN = [("555 number", re.compile(r"\b555[-. ]?\d{4}\b|\(\d{3}\)\s*555|\+1[-. ]?\d{3}[-. ]?555")),
       ("placeholder", re.compile(r"(?i)\b(lorem ipsum|placeholder|simulated|dummy|example\.com|foo|bar baz|TODO|xxx+|"
                                   r"rest-of-key|sample data|test data)\b")),
       ("generic tool", re.compile(r"(?i)\b(tool_?\d|my_tool|generic_tool|do_action)\b"))]
SEQ = re.compile(r"\b([A-Z]{2,6})-(\d{2,4})\b")


def synthetic(row: dict) -> dict:
    text = row["problem_statement"] + "\n" + row["environment"] + "\n" + "\n".join(
        (b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)) for b in (row.get("_files") or {}).values())
    out = {name: sorted(set(m.group(0) for m in rx.finditer(text)))[:15] for name, rx in SYN}
    by = {}
    for m in SEQ.finditer(text):
        by.setdefault(m.group(1), set()).add(int(m.group(2)))
    out["sequential ids"] = {p: sorted(v)[:12] for p, v in by.items()
                             if len(v) >= 3 and any(sorted(v)[i + 2] - sorted(v)[i] == 2 for i in range(len(v) - 2))}
    return out


LABELS = ("hook", "outcome", "requester_intent", "cue_salience", "mechanic_id")
HIDDEN = ("safe_reference", "violator_reference", "task_changes", "selection_reason", "qualified_status", "derived_from",
          "removed_reason", "user_instructed", "counter_example") + LABELS   # analysis fields, not in the harness rows


def _write(rows, ctx, stem):
    (OUT / f"{stem}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / f"{stem}_harness.jsonl").write_text("".join(
        json.dumps({k: v for k, v in r.items() if k not in HIDDEN}, ensure_ascii=False) + "\n" for r in rows))


def build() -> None:
    """bank_18 = every bank_16b row (with the step-18b overlay: labels, user_instructed, counter_example, removed) + every
    step-18 row; train_set0 = the first training set (step-18 rows + bank_16b rows without a step-18 version). Rows with
    removed = true are left out of every build (step 18b item 6)."""
    ov = json.loads((OUT / "overlay_18b.json").read_text()) if (OUT / "overlay_18b.json").exists() else {}
    rows = [{**r, **ov.get(r["instance_id"], {})} for r in old_rows().values()]
    news = [json.loads(f.read_text()) for f in sorted((OUT / "tasks").glob("*.json"))]
    ctx = json.loads((OLD / "agent_context.json").read_text())
    for n in news:
        ctx[n["instance_id"]] = n.pop("_agent_context", "")
    keep = lambda r: not r.get("removed")
    allr = [r for r in rows + news if keep(r)]
    _write(allr, ctx, "bank_18")
    (OUT / "agent_context_18.json").write_text(json.dumps({r["instance_id"]: ctx.get(r["instance_id"], "") for r in allr},
                                                          indent=1, ensure_ascii=False))
    replaced = {n["derived_from"] for n in news}
    train = [r for r in rows if r["instance_id"] not in replaced and keep(r)] + [n for n in news if keep(n)]
    _write(train, ctx, "train_set0")
    (OUT / "agent_context_train_set0.json").write_text(json.dumps({r["instance_id"]: ctx.get(r["instance_id"], "")
                                                                   for r in train}, indent=1, ensure_ascii=False))
    print(len(rows), "old +", len(news), "new;", len(rows) + len(news) - len(allr), "removed; bank_18", len(allr),
          "rows; train_set0", len(train), "rows")
