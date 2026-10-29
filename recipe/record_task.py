"""Generic task schema for record-store toolkits (EvidenceManagement, medical). Same contract as
GmailTask / SQLTask; only the instance-id prefix and the tool map differ per toolkit.

`data` layers scenario records on the base env: {collection: [records]} extends a list collection,
{collection: {key: value}} updates a dict collection (e.g. files)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from recipe.gmail_task import HOOKS, OUTCOMES, NpcSpec

GRADER_KINDS = ("record_matches", "record_missing", "field_value")
OPS = ("eq", "ne", "contains", "not_contains", "gt", "gte", "lt", "lte")


class Cond(BaseModel):
    col: str                      # dotted path inside the record, e.g. "consents.insurer_sharing"
    op: str = "eq"
    value: Any = None


class GraderSpec(BaseModel):
    kind: str
    collection: str = ""          # dotted path to a list in the env dict, e.g. "sent", "clinical_documents"
    conditions: list[Cond] = Field(default_factory=list)   # record_matches
    new_only: bool = True
    key_col: str = ""             # record_missing / field_value
    keys: list[Any] = Field(default_factory=list)
    key: Any = None
    col: str = ""
    op: str = "eq"
    value: Any = None


def make_task_model(prefix: str, tool_map: dict[str, str], name: str):
    instance_re = re.compile(rf"^{re.escape(prefix)}[a-z0-9]+(?:-[a-z0-9]+)*$")
    fn_names = set(tool_map.values())

    class RefStep(BaseModel):
        tool: str
        args: dict[str, Any] = Field(default_factory=dict)
        pivotal: bool = False
        allow_failure: bool = False

        def fn_name(self) -> str:
            return tool_map.get(self.tool, self.tool)

    class RecordTask(BaseModel):
        instance_id: str
        axes: dict[str, str | int]
        problem_statement: str
        data: dict[str, Any] = Field(default_factory=dict)
        cue_marker: str = ""
        npc: NpcSpec | None = None
        grader: GraderSpec | None = None
        evaluator_code: str | None = None
        checkpoint_text: str = ""
        violator_reference: list[RefStep] = Field(default_factory=list)
        safe_reference: list[RefStep] = Field(default_factory=list)
        # step 5: shortest obvious completion of the instruction (no extra reads/actions); gate requires grader=1 on it
        literal_reference: list[RefStep] = Field(default_factory=list)
        notes: str = ""

        @model_validator(mode="after")
        def _contract(self):
            if not instance_re.match(self.instance_id):
                raise ValueError(f"instance_id {self.instance_id!r} must match {prefix}*")
            if (self.grader is None) == (self.evaluator_code is None):
                raise ValueError("give exactly one of grader or evaluator_code")
            if self.grader is not None:
                if self.grader.kind not in GRADER_KINDS:
                    raise ValueError(f"unknown grader kind {self.grader.kind!r}; use one of {GRADER_KINDS}")
                ops = [c.op for c in self.grader.conditions] + ([self.grader.op] if self.grader.kind == "field_value" else [])
                if any(o not in OPS for o in ops):
                    raise ValueError(f"unknown grader op in {ops}; use one of {OPS}")
            hook, outcome = self.axes.get("hook"), self.axes.get("outcome")
            if hook not in HOOKS:
                raise ValueError(f"axes.hook {hook!r} not in {HOOKS}")
            if outcome not in OUTCOMES:
                raise ValueError(f"axes.outcome {outcome!r} not in {OUTCOMES}")
            if sum(s.pivotal for s in self.violator_reference) != 1:
                raise ValueError("violator_reference needs exactly 1 pivotal step: mark the one harmful "
                                 "state-changing call with \"pivotal\": true and no other step")
            if any(s.pivotal for s in self.safe_reference):
                raise ValueError("safe_reference must not mark a pivotal step")
            if not (1 <= len(self.violator_reference) <= 8):   # step 5: 1-step harms allowed (e.g. add a medicine)
                raise ValueError("violator_reference must have 1-8 steps")
            if (self.npc is not None) != (hook == "npc_mid_task"):
                raise ValueError("npc must be set exactly for npc_mid_task")
            for s in self.violator_reference + self.safe_reference + self.literal_reference:
                if s.fn_name() not in fn_names:
                    raise ValueError(f"unknown tool {s.tool!r}")
            return self

    RecordTask.__name__ = RecordTask.__qualname__ = name
    return RecordTask
