"""Gmail environment for AgentDojo: real Pydantic state, diffable before/after.

Models follow the ToolEmu Gmail toolkit field names closely so a ToolEmu/
HAICosystem Gmail scenario maps 1:1. State is mutated in place by tools.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, Field

# The account the assistant operates on behalf of (the "owner").
ACCOUNT_EMAIL = "me@company.com"
COMPANY_DOMAIN = "company.com"


class Attachment(BaseModel):
    id: str
    name: str
    content: str = ""  # inline text content so checkers can diff what left


class Email(BaseModel):
    id: str
    sender: str = ACCOUNT_EMAIL
    recipients: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    timestamp: str = ""
    folder: str = "inbox"
    labels: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)


class Contact(BaseModel):
    id: str
    name: str = ""
    email: str = ""
    remark: str = ""
    info: dict = Field(default_factory=dict)


class GmailEnvironment(TaskEnvironment):
    inbox: list[Email] = Field(default_factory=list)
    sent: list[Email] = Field(default_factory=list)
    trash: list[Email] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    downloads: list[str] = Field(default_factory=list)  # attachment ids downloaded

    def all_emails(self) -> list[Email]:
        return self.inbox + self.sent + self.trash

    def next_email_id(self) -> str:
        n = len(self.all_emails()) + 1
        ids = {e.id for e in self.all_emails()}
        while f"email_{n}" in ids:
            n += 1
        return f"email_{n}"

    def next_contact_id(self) -> str:
        n = len(self.contacts) + 1
        ids = {c.id for c in self.contacts}
        while f"contact_{n}" in ids:
            n += 1
        return f"contact_{n}"


def load_environment(path: str | Path) -> GmailEnvironment:
    data = yaml.safe_load(Path(path).read_text())
    return GmailEnvironment.model_validate(data or {})


def env_to_dict(env: GmailEnvironment) -> dict:
    return env.model_dump(mode="json")
