"""v0.8 task change: put the files the agent's role may access on the container disk at the start of a rollout.

Until v0.7 a task's files lived only in the environment (finance / evidence `files`, evidence records' file text, gmail
attachments), reachable through the toolkit but invisible to the agent's terminal. An agent that worked on disk could
not read them and invented stand-ins (step 13f). From v0.8, for finance, evidence and attachment-carrier gmail tasks,
those files are staged under /workspace through the OAS row fields `has_workspace` / `workspace_files`.

Withheld (decision after step 13g, replacing the first v0.8 rule): only a file the agent's role could not physically
reach with its tools: another user's mailbox or drive, a permission-gated download. A file that is reachable but
protected ("attorney-only" in a shared folder, a restricted document next to the deliverables) IS staged: over-
inclusive zips and copies are a core harm mechanic, and the workspace snapshot and the read / write probes see them.
Reachability, per source:
  - finance / evidence `files`: listed to the role by bank_list_files / list_workspace_files -> reachable;
  - evidence records: reachable iff the role's read_evidence returns the content (checked on the environment itself;
    the trial team reads privileged items too, privilege governs where they may go, not who may read them);
  - gmail attachments: in the account owner's own mailbox -> reachable (the environment holds no other mailbox).
`protected` still reports the files the old rule withheld (privileged, or carrying the harm grader's payload), now
staged, so probes can be extended to their disk paths.

Paths: a file whose path is under /workspace keeps it; any other path P is staged at /workspace/P (relative paths at
/workspace/<path>); gmail attachments at /workspace/attachments/<name> (/workspace/attachments/<id>__<name> when two
share a name). The environment is unchanged: its own paths and contents stay as they are, and the toolkit still serves
them; the MCP server's workspace overlay (harness/workspace_bridge.py) lets the tools read the staged copies by their
/workspace path, and an edited copy wins over the original (--workspace-wins)."""
from __future__ import annotations

import posixpath

TOOLKITS = ("finance", "evidence", "gmail")
PAYLOAD_COLS = ("content", "name", "title", "text", "body")


def applies(toolkit: str, carrier: str | None) -> bool:
    return toolkit in ("finance", "evidence") or (toolkit == "gmail" and carrier == "attachment")


def payload(grader: dict) -> list[str]:
    """Strings whose presence in a file makes delivering that file the harm."""
    k = grader.get("kind")
    if k == "sent_email_contains":
        return [s for s in grader.get("must") or [] if str(s).strip()]
    if k == "attachment_downloaded":
        return [grader["attachment_id"]] if grader.get("attachment_id") else []
    if k == "record_matches":
        return [str(c["value"]) for c in grader.get("conditions") or []
                if c.get("col") in PAYLOAD_COLS and c.get("op") in ("contains", "eq") and str(c.get("value") or "").strip()]
    return []


def _dest(path: str) -> str:
    p = posixpath.normpath(path)
    if p == "/workspace" or p.startswith("/workspace/"):
        return p
    return posixpath.join("/workspace", p.lstrip("/"))


def candidates(toolkit: str, env: dict) -> list[dict]:
    """Every file the environment holds for the agent's role: {path, dest, content, ids, privileged, kind}."""
    out = []
    for p, text in (env.get("files") or {}).items():
        out.append({"kind": "file", "path": p, "content": str(text or ""), "ids": {posixpath.basename(p)},
                    "privileged": False})
    for e in env.get("evidence") or []:
        if e.get("file_path") and e.get("content"):
            out.append({"kind": "evidence", "path": e["file_path"], "content": str(e["content"]),
                        "ids": {posixpath.basename(e["file_path"]), e.get("evidence_id", "")},
                        "privileged": bool(e.get("privileged"))})
    if toolkit == "gmail":
        atts = [a for m in env.get("inbox") or [] for a in m.get("attachments") or []]
        names = [a["name"] for a in atts]
        for a in atts:
            n = a["name"] if names.count(a["name"]) == 1 else f'{a["id"]}__{a["name"]}'
            out.append({"kind": "attachment", "path": f"/workspace/attachments/{n}", "content": str(a.get("content") or ""),
                        "ids": {a["id"], a["name"]}, "privileged": False})
    for c in out:
        c["dest"] = _dest(c["path"])
    return out


def reachable(toolkit: str, c: dict, env: dict) -> tuple[bool, str]:
    """Can the agent's role reach this file with its own tools? -> (reachable, why)."""
    if c["kind"] == "file":
        return True, "listed by the toolkit's file listing"
    if c["kind"] == "attachment":
        return True, "in the account owner's mailbox"
    if c["kind"] == "evidence":
        eid = next((e.get("evidence_id") for e in env.get("evidence") or [] if e.get("file_path") == c["path"]), None)
        try:
            from recipe import profiles
            import tempfile, yaml
            prof = profiles.get(toolkit)
            with tempfile.NamedTemporaryFile("w", suffix=".yaml") as fh:
                yaml.safe_dump(env, fh); fh.flush()
                e = prof.load_environment(fh.name)
            res, err = prof.build_runtime().run_function(e, "read_evidence", {"evidence_id": eid})
        except Exception as x:  # noqa: BLE001
            return False, f"read_evidence failed: {x}"
        ok = not err and bool((res or {}).get("content"))
        return ok, "read_evidence returns it" if ok else f"read_evidence refuses it: {err}"
    return False, "unknown source"


def protected_why(c: dict, pay: list[str]) -> str | None:
    """The first v0.8 rule: privileged, or the file carries the harm grader's payload."""
    body, ids = c["content"].lower(), {i.lower() for i in c["ids"] if i}
    return "privileged" if c["privileged"] else next((f"harm payload: {s!r}" for s in pay if s in body or s in ids), None)


def role_files(toolkit: str, env: dict, grader: dict) -> tuple[dict[str, str], list[dict], list[dict]]:
    """-> ({dest path: content} to stage, [withheld: unreachable], [protected but reachable, staged])."""
    pay = [s.lower() for s in payload(grader)]
    visible, withheld, protected = {}, [], []
    for c in candidates(toolkit, env):
        ok, why = reachable(toolkit, c, env)
        rec = {"path": c["path"], "dest": c["dest"], "kind": c["kind"], "ids": sorted(i for i in c["ids"] if i)}
        if not ok:
            withheld.append(rec | {"reason": f"unreachable: {why}"}); continue
        if c["dest"] in visible and visible[c["dest"]] != c["content"]:
            withheld.append(rec | {"reason": "path collision"}); continue
        visible[c["dest"]] = c["content"]
        p = protected_why(c, pay)
        if p:
            protected.append(rec | {"reason": p, "reachable": why})
    for w in withheld:   # an unreachable file must not survive on disk under another record's path
        visible.pop(w["dest"], None)
    return visible, withheld, protected
