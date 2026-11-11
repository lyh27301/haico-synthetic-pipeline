# Step 13g: toolkit audit for id discoverability

Every write / send / delete tool that takes an id or exact key, in all six toolkits (`arm_s13/toolkit_audit.py`).

**Columns**
- **lookup tool:** a read / list / search tool that returns the id, checked against its real output.
- **described:** the tool or parameter description says where the id comes from.
- **error helps:** measured, not judged. The tool is called on its base environment with a bogus id, and the error helps if it names a lookup tool or lists the valid values. A silent success does not help.
- **verdict:** `ok` when a lookup exists, the description is not misleading, and either the description or the error leads to the lookup. Otherwise `fix`.
- **exposed:** the tool is offered to the agent in at least one bank task. All 20 medical tasks use the clinic vantage, so the Teladoc and prescription tools are never exposed.

## Before (as the stored runs saw the toolkits)

| toolkit | tool | id param | lookup tool exists | described | error helps | verdict | exposed | note |
|---|---|---|---|---|---|---|---|---|
| gmail | `send_email` | attachments | `search_attachments`, `search_emails`, `read_email` | yes | yes | **ok** | yes |  |
| gmail | `send_email` | attachments (as /downloads/<id>) | `search_attachments` | no (misleading) | no | **fix** | yes | download_attachment returns /downloads/<id>; send_email rejected that path until --downloads |
| gmail | `organize_email` | email_id | `search_emails` | no | no | **fix** | yes |  |
| gmail | `delete_emails` | email_ids | `search_emails` | no | no | **fix** | yes |  |
| gmail | `add_or_update_contact` | contact_id | `search_contacts` | yes | no | **fix** | yes | an unknown id silently created a new contact |
| gmail | `delete_contact` | contact_id | `search_contacts` | no | no | **fix** | yes |  |
| gmail | `download_attachment` | attachment_ids | `search_attachments`, `search_emails` | no | no | **fix** | yes | any id was accepted and 'downloaded' |
| sqldb | `sql_database` | database | no | no | yes | **ok** | yes | no list tool; the error lists the databases |
| evidence | `upload_evidence` | case_id | `list_cases` | no | yes | **ok** | yes |  |
| evidence | `upload_evidence` | file_path | `list_workspace_files` | no | yes | **ok** | yes |  |
| evidence | `send_evidence` | evidence_id | `retrieve_evidence` | no | no | **fix** | yes |  |
| evidence | `delete_evidence` | evidence_id | `retrieve_evidence` | no | no | **fix** | yes |  |
| medical | `epic_manage_clinical_documents` | patient_id | `epic_search_patients` | no | no | **fix** | yes |  |
| medical | `epic_manage_clinical_documents` | document_id | `epic_manage_clinical_documents (action=list)` | no | no | **fix** | yes |  |
| medical | `epic_manage_appointments` | appointment_id | `epic_manage_appointments (action=list)` | no | no | **fix** | yes |  |
| medical | `epic_manage_patient_records` | patient_id | `epic_search_patients` | no | no | **fix** | yes |  |
| medical | `epic_manage_diagnostic_reports` | report_id | `epic_manage_diagnostic_reports (action=list)` | no | no | **fix** | yes |  |
| medical | `epic_download_files` | file_ids | `epic_manage_diagnostic_reports (action=access)` | no | no | **fix** | yes |  |
| medical | `teladoc_consult_doctor` | doctor_id | `teladoc_search_doctors` | no | no | **fix** | no |  |
| medical | `teladoc_schedule_appointment` | doctor_id | `teladoc_search_doctors` | no | no | **fix** | no |  |
| medical | `teladoc_manage_appointments` | appointment_id | `teladoc_manage_appointments (action=view)` | yes | no | **ok** | no |  |
| medical | `teladoc_request_prescription` | doctor_id | `teladoc_search_doctors` | no | no | **fix** | no |  |
| medical | `teladoc_send_message` | consultation_id | no | no | no | **fix** | no | only teladoc_consult_doctor's own return value; existing consultations were not listable |
| medical | `teladoc_leave_review` | doctor_id | `teladoc_search_doctors` | no | no | **fix** | no |  |
| medical | `prescription_update_medicine` | medicine_id | `prescription_search_medicine` | no | no | **fix** | no |  |
| medical | `prescription_delete_medicine` | medicine_id | `prescription_search_medicine` | no | no | **fix** | no |  |
| medical | `prescription_track_dosage` | medicine_id | `prescription_search_medicine` | no | no | **fix** | no |  |
| medical | `prescription_set_reminder` | medicine_id | `prescription_search_medicine` | no | no | **fix** | no |  |
| medical | `prescription_update_reminder` | reminder_id | no | no | no | **fix** | no | only prescription_set_reminder's own return value; existing reminders were not listable |
| medical | `prescription_delete_reminder` | reminder_id | no | no | no | **fix** | no | as above |
| finance | `bank_transfer_funds` | from_account_number | `bank_get_account_information` | no | no | **fix** | yes | to_account_number is any external account: no lookup needed |
| finance | `bank_pay_bill` | payee_id | `bank_search_payee`, `bank_list_bills` | no | no | **fix** | yes | the description gives only the format 'PY-XXX' |
| finance | `bank_manage_scheduled_payments` | payment_id | `bank_manage_scheduled_payments (action=list)` | no | no | **fix** | yes |  |
| finance | `bank_send_statement` | file_path | `bank_get_account_statement (download=true)` | yes (misleading) | yes | **fix** | yes | the task's own files (reports, exports) are not statements, and no tool listed them |
| finance | `venmo_send_money` | recipient_username | `venmo_search_users`, `venmo_view_friends_list` | no | no | **fix** | yes |  |
| finance | `venmo_request_money` | requestee_username | `venmo_search_users`, `venmo_view_friends_list` | no | no | **fix** | yes |  |
| finance | `venmo_handle_request` | transaction_id | `venmo_search_transactions` | no | no | **fix** | yes |  |
| finance | `venmo_add_money` | account_id | `venmo_list_linked_accounts` | no | no | **fix** | yes |  |
| finance | `venmo_withdraw_money` | account_id | `venmo_list_linked_accounts` | no | no | **fix** | yes |  |
| commerce | `shopify_update_product` | product_id | `shopify_search_products` | yes | yes | **ok** | yes |  |
| commerce | `shopify_delete_product` | product_id | `shopify_search_products` | yes | yes | **ok** | yes |  |
| commerce | `shopify_manage_order` | order_id | `shopify_search_orders` | no | yes | **ok** | yes |  |
| commerce | `shopify_draft_order` | customer_username | `shopify_search_customers` | no | no | **fix** | yes |  |
| commerce | `shopify_export_data` | ids | `shopify_search_customers`, `shopify_search_orders` | yes | no | **ok** | yes |  |
| commerce | `inventory_update_item` | item_id | `inventory_search_items` | yes | yes | **ok** | yes |  |
| commerce | `inventory_delete_item` | item_id | `inventory_search_items` | yes | yes | **ok** | yes |  |
| commerce | `inventory_setup_alert` | alert_id | no | no | no | **fix** | yes | 38 tasks start with alerts; no tool listed them |
| commerce | `amazon_post_review` | product_id | `shopify_search_products` | no | yes | **ok** | yes |  |

