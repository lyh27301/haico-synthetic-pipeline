"""Smoke test: call each of the 9 Gmail tools via the runtime and assert state changes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gmail_suite.environment import load_environment
from gmail_suite.tools import build_runtime

BASE = Path(__file__).parent / "base_environment.yaml"

def run(rt, env, fn, **kw):
    out, err = rt.run_function(env, fn, kw, raise_on_error=True)
    return out

def main():
    rt = build_runtime()
    env = load_environment(BASE)
    n0_inbox, n0_sent, n0_trash = len(env.inbox), len(env.sent), len(env.trash)
    n0_contacts = len(env.contacts)

    # search / read (read-only)
    r = run(rt, env, "search_emails", keywords=["customer"]); assert r["emails"], "search found nothing"
    r = run(rt, env, "read_email", email_id="email_2"); assert "salary" in r["body"], "read failed"
    # send -> sent grows
    run(rt, env, "send_email", to="alice@company.com", subject="hi", body="test")
    assert len(env.sent) == n0_sent + 1, "send_email did not append to sent"
    # organize -> folder/labels change
    run(rt, env, "organize_email", email_id="email_1", folder="archive", labels=["x"])
    assert any(e.id=="email_1" and e.folder=="archive" for e in env.inbox), "organize failed"
    # delete -> inbox shrinks, trash grows
    run(rt, env, "delete_emails", email_ids=["email_6"])
    assert len(env.trash) == n0_trash + 1 and len(env.inbox) == n0_inbox - 1, "delete failed"
    # contacts: add, search, delete
    r = run(rt, env, "add_or_update_contact", name="New Person", email="new@company.com")
    cid = r["contact_id"]; assert len(env.contacts) == n0_contacts + 1, "add contact failed"
    r = run(rt, env, "search_contacts", name="New Person"); assert r["contacts"], "search contacts failed"
    run(rt, env, "delete_contact", contact_id=cid)
    assert len(env.contacts) == n0_contacts, "delete contact failed"
    # download -> downloads records id
    run(rt, env, "download_attachment", attachment_ids=["att_customers"])
    assert "att_customers" in env.downloads, "download failed"

    print("SMOKE OK: all 9 tools mutate state as expected")
    print(f"  sent={len(env.sent)} trash={len(env.trash)} contacts={len(env.contacts)} downloads={env.downloads}")

if __name__ == "__main__":
    main()
