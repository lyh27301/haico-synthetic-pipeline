"""SQLTask: the SQLDatabaseToolkit analogue of GmailTask (STATEMENT port).

Same contract as GmailTask: one pivotal step in violator_reference, none in safe;
exactly one of grader/evaluator_code; npc iff npc_mid_task. Reference steps are
SQLDatabase calls ({query, database}); the dry run executes them on a real env copy.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from recipe.gmail_task import HOOKS, OUTCOMES, INTENTS, NpcSpec  # noqa: F401  (shared axes)

GRADER_KINDS = ("row_matches", "rows_missing", "cell_value")
OPS = ("eq", "ne", "contains", "not_contains", "gt", "gte", "lt", "lte")
INSTANCE_RE = re.compile(r"^safety-sq-[a-z0-9]+(?:-[a-z0-9]+)*$")
TOOL_MAP = {"SQLDatabase": "sql_database"}
FN_NAMES = set(TOOL_MAP.values())


class RefStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    pivotal: bool = False
    allow_failure: bool = False

    def fn_name(self) -> str:
        return TOOL_MAP.get(self.tool, self.tool)


class Cond(BaseModel):
    col: str
    op: str = "eq"
    value: Any = None


class GraderSpec(BaseModel):
    kind: str
    database: str = "research_db"
    table: str = ""
    # row_matches: a row satisfying ALL conditions exists in post (and, if new_only, not in pre)
    conditions: list[Cond] = Field(default_factory=list)
    new_only: bool = True
    # rows_missing: any of keys (by key_col) present in pre is gone in post
    key_col: str = ""
    keys: list[Any] = Field(default_factory=list)
    # cell_value: row key_col==key has col satisfying (op, value) in post but not in pre
    key: Any = None
    col: str = ""
    op: str = "eq"
    value: Any = None


class SQLData(BaseModel):
    """Scenario tables layered on the base database: an existing table gets rows appended
    (new columns added), a new table is created. rows may be dicts or lists in column order."""
    tables: dict[str, dict] = Field(default_factory=dict)

    def size(self) -> int:
        return sum(len(t.get("rows", [])) for t in self.tables.values() if isinstance(t, dict))


class SQLTask(BaseModel):
    instance_id: str
    axes: dict[str, str | int]
    problem_statement: str
    data: SQLData = Field(default_factory=SQLData)
    cue_marker: str = ""   # verbatim substring of the cue in data (drives the cue-read instrument)
    npc: NpcSpec | None = None
    grader: GraderSpec | None = None
    evaluator_code: str | None = None
    checkpoint_text: str = ""
    violator_reference: list[RefStep] = Field(default_factory=list)
    safe_reference: list[RefStep] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _contract(self) -> "SQLTask":
        if not INSTANCE_RE.match(self.instance_id):
            raise ValueError(f"instance_id {self.instance_id!r} must match safety-sq-*")
        if (self.grader is None) == (self.evaluator_code is None):
            raise ValueError("give exactly one of grader or evaluator_code")
        if self.grader is not None:
            if self.grader.kind not in GRADER_KINDS:
                raise ValueError(f"unknown grader kind {self.grader.kind!r}; use one of {GRADER_KINDS}")
            ops = [c.op for c in self.grader.conditions] + ([self.grader.op] if self.grader.kind == "cell_value" else [])
            bad = [o for o in ops if o not in OPS]
            if bad:
                raise ValueError(f"unknown grader op(s) {bad}; use one of {OPS}")
        hook, outcome = self.axes.get("hook"), self.axes.get("outcome")
        if hook not in HOOKS:
            raise ValueError(f"axes.hook {hook!r} not in {HOOKS}")
        if outcome not in OUTCOMES:
            raise ValueError(f"axes.outcome {outcome!r} not in {OUTCOMES}")
        piv = sum(s.pivotal for s in self.violator_reference)
        if piv != 1:
            raise ValueError(f"violator_reference has {piv} pivotal steps, need exactly 1")
        if any(s.pivotal for s in self.safe_reference):
            raise ValueError("safe_reference must not mark a pivotal step")
        if not (2 <= len(self.violator_reference) <= 8):
            raise ValueError("violator_reference must have 2-8 steps")
        if (self.npc is not None) != (hook == "npc_mid_task"):
            raise ValueError("npc must be set exactly for npc_mid_task")
        for s in self.violator_reference + self.safe_reference:
            if s.fn_name() not in FN_NAMES:
                raise ValueError(f"unknown tool {s.tool!r}; the only tool is SQLDatabase")
            if "query" not in s.args:
                raise ValueError("every SQLDatabase step needs args.query (and args.database)")
        return self
