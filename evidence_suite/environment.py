"""EvidenceManagement environment: legal cases, their evidence items, the local files evidence is
uploaded from, outgoing transmissions, deleted evidence, and an access log. Real Pydantic state,
mutated in place by tools.py, diffable before/after."""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, Field


class Case(BaseModel):
    case_id: str
    title: str = ""
    court: str = ""
    parties: list[str] = Field(default_factory=list)
    notes: str = ""                 # e.g. standing orders, motions in limine


class Evidence(BaseModel):
    evidence_id: str
    case_id: str
    evidence_type: str = "document"  # document | video | audio | image
    title: str = ""
    file_path: str = ""
    content: str = ""                # transcript / text extract of the file
    notes: str = ""                  # paralegal / court notes shown in RetrieveEvidence
    privileged: bool = False
    uploaded_at: str = ""


class Transmission(BaseModel):
    transmission_id: str
    evidence_id: str
    recipient: str
    recipient_category: str = "unknown"   # jury_display | opposing_counsel | clerk | co_counsel | external | unknown
    content: str                     # exactly what left the system
    sent_at: str = ""


class EvidenceEnvironment(TaskEnvironment):
    cases: list[Case] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)      # local workspace path -> content
    recipients: dict[str, str] = Field(default_factory=dict)  # known recipient id -> description
    sent: list[Transmission] = Field(default_factory=list)
    deleted: list[Evidence] = Field(default_factory=list)
    access_log: list[dict] = Field(default_factory=list)


def load_environment(path: str | Path) -> EvidenceEnvironment:
    return EvidenceEnvironment.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def env_to_dict(env: EvidenceEnvironment) -> dict:
    return env.model_dump(mode="json")
