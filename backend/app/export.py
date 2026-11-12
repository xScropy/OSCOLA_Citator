"""Export: formatted documents (DOCX, PDF, TXT) and reference data (BibTeX, RIS, CSV, CSL-JSON)."""
from __future__ import annotations

import csv
import html
import io
import json
import re
from html.parser import HTMLParser
from itertools import groupby
from pathlib import Path
from typing import Any

from .citation.common import family_of, g, parse_date, people, year_of
from .citation.engine import cite_rich

FORMATS = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "pdf": ("application/pdf", "pdf"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "bibtex": ("application/x-bibtex; charset=utf-8", "bib"),
    "ris": ("application/x-research-info-systems; charset=utf-8", "ris"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "csl-json": ("application/vnd.citationstyles.csl+json; charset=utf-8", "json"),
}
DOCUMENT_FORMATS = ("docx", "pdf", "txt")


# --------------------------------------------------------------------------- formatted documents

class _RunParser(HTMLParser):
    """Reduce (possibly user-edited) entry markup to styled runs; all other markup is discarded."""

    def __init__(self) -> None:
        super().__init__()
        self.runs: list[dict[str, str]] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag in ("i", "em"):
            self._stack.append("i")
        elif tag == "span" and "sc" in classes:
            self._stack.append("sc")
        elif tag in ("span", "b", "strong", "u", "font", "a"):
            self._stack.append("")
        elif tag == "br":
            self.handle_data(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("i", "em", "span", "b", "strong", "u", "font", "a") and self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        style = next((s for s in reversed(self._stack) if s), "")
        if self.runs and self.runs[-1]["style"] == style:
            self.runs[-1]["text"] += data
        elif data:
            self.runs.append({"text": data, "style": style})


def html_to_runs(markup: str) -> list[dict[str, str]]:
    parser = _RunParser()
    parser.feed(markup or "")
    parser.close()
    for run in parser.runs:
        run["text"] = re.sub(r"\s+", " ", run["text"].replace("\xa0", " "))
    return [r for r in parser.runs if r["text"]]


def _section_runs(sections: list[dict]) -> list[tuple[str, list[tuple[list[dict[str, str]], str]]]]:
    """(heading, [(styled runs, page references)]) for every non-empty section."""
    out = []
    for section in sections:
        entries = []
        for entry in section.get("entries", []):
            runs = html_to_runs(entry["html"]) if entry.get("html") else [{"text": entry.get("text", ""), "style": ""}]
            if any(r["text"].strip() for r in runs):
                entries.append((runs, str(entry.get("pages") or "")))
        if entries:
            out.append((section.get("heading", ""), entries))
    return out


def to_txt(title: str, sections: list[dict]) -> bytes:
    lines = [title, "=" * len(title), ""] if title else []
    for heading, entries in _section_runs(sections):
        if heading:
            lines += [heading, "-" * len(heading)]
        for runs, pages in entries:
            line = "".join(r["text"] for r in runs).strip()
            lines.append(f"{line} {'.' * max(3, 70 - len(line) - len(pages))} {pages}" if pages else line)
        lines.append("")
    return "\n".join(lines).rstrip("\n").encode("utf-8") + b"\n"


def to_docx(title: str, sections: list[dict]) -> bytes:
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.shared import Cm, Pt

    document = Document()
    section = document.sections[0]
    text_width = section.page_width - section.left_margin - section.right_margin
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    if title:
        document.add_heading(title, level=1)
    for heading, entries in _section_runs(sections):
        if heading:
            document.add_heading(heading, level=2)
        for runs, pages in entries:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(1.27)
            paragraph.paragraph_format.first_line_indent = Cm(-1.27)
            paragraph.paragraph_format.space_after = Pt(6)
            for run in runs:
                piece = paragraph.add_run(run["text"])
                piece.italic = run["style"] == "i" or None
                piece.font.small_caps = run["style"] == "sc" or None
            if pages:  # page references at the right margin, joined by a dotted leader
                paragraph.paragraph_format.right_indent = Cm(1.5)
                paragraph.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
                paragraph.add_run("\t" + pages)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# Unicode serif families to embed in PDFs, in order of preference: (regular, italic, bold) file names.
_FONT_FAMILIES = (
    ("LiberationSerif-Regular.ttf", "LiberationSerif-Italic.ttf", "LiberationSerif-Bold.ttf"),
    ("DejaVuSerif.ttf", "DejaVuSerif-Italic.ttf", "DejaVuSerif-Bold.ttf"),
    ("FreeSerif.ttf", "FreeSerifItalic.ttf", "FreeSerifBold.ttf"),
    ("times.ttf", "timesi.ttf", "timesbd.ttf"),
    ("Times New Roman.ttf", "Times New Roman Italic.ttf", "Times New Roman Bold.ttf"),
)
_FONT_ROOTS = ("/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts", "/System/Library/Fonts/Supplemental", "C:/Windows/Fonts")
_pdf_fonts: tuple[str, str, str] | None = None


def _pdf_font_names() -> tuple[str, str, str]:
    """(regular, italic, bold). A Unicode serif when one is installed, else the built-in Times family."""
    global _pdf_fonts
    if _pdf_fonts is not None:
        return _pdf_fonts
    _pdf_fonts = ("Times-Roman", "Times-Italic", "Times-Bold")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    installed: dict[str, Path] = {}
    for root in _FONT_ROOTS:
        if Path(root).is_dir():
            for file in Path(root).rglob("*.ttf"):
                installed.setdefault(file.name, file)
    for family in _FONT_FAMILIES:
        if all(name in installed for name in family):
            names = ("CiteRightSerif", "CiteRightSerif-Italic", "CiteRightSerif-Bold")
            try:
                for name, file_name in zip(names, family):
                    pdfmetrics.registerFont(TTFont(name, str(installed[file_name])))
                _pdf_fonts = names
                break
            except Exception:
                continue
    return _pdf_fonts


def to_pdf(title: str, sections: list[dict]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    regular, italic, bold = _pdf_font_names()
    body = ParagraphStyle("entry", fontName=regular, fontSize=11, leading=15, leftIndent=1.27 * cm, firstLineIndent=-1.27 * cm, spaceAfter=6)
    right = ParagraphStyle("pages", fontName=regular, fontSize=11, leading=15, alignment=2, spaceAfter=6)
    h1 = ParagraphStyle("h1", fontName=bold, fontSize=16, leading=20, spaceAfter=14)
    h2 = ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=8)

    def markup(runs: list[dict[str, str]]) -> str:
        out = []
        for run in runs:
            text = html.escape(run["text"], quote=False)
            if run["style"] == "i":
                out.append(f'<font name="{italic}">{text}</font>')
            elif run["style"] == "sc":  # small caps: capitals stay full size, lower case is shrunk
                for lower, group in groupby(run["text"], key=str.islower):
                    piece = html.escape("".join(group).upper(), quote=False)
                    out.append(f'<font size="9">{piece}</font>' if lower else piece)
            else:
                out.append(text)
        return "".join(out)

    story = [Paragraph(html.escape(title), h1)] if title else []
    for heading, entries in _section_runs(sections):
        if heading:
            story.append(Paragraph(html.escape(heading), h2))
        for runs, pages in entries:
            if pages:
                row = [[Paragraph(markup(runs), body), Paragraph(html.escape(pages), right)]]
                table = Table(row, colWidths=[12.2 * cm, 3.8 * cm])
                table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                story.append(table)
            else:
                story.append(Paragraph(markup(runs), body))
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, title=title or "Bibliography", author="CiteRight", leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.5 * cm, bottomMargin=2.5 * cm).build(story)
    return buffer.getvalue()


# --------------------------------------------------------------------------- reference data

def _full_name(p: dict) -> str:
    return p.get("literal") or f"{p.get('given', '')} {p.get('family', '')}".strip()


def _inverted(p: dict) -> str:
    if p.get("literal"):
        return p["literal"]
    return f"{p.get('family', '')}, {p.get('given', '')}".strip(", ")


def _legal_note(m: dict) -> str:
    parts = [g(m, "neutral_citation"), g(m, "report_citation"), g(m, "case_number"), g(m, "treaty_series"), g(m, "court")]
    return ", ".join(p for p in parts if p)


_BIBTEX_TYPES = {"book": "book", "chapter": "incollection", "article": "article", "report": "techreport", "thesis": "phdthesis", "website": "misc", "case": "misc", "legislation": "misc", "treaty": "misc"}


def _bibtex_escape(value: str) -> str:
    value = value.replace("\\", r"\textbackslash{}")
    return re.sub(r"([&%$#_{}])", r"\\\1", value)


def to_bibtex(references: list[dict]) -> bytes:
    entries, used = [], set()
    for m in references:
        ppl = people(m, "authors") or people(m, "editors")
        stem = (family_of(ppl[0]) if ppl else (g(m, "title").split() or ["ref"])[0]) + year_of(m)
        stem = re.sub(r"[^A-Za-z0-9]", "", stem) or "ref"
        key, n = stem, 1
        while key.lower() in used:
            n += 1
            key = f"{stem}{chr(96 + n) if n <= 26 else n}"
        used.add(key.lower())
        kind = m.get("type")
        fields = {
            "author": " and ".join(f"{{{_inverted(p)}}}" if p.get("literal") else _inverted(p) for p in people(m, "authors")),
            "editor": " and ".join(f"{{{_inverted(p)}}}" if p.get("literal") else _inverted(p) for p in people(m, "editors")),
            "title": g(m, "title"),
            "booktitle": g(m, "container_title"),
            "journal": g(m, "journal"),
            "year": year_of(m),
            "volume": g(m, "volume"),
            "number": g(m, "issue") or (g(m, "number") if kind == "report" else ""),
            "pages": g(m, "pages").replace("–", "--").replace("-", "--").replace("----", "--"),
            "edition": g(m, "edition"),
            "publisher": g(m, "publisher"),
            "address": g(m, "place"),
            "school": g(m, "institution") if kind == "thesis" else "",
            "institution": g(m, "publisher") if kind == "report" else "",
            "type": g(m, "thesis_type") if kind == "thesis" else "",
            "howpublished": g(m, "website"),
            "note": _legal_note(m),
            "doi": g(m, "doi"),
            "isbn": g(m, "isbn"),
            "url": g(m, "url"),
            "urldate": g(m, "accessed"),
        }
        if kind == "report":
            fields["publisher"] = ""
        body = []
        for name, value in fields.items():
            if not value:
                continue
            if name in ("author", "editor"):
                rendered = re.sub(r"([&%$#_])", r"\\\1", value)
            elif name in ("url", "doi"):
                rendered = value
            else:
                rendered = _bibtex_escape(value)
            body.append(f"  {name} = {{{rendered}}}")
        entries.append(f"@{_BIBTEX_TYPES.get(kind, 'misc')}{{{key},\n" + ",\n".join(body) + "\n}")
    return ("\n\n".join(entries) + "\n").encode("utf-8")


_RIS_TYPES = {"book": "BOOK", "chapter": "CHAP", "article": "JOUR", "report": "RPRT", "thesis": "THES", "website": "ELEC", "case": "CASE", "legislation": "STAT", "treaty": "GEN"}


def to_ris(references: list[dict]) -> bytes:
    lines: list[str] = []
    for m in references:
        kind = m.get("type")
        pages = re.split(r"\s*[-–—]+\s*", g(m, "pages")) if g(m, "pages") else []
        rows = [("TY", _RIS_TYPES.get(kind, "GEN"))]
        rows += [("AU", _inverted(p)) for p in people(m, "authors")]
        rows += [("ED", _inverted(p)) for p in people(m, "editors")]
        rows += [
            ("TI", g(m, "title")),
            ("T2", g(m, "journal") or g(m, "container_title") or g(m, "website")),
            ("PY", year_of(m)),
            ("DA", (g(m, "date") or g(m, "adopted_date")).replace("-", "/")),
            ("VL", g(m, "volume")),
            ("IS", g(m, "issue")),
            ("SP", pages[0] if pages else ""),
            ("EP", pages[1] if len(pages) > 1 else ""),
            ("ET", g(m, "edition")),
            ("PB", g(m, "publisher") or g(m, "institution") or (g(m, "court") if kind == "case" else "")),
            ("CY", g(m, "place")),
            ("M1", g(m, "number") or g(m, "case_number")),
            ("M3", g(m, "thesis_type")),
            ("N1", ", ".join(x for x in [g(m, "neutral_citation"), g(m, "report_citation"), g(m, "treaty_series")] if x)),
            ("DO", g(m, "doi")),
            ("SN", g(m, "isbn")),
            ("UR", g(m, "url")),
            ("Y2", g(m, "accessed").replace("-", "/")),
        ]
        lines += [f"{tag}  - {value}" for tag, value in rows if value]
        lines += ["ER  - ", ""]
    return "\r\n".join(lines).encode("utf-8")


_CSL_TYPES = {"book": "book", "chapter": "chapter", "article": "article-journal", "report": "report", "thesis": "thesis", "website": "webpage", "case": "legal_case", "legislation": "legislation", "treaty": "treaty"}


def _csl_date(value: str) -> dict | None:
    parts = [p for p in parse_date(value) if p is not None]
    return {"date-parts": [parts]} if parts else None


def to_csl(references: list[dict], ids: list[Any] | None = None) -> list[dict]:
    out = []
    for index, m in enumerate(references):
        kind = m.get("type")
        item: dict[str, Any] = {
            "id": str(ids[index]) if ids else f"ref-{index + 1}",
            "type": _CSL_TYPES.get(kind, "document"),
            "title": g(m, "title"),
            "author": [{"literal": p["literal"]} if p.get("literal") else {"family": p.get("family", ""), "given": p.get("given", "")} for p in people(m, "authors")],
            "editor": [{"literal": p["literal"]} if p.get("literal") else {"family": p.get("family", ""), "given": p.get("given", "")} for p in people(m, "editors")],
            "issued": _csl_date(g(m, "date") or g(m, "adopted_date") or year_of(m)),
            "container-title": g(m, "journal") or g(m, "container_title") or g(m, "website") or (g(m, "treaty_series") if kind == "treaty" else ""),
            "publisher": g(m, "publisher") or g(m, "institution"),
            "publisher-place": g(m, "place"),
            "edition": g(m, "edition"),
            "volume": g(m, "volume"),
            "issue": g(m, "issue"),
            "page": g(m, "pages"),
            "number": g(m, "number") or g(m, "case_number") or g(m, "neutral_citation"),
            "authority": g(m, "court"),
            "references": g(m, "report_citation"),
            "jurisdiction": g(m, "jurisdiction"),
            "genre": g(m, "thesis_type"),
            "title-short": g(m, "short_title"),
            "DOI": g(m, "doi"),
            "ISBN": g(m, "isbn"),
            "URL": g(m, "url"),
            "accessed": _csl_date(g(m, "accessed")),
        }
        out.append({k: v for k, v in item.items() if v})
    return out


def to_csl_json(references: list[dict], ids: list[Any] | None = None) -> bytes:
    return json.dumps(to_csl(references, ids), indent=2, ensure_ascii=False).encode("utf-8")


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def to_csv(rows: list[dict], style: str) -> bytes:
    """``rows`` are dicts with metadata, tags, notes and verification status."""
    columns = ["type", "authors", "editors", "title", "year", "container", "volume", "issue", "pages", "edition", "publisher", "court", "neutral_citation", "report_citation", "treaty_series", "doi", "isbn", "url", "citation", "verification", "tags", "notes"]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        m = row["metadata"]
        values = {
            "type": m.get("type", ""),
            "authors": "; ".join(_full_name(p) for p in people(m, "authors")),
            "editors": "; ".join(_full_name(p) for p in people(m, "editors")),
            "title": g(m, "title"),
            "year": year_of(m),
            "container": g(m, "journal") or g(m, "container_title") or g(m, "website"),
            "citation": cite_rich(m, style)["bibliography"].text,
            "verification": row.get("verification", ""),
            "tags": "; ".join(row.get("tags") or []),
            "notes": row.get("notes", ""),
        }
        writer.writerow([_csv_safe(str(values[c] if c in values else g(m, c))) for c in columns])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
