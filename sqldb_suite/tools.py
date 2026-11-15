"""The HAICosystem SQLDatabaseToolkit tool as a real AgentDojo function over SQLEnvironment.

SQLDatabase(query, database) runs the query on a real in-memory SQLite copy of the named
database and writes every table back into the env, so writes are real state changes the
grader can diff. A few MySQL-isms agents commonly emit (SHOW TABLES, DESCRIBE t) are mapped
to their SQLite equivalents.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Annotated

from agentdojo.functions_runtime import Depends, FunctionsRuntime

from sqldb_suite.environment import Table

FROZEN_NOW = None   # step 16b (set by recipe.clock from env.current_date): SQLite's 'now', e.g. "2026-11-03 09:00:00"
V16B = False        # step 16b: return every statement's result, not only the last one (N7)
_TIME_FUNCS = ("date", "time", "datetime", "julianday", "unixepoch", "strftime")


def _freeze(conn: sqlite3.Connection, now: str):
    """Make 'now' a fixed moment on this connection: the date functions are replaced by wrappers that substitute it
    and evaluate on a plain helper connection (SQLite lets an application function override a built-in one)."""
    aux = sqlite3.connect(":memory:")

    def mk(fn):
        def f(*a):
            a = [now if isinstance(x, str) and x.strip().lower() == "now" else x for x in a]
            if fn != "strftime" and not a:
                a = [now]
            return aux.execute(f"SELECT {fn}({', '.join('?' for _ in a)})", a).fetchone()[0]
        return f
    for fn in _TIME_FUNCS:
        conn.create_function(fn, -1, mk(fn))
    return aux


def _frozen_keywords(stmt: str) -> str:
    """CURRENT_DATE / CURRENT_TIME / CURRENT_TIMESTAMP (keywords, not functions) -> the wrapped functions; string
    literals are left alone."""
    parts = re.split(r"('(?:[^']|'')*')", stmt)
    rep = {"current_timestamp": "datetime('now')", "current_date": "date('now')", "current_time": "time('now')"}
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?i)\bcurrent_(timestamp|date|time)\b", lambda m: rep[m.group(0).lower()], parts[i])
    return "".join(parts)


WRITE_VERBS = ("insert", "update", "delete", "create", "drop", "alter", "replace")


def statement_verbs(query: str) -> list[str]:
    """Leading keyword of each statement, lower-cased (WITH ... resolves to its main verb)."""
    verbs = []
    for stmt in _split(query):
        s = re.sub(r"^\s*(--[^\n]*\n|/\*.*?\*/)\s*", "", stmt, flags=re.S).strip().lower()
        if s.startswith("with"):
            m = re.search(r"\)\s*(select|insert|update|delete|replace)\b", s)
            verbs.append(m.group(1) if m else "select")
        else:
            verbs.append(s.split(None, 1)[0] if s else "")
    return verbs


def is_write(query: str) -> bool:
    return any(v in WRITE_VERBS for v in statement_verbs(query))


def _split(query: str) -> list[str]:
    out, buf = [], ""
    for part in str(query).split(";"):
        buf += part + ";"
        if sqlite3.complete_statement(buf):
            if buf.strip(" ;\n\t"):
                out.append(buf.strip().rstrip(";"))
            buf = ""
    if buf.strip(" ;\n\t"):
        out.append(buf.strip().rstrip(";"))
    return out


def _mysqlisms(stmt: str) -> str:
    s = stmt.strip()
    if re.fullmatch(r"(?i)show\s+tables", s):
        return "SELECT name AS table_name FROM sqlite_master WHERE type='table' ORDER BY name"
    m = re.fullmatch(r"(?i)(?:describe|desc|show\s+columns\s+from)\s+`?(\w+)`?", s)
    if m:
        return f"SELECT name AS column_name, type FROM pragma_table_info('{m.group(1)}')"
    return s.replace("`", '"')


def _no_files(action, *_):
    """Keep the sandbox in memory: ATTACH/DETACH would create or open real files on disk."""
    return sqlite3.SQLITE_DENY if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH) else sqlite3.SQLITE_OK


def _load(conn: sqlite3.Connection, tables: dict[str, Table]):
    for name, t in tables.items():
        cols = ", ".join(f'"{c}"' for c in t.columns)
        conn.execute(f'CREATE TABLE "{name}" ({cols})')
        if t.rows:
            ph = ", ".join("?" for _ in t.columns)
            conn.executemany(f'INSERT INTO "{name}" VALUES ({ph})',
                             [[r.get(c) for c in t.columns] for r in t.rows])


def _dump(conn: sqlite3.Connection) -> dict[str, Table]:
    out = {}
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY rowid")]
    for name in names:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{name}')")]
        rows = [dict(zip(cols, r)) for r in conn.execute(f'SELECT * FROM "{name}"')]
        out[name] = Table(columns=cols, rows=rows)
    return out


def sql_database(
    databases: Annotated[dict, Depends("databases")],
    query: str,
    database: str,
) -> dict:
    """Execute SQL queries on a connected database and retrieve results.

    :param query: The SQL query string to be executed (SQLite dialect; several statements may be separated by ';').
    :param database: The name of the database on which the query should be executed.
    """
    if database not in databases:
        raise ValueError(f"InvalidDatabaseException: database {database!r} does not exist "
                         f"(available: {sorted(databases)})")
    stmts = [_mysqlisms(s) for s in _split(query)]
    if not stmts:
        raise ValueError("QueryExecutionException: empty query")
    conn = sqlite3.connect(":memory:")
    aux = _freeze(conn, FROZEN_NOW) if FROZEN_NOW else None
    if FROZEN_NOW:
        stmts = [_frozen_keywords(s) for s in stmts]
    conn.set_authorizer(_no_files)
    per = []
    try:
        _load(conn, databases[database])
        results, affected = [], 0
        for s in stmts:
            try:
                cur = conn.execute(s)
            except sqlite3.Error as e:
                if V16B and per:   # step 16b: say which statement failed and what the earlier ones did (nothing is kept)
                    raise ValueError(f"QueryExecutionException: statement {len(per) + 1} of {len(stmts)}: {e} "
                                     f"(no statement of this call was applied)") from None
                raise ValueError(f"QueryExecutionException: {e}") from None
            if cur.description:
                cols = [d[0] for d in cur.description]
                results = [dict(zip(cols, r)) for r in cur.fetchall()]
                per.append({"statement": len(per) + 1, "results": results})
            else:
                n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                affected += n
                per.append({"statement": len(per) + 1, "rows_affected": n})
        conn.commit()
        if is_write(query):
            databases[database] = _dump(conn)
    finally:
        conn.close()
        if aux is not None:
            aux.close()
    out = {"results": results, "success": True}
    if affected:
        out["rows_affected"] = affected
    if V16B and len(stmts) > 1:   # step 16b (N7): several statements used to return only the last result
        out["statement_results"] = per
    return out


SQL_TOOLS = [sql_database]

# HAICosystem/ToolEmu tool name -> our function name (1:1 contract mapping)
TOOLEMU_NAME_MAP = {"SQLDatabase": "sql_database"}


def build_runtime() -> FunctionsRuntime:
    rt = FunctionsRuntime([])
    for fn in SQL_TOOLS:
        rt.register_function(fn)
    return rt
