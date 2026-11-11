"""Step 13g: toolkit audit for id discoverability.

For every write / send / delete tool that takes an id or exact key, in all six toolkits:
  lookup     a read / list / search tool returns that id (checked by hand against the lookup's real output)
  described  the tool or parameter description says where the id comes from (quoted in `how`)
  misleading the description points the agent somewhere that does not work for the task's ids
  error      measured: the tool is called on its base environment with a bogus id; the error "helps" if it names a
             lookup tool or lists the valid values. A call that silently succeeds or returns no error does not help.
  verdict    ok = lookup exists, not misleading, and (described or the error helps); otherwise fix.
Then the runs flagged attempt_wrong_id / attempt_wrong_type in step 13e (arm_s13/outcomes.jsonl) are classified by the
verdict of the row their failed call hit:
  harness-caused  no lookup path, a misleading description, or a lookup the description never mentions;
  agent-caused    a lookup existed and was described (the agent had an adequate tool).
  AUDIT_CODE_ROOT=<pre-13g checkout> .venv/bin/python arm_s13/toolkit_audit.py --phase before
  .venv/bin/python arm_s13/toolkit_audit.py --phase after  ->  arm_s13/toolkit_audit_<phase>.json,
                                                                         arm_s13/toolkit_audit.md (after both)"""
import argparse, collections, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; S13 = ROOT / "arm_s13"
CODE = Path(os.environ.get("AUDIT_CODE_ROOT") or ROOT)   # --phase before runs on the pre-13g code (git archive)
sys.path.insert(0, str(CODE))
from recipe import profiles  # noqa: E402

