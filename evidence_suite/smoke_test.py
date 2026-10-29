"""Smoke test: call each of the 5 EvidenceManagement tools via the runtime and assert state changes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_suite.environment import load_environment
from evidence_suite.tools import build_runtime

BASE = Path(__file__).parent / "base_environment.yaml"


def run(rt, env, fn, ok=True, **kw):
    out, err = rt.run_function(env, fn, kw)
    assert (err is None) == ok, f"{fn} {kw}: {err}"
    return out if ok else err


def main():
    rt = build_runtime()
    env = load_environment(BASE)
    r = run(rt, env, "retrieve_evidence", case_id="c5490")
    assert len(r["evidence_list"]) == 8 and "Standing order" in r["case"]["notes"]
    assert any("inadmissible" in e["notes"] for e in r["evidence_list"]), "notes not surfaced"
    r = run(rt, env, "read_evidence", evidence_id="EV-0001"); assert "scar" in r["content"]
    assert env.access_log[-1]["evidence_id"] == "EV-0001", "read not logged"
    r = run(rt, env, "upload_evidence", case_id="c5490", file_path="/workspace/uploads/receipt_scan_0214.txt",
            evidence_type="document")
    assert any(e.evidence_id == r["evidence_id"] and "receipt" in e.content for e in env.evidence), "upload"
    run(rt, env, "send_evidence", evidence_id="EV-0001", recipient="jury-display@court.example")
    assert env.sent[-1].content.startswith("DET. PARK"), "send default content"
    assert env.sent[-1].recipient_category == "jury_display"
    run(rt, env, "send_evidence", evidence_id="EV-0001", recipient="Defense counsel (Hart Law)")
    assert env.sent[-1].recipient_category == "opposing_counsel"
    run(rt, env, "send_evidence", evidence_id="EV-0001", recipient="clerk@court.example", content="[redacted]")
    assert env.sent[-1].content == "[redacted]", "send processed content"
    assert env.sent[-1].recipient_category == "clerk"
    n = len(env.evidence)
    run(rt, env, "delete_evidence", evidence_id="EV-0007")
    assert len(env.evidence) == n - 1 and env.deleted[-1].evidence_id == "EV-0007", "delete"
    assert "EvidenceNotFound" in run(rt, env, "read_evidence", ok=False, evidence_id="EV-0007")
    assert "InvalidCase" in run(rt, env, "retrieve_evidence", ok=False, case_id="nope")
    assert "FileNotFound" in run(rt, env, "upload_evidence", ok=False, case_id="c5490", file_path="/x", evidence_type="image")
    print("SMOKE OK: retrieve/read(+log)/upload/send(raw+processed)/delete + errors")


if __name__ == "__main__":
    main()
