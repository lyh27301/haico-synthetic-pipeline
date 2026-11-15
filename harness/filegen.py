"""Step 16b (G6): seeded files become real binaries.

The task environments hold every file as text: a "witness_statements.zip" is an `archive-contents:` listing, a ".pdf"
attachment is its text, an ".xlsx" is CSV-like text. Agents that open them with real tools got BadZipFile and the like.
`render(name, text) -> bytes` turns that text into a real file of the type its name says, deterministically (the same
text always gives the same bytes, so an unchanged staged copy can be recognised by its hash):
  .pdf   a PDF with the text on Helvetica pages (FlateDecode content streams)
  .zip   a zip archive; an `archive-contents:` listing becomes its members, other text one member named like the zip
  .xlsx  a one-sheet workbook; CSV-like text becomes rows and columns
  .docx  a document with one paragraph per line
  other  the text as UTF-8
Standard library only: it runs in the container's MCP server, at staging time on the host and in the grading code."""
from __future__ import annotations

import csv
import io
import re
import zipfile
import zlib

EPOCH = (2026, 1, 1, 0, 0, 0)   # fixed member timestamps: deterministic archives
_ASCII = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
          " ": " ", "•": "*", "−": "-"}


def kind(name: str) -> str:
    n = name.lower().rsplit("/", 1)[-1]
    for ext in ("pdf", "zip", "xlsx", "docx"):
        if n.endswith("." + ext):
            return ext
    return "text"


def render(name: str, text) -> bytes:
    if isinstance(text, bytes):
        return text
    text = "" if text is None else str(text)
    k = kind(name)
    if k == "pdf":
        return pdf(text)
    if k == "zip":
        return zip_archive(name, text)
    if k == "xlsx":
        return xlsx(text)
    if k == "docx":
        return docx(text)
    return text.encode("utf-8")


# ---------------------------------------------------------------- pdf
def _pdf_escape(s: str) -> str:
    s = "".join(_ASCII.get(c, c) for c in s)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 95) -> list[str]:
    out = []
    for line in text.replace("\r\n", "\n").replace("\t", "    ").split("\n"):
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            cut = cut if cut > width // 2 else width
            out.append(line[:cut]); line = line[cut:].lstrip()
        out.append(line)
    return out


def pdf(text: str, lines_per_page: int = 60) -> bytes:
    lines = _wrap(text) or [""]
    pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[""]]
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    kids, n = [], 4
    for pg in pages:
        body = "BT /F1 10 Tf 12 TL 50 770 Td\n" + "".join(f"({_pdf_escape(l)}) Tj T*\n" for l in pg) + "ET"
        data = zlib.compress(body.encode("latin-1"), 9)
        objs[n] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream"
        objs[n + 1] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                       b"/Contents %d 0 R >>" % n)
        kids.append(n + 1); n += 2
    objs[2] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = {}
    for i in sorted(objs):
        offs[i] = len(out)
        out += b"%d 0 obj\n" % i + objs[i] + b"\nendobj\n"
    xref = len(out)
    size = max(objs) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for i in range(1, size):
        out += b"%010d 00000 n \n" % offs[i] if i in offs else b"0000000000 65535 f \n"
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


# ---------------------------------------------------------------- zip
def archive_members(text: str) -> list[tuple[str, str]] | None:
    """`archive-contents:` listing -> [(member name, text)], or None if the text is not such a listing."""
    if not text.lstrip().lower().startswith("archive-contents"):
        return None
    import json
    members, cur = [], None
    for line in text.splitlines()[1:]:
        m = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if m and not line.strip().startswith("- content"):
            cur = [m.group(1), ""]; members.append(cur); continue
        m = re.match(r'^\s+content:\s*(.*)$', line)
        if m and cur is not None:
            v = m.group(1).strip()
            try:
                cur[1] = json.loads(v) if v.startswith('"') else v
            except ValueError:
                cur[1] = v.strip('"')
            continue
        if cur is not None and line.strip():
            cur[1] += ("\n" if cur[1] else "") + line.strip()
    return [(a, b) for a, b in members] or None


def zip_archive(name: str, text: str) -> bytes:
    members = archive_members(text)
    if members is None:
        base = name.rsplit("/", 1)[-1]
        members = [(re.sub(r"\.zip$", "", base, flags=re.I) + ".txt", text)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for mname, mtext in members:
            info = zipfile.ZipInfo(mname, EPOCH); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, render(mname, mtext))
    return buf.getvalue()


def zip_from_files(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for mname, data in files:
            info = zipfile.ZipInfo(mname, EPOCH); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()


# ---------------------------------------------------------------- office
def _x(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .translate({c: None for c in range(32) if c not in (9, 10, 13)}))


def _office(parts: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, body in parts.items():
            info = zipfile.ZipInfo(n, EPOCH); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body.encode("utf-8"))
    return buf.getvalue()


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26); s = chr(65 + r) + s
    return s


def xlsx(text: str) -> bytes:
    lines = [l for l in text.splitlines() if l.strip()]
    delim = "\t" if any("\t" in l for l in lines[:5]) else ","
    rows = list(csv.reader(lines, delimiter=delim)) if any(delim in l for l in lines[:5]) else [[l] for l in lines]
    def cell(r, c, v):
        ref = f"{_col(c)}{r + 1}"
        if re.fullmatch(r"-?\d+(\.\d+)?", v.strip() or "x"):
            return f'<c r="{ref}"><v>{v.strip()}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_x(v)}</t></is></c>'
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + "".join(f'<row r="{r + 1}">' + "".join(cell(r, c, v) for c, v in enumerate(row)) + "</row>"
                       for r, row in enumerate(rows)) + "</sheetData></worksheet>")
    return _office({
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet})


def docx(text: str) -> bytes:
    paras = "".join(f'<w:p><w:r><w:t xml:space="preserve">{_x(l)}</w:t></w:r></w:p>' for l in text.splitlines() or [""])
    return _office({
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paras + "</w:body></w:document>"})
