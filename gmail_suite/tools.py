"""The 9 ToolEmu Gmail tools as real AgentDojo functions over GmailEnvironment.

Each tool takes the env slices it needs via ``Depends(...)`` and actually
mutates state. Docstrings use the AgentDojo ``:param:`` format so they become
the tool schema the agent sees. Argument names follow the ToolEmu contract.
"""

from __future__ import annotations

from typing import Annotated

from agentdojo.functions_runtime import Depends, FunctionsRuntime

from gmail_suite.environment import (
    ACCOUNT_EMAIL,
    Attachment,
    Contact,
    Email,
)


def _as_list(x) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    # comma/semicolon separated string
    return [p.strip() for p in str(x).replace(";", ",").split(",") if p.strip()]


def _find_email(pools: list[list[Email]], email_id: str) -> Email | None:
    for pool in pools:
        for e in pool:
            if e.id == email_id:
                return e
    return None


def send_email(
    sent: Annotated[list, Depends("sent")],
    inbox: Annotated[list, Depends("inbox")],
    to: str | list[str],
    subject: str,
    body: str,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    send_at: str | None = None,
    attachments: list[str] | None = None,
) -> dict:
    """Send an email from the account owner's mailbox.

    :param to: Recipient email address(es): a single string, a comma-separated string, or a list of strings.
    :param subject: The subject line.
    :param body: The email body.
    :param cc: CC email address(es): a string, comma-separated string, or list of strings. If null, none.
    :param bcc: BCC email address(es): a string, comma-separated string, or list of strings. If null, none.
    :param send_at: ISO timestamp to schedule send. If null, send now.
    :param attachments: List of attachment ids (from existing emails) to attach. If null, none.
    """
    att_objs: list[Attachment] = []
    for aid in attachments or []:
        found = None
        for e in inbox:
            for a in e.attachments:
                if a.id == aid:
                    found = a
        if found is None:   # step 6: an unknown id used to attach an empty placeholder silently
            known = sorted({a.id for e in inbox for a in e.attachments})
            raise ValueError(f"AttachmentNotFound: no attachment {aid!r} (known attachment ids: {known})")
        att_objs.append(found)
    email = Email(
        id=f"sent_{len(sent) + 1}",
        sender=ACCOUNT_EMAIL,
        recipients=_as_list(to),
        cc=_as_list(cc),
        bcc=_as_list(bcc),
        subject=subject,
        body=body,
        timestamp=send_at or "now",
        folder="sent",
        attachments=att_objs,
    )
    sent.append(email)
    return {"success": True}


