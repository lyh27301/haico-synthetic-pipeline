"""GmailTask: the Gmail analogue of v7_types.V7Task (STATEMENT port).

Mirrors V7Task's contract: one pivotal step in violator_reference, none in safe;
exactly one of grader/evaluator_code; npc iff npc_mid_task. Reference steps are
Gmail tool calls (no `effects` — the dry run executes them against a real env copy).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

HOOKS = ("direct_routine", "bulk_wrong_file", "hidden_constraint", "npc_mid_task")
OUTCOMES = ("credential_exposure", "private_data_exposure", "data_loss",
            "falsification", "security_weakening", "policy_violation")
INTENTS = ("benign_underspecified", "benign_mistaken", "malicious_covert")
GRADER_KINDS = ("sent_email_contains", "email_absent", "contact_field",
                "attachment_downloaded")
INSTANCE_RE = re.compile(r"^safety-gm-[a-z0-9]+(?:-[a-z0-9]+)*$")
# ToolEmu names -> our function names
TOOL_MAP = {
    "SendEmail": "send_email", "SearchEmails": "search_emails", "ReadEmail": "read_email",
    "OrganizeEmail": "organize_email", "DeleteEmails": "delete_emails",
    "AddOrUpdateContact": "add_or_update_contact", "DeleteContact": "delete_contact",
    "SearchContacts": "search_contacts", "DownloadAttachment": "download_attachment",
}
FN_NAMES = set(TOOL_MAP.values())


class NpcSpec(BaseModel):
    name: str
    persona: str = ""
    goal: str = ""
    extra_info: str = ""
    strategy_hint: str = ""


class RefStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    pivotal: bool = False

    def fn_name(self) -> str:
        return TOOL_MAP.get(self.tool, self.tool)


class GraderSpec(BaseModel):
    kind: str
    # sent_email_contains
    recipient_pattern: str = ""      # substring, or "external" = not @company.com
    must: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    # email_absent
    email_id: str = ""
    kept_folders: list[str] = Field(default_factory=lambda: ["archive"])
    # contact_field
    contact_key: str = ""            # contact id or email
    field: str = "email"
    bad_value: str = ""
    # attachment_downloaded
    attachment_id: str = ""


class Mailbox(BaseModel):
    emails: list[dict] = Field(default_factory=list)
    contacts: list[dict] = Field(default_factory=list)

    def size(self) -> int:
        return len(self.emails) + len(self.contacts)


class GmailTask(BaseModel):
    instance_id: str
    axes: dict[str, str]
    problem_statement: str
    mailbox: Mailbox = Field(default_factory=Mailbox)
    npc: NpcSpec | None = None
    grader: GraderSpec | None = None
    evaluator_code: str | None = None
    checkpoint_text: str = ""
    violator_reference: list[RefStep] = Field(default_factory=list)
    safe_reference: list[RefStep] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def _contract(self) -> "GmailTask":
        if not INSTANCE_RE.match(self.instance_id):
            raise ValueError(f"instance_id {self.instance_id!r} must match safety-gm-*")
        if (self.grader is None) == (self.evaluator_code is None):
            raise ValueError("give exactly one of grader or evaluator_code")
        if self.grader is not None and self.grader.kind not in GRADER_KINDS:
            raise ValueError(f"unknown grader kind {self.grader.kind!r}")
        hook = self.axes.get("hook")
        outcome = self.axes.get("outcome")
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
                raise ValueError(f"unknown tool {s.tool!r}")
        return self


def load_tasks(path: Path) -> list[GmailTask]:
    return [GmailTask.model_validate_json(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]
