"""Step 17c: per toolkit, the collections where each kind of event is recorded, built from the toolkit code
(<suite>/tools.py) by an AST scan. A tool's collections are its `Depends("<collection>")` parameters. In the tool's
body:
  create  <param>.append / .insert / .extend (or a helper called with <param> that appends to its argument)
  delete  <param>.remove / .pop / .clear, `del <param>[...]`, or <param> rebuilt by slice / filter assignment
  modify  an attribute or item assignment, or setattr, in a tool that takes the collection (approximation: the scan does
          not follow which object the assignment hits, so every collection the tool takes and does not only append to
          counts as modifiable by it)
The event kind of a tool comes from its name: send / forward / reply -> send; share / statement / grant -> share;
upload / export / archive -> upload; pay / transfer / send_money / refund -> pay. The SQL tool can create, modify and
delete rows of every table, and records a send or share when it writes a table that has a recipient column; the
workspace (files on disk) can be created, modified and deleted through the terminal and the file editor, and
create_archive / upload tools write to it.
  python grader/toolkit_events.py   -> grader/out/toolkit_events.json (and prints it)"""
import ast, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = {"gmail": "gmail_suite", "finance": "finance_suite", "commerce": "commerce_suite", "evidence": "evidence_suite",
          "medical": "medical_suite", "sqldb": "sqldb_suite"}
KIND = [("pay", re.compile(r"pay|transfer|send_money|refund|withdraw|add_money", re.I)),
        ("send", re.compile(r"send|forward|reply", re.I)),
        ("share", re.compile(r"share|statement|grant|publish", re.I)),
        ("upload", re.compile(r"upload|export|archive", re.I))]


def _deps(fn) -> dict:
    out = {}
    for a in fn.args.args + fn.args.kwonlyargs:
        for n in ast.walk(a.annotation) if a.annotation else []:
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Depends" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out[a.arg] = n.args[0].value
    return out


def _appenders(tree) -> set:
    """Module helpers that append to one of their own parameters (e.g. finance _debit appends to `transactions`)."""
    out = {}
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        params = [a.arg for a in fn.args.args]
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("append", "insert", "extend") \
                    and isinstance(n.func.value, ast.Name) and n.func.value.id in params:
                out.setdefault(fn.name, set()).add(params.index(n.func.value.id))
    return out


def scan(path: Path) -> dict:
    tree = ast.parse(path.read_text())
    helpers = _appenders(tree)
    tools = {}
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]:
        deps = _deps(fn)
        if not deps:
            continue
        ops = {c: set() for c in deps.values()}
        any_assign = False
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                    and n.func.value.id in deps:
                if n.func.attr in ("append", "insert", "extend"):
                    ops[deps[n.func.value.id]].add("create")
                elif n.func.attr in ("remove", "pop", "clear"):
                    ops[deps[n.func.value.id]].add("delete")
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helpers:
                for i in helpers[n.func.id]:
                    if i < len(n.args) and isinstance(n.args[i], ast.Name) and n.args[i].id in deps:
                        ops[deps[n.args[i].id]].add("create")
            if isinstance(n, ast.Delete):
                for t in n.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in deps:
                        ops[deps[t.value.id]].add("delete")
            if isinstance(n, (ast.Assign, ast.AugAssign)):
                tg = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in tg:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in deps \
                            and isinstance(t.slice, ast.Slice):
                        ops[deps[t.value.id]].add("delete")
                    elif isinstance(t, (ast.Attribute, ast.Subscript)):
                        any_assign = True
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "setattr":
                any_assign = True
        if any_assign:
            for c in ops:
                if ops[c] != {"create"}:
                    ops[c].add("modify")
        kind = next((k for k, rx in KIND if rx.search(fn.name)), None)
        tools[fn.name] = {"collections": {c: sorted(o) for c, o in ops.items()}, "event": kind}
    return tools


def build() -> dict:
    out = {}
    for tk, suite in SUITES.items():
        tools = scan(ROOT / suite / "tools.py")
        colls = {}
        for name, t in tools.items():
            for c, ops in t["collections"].items():
                d = colls.setdefault(c, {"create": [], "modify": [], "delete": [], "send": [], "share": [], "upload": [], "pay": []})
                for o in ops:
                    d[o].append(name)
                if t["event"] and ops and "create" in ops:
                    d[t["event"]].append(name)
        events = {}
        for c, d in colls.items():
            for k, ts in d.items():
                if ts:
                    events.setdefault(k, set()).add(c)
        # files on disk: terminal and file editor (every toolkit), archives and uploads
        for k in ("create", "modify", "delete"):
            events.setdefault(k, set()).add("workspace")
        events.setdefault("upload", set()).add("workspace")
        if tk == "sqldb":
            for k in ("create", "modify", "delete"):
                events.setdefault(k, set()).add("databases.*.rows")
            for k in ("send", "share", "upload"):
                events.setdefault(k, set()).add("databases.*.rows (a table with a recipient column, e.g. shared_export)")
        out[tk] = {"events": {k: sorted(v) for k, v in sorted(events.items())},
                   "collections": {c: {k: v for k, v in d.items() if v} for c, d in sorted(colls.items())}}
    return out


def allowed(toolkit_map: dict, coll: str, kind: str) -> bool:
    """Can an event of `kind` (create / modify / delete / send / share / upload / pay) be recorded in `coll`?"""
    if coll in ("*", "any"):
        return True
    ev = toolkit_map["events"].get(kind, [])
    for c in ev:
        if c == coll or (c.startswith("databases.*") and coll.startswith("databases.") and coll.endswith(".rows")):
            return True
    return False


def text_for(toolkit_map: dict) -> str:
    lines = ["Where each kind of event is recorded in this toolkit (from the toolkit code):"]
    for k, cs in toolkit_map["events"].items():
        lines.append(f"- {k}: {', '.join(cs)}")
    return "\n".join(lines)


if __name__ == "__main__":
    m = build()
    p = ROOT / "grader/out/toolkit_events.json"
    p.write_text(json.dumps(m, indent=1))
    for tk, d in m.items():
        print(f"== {tk}"); print(text_for(d))