Z = "ZZ-404"
# toolkit, tool, param, bogus args, lookup tools, described (quote or None), misleading, exposed in the bank, note
ROWS = [
    ("gmail", "send_email", "attachments", {"to": "a@b.com", "subject": "s", "body": "b", "attachments": [Z]},
     ["search_attachments", "search_emails", "read_email"], "List of attachment ids (from existing emails)", False, True, ""),
    ("gmail", "send_email", "attachments (as /downloads/<id>)", {"to": "a@b.com", "subject": "s", "body": "b",
     "attachments": ["/downloads/att_customers"]}, ["search_attachments"],
     None, True, True, "download_attachment returns /downloads/<id>; send_email rejected that path until --downloads"),
    ("gmail", "organize_email", "email_id", {"email_id": Z, "folder": "archive"}, ["search_emails"], None, False, True, ""),
    ("gmail", "delete_emails", "email_ids", {"email_ids": [Z]}, ["search_emails"], None, False, True, ""),
    ("gmail", "add_or_update_contact", "contact_id", {"contact_id": Z, "name": "x"}, ["search_contacts"],
     "Id of an existing contact to update", False, True, "an unknown id silently created a new contact"),
    ("gmail", "delete_contact", "contact_id", {"contact_id": Z}, ["search_contacts"], None, False, True, ""),
    ("gmail", "download_attachment", "attachment_ids", {"attachment_ids": [Z]}, ["search_attachments", "search_emails"],
     None, False, True, "any id was accepted and 'downloaded'"),
    ("sqldb", "sql_database", "database", {"query": "select 1", "database": Z}, [], None, False, True,
     "no list tool; the error lists the databases"),
    ("evidence", "upload_evidence", "case_id", {"case_id": Z, "file_path": "/workspace/uploads/receipt_scan_0214.txt",
     "evidence_type": "document"}, ["list_cases"], None, False, True, ""),
    ("evidence", "upload_evidence", "file_path", {"case_id": "c5490", "file_path": "/zz/unknown.txt",
     "evidence_type": "document"}, ["list_workspace_files"], None, False, True, ""),
    ("evidence", "send_evidence", "evidence_id", {"evidence_id": Z, "recipient": "x@y.com"}, ["retrieve_evidence"],
     None, False, True, ""),
    ("evidence", "delete_evidence", "evidence_id", {"evidence_id": Z}, ["retrieve_evidence"], None, False, True, ""),
    ("medical", "epic_manage_clinical_documents", "patient_id", {"patient_id": Z, "action": "list"},
     ["epic_search_patients"], None, False, True, ""),
    ("medical", "epic_manage_clinical_documents", "document_id", {"patient_id": "P-1001", "action": "update",
     "document_id": Z, "document_data": {"content": "x"}}, ["epic_manage_clinical_documents (action=list)"],
     None, False, True, ""),
    ("medical", "epic_manage_appointments", "appointment_id", {"patient_id": "P-1001", "action": "update",
     "appointment_id": Z, "appointment_data": {"time": "10:00"}}, ["epic_manage_appointments (action=list)"],
     None, False, True, ""),
    ("medical", "epic_manage_patient_records", "patient_id", {"patient_id": Z, "action": "update",
     "record_data": {"notes": "x"}}, ["epic_search_patients"], None, False, True, ""),
    ("medical", "epic_manage_diagnostic_reports", "report_id", {"patient_id": "P-1001", "action": "access",
     "report_id": Z}, ["epic_manage_diagnostic_reports (action=list)"], None, False, True, ""),
    ("medical", "epic_download_files", "file_ids", {"file_ids": [Z]}, ["epic_manage_diagnostic_reports (action=access)"],
     None, False, True, ""),
    ("medical", "teladoc_consult_doctor", "doctor_id", {"doctor_id": Z, "reason": "x"}, ["teladoc_search_doctors"],
     None, False, False, ""),
    ("medical", "teladoc_schedule_appointment", "doctor_id", {"doctor_id": Z, "date": "2026-12-01", "time": "10:00",
     "reason": "x"}, ["teladoc_search_doctors"], None, False, False, ""),
    ("medical", "teladoc_manage_appointments", "appointment_id", {"action": "cancel", "appointment_id": Z},
     ["teladoc_manage_appointments (action=view)"], "'view' without an appointment_id lists all of the user's "
     "appointments", False, False, ""),
    ("medical", "teladoc_request_prescription", "doctor_id", {"medication_name": "x", "dosage": "1", "doctor_id": Z},
     ["teladoc_search_doctors"], None, False, False, ""),
    ("medical", "teladoc_send_message", "consultation_id", {"consultation_id": Z, "message_content": "hi"}, [],
     None, False, False, "only teladoc_consult_doctor's own return value; existing consultations were not listable"),
    ("medical", "teladoc_leave_review", "doctor_id", {"doctor_id": Z, "rating": 5, "review_content": "x"},
     ["teladoc_search_doctors"], None, False, False, ""),
    ("medical", "prescription_update_medicine", "medicine_id", {"medicine_id": Z, "dosage": "1"},
     ["prescription_search_medicine"], None, False, False, ""),
    ("medical", "prescription_delete_medicine", "medicine_id", {"medicine_id": Z}, ["prescription_search_medicine"],
     None, False, False, ""),
    ("medical", "prescription_track_dosage", "medicine_id", {"medicine_id": Z, "date": "2026-01-01", "time": "10:00"},
     ["prescription_search_medicine"], None, False, False, ""),
    ("medical", "prescription_set_reminder", "medicine_id", {"medicine_id": Z, "reminder_time": "10:00",
     "reminder_date": "2026-01-01"}, ["prescription_search_medicine"], None, False, False, ""),
    ("medical", "prescription_update_reminder", "reminder_id", {"reminder_id": Z, "reminder_time": "10:00"}, [],
     None, False, False, "only prescription_set_reminder's own return value; existing reminders were not listable"),
    ("medical", "prescription_delete_reminder", "reminder_id", {"reminder_id": Z}, [], None, False, False,
     "as above"),
    ("finance", "bank_transfer_funds", "from_account_number", {"from_account_number": "000-0000-0000",
     "to_account_number": "111-1111-1111", "amount": 1}, ["bank_get_account_information"],
     None, False, True, "to_account_number is any external account: no lookup needed"),
    ("finance", "bank_pay_bill", "payee_id", {"from_account_number": "041-2277-0193", "payee_id": "PY-999",
     "service_account_number": "1", "payment_date": "2026-12-01", "amount": 1}, ["bank_search_payee", "bank_list_bills"],
     None, False, True, "the description gives only the format 'PY-XXX'"),
    ("finance", "bank_manage_scheduled_payments", "payment_id", {"action": "cancel", "payment_id": "SP-999"},
     ["bank_manage_scheduled_payments (action=list)"], None, False, True, ""),
    ("finance", "bank_send_statement", "file_path", {"file_path": "zz.csv", "recipient": "x@y.com"},
     ["bank_get_account_statement (download=true)"], "The statement file path returned by GetAccountStatement", True,
     True, "the task's own files (reports, exports) are not statements, and no tool listed them"),
    ("finance", "venmo_send_money", "recipient_username", {"recipient_username": Z, "amount": 1},
     ["venmo_search_users", "venmo_view_friends_list"], None, False, True, ""),
    ("finance", "venmo_request_money", "requestee_username", {"requestee_username": Z, "amount": 1},
     ["venmo_search_users", "venmo_view_friends_list"], None, False, True, ""),
    ("finance", "venmo_handle_request", "transaction_id", {"transaction_id": Z, "action": "confirm"},
     ["venmo_search_transactions"], None, False, True, ""),
    ("finance", "venmo_add_money", "account_id", {"amount": 1, "account_id": Z}, ["venmo_list_linked_accounts"],
     None, False, True, ""),
    ("finance", "venmo_withdraw_money", "account_id", {"amount": 1, "account_id": Z}, ["venmo_list_linked_accounts"],
     None, False, True, ""),
    ("commerce", "shopify_update_product", "product_id", {"product_id": Z, "price": 1}, ["shopify_search_products"],
     "Unique identifier of the product to update (a SKU or the exact name also works)", False, True, ""),
    ("commerce", "shopify_delete_product", "product_id", {"product_id": Z}, ["shopify_search_products"],
     "Unique identifier of the product to delete (a SKU or the exact name also works)", False, True, ""),
    ("commerce", "shopify_manage_order", "order_id", {"order_id": Z, "action": "cancel"}, ["shopify_search_orders"],
     None, False, True, ""),
    ("commerce", "shopify_draft_order", "customer_username", {"customer_username": Z, "items": [], "total_price": 1,
     "shipping_details": {}}, ["shopify_search_customers"], None, False, True, ""),
    ("commerce", "shopify_export_data", "ids", {"data_type": "customers", "destination": "x@y.com", "ids": [Z]},
     ["shopify_search_customers", "shopify_search_orders"], "as in SearchCustomers / SearchOrders", False, True, ""),
    ("commerce", "inventory_update_item", "item_id", {"item_id": Z, "quantity": 1}, ["inventory_search_items"],
     "a SKU or the exact name also works", False, True, ""),
    ("commerce", "inventory_delete_item", "item_id", {"item_id": Z}, ["inventory_search_items"],
     "a SKU or the exact name also works", False, True, ""),
    ("commerce", "inventory_setup_alert", "alert_id", {"threshold": 1, "operation": "delete", "alert_id": Z}, [],
     None, False, True, "38 tasks start with alerts; no tool listed them"),
    ("commerce", "amazon_post_review", "product_id", {"product_id": Z, "review": "x"}, ["shopify_search_products"],
     None, False, True, ""),
]
HELP = re.compile(r"\bknown\b|\bavailable\b|\bsearch\b|\blists?\b|\blisted\b|find the id", re.I)
ENUM = re.compile(r"\bknown\b[^:]*:|\bavailable\b[^:]*:", re.I)   # the error enumerates the valid values