def search_emails(
    inbox: Annotated[list, Depends("inbox")],
    sent: Annotated[list, Depends("sent")],
    keywords: list[str] | None = None,
    folders: list[str] | None = None,
    limit: int | None = None,
    from_: str | None = None,
    to: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """Search emails in the mailbox by keyword / sender / folder.

    :param keywords: Keywords to match in subject or body. If null, match all.
    :param folders: Folders to search (e.g. ["inbox","sent"]). If null, inbox+sent.
    :param limit: Max number of results. If null, no limit.
    :param from_: Filter by sender email. If null, any sender.
    :param to: Filter by recipient email. If null, any recipient.
    :param labels: Filter by labels. If null, any.
    """
    pools = {"inbox": inbox, "sent": sent}
    use = folders or ["inbox", "sent"]
    results = []
    for folder in use:
        for e in pools.get(folder, []):
            hay = (e.subject + " " + e.body).lower()
            if keywords and not any(str(k).lower() in hay for k in keywords):
                continue
            if from_ and from_.lower() not in e.sender.lower():
                continue
            if to and not any(to.lower() in r.lower() for r in e.recipients):
                continue
            if labels and not any(lbl in e.labels for lbl in labels):
                continue
            results.append(
                {"id": e.id, "sender": e.sender, "recipients": e.recipients,
                 "subject": e.subject, "snippet": e.body[:120], "folder": e.folder,
                 "attachments": [a.id for a in e.attachments]}
            )
    if limit:
        results = results[: int(limit)]
    return {"emails": results}


def read_email(
    inbox: Annotated[list, Depends("inbox")],
    sent: Annotated[list, Depends("sent")],
    trash: Annotated[list, Depends("trash")],
    email_id: str,
) -> dict:
    """Read the full content of one email by id.

    :param email_id: The id of the email to read.
    """
    e = _find_email([inbox, sent, trash], email_id)
    if e is None:
        return {"error": f"email {email_id} not found"}
    return {
        "from": e.sender, "to": e.recipients, "cc": e.cc, "bcc": e.bcc,
        "subject": e.subject, "body": e.body, "timestamp": e.timestamp,
        "folder": e.folder, "labels": e.labels,
        "attachments": [{"id": a.id, "name": a.name, "content": a.content} for a in e.attachments],
    }


def organize_email(
    inbox: Annotated[list, Depends("inbox")],
    email_id: str,
    folder: str | None = None,
    labels: list[str] | None = None,
) -> dict:
    """Move an email to a folder and/or set labels.

    :param email_id: The id of the email to organize.
    :param folder: Destination folder. If null, unchanged.
    :param labels: Labels to set. If null, unchanged.
    """
    e = _find_email([inbox], email_id)
    if e is None:
        return {"success": False, "error": f"email {email_id} not found in inbox"}
    if folder:
        e.folder = folder
    if labels is not None:
        e.labels = list(labels)
    return {"success": True}


def delete_emails(
    inbox: Annotated[list, Depends("inbox")],
    trash: Annotated[list, Depends("trash")],
    email_ids: list[str],
) -> dict:
    """Delete emails (move them from inbox to trash).

    :param email_ids: List of email ids to delete.
    """
    ids = set(_as_list(email_ids))
    moved = [e for e in inbox if e.id in ids]
    for e in moved:
        e.folder = "trash"
        trash.append(e)
        inbox.remove(e)
    return {"success": True, "deleted": [e.id for e in moved]}


def add_or_update_contact(
    contacts: Annotated[list, Depends("contacts")],
    contact_id: str | None = None,
    name: str | None = None,
    email: str | None = None,
    remark: str | None = None,
    info: dict | None = None,
) -> dict:
    """Add a new contact or update an existing one.

    :param contact_id: Id of an existing contact to update. If null, create new.
    :param name: Contact name.
    :param email: Contact email address.
    :param remark: A remark/note on the contact.
    :param info: Extra structured info.
    """
    c = None
    if contact_id:
        c = next((x for x in contacts if x.id == contact_id), None)
    if c is None:
        cid = contact_id or f"contact_{len(contacts) + 1}"
        c = Contact(id=cid)
        contacts.append(c)
    if name is not None:
        c.name = name
    if email is not None:
        c.email = email
    if remark is not None:
        c.remark = remark
    if info is not None:
        c.info = info
    return {"contact_id": c.id}


def delete_contact(
    contacts: Annotated[list, Depends("contacts")],
    contact_id: str,
) -> dict:
    """Delete a contact by id.

    :param contact_id: The id of the contact to delete.
    """
    before = len(contacts)
    keep = [c for c in contacts if c.id != contact_id]
    contacts.clear()
    contacts.extend(keep)
    return {"success": len(contacts) < before}


def search_contacts(
    contacts: Annotated[list, Depends("contacts")],
    name: str | None = None,
    email: str | None = None,
    remark: str | None = None,
    limit: int | None = None,
) -> dict:
    """Search contacts by name / email / remark.

    :param name: Name substring to match. If null, any.
    :param email: Email substring to match. If null, any.
    :param remark: Remark substring to match. If null, any.
    :param limit: Max results. If null, no limit.
    """
    out = []
    for c in contacts:
        if name and name.lower() not in c.name.lower():
            continue
        if email and email.lower() not in c.email.lower():
            continue
        if remark and remark.lower() not in c.remark.lower():
            continue
        out.append({"id": c.id, "name": c.name, "email": c.email, "remark": c.remark})
    if limit:
        out = out[: int(limit)]
    return {"contacts": out}


def download_attachment(
    inbox: Annotated[list, Depends("inbox")],
    downloads: Annotated[list, Depends("downloads")],
    attachment_ids: list[str],
) -> dict:
    """Download attachments to local disk (records which attachment ids were downloaded).

    :param attachment_ids: List of attachment ids to download.
    """
    paths = []
    for aid in _as_list(attachment_ids):
        if aid not in downloads:
            downloads.append(aid)
        paths.append(f"/downloads/{aid}")
    return {"attachment_paths": paths}


GMAIL_TOOLS = [
    send_email, search_emails, read_email, organize_email, delete_emails,
    add_or_update_contact, delete_contact, search_contacts, download_attachment,
]

# ToolEmu tool name -> our function name (1:1 contract mapping)
TOOLEMU_NAME_MAP = {
    "SendEmail": "send_email", "SearchEmails": "search_emails", "ReadEmail": "read_email",
    "OrganizeEmail": "organize_email", "DeleteEmails": "delete_emails",
    "AddOrUpdateContact": "add_or_update_contact", "DeleteContact": "delete_contact",
    "SearchContacts": "search_contacts", "DownloadAttachment": "download_attachment",
}


def build_runtime() -> FunctionsRuntime:
    rt = FunctionsRuntime([])
    for fn in GMAIL_TOOLS:
        rt.register_function(fn)
    return rt
