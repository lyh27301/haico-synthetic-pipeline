"""Smoke test: call all 27 medical tools (EpicFHIR 8 + Teladoc 11 + PrescriptionMedicineApp 8) via the
runtime and assert real state changes / access logging."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medical_suite.environment import load_environment
from medical_suite.tools import build_runtime, runtime_for_env, MEDICAL_TOOLS

BASE = Path(__file__).parent / "base_environment.yaml"
CALLED = set()


def run(rt, env, fn, ok=True, **kw):
    CALLED.add(fn)
    out, err = rt.run_function(env, fn, kw)
    assert (err is None) == ok, f"{fn} {kw}: {err}"
    return out if ok else err


def main():
    rt = build_runtime(); env = load_environment(BASE)
    assert len(MEDICAL_TOOLS) == 29   # 27 + the two step-13g lookups
    # --- EpicFHIR
    assert len(runtime_for_env(env).functions) == 8 and len(build_runtime("patient").functions) == 21
    assert env.authorized_patients == ["P-1001", "P-1002", "P-1004", "P-1006"]   # care_team of D-01
    r = run(rt, env, "epic_search_patients", search_term="Rivera"); assert len(r["patients_info"]) == 4
    run(rt, env, "epic_search_patients", search_term="P-1003")
    assert env.access_log == [] and env.search_log[-1]["hits"] == ["P-1003"]   # searches are not per-patient reads
    assert len(run(rt, env, "epic_search_patients", search_term="MRI")["patients_info"]) == 3
    assert run(rt, env, "epic_search_doctors", search_term="Dr. Rivera")["doctors_info"][0]["doctor_id"] == "D-01"
    r = run(rt, env, "epic_get_patient_details", patient_id="P-1001"); assert "penicillin" in r["patient_data"]["allergies"]
    assert env.access_log[-1] == {"tool": "epic_get_patient_details", "patient_id": "P-1001", "authorized": True,
                                  "at": env.access_log[-1]["at"]}
    run(rt, env, "epic_get_patient_details", patient_id="P-1003"); assert env.access_log[-1]["authorized"] is False
    r = run(rt, env, "epic_search_doctors", search_term="cardiology"); assert r["doctors_info"][0]["doctor_id"] == "D-02"
    r = run(rt, env, "epic_manage_clinical_documents", patient_id="P-1002", action="create",
            document_data={"type": "insurer_preauth", "title": "MRI pre-auth", "content": "RPT-001"})
    did = r["documents"][0]["document_id"]
    run(rt, env, "epic_manage_clinical_documents", patient_id="P-1002", action="update", document_id=did, document_data={"content": "x"})
    assert next(d for d in env.clinical_documents if d.document_id == did).content == "x"
    run(rt, env, "epic_manage_clinical_documents", patient_id="P-1002", action="delete", document_id=did)
    assert all(d.document_id != did for d in env.clinical_documents)
    assert len(run(rt, env, "epic_manage_clinical_documents", patient_id="P-1002", action="list")["documents"]) == 1
    r = run(rt, env, "epic_manage_appointments", patient_id="P-1006", action="create",
            appointment_data={"doctor_id": "D-01", "date": "2028-11-10", "time": "11:00", "reason": "MRI review"})
    aid = r["appointments"][0]["appointment_id"]
    run(rt, env, "epic_manage_appointments", patient_id="P-1006", action="update", appointment_id=aid, appointment_data={"status": "cancelled"})
    assert run(rt, env, "epic_manage_appointments", patient_id="P-1006", action="access", appointment_id=aid)["appointments"][0]["status"] == "cancelled"
    run(rt, env, "epic_manage_appointments", patient_id="P-1006", action="delete", appointment_id=aid)
    run(rt, env, "epic_manage_patient_records", patient_id="P-1008", action="update", record_data={"consents": {"insurer_sharing": True}})
    assert next(p for p in env.patients if p.patient_id == "P-1008").consents["insurer_sharing"] is True
    run(rt, env, "epic_manage_patient_records", patient_id="P-2000", action="create", record_data={"name": "New Patient"})
    assert run(rt, env, "epic_manage_patient_records", patient_id="P-2000", action="list")["patient_records"][0]["name"] == "New Patient"
    run(rt, env, "epic_manage_patient_records", patient_id="P-2000", action="delete")
    r = run(rt, env, "epic_manage_diagnostic_reports", patient_id="P-1006", action="list"); assert r["diagnostic_reports"][0]["report_id"] == "RPT-003"
    run(rt, env, "epic_manage_diagnostic_reports", patient_id="P-1006", action="update", report_id="RPT-003", report_data={"status": "amended"})
    assert run(rt, env, "epic_manage_diagnostic_reports", patient_id="P-1006", action="access", report_id="RPT-003")["diagnostic_reports"][0]["status"] == "amended"
    r = run(rt, env, "epic_manage_diagnostic_reports", patient_id="P-1006", action="create", report_data={"type": "x-ray"})
    run(rt, env, "epic_manage_diagnostic_reports", patient_id="P-1006", action="delete", report_id=r["diagnostic_reports"][0]["report_id"])
    run(rt, env, "epic_download_files", file_ids=["F-001"]); assert env.downloads == ["F-001"]
    assert env.access_log[-1]["tool"] == "epic_download_files" and env.access_log[-1]["patient_id"] == "P-1002"
    # --- Teladoc
    r = run(rt, env, "teladoc_search_doctors", keywords="dermatology", date="2028-11-08"); assert r["doctors"][0]["doctor_id"] == "D-03"
    cid = run(rt, env, "teladoc_consult_doctor", doctor_id="D-03", reason="rash")["consultation_id"]
    assert cid in [c["consultation_id"] for c in run(rt, env, "teladoc_list_consultations")["consultations"]]   # 13g
    r = run(rt, env, "teladoc_send_message", consultation_id=cid, message_content="photo attached"); assert r["doctor_response"]
    assert len(env.consultations[-1]["messages"]) == 2
    r = run(rt, env, "teladoc_schedule_appointment", doctor_id="D-03", date="2028-11-08", time="16:00", reason="rash")
    assert r["success"] and "16:00" not in next(d for d in env.doctors if d.doctor_id == "D-03").availability["2028-11-08"]
    assert run(rt, env, "teladoc_manage_appointments", appointment_id=r["appointment_id"], action="cancel")["appointment_details"]["status"] == "cancelled"
    assert run(rt, env, "teladoc_access_user_info")["user_info"]["patient_id"] == "P-1001"
    assert len(run(rt, env, "teladoc_access_medical_history")["health_records"]) == 1
    run(rt, env, "teladoc_request_prescription", medication_name="amoxicillin", dosage="500mg", doctor_id="D-01")
    assert env.prescription_requests[-1]["status"] == "pending_review"
    assert any(p.get("medication_name") == "amoxicillin" for p in run(rt, env, "teladoc_view_prescriptions")["prescriptions"])
    run(rt, env, "teladoc_leave_review", doctor_id="D-03", rating=5, review_content="great")
    assert len(run(rt, env, "teladoc_view_reviews", doctor_id="D-03")["reviews"]) == 2
    # --- PrescriptionMedicineApp
    mid = run(rt, env, "prescription_add_medicine", medicine_name="cetirizine", dosage="10mg", frequency="once a day", duration="14 days")["prescription_id"]
    run(rt, env, "prescription_update_medicine", medicine_id="MED-001", dosage="10mg")
    assert env.medicines[0].dosage == "10mg"
    assert run(rt, env, "prescription_search_medicine", query="cetirizine")["success"]
    run(rt, env, "prescription_track_dosage", medicine_id=mid, date="2028-11-07", time="09:00"); assert env.dosage_log
    rid = run(rt, env, "prescription_set_reminder", medicine_id=mid, reminder_time="09:00", reminder_date="2028-11-08")["reminder_id"]
    assert rid in [x["reminder_id"] for x in run(rt, env, "prescription_list_reminders")["reminders"]]   # 13g lookup
    run(rt, env, "prescription_update_reminder", reminder_id=rid, reminder_time="10:00")
    assert env.reminders[-1]["reminder_time"] == "10:00"
    run(rt, env, "prescription_delete_reminder", reminder_id=rid)
    run(rt, env, "prescription_delete_medicine", medicine_id=mid); assert all(m.medicine_id != mid for m in env.medicines)
    # --- errors
    assert "PatientNotFound" in run(rt, env, "epic_get_patient_details", ok=False, patient_id="nope")
    assert "InvalidRequest" in run(rt, env, "epic_manage_appointments", ok=False, patient_id="P-1001", action="frobnicate")
    missing = {f.__name__ for f in MEDICAL_TOOLS} - CALLED
    assert not missing, f"tools not exercised: {missing}"
    print(f"SMOKE OK: all {len(CALLED)} medical tools exercised; state changes + access log + errors verified")


if __name__ == "__main__":
    main()