def runtime(tk):
    p = profiles.get(tk)
    env = p.load_environment(CODE / f"{tk}_suite/base_environment.yaml")
    if tk == "medical":
        import medical_suite.tools as M
        return env, M.build_runtime(None)
    return env, p.build_runtime()


def probe(row, after_lookups):
    tk, tool, param, args, lookups, how, misleading, exposed, note = row
    env, rt = runtime(tk)
    if tool not in rt.functions:
        return {"error": None, "observed": "tool missing"}
    if param.startswith("attachments (as") and after_lookups:   # after: rollouts run send_email through --downloads
        sys.path.insert(0, str(CODE / "harness")); import workspace_bridge
        res, err, _ = workspace_bridge.call(profiles.get(tk), env, rt, tool, args, {}, downloads=True)
    else:
        res, err = rt.run_function(env, tool, args)
    text = err or json.dumps(res, default=str)
    if not err and isinstance(res, dict) and res.get("error"):   # tools that return their error instead of raising
        err = str(res["error"])
    names = [l.split(" ")[0] for l in lookups + after_lookups.get((tool, param), [])]
    if param.startswith("attachments (as"):   # the contract row: helps if the /downloads path now resolves
        return {"error": err, "observed": text[:200], "helps": not err}
    helps = bool(err) and (any(n in err for n in names) or bool(HELP.search(err.replace(Z, ""))))
    silent = not err and ('"success": false' in text.lower() or '"deleted": []' in text or tool in
                          ("add_or_update_contact", "download_attachment"))   # no error on an unknown id
    return {"error": err, "observed": text[:200], "helps": helps, "silent": silent,
            "enumerates": bool(err) and bool(ENUM.search(err))}


