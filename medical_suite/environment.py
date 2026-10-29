"""Medical-records environment merged from HAICosystem EpicFHIR + Teladoc + PrescriptionMedicineApp.

One clinic (Riverside Family Health). EpicFHIR tools operate on the clinic's records (patients, doctors,
clinical documents, appointments, diagnostic reports, downloadable files). Teladoc and the prescription app
act for ONE signed-in patient (`app_user_id`): consultations, prescription requests, reviews, the patient's
medicine list, dosage log and reminders. Every read of a patient's record is written to `access_log` (the
FHIR audit trail), so unauthorized access is visible in state. Records allow extra fields (task data may add
some); the listed fields are the proposed schema.

Step 5 review: one task = one VANTAGE. `vantage == "clinic"`: the actor is clinic staff (`actor_role`) working
for `actor_doctors`; `authorized_patients` is derived = patients whose care_team includes one of those doctors.
`vantage == "patient"`: the actor is the signed-in patient's assistant; authorized = [app_user_id].
`access_log` holds only per-patient reads (details, document/report reads, file downloads), each with
`authorized`; search hits go to `search_log`, which graders never use."""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Rec(BaseModel):
    model_config = ConfigDict(extra="allow")


class Patient(_Rec):
    patient_id: str
    name: str
    dob: str = ""
    sex: str = ""
    contact: dict = Field(default_factory=dict)          # phone, email, address
    insurance: dict = Field(default_factory=dict)        # provider, member_id
    allergies: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    care_team: list[str] = Field(default_factory=list)   # doctor_ids
    consents: dict = Field(default_factory=dict)         # e.g. insurer_sharing: bool, research: bool
    notes: str = ""

    @field_validator("allergies", "medications", "conditions", "care_team", mode="before")
    @classmethod
    def _strs(cls, v):
        """Task writers sometimes give structured items ({'substance': 'penicillin', 'reaction': ...});
        keep the information as one string per item instead of failing the dry run."""
        if not isinstance(v, list):
            return v
        return [x if isinstance(x, str) else "; ".join(f"{k}: {y}" for k, y in x.items()) if isinstance(x, dict)
                else str(x) for x in v]


class Doctor(_Rec):
    doctor_id: str
    name: str
    specialty: str = ""
    location: str = ""
    availability: dict[str, list[str]] = Field(default_factory=dict)   # date -> ["HH:mm", ...]
    auto_reply: str = "Thanks, I've received your message and will review it shortly."


class ClinicalDocument(_Rec):
    document_id: str
    patient_id: str
    type: str = "progress_note"     # progress_note | discharge_summary | referral | insurer_preauth | ...
    title: str = ""
    content: str = ""
    author: str = ""
    date: str = ""


class Appointment(_Rec):
    appointment_id: str
    patient_id: str
    doctor_id: str
    date: str = ""
    time: str = ""
    reason: str = ""
    status: str = "scheduled"       # scheduled | cancelled | completed
    source: str = "epic"            # epic | teladoc


class DiagnosticReport(_Rec):
    report_id: str
    patient_id: str
    type: str = ""
    result: str = ""
    date: str = ""
    status: str = "final"
    file_id: str = ""


class Medicine(_Rec):
    medicine_id: str
    patient_id: str
    name: str
    dosage: str = ""
    frequency: str = ""
    duration: str = ""


class MedicalEnvironment(TaskEnvironment):
    patients: list[Patient] = Field(default_factory=list)
    doctors: list[Doctor] = Field(default_factory=list)
    clinical_documents: list[ClinicalDocument] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    diagnostic_reports: list[DiagnosticReport] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    downloads: list[str] = Field(default_factory=list)
    app_user_id: str = ""
    consultations: list[dict] = Field(default_factory=list)          # consultation_id, doctor_id, patient_id, reason, messages[]
    prescription_requests: list[dict] = Field(default_factory=list)  # request_id, patient_id, medication_name, dosage, doctor_id, status
    reviews: list[dict] = Field(default_factory=list)                # doctor_id, rating, review_content, author
    medicines: list[Medicine] = Field(default_factory=list)
    dosage_log: list[dict] = Field(default_factory=list)             # tracking_id, medicine_id, date, time
    reminders: list[dict] = Field(default_factory=list)              # reminder_id, medicine_id, reminder_date, reminder_time
    access_log: list[dict] = Field(default_factory=list)             # tool, patient_id, authorized (per-patient reads only)
    search_log: list[dict] = Field(default_factory=list)             # tool, term, hits (never graded)
    vantage: str = "clinic"                                          # clinic | patient
    actor_role: str = "care_coordinator"                             # care_coordinator | nurse | front_desk (clinic)
    actor_doctors: list[str] = Field(default_factory=lambda: ["D-01"])
    authorized_patients: list[str] = Field(default_factory=list)     # derived, see _derive

    @model_validator(mode="after")
    def _derive(self):
        if self.vantage == "patient":
            self.authorized_patients = [self.app_user_id]
        else:
            docs = set(self.actor_doctors)
            self.authorized_patients = [p.patient_id for p in self.patients if docs & set(p.care_team)]
        return self


def load_environment(path: str | Path) -> MedicalEnvironment:
    return MedicalEnvironment.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def env_to_dict(env: MedicalEnvironment) -> dict:
    return env.model_dump(mode="json")
