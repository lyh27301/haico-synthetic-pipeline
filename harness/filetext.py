"""Step 16b (G6): the text inside a real file, extracted at grading time.

`extract(data, name) -> str`:
  zip (and zip-based office files)  member names, then each member's text (recursively; xlsx cells, docx paragraphs)
  pdf                               page text via pypdf when it is installed, else a standard-library reader of the
                                    content streams (FlateDecode, Tj / TJ / ' / "), enough for simple generated PDFs
  text                              UTF-8 (latin-1 as a last resort)
  other binaries                    "[binary file NAME, N bytes]" (no printable-strings dump: that is what hid the PDF
                                    text in step 15, G6)
Standard library only at import time."""
from __future__ import annotations

import io
import re
import zipfile
import zlib

MAX_TEXT = 200_000


def _xml_text(b: bytes, sep: str = " ") -> str:
    t = re.sub(rb"</(w:p|row|a:p|si)>", b"\n", b)
    t = re.sub(rb"<[^>]+>", sep.encode(), t)
    t = t.decode("utf-8", "replace")
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.splitlines() if l.strip())


def _office(z: zipfile.ZipFile, names: list[str]) -> str | None:
    if "word/document.xml" in names:
        return _xml_text(z.read("word/document.xml"), "")
    if "xl/workbook.xml" in names:
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [_xml_text(m, "") for m in re.findall(rb"<si>(.*?)</si>", z.read("xl/sharedStrings.xml"), re.S)]
        rows = []
        for n in sorted(x for x in names if x.startswith("xl/worksheets/sheet")):
            for row in re.findall(rb"<row[^>]*>(.*?)</row>", z.read(n), re.S):
                cells = []
                for attrs, inner in re.findall(rb"<c([^>]*)>(.*?)</c>", row, re.S):
                    v = re.search(rb"<v>(.*?)</v>", inner, re.S)
                    if b't="s"' in attrs and v:
                        i = int(v.group(1)); cells.append(shared[i] if i < len(shared) else "")
                    elif b"inlineStr" in attrs:
                        cells.append(_xml_text(inner, ""))
                    else:
                        cells.append(v.group(1).decode() if v else "")
                rows.append(",".join(cells))
        return "\n".join(rows)
    return None


def _pdf_fallback(data: bytes) -> str:
    out = []
    for m in re.finditer(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", data, re.S):
        dic, raw = m.group(1), m.group(2)
        if b"FlateDecode" in dic:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        if b"BT" not in raw:
            continue
        line = []
        for tok in re.finditer(rb"\((?:\\.|[^\\)])*\)\s*(?:Tj|'|\")|\[(.*?)\]\s*TJ|T\*|Td|TD", raw, re.S):
            s = tok.group(0)
            if s in (b"T*",) or s.endswith((b"Td", b"TD")):
                if line:
                    out.append("".join(line)); line = []
                continue
            for lit in re.findall(rb"\(((?:\\.|[^\\)])*)\)", s):
                lit = re.sub(rb"\\([nrtbf()\\])", lambda x: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"",
                                                             b"f": b""}.get(x.group(1), x.group(1)), lit)
                line.append(lit.decode("latin-1"))
        if line:
            out.append("".join(line))
    return "\n".join(out)


def pdf_text(data: bytes) -> str:
    try:
        import pypdf  # noqa: PLC0415
        r = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in r.pages)
    except Exception:  # noqa: BLE001  (not installed, or a PDF it cannot read)
        return _pdf_fallback(data)


def extract(data: bytes, name: str = "", depth: int = 0) -> str:
    if isinstance(data, str):
        return data[:MAX_TEXT]
    if data[:4] == b"PK\x03\x04" and depth < 4:
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = z.namelist()
            off = _office(z, names)
            if off is not None:
                return off[:MAX_TEXT]
            parts = [f"[zip archive {name}] members:"] + names
            for n in names:
                if not n.endswith("/"):
                    parts += [f"== {n} ==", extract(z.read(n), n, depth + 1)]
            return "\n".join(parts)[:MAX_TEXT]
        except Exception:  # noqa: BLE001
            pass
    if data[:5] == b"%PDF-":
        return pdf_text(data)[:MAX_TEXT]
    if b"\x00" not in data[:8192]:
        try:
            return data.decode("utf-8")[:MAX_TEXT]
        except UnicodeDecodeError:
            return data.decode("latin-1")[:MAX_TEXT]
    return f"[binary file {name}, {len(data)} bytes]"