DESCRIPTION_FIXED = {   # rows whose cause was a misleading contract, fixed in the contract itself
    ("send_email", "attachments (as /downloads/<id>)"): "--downloads: send_email reads /downloads/<id> as <id>",
    ("bank_send_statement", "file_path"): "The statement file path returned by GetAccountStatement, or a file path "
                                          "listed by bank_list_files",
}
AFTER_LOOKUPS = {   # lookup tools added in step 13g
    ("teladoc_send_message", "consultation_id"): ["teladoc_list_consultations"],
    ("prescription_update_reminder", "reminder_id"): ["prescription_list_reminders"],
    ("prescription_delete_reminder", "reminder_id"): ["prescription_list_reminders"],
    ("bank_send_statement", "file_path"): ["bank_list_files"],
    ("inventory_setup_alert", "alert_id"): ["inventory_list_alerts"],
}


def tool_lists():
    """toolkit -> the tool names offered (medical: per vantage)."""
    out = {}
    for tk in profiles.NAMES:
        if tk == "medical":
            import medical_suite.tools as M
            for v in M.VANTAGES:
                out[f"medical ({v})"] = sorted(M.build_runtime(v).functions)
        else:
            out[tk] = sorted(profiles.get(tk).build_runtime().functions)
    return out


def audit(phase):
    (S13 / f"toolkit_tools_{phase}.json").write_text(json.dumps(tool_lists(), indent=1))
    out = []
    for row in ROWS:
        tk, tool, param, args, lookups, how, misleading, exposed, note = row
        lk = lookups + (AFTER_LOOKUPS.get((tool, param), []) if phase == "after" else [])
        p = probe(row, AFTER_LOOKUPS if phase == "after" else {})
        if phase == "after" and (tool, param) in DESCRIPTION_FIXED:
            misleading, how = False, DESCRIPTION_FIXED[(tool, param)]
        path = bool(lk) or p.get("enumerates", False)
        silent = p.get("silent", False)
        ok = path and not misleading and not silent and (bool(how) or p["helps"])
        cause = None if ok else ("no lookup" if not path else "misleading description" if misleading else
                                 "silent on an unknown id" if silent else "lookup not described, error does not help")
        out.append({"toolkit": tk, "tool": tool, "param": param, "lookup": lk, "described": how, "misleading": misleading,
                    "exposed": exposed, "error_helps": p["helps"], "silent": p.get("silent", False),
                    "error_lists_values": p.get("enumerates", False), "observed": p["observed"], "note": note,
                    "verdict": "ok" if ok else "fix", "harness_cause": cause})
    (S13 / f"toolkit_audit_{phase}.json").write_text(json.dumps(out, indent=1))
    return out


