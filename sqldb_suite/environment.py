"""SQLDatabaseToolkit environment for AgentDojo: real Pydantic state, diffable before/after.

The HAICosystem SQLDatabaseToolkit exposes one tool, SQLDatabase(query, database). State is
a set of named databases, each a set of tables (columns + rows). tools.py materialises the
target database into an in-memory SQLite connection per call, executes the query for real,
and writes every table back, so INSERT/UPDATE/DELETE/CREATE/DROP all change this model.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, Field

DEFAULT_DB = "research_db"


class Table(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)


class SQLEnvironment(TaskEnvironment):
    current_date: str = ""   # step 16b: fixed "today" (ISO date or datetime); empty = the old fixed clock
    databases: dict[str, dict[str, Table]] = Field(default_factory=dict)


def load_environment(path: str | Path) -> SQLEnvironment:
    data = yaml.safe_load(Path(path).read_text())
    return SQLEnvironment.model_validate(data or {})


def env_to_dict(env: SQLEnvironment) -> dict:
    d = env.model_dump(mode="json")
    for k in ("current_date", "owner_email"):   # step 16b fields: absent unless set, so old dumps are unchanged
        if d.get(k) == "":
            d.pop(k)
    return d
