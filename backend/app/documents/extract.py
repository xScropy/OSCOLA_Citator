"""Read the footnotes (with their page numbers) out of an uploaded PDF or Word document.

Uploaded bytes are processed in memory and never written to disk.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_XML_BYTES = 60 * 1024 * 1024
MAX_PDF_PAGES = 1500

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(Exception):
    """The upload cannot be read; the message is safe to show to the user."""


@dataclass
class Footnote:
    number: int
    page: str | None
    text: str  # paragraphs joined with "\n"
    italic: list[bool]  # one flag per character of ``text``
    source_id: str = ""  # w:id in footnotes.xml (Word documents)


@dataclass
class Extracted:
    kind: str  # "docx" | "pdf"
    footnotes: list[Footnote] = field(default_factory=list)
    pages_available: bool = False
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


def sniff(data: bytes, filename: str) -> str:
    """Decide the document type from its content, not just its name."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("The file is larger than 25 MB.")
    name = (filename or "").lower()
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    if name.endswith(".doc"):
        raise DocumentError("Old .doc files are not supported. Save the document as .docx or PDF and upload it again.")
    raise DocumentError("Upload a PDF or a Word (.docx) document.")


# --------------------------------------------------------------------------- Word

def _read_xml(archive: zipfile.ZipFile, name: str):
    from lxml import etree

    info = archive.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise DocumentError("The document is too large to analyse.")
    raw = archive.read(name)
    if b"<!DOCTYPE" in raw[:4096] or b"<!ENTITY" in raw[:4096]:
        raise DocumentError("The document contains markup that cannot be processed safely.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        return etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise DocumentError("The document is damaged and could not be read.") from exc


def _is_on(element) -> bool:
    return element is not None and element.get(f"{W}val", "true") not in ("0", "false", "off")


def run_text(run) -> str:
    out = []
    for child in run:
        if child.tag == f"{W}t":
            out.append(child.text or "")
        elif child.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
            out.append(" ")
        elif child.tag == f"{W}noBreakHyphen":
            out.append("-")
    return "".join(out)


def is_reference_run(run) -> bool:
    return run.find(f"{W}footnoteRef") is not None or run.find(f"{W}endnoteRef") is not None


def paragraph_runs(paragraph) -> list[tuple[str, bool]]:
    """(text, italic) for each text run of a note paragraph, skipping the note mark and deletions."""
    out = []
    for run in paragraph.iter(f"{W}r"):
        if is_reference_run(run) or any(a.tag == f"{W}del" for a in run.iterancestors()):
            continue
        text = run_text(run)
        if text:
            properties = run.find(f"{W}rPr")
            out.append((text, properties is not None and _is_on(properties.find(f"{W}i"))))
    return out


def note_paragraphs(note) -> list:
    return [p for p in note.iter(f"{W}p")]


def _docx(data: bytes, first_page: int) -> Extracted:
    result = Extracted(kind="docx")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        part, reference = "word/footnotes.xml", "footnoteReference"
        body = _read_xml(archive, "word/document.xml")
        if part not in names or not any(True for _ in body.iter(f"{W}{reference}")):
            if "word/endnotes.xml" in names and any(True for _ in body.iter(f"{W}endnoteReference")):
                part, reference = "word/endnotes.xml", "endnoteReference"
                result.warnings.append("The document uses endnotes; they were analysed in place of footnotes.")
            else:
                result.warnings.append("No footnotes were found in this document.")
                return result
        notes_root = _read_xml(archive, part)

    notes = {}
    for note in notes_root:
        if note.get(f"{W}type") in ("separator", "continuationSeparator", "continuationNotice"):
            continue
        notes[note.get(f"{W}id")] = note

    # Walk the body in order: Word records where each page started when it last laid the text out.
    rendered = any(True for _ in body.iter(f"{W}lastRenderedPageBreak"))
    page = first_page
    number = 0
    for element in body.iter(f"{W}lastRenderedPageBreak", f"{W}{reference}"):
        if element.tag == f"{W}lastRenderedPageBreak":
            page += 1
            continue
        note = notes.get(element.get(f"{W}id"))
        if note is None:
            continue
        number += 1
        text, italic = "", []
        for index, paragraph in enumerate(note_paragraphs(note)):
            runs = paragraph_runs(paragraph)
            joined = "".join(t for t, _ in runs)
            flags = [flag for t, flag in runs for _ in t]
            lead = len(joined) - len(joined.lstrip())
            joined, flags = joined[lead:], flags[lead:]
            if not joined.strip():
                continue
            if text:
                text, italic = text + "\n", italic + [False]
            text, italic = text + joined, italic + flags
        result.footnotes.append(Footnote(number, str(page) if rendered else None, text.rstrip(), italic[: len(text.rstrip())], element.get(f"{W}id")))

    result.pages_available = rendered
    if result.footnotes and not rendered:
        result.warnings.append(
            "This Word file does not record page breaks, so authorities are indexed by footnote number. "
            "For page numbers, open and save the file in Microsoft Word, or upload it as a PDF."
        )
    elif rendered:
        result.warnings.append("Page numbers come from Word's last saved layout. Check them against the final printed version.")
    return result


# --------------------------------------------------------------------------- PDF

_NOTE_START = re.compile(r"^\s*(\d{1,4})[.)]?\s*(\S.*)$")


def _pdf_lines(page) -> list[dict]:
    lines = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text")]
            text = "".join(s["text"] for s in spans)
            if not text.strip():
                continue
            sizes = Counter()
            for span in spans:
                sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
            lines.append({
                "text": text,
                "italic": [bool(s["flags"] & 2) for s in spans for _ in s["text"]],
                "size": sizes.most_common(1)[0][0],
                "y": line["bbox"][1],
                "x": line["bbox"][0],
            })
    lines.sort(key=lambda l: (round(l["y"]), l["x"]))
    return lines


def _pdf(data: bytes, first_page: int) -> Extracted:
    import pymupdf

    result = Extracted(kind="pdf", pages_available=True)
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentError("The PDF is damaged and could not be opened.") from exc
    with document:
        if document.needs_pass:
            raise DocumentError("The PDF is password-protected. Remove the password and upload it again.")
        if document.page_count > MAX_PDF_PAGES:
            raise DocumentError(f"The PDF has more than {MAX_PDF_PAGES} pages.")
        result.page_count = document.page_count
        pages = []
        for index, page in enumerate(document):
            label = ""
            try:
                label = page.get_label() or ""
            except Exception:
                pass
            pages.append((label or str(index + first_page), page.rect.height, _pdf_lines(page)))

    weights = Counter()
    for _, _, lines in pages:
        for line in lines:
            weights[line["size"]] += len(line["text"].strip())
    if not weights:
        result.warnings.append("This PDF has no text layer (it may be a scan). Run text recognition (OCR) on it and upload it again.")
        return result
    body_size = weights.most_common(1)[0][0]
    has_small = any(line["size"] < body_size - 0.4 for _, _, lines in pages for line in lines)
    if not has_small:
        result.warnings.append("Footnotes are set in the same size as the main text, so they were located by position and numbering. Check the result carefully.")

    current: Footnote | None = None
    for label, height, lines in pages:
        if has_small:
            zone = [l for l in lines if l["size"] < body_size - 0.4 and l["y"] > height * 0.2]
        else:
            zone = [l for l in lines if l["y"] > height * 0.5]
        started_here = False
        for line in zone:
            text = line["text"].rstrip()
            if re.fullmatch(r"\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*", text):
                continue  # a page number
            start = _NOTE_START.match(text)
            expected = (current.number + 1) if current else None
            if start and (int(start.group(1)) == expected or (expected is None and int(start.group(1)) <= 3)):
                offset = start.start(2)
                current = Footnote(int(start.group(1)), label, text[offset:], line["italic"][offset : len(text)])
                result.footnotes.append(current)
                started_here = True
            elif current is not None and (started_here or has_small):
                stripped = text.lstrip()
                flags = line["italic"][len(text) - len(stripped) : len(text)]
                glue = "" if current.text.endswith("-") and stripped[:1].islower() else " "
                current.text += glue + stripped
                current.italic += [False] * len(glue) + flags
    for note in result.footnotes:
        note.italic = (note.italic + [False] * len(note.text))[: len(note.text)]
    if not result.footnotes:
        result.warnings.append("No numbered footnotes were found in this PDF.")
    return result


def extract(data: bytes, filename: str, first_page: int = 1) -> Extracted:
    kind = sniff(data, filename)
    return _docx(data, first_page) if kind == "docx" else _pdf(data, first_page)