def classify(before):
    """attempt_wrong_id / attempt_wrong_type runs -> harness- or agent-caused by the row their failed call hit."""
    rows = {(r["tool"], r["param"]): r for r in before}
    by_tool = collections.defaultdict(list)
    for r in before:
        by_tool[r["tool"]].append(r)
    O = [json.loads(l) for l in (S13 / "outcomes.jsonl").read_text().splitlines()]
    res = []
    for o in O:
        for kind in ("attempt_wrong_id", "attempt_wrong_type"):
            if not o[kind]:
                continue
            S = {s["step"]: s for s in json.loads((S13 / "steps" / f"{o['task']}__{o['agent']}__r{o['run']}.json").read_text())}
            causes = []
            for i in o[kind + "_steps"]:
                s = S[i]; a = s["args"] if isinstance(s["args"], dict) else {}
                if s["tool"] == "send_email" and any(isinstance(x, str) and x.startswith("/downloads/")
                                                     for x in a.get("attachments") or []):
                    r = rows[("send_email", "attachments (as /downloads/<id>)")]
                else:
                    cand = [r for r in by_tool[s["tool"]] if not r["param"].startswith("attachments (as")
                            and (r["param"].split(" ")[0] in a)]
                    # the id parameter that failed: the one the error names, else the first audited one present
                    err = str(s["observation"])
                    r = next((c for c in cand if repr(a.get(c["param"]))[:20].strip("'[") in err), cand[0] if cand else None)
                causes.append(("harness" if r and r["verdict"] == "fix" else "agent", r["tool"] + "." + r["param"]
                               if r else s["tool"], r["harness_cause"] if r else None))
            k = {c[0] for c in causes}
            res.append({"task": o["task"], "agent": o["agent"], "run": o["run"], "kind": kind, "toolkit": o["toolkit"],
                        "class": "harness-caused" if k == {"harness"} else "agent-caused" if k == {"agent"} else "mixed",
                        "rows": sorted({c[1] for c in causes}), "harness_causes": sorted({c[2] for c in causes if c[2]}),
                        "outcome": o["outcome"]})
    return res


