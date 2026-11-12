"""Write corrected footnotes back into a Word document.

Only footnotes that actually changed are touched. Their text runs are rebuilt
(keeping the footnote mark, paragraph settings and base font); everything else in
the file is copied through byte for byte.
"""
from __future__ import annotations

import copy
import io
import zipfile

from .extract import W, DocumentError, _read_xml, is_reference_run, note_paragraphs, paragraph_runs

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _split_paragraphs(runs: list[dict]) -> list[list[dict]]:
    """Revised runs use '\\n' between the paragraphs of a footnote."""
    paragraphs: list[list[dict]] = [[]]
    for run in runs:
        pieces = run["text"].split("\n")
        for index, piece in enumerate(pieces):
            if index:
                paragraphs.append([])
            if piece:
                paragraphs[-1].append({"text": piece, "style": run["style"]})
    return paragraphs


def _rebuild(paragraph, runs: list[dict]) -> None:
    from lxml import etree

    template = None
    for run in paragraph.iter(f"{W}r"):
        if not is_reference_run(run) and run.find(f"{W}t") is not None:
            template = run.find(f"{W}rPr")
            break
    had_space = False
    existing = paragraph_runs(paragraph)
    if existing:
        had_space = existing[0][0][:1].isspace()
    for child in list(paragraph):
        if child.tag == f"{W}pPr":
            continue
        if child.tag == f"{W}r" and is_reference_run(child):
            continue
        if any(is_reference_run(r) for r in child.iter(f"{W}r")):
            continue
        paragraph.remove(child)
    has_mark = any(is_reference_run(r) for r in paragraph.iter(f"{W}r"))
    for index, run in enumerate(runs):
        element = etree.SubElement(paragraph, f"{W}r")
        properties = copy.deepcopy(template) if template is not None else etree.Element(f"{W}rPr")
        for tag in ("i", "iCs", "smallCaps"):
            for old in properties.findall(f"{W}{tag}"):
                properties.remove(old)
        if run["style"] == "i":
            etree.SubElement(properties, f"{W}i")
            etree.SubElement(properties, f"{W}iCs")
        elif run["style"] == "sc":
            etree.SubElement(properties, f"{W}smallCaps")
        if len(properties):
            element.append(properties)
        text = etree.SubElement(element, f"{W}t")
        text.set(XML_SPACE, "preserve")
        text.text = (" " if index == 0 and has_mark and had_space else "") + run["text"]


def apply_corrections(data: bytes, footnotes: list[dict]) -> bytes:
    """Return a copy of the .docx with each changed footnote replaced by its revised text."""
    from lxml import etree

    changed = {n["source_id"]: n["revised_runs"] for n in footnotes if n["changed"] and n.get("source_id")}
    source = zipfile.ZipFile(io.BytesIO(data))
    names = source.namelist()
    part = "word/footnotes.xml" if "word/footnotes.xml" in names else "word/endnotes.xml"
    if part not in names:
        raise DocumentError("This document has no footnotes to correct.")
    root = _read_xml(source, part)
    for note in root:
        runs = changed.get(note.get(f"{W}id"))
        if runs is None or note.get(f"{W}type") in ("separator", "continuationSeparator", "continuationNotice"):
            continue
        paragraphs = [p for p in note_paragraphs(note) if "".join(t for t, _ in paragraph_runs(p)).strip()]
        revised = _split_paragraphs(runs)
        if len(paragraphs) != len(revised):
            continue  # structure changed unexpectedly: leave this footnote exactly as it was
        for paragraph, new_runs in zip(paragraphs, revised):
            old_text = "".join(t for t, _ in paragraph_runs(paragraph)).strip()
            old_runs = [(t, f) for t, f in paragraph_runs(paragraph)]
            old_italic = "".join(t for t, f in old_runs if f).strip()
            new_italic = "".join(r["text"] for r in new_runs if r["style"] == "i").strip()
            if old_text != "".join(r["text"] for r in new_runs).strip() or old_italic != new_italic:
                _rebuild(paragraph, new_runs)
    payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info, payload if info.filename == part else source.read(info.filename))
    source.close()
    return buffer.getvalue()