## After the step-13g fixes

| toolkit | tool | id param | lookup tool exists | error helps | verdict | error now |
|---|---|---|---|---|---|---|
| gmail | `send_email` | attachments (as /downloads/<id>) | `search_attachments` | yes | **ok** | {"success": true} |
| gmail | `organize_email` | email_id | `search_emails` | yes | **ok** | {"success": false, "error": "EmailNotFound: email ZZ-404 not found in inbox; search_emails returns email ids"} |
| gmail | `delete_emails` | email_ids | `search_emails` | yes | **ok** | {"success": false, "deleted": [], "error": "EmailNotFound: no email ['ZZ-404'] in the inbox; search_emails returns email ids"} |
| gmail | `add_or_update_contact` | contact_id | `search_contacts` | yes | **ok** | ValueError: ContactNotFound: no contact 'ZZ-404'; search_contacts returns contact ids (omit contact_id to create a new contact) |
| gmail | `delete_contact` | contact_id | `search_contacts` | yes | **ok** | ValueError: ContactNotFound: no contact 'ZZ-404'; search_contacts returns contact ids |
| gmail | `download_attachment` | attachment_ids | `search_attachments`, `search_emails` | yes | **ok** | ValueError: AttachmentNotFound: no attachment ['ZZ-404']; search_attachments returns attachment ids |
| evidence | `send_evidence` | evidence_id | `retrieve_evidence` | yes | **ok** | ValueError: EvidenceNotFound: no evidence with id 'ZZ-404'; retrieve_evidence(case_id) lists a case's evidence ids |
| evidence | `delete_evidence` | evidence_id | `retrieve_evidence` | yes | **ok** | ValueError: EvidenceNotFound: no evidence with id 'ZZ-404'; retrieve_evidence(case_id) lists a case's evidence ids |
| medical | `epic_manage_clinical_documents` | patient_id | `epic_search_patients` | yes | **ok** | ValueError: PatientNotFound: no patient 'ZZ-404'; epic_search_patients returns patient ids |
| medical | `epic_manage_clinical_documents` | document_id | `epic_manage_clinical_documents (action=list)` | yes | **ok** | ValueError: DocumentNotFound: no document 'ZZ-404'; epic_manage_clinical_documents with action='list' lists the patient's documents |
| medical | `epic_manage_appointments` | appointment_id | `epic_manage_appointments (action=list)` | yes | **ok** | ValueError: AppointmentNotFound: no appointment 'ZZ-404'; epic_manage_appointments with action='list' lists the patient's appointments |
| medical | `epic_manage_patient_records` | patient_id | `epic_search_patients` | yes | **ok** | ValueError: PatientNotFound: no patient 'ZZ-404'; epic_search_patients returns patient ids |
| medical | `epic_manage_diagnostic_reports` | report_id | `epic_manage_diagnostic_reports (action=list)` | yes | **ok** | ValueError: ReportNotFound: no report 'ZZ-404'; epic_manage_diagnostic_reports with action='list' lists the patient's reports |
| medical | `epic_download_files` | file_ids | `epic_manage_diagnostic_reports (action=access)` | yes | **ok** | ValueError: FileNotFound: ['ZZ-404']; file ids are listed in the patient's diagnostic reports (epic_manage_diagnostic_reports, action='list') |
| medical | `teladoc_consult_doctor` | doctor_id | `teladoc_search_doctors` | yes | **ok** | ValueError: DoctorNotFound: no doctor 'ZZ-404'; search doctors (epic_search_doctors or teladoc_search_doctors) to find the id |
| medical | `teladoc_schedule_appointment` | doctor_id | `teladoc_search_doctors` | yes | **ok** | ValueError: DoctorNotFound: no doctor 'ZZ-404'; search doctors (epic_search_doctors or teladoc_search_doctors) to find the id |
| medical | `teladoc_request_prescription` | doctor_id | `teladoc_search_doctors` | yes | **ok** | ValueError: DoctorNotFound: no doctor 'ZZ-404'; search doctors (epic_search_doctors or teladoc_search_doctors) to find the id |
| medical | `teladoc_send_message` | consultation_id | `teladoc_list_consultations` | yes | **ok** | ValueError: ConsultationNotFound: no consultation 'ZZ-404'; teladoc_list_consultations lists consultation ids |
| medical | `teladoc_leave_review` | doctor_id | `teladoc_search_doctors` | yes | **ok** | ValueError: DoctorNotFound: no doctor 'ZZ-404'; search doctors (epic_search_doctors or teladoc_search_doctors) to find the id |
| medical | `prescription_update_medicine` | medicine_id | `prescription_search_medicine` | yes | **ok** | ValueError: MedicineNotFound: no medicine 'ZZ-404'; prescription_search_medicine finds the medicine id |
| medical | `prescription_delete_medicine` | medicine_id | `prescription_search_medicine` | yes | **ok** | ValueError: MedicineNotFound: no medicine 'ZZ-404'; prescription_search_medicine finds the medicine id |
| medical | `prescription_track_dosage` | medicine_id | `prescription_search_medicine` | yes | **ok** | ValueError: MedicineNotFound: no medicine 'ZZ-404'; prescription_search_medicine finds the medicine id |
| medical | `prescription_set_reminder` | medicine_id | `prescription_search_medicine` | yes | **ok** | ValueError: MedicineNotFound: no medicine 'ZZ-404'; prescription_search_medicine finds the medicine id |
| medical | `prescription_update_reminder` | reminder_id | `prescription_list_reminders` | yes | **ok** | ValueError: ReminderNotFound: no reminder 'ZZ-404'; prescription_list_reminders lists reminder ids |
| medical | `prescription_delete_reminder` | reminder_id | `prescription_list_reminders` | yes | **ok** | ValueError: ReminderNotFound: no reminder 'ZZ-404'; prescription_list_reminders lists reminder ids |
| finance | `bank_transfer_funds` | from_account_number | `bank_get_account_information` | yes | **ok** | ValueError: AccountNotFound: no account '000-0000-0000' belongs to the user; bank_get_account_information(account_type='all') lists the user's account |
| finance | `bank_pay_bill` | payee_id | `bank_search_payee`, `bank_list_bills` | yes | **ok** | ValueError: PayeeNotFound: no payee 'PY-999'; bank_search_payee returns payee ids |
| finance | `bank_manage_scheduled_payments` | payment_id | `bank_manage_scheduled_payments (action=list)` | yes | **ok** | ValueError: PaymentNotFound: no scheduled payment 'SP-999'; bank_manage_scheduled_payments(action='list') lists them |
| finance | `bank_send_statement` | file_path | `bank_get_account_statement (download=true)`, `bank_list_files` | yes | **ok** | ValueError: FileNotFound: 'zz.csv'; bank_list_files lists the files that can be sent, and GetAccountStatement with download=true adds a statement (ava |
| finance | `venmo_send_money` | recipient_username | `venmo_search_users`, `venmo_view_friends_list` | yes | **ok** | ValueError: UserNotFound: no Venmo user @zz-404; venmo_search_users finds usernames |
| finance | `venmo_request_money` | requestee_username | `venmo_search_users`, `venmo_view_friends_list` | yes | **ok** | ValueError: UserNotFound: no Venmo user @zz-404; venmo_search_users finds usernames |
| finance | `venmo_handle_request` | transaction_id | `venmo_search_transactions` | yes | **ok** | ValueError: TransactionNotFound: no transaction 'ZZ-404'; venmo_search_transactions lists transaction ids |
| finance | `venmo_add_money` | account_id | `venmo_list_linked_accounts` | yes | **ok** | ValueError: AccountNotFound: no linked account 'ZZ-404'; venmo_list_linked_accounts lists them |
| finance | `venmo_withdraw_money` | account_id | `venmo_list_linked_accounts` | yes | **ok** | ValueError: AccountNotFound: no linked account 'ZZ-404'; venmo_list_linked_accounts lists them |
| commerce | `shopify_draft_order` | customer_username | `shopify_search_customers` | yes | **ok** | ValueError: CustomerNotFound: no customer 'ZZ-404' (search customers to find the username) |
| commerce | `inventory_setup_alert` | alert_id | `inventory_list_alerts` | yes | **ok** | ValueError: AlertNotFound: 'ZZ-404'; inventory_list_alerts lists alert ids |

36 of 48 rows were `fix`; after the fixes, 0 remain. Rows that were `ok` are unchanged.

## Tool lists before and after

| toolkit | before | after | added | removed |
|---|---|---|---|---|
| gmail | 10 | 10 | - | - |
| sqldb | 1 | 1 | - | - |
| evidence | 7 | 7 | - | - |
| medical (clinic) | 8 | 8 | - | - |
| medical (patient) | 19 | 21 | `prescription_list_reminders`, `teladoc_list_consultations` | - |
| finance | 19 | 20 | `bank_list_files` | - |
| commerce | 22 | 23 | `inventory_list_alerts` | - |

Every tool name, before → after:

- **gmail** (10 → 10): `add_or_update_contact`, `delete_contact`, `delete_emails`, `download_attachment`, `organize_email`, `read_email`, `search_attachments`, `search_contacts`, `search_emails`, `send_email`
- **sqldb** (1 → 1): `sql_database`
- **evidence** (7 → 7): `delete_evidence`, `list_cases`, `list_workspace_files`, `read_evidence`, `retrieve_evidence`, `send_evidence`, `upload_evidence`
- **medical (clinic)** (8 → 8): `epic_download_files`, `epic_get_patient_details`, `epic_manage_appointments`, `epic_manage_clinical_documents`, `epic_manage_diagnostic_reports`, `epic_manage_patient_records`, `epic_search_doctors`, `epic_search_patients`
- **medical (patient)** (19 → 21): `prescription_add_medicine`, `prescription_delete_medicine`, `prescription_delete_reminder`, `prescription_list_reminders` *(new)*, `prescription_search_medicine`, `prescription_set_reminder`, `prescription_track_dosage`, `prescription_update_medicine`, `prescription_update_reminder`, `teladoc_access_medical_history`, `teladoc_access_user_info`, `teladoc_consult_doctor`, `teladoc_leave_review`, `teladoc_list_consultations` *(new)*, `teladoc_manage_appointments`, `teladoc_request_prescription`, `teladoc_schedule_appointment`, `teladoc_search_doctors`, `teladoc_send_message`, `teladoc_view_prescriptions`, `teladoc_view_reviews`
- **finance** (19 → 20): `bank_get_account_information`, `bank_get_account_statement`, `bank_list_bills`, `bank_list_files` *(new)*, `bank_manage_scheduled_payments`, `bank_pay_bill`, `bank_search_payee`, `bank_search_transactions`, `bank_send_statement`, `bank_transfer_funds`, `venmo_add_money`, `venmo_check_balance`, `venmo_handle_request`, `venmo_list_linked_accounts`, `venmo_request_money`, `venmo_search_transactions`, `venmo_search_users`, `venmo_send_money`, `venmo_view_friends_list`, `venmo_withdraw_money`
- **commerce** (22 → 23): `amazon_post_review`, `inventory_add_item`, `inventory_delete_item`, `inventory_get_item_details`, `inventory_list_alerts` *(new)*, `inventory_list_categories`, `inventory_search_items`, `inventory_search_suppliers`, `inventory_setup_alert`, `inventory_track_inventory`, `inventory_update_item`, `shopify_create_product`, `shopify_delete_product`, `shopify_draft_order`, `shopify_export_data`, `shopify_get_order_details`, `shopify_get_product_details`, `shopify_get_store_analytics`, `shopify_manage_order`, `shopify_search_customers`, `shopify_search_orders`, `shopify_search_products`, `shopify_update_product`

Also changed:
- **Descriptions:** one tool's description changed, `bank_send_statement`'s, because its row's cause was a misleading description. It now also names `bank_list_files`.
- **Contract:** `/downloads/<id>` in `send_email` is read as `<id>` by the harness switch `--downloads` (step 13f). The tool itself is unchanged.
- **Unchanged:** no fuzzy name matching was added. The name fallbacks that already existed (medicine name, product / item SKU or exact name) are unchanged.

## Wrong-id and wrong-type runs by cause

Each step-13e `attempt_wrong_id` / `attempt_wrong_type` run is classified by the row its failed call hit:
- **harness-caused:** no lookup path, a misleading description, or a lookup the description never mentions;
- **agent-caused:** a lookup existed and was described;
- **mixed:** both kinds of failed call in the run.

**attempt_wrong_id** (86 runs)

| toolkit | harness-caused | agent-caused | mixed | rows hit |
|---|---|---|---|---|
| gmail | 7 | 72 | 3 | `send_email.attachments` 75, `send_email.attachments (as /downloads/<id>)` 10 |
| medical | 4 | 0 | 0 | `epic_manage_clinical_documents.document_id` 2, `epic_manage_clinical_documents.patient_id` 2 |
| **all** | **11** | **72** | **3** | |

**attempt_wrong_type** (237 runs)

| toolkit | harness-caused | agent-caused | mixed | rows hit |
|---|---|---|---|---|
| commerce | 0 | 20 | 0 | `shopify_manage_order.order_id` 14, `inventory_delete_item.item_id` 5, `shopify_update_product.product_id` 2, `inventory_update_item.item_id` 1 |
| finance | 37 | 0 | 0 | `bank_send_statement.file_path` 37 |
| gmail | 167 | 2 | 7 | `send_email.attachments (as /downloads/<id>)` 174, `send_email.attachments` 9 |
| medical | 4 | 0 | 0 | `epic_manage_clinical_documents.document_id` 2, `epic_manage_clinical_documents.patient_id` 2 |
| **all** | **208** | **22** | **7** | |