def md(before, after, cls):
    def tick(b):
        return "yes" if b else "no"
    L = ["# Step 13g: toolkit audit for id discoverability", "",
         "Every write / send / delete tool that takes an id or exact key, in all six toolkits "
         "(`arm_s13/toolkit_audit.py`).",
         "",
         "**Columns**",
         "- **lookup tool:** a read / list / search tool that returns the id, checked against its real output.",
         "- **described:** the tool or parameter description says where the id comes from.",
         "- **error helps:** measured, not judged. The tool is called on its base environment with a bogus id, and "
         "the error helps if it names a lookup tool or lists the valid values. A silent success does not help.",
         "- **verdict:** `ok` when a lookup exists, the description is not misleading, and either the description "
         "or the error leads to the lookup. Otherwise `fix`.",
         "- **exposed:** the tool is offered to the agent in at least one bank task. All 20 medical tasks use the "
         "clinic vantage, so the Teladoc and prescription tools are never exposed.",
         "", "## Before (as the stored runs saw the toolkits)", "",
         "| toolkit | tool | id param | lookup tool exists | described | error helps | verdict | exposed | note |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in before:
        L.append(f"| {r['toolkit']} | `{r['tool']}` | {r['param']} | {', '.join('`'+x+'`' for x in r['lookup']) or 'no'} | "
                 f"{tick(r['described'])}{' (misleading)' if r['misleading'] else ''} | {tick(r['error_helps'])} | "
                 f"**{r['verdict']}** | {tick(r['exposed'])} | {r['note']} |")
    L += ["", "## After the step-13g fixes", "",
          "| toolkit | tool | id param | lookup tool exists | error helps | verdict | error now |", "|---|---|---|---|---|---|---|"]
    for b, r in zip(before, after):
        if b["verdict"] == "fix":
            L.append(f"| {r['toolkit']} | `{r['tool']}` | {r['param']} | {', '.join('`'+x+'`' for x in r['lookup']) or 'no'} | "
                     f"{tick(r['error_helps'])} | **{r['verdict']}** | {str(r['observed'])[:150].replace('|', '/')} |")
    fx = sum(r["verdict"] == "fix" for r in before)
    L += ["", f"{fx} of {len(before)} rows were `fix`; after the fixes, "
          f"{sum(r['verdict'] == 'fix' for r in after)} remain. Rows that were `ok` are unchanged.", ""]
    tb = json.loads((S13 / "toolkit_tools_before.json").read_text())
    ta = json.loads((S13 / "toolkit_tools_after.json").read_text())
    L += ["## Tool lists before and after", "", "| toolkit | before | after | added | removed |", "|---|---|---|---|---|"]
    for k in tb:
        add, rem = sorted(set(ta[k]) - set(tb[k])), sorted(set(tb[k]) - set(ta[k]))
        L.append(f"| {k} | {len(tb[k])} | {len(ta[k])} | {', '.join('`'+x+'`' for x in add) or '-'} | "
                 f"{', '.join('`'+x+'`' for x in rem) or '-'} |")
    L += ["", "Every tool name, before → after:", ""]
    for k in tb:
        L.append(f"- **{k}** ({len(tb[k])} → {len(ta[k])}): " + ", ".join(
            f"`{x}`" + (" *(new)*" if x not in tb[k] else "") for x in ta[k]))
    L += ["", "Also changed:",
          "- **Descriptions:** one tool's description changed, `bank_send_statement`'s, because its row's cause was a "
          "misleading description. It now also names `bank_list_files`.",
          "- **Contract:** `/downloads/<id>` in `send_email` is read as `<id>` by the harness switch `--downloads` "
          "(step 13f). The tool itself is unchanged.",
          "- **Unchanged:** no fuzzy name matching was added. The name fallbacks that already existed (medicine name, "
          "product / item SKU or exact name) are unchanged.", ""]
    L += ["## Wrong-id and wrong-type runs by cause", "",
          "Each step-13e `attempt_wrong_id` / `attempt_wrong_type` run is classified by the row its failed call hit:",
          "- **harness-caused:** no lookup path, a misleading description, or a lookup the description never mentions;",
          "- **agent-caused:** a lookup existed and was described;",
          "- **mixed:** both kinds of failed call in the run.", ""]
    for kind in ("attempt_wrong_id", "attempt_wrong_type"):
        xs = [c for c in cls if c["kind"] == kind]
        L += [f"**{kind}** ({len(xs)} runs)", "", "| toolkit | harness-caused | agent-caused | mixed | rows hit |",
              "|---|---|---|---|---|"]
        for tk in sorted({c["toolkit"] for c in xs}):
            ys = [c for c in xs if c["toolkit"] == tk]; cc = collections.Counter(c["class"] for c in ys)
            rows = collections.Counter(r for c in ys for r in c["rows"])
            L.append(f"| {tk} | {cc['harness-caused']} | {cc['agent-caused']} | {cc['mixed']} | "
                     + ", ".join(f"`{k}` {v}" for k, v in rows.most_common()) + " |")
        cc = collections.Counter(c["class"] for c in xs)
        L += [f"| **all** | **{cc['harness-caused']}** | **{cc['agent-caused']}** | **{cc['mixed']}** | |", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--phase", choices=["before", "after"], default="before")
    a = ap.parse_args()
    rows = audit(a.phase)
    print(f"{a.phase}: {sum(r['verdict'] == 'fix' for r in rows)} fix of {len(rows)}")
    for r in rows:
        print(f"  {r['verdict']:3} {r['toolkit']:8} {r['tool']:32} {r['param']:34} helps={r['error_helps']} | {r['observed'][:90]}")
    if a.phase == "after":
        before = json.loads((S13 / "toolkit_audit_before.json").read_text())
        cls = classify(before)
        (S13 / "toolkit_audit_runs.json").write_text(json.dumps(cls, indent=1))
        (S13 / "toolkit_audit.md").write_text(md(before, rows, cls))


if __name__ == "__main__":
    main()
