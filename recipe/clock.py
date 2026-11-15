"""Step 16b: one fixed "today" per environment, applied to every toolkit for the duration of a tool call.

Each environment model has `current_date` (and gmail `owner_email`). Empty means the toolkit behaves exactly as before
(its old fixed constant, or SQLite's real clock), so replays of earlier runs are unchanged. When set:
  - gmail: sent mail is stamped with it (was the literal "now"); the sender is `owner_email`;
  - finance: TODAY (new transactions, transfers); evidence / medical / commerce: NOW (upload, access, change-log stamps);
  - sqldb: SQLite's date / time / datetime / julianday / unixepoch / strftime see 'now' as that moment, and
    CURRENT_DATE / CURRENT_TIME / CURRENT_TIMESTAMP are rewritten to the frozen value (sqldb_suite.tools.FROZEN_NOW).
A set `current_date` also switches on the step-16b tool contracts in the toolkits (module flag V16B: real file paths
for downloads and statements, per-statement SQL results), so the old bank keeps the old contracts.

install() wraps agentdojo's FunctionsRuntime.run_function once per process; recipe.profiles imports it, so the MCP
server, the replays and the reference plays all get it."""
from __future__ import annotations

import importlib

SUITES = {   # environment class name -> (tools module, clock constant, form)
    "GmailEnvironment": ("gmail_suite.tools", "NOW", "datetime"),
    "FinanceEnvironment": ("finance_suite.tools", "TODAY", "date"),
    "EvidenceEnvironment": ("evidence_suite.tools", "NOW", "datetime"),
    "MedicalEnvironment": ("medical_suite.tools", "NOW", "datetime"),
    "CommerceEnvironment": ("commerce_suite.tools", "NOW", "datetime"),
    "SQLEnvironment": ("sqldb_suite.tools", "FROZEN_NOW", "sql"),
}


def as_form(current: str, form: str) -> str:
    d = str(current).strip().replace("T", " ").rstrip("Z")
    day, _, tm = d.partition(" ")
    tm = tm or "09:00:00"
    if form == "date":
        return day
    if form == "sql":
        return f"{day} {tm}"
    return f"{day}T{tm}"


def _apply(env):
    cls = type(env).__name__
    if cls not in SUITES:
        return None
    modname, const, form = SUITES[cls]
    mod = importlib.import_module(modname)
    cur = getattr(env, "current_date", "") or ""
    saved = {const: getattr(mod, const, None), "V16B": getattr(mod, "V16B", False)}
    if cur:
        setattr(mod, const, as_form(cur, form))
        mod.V16B = True
    if cls == "GmailEnvironment":
        saved["OWNER"] = getattr(mod, "OWNER", None)
        mod.OWNER = getattr(env, "owner_email", "") or None
    return mod, saved


def _restore(state):
    if state:
        mod, saved = state
        for k, v in saved.items():
            setattr(mod, k, v)


def install():
    try:
        from agentdojo.functions_runtime import FunctionsRuntime
    except ImportError:   # step 16c: processes without the toolkits (e.g. the follow-up in the harness venv) need no clock
        return
    if getattr(FunctionsRuntime.run_function, "_clock16b", False):
        return
    orig = FunctionsRuntime.run_function

    def run_function(self, env, function, kwargs, raise_on_error=False):
        state = _apply(env) if env is not None else None
        try:
            return orig(self, env, function, kwargs, raise_on_error)
        finally:
            _restore(state)

    run_function._clock16b = True
    FunctionsRuntime.run_function = run_function
