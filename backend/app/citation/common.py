"""Shared building blocks for the deterministic citation formatters.

Formatters never invent data: a field that is absent from the metadata is
simply left out of the citation and reported through ``missing_fields``.
"""
from __future__ import annotations

import html
import re
from typing import Any

SOURCE_TYPES = (
    "case",
    "legislation",
    "treaty",
    "book",
    "chapter",
    "article",
    "report",
    "thesis",
    "website",
)

LEGAL_TYPES = ("case", "legislation", "treaty")

PINPOINT_KINDS = ("page", "para", "article", "section")


class Rich:
    """A string with inline styles: '' (roman), 'i' (italic), 'sc' (small caps)."""

    __slots__ = ("parts",)

    def __init__(self, *items: Any):
        self.parts: list[tuple[str, str]] = []
        for item in items:
            self._push(item)

    def _push(self, item: Any) -> None:
        if item is None or item == "":
            return
        if isinstance(item, Rich):
            for text, style in item.parts:
                self._push_part(text, style)
        elif isinstance(item, tuple):
            self._push_part(str(item[0]), item[1])
        else:
            self._push_part(str(item), "")

    def _push_part(self, text: str, style: str) -> None:
        if not text:
            return
        if self.parts and self.parts[-1][1] == style:
            self.parts[-1] = (self.parts[-1][0] + text, style)
        else:
            self.parts.append((text, style))

    def __add__(self, other: Any) -> "Rich":
        return Rich(self, other)

    def __radd__(self, other: Any) -> "Rich":
        return Rich(other, self)

    def __bool__(self) -> bool:
        return bool(self.parts)

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.parts)

    @property
    def html(self) -> str:
        out = []
        for text, style in self.parts:
            escaped = html.escape(text, quote=False)
            if style == "i":
                out.append(f"<i>{escaped}</i>")
            elif style == "sc":
                out.append(f'<span class="sc">{escaped}</span>')
            else:
                out.append(escaped)
        return "".join(out)

    @property
    def runs(self) -> list[dict[str, str]]:
        return [{"text": text, "style": style} for text, style in self.parts]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "html": self.html}


def I(text: Any) -> Rich:  # noqa: E743 - short on purpose
    return Rich((text, "i")) if text else Rich()


def SC(text: Any) -> Rich:
    return Rich((text, "sc")) if text else Rich()


def join(sep: str, items: list[Any]) -> Rich:
    out = Rich()
    for item in items:
        if not item:
            continue
        out = out + sep + item if out else Rich(item)
    return out


def end(r: Rich) -> Rich:
    """Close a citation with a full stop unless it already ends with one."""
    if not r:
        return r
    return r if r.text.rstrip().endswith((".", "?", "!")) else r + "."


def g(m: dict, key: str) -> str:
    value = m.get(key)
    if value is None:
        return ""
    return str(value).strip()


def people(m: dict, key: str) -> list[dict]:
    out = []
    for p in m.get(key) or []:
        if isinstance(p, str):
            p = parse_name(p)
        if not isinstance(p, dict):
            continue
        if (p.get("family") or "").strip() or (p.get("literal") or "").strip() or (p.get("given") or "").strip():
            out.append(p)
    return out


_PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "du", "la", "le", "bin", "ibn", "al", "ter", "ten"}


def parse_name(raw: str) -> dict:
    """Split a personal name into given/family parts.

    'Aust, Anthony' and 'Anthony Aust' both give {given: Anthony, family: Aust}.
    """
    raw = re.sub(r"\s+", " ", raw or "").strip()
    if not raw:
        return {}
    if "," in raw:
        family, given = raw.split(",", 1)
        return {"family": family.strip(), "given": given.strip()}
    tokens = raw.split(" ")
    if len(tokens) == 1:
        return {"family": tokens[0], "given": ""}
    idx = len(tokens) - 1
    while idx > 1 and tokens[idx - 1].lower() in _PARTICLES and tokens[idx - 1].islower():
        idx -= 1
    return {"given": " ".join(tokens[:idx]), "family": " ".join(tokens[idx:])}


def family_of(p: dict) -> str:
    return (p.get("family") or p.get("literal") or p.get("given") or "").strip()


def initials(given: str, dot: str = "", sep: str = "") -> str:
    """'Herbert Lionel Adolphus' -> 'HLA' (OSCOLA) or 'H. L. A.' (APA)."""
    out = []
    for token in re.split(r"[\s.]+", given or ""):
        if not token:
            continue
        pieces = [piece[0].upper() + dot for piece in token.split("-") if piece]
        out.append("-".join(pieces))
    return sep.join(out)


def year_of(m: dict) -> str:
    year = g(m, "year")
    if year:
        return year
    for key in ("date", "adopted_date"):
        match = re.match(r"(\d{4})", g(m, key))
        if match:
            return match.group(1)
    return ""


_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_BB_MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def parse_date(value: str) -> tuple[int | None, int | None, int | None]:
    match = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", (value or "").strip())
    if not match:
        return (None, None, None)
    year, month, day = (int(x) if x else None for x in match.groups())
    if month is not None and not 1 <= month <= 12:
        month = day = None
    return (year, month, day)


def format_date(value: str, style: str) -> str:
    """Format an ISO date (YYYY, YYYY-MM or YYYY-MM-DD). Unparseable input is returned as typed."""
    year, month, day = parse_date(value)
    if year is None:
        return (value or "").strip()
    if month is None:
        return str(year)
    if style == "oscola":
        return f"{day} {_MONTHS[month - 1]} {year}" if day else f"{_MONTHS[month - 1]} {year}"
    if style == "bluebook":
        return f"{_BB_MONTHS[month - 1]} {day}, {year}" if day else f"{_BB_MONTHS[month - 1]} {year}"
    if style == "apa":  # "2009, May 1"
        return f"{year}, {_MONTHS[month - 1]} {day}" if day else f"{year}, {_MONTHS[month - 1]}"
    if style == "apa_long":  # "May 1, 2009"
        return f"{_MONTHS[month - 1]} {day}, {year}" if day else f"{_MONTHS[month - 1]} {year}"
    return value


def edition_number(m: dict) -> int | None:
    match = re.search(r"\d+", g(m, "edition"))
    return int(match.group()) if match else None


def ordinal(n: int, bluebook: bool = False) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    if bluebook and suffix in ("nd", "rd"):
        suffix = "d"
    return f"{n}{suffix}"


def edition_text(m: dict, word: str, bluebook: bool = False) -> str:
    """'3rd edn' / '3d ed.'; first editions are conventionally not cited."""
    raw = g(m, "edition")
    if not raw:
        return ""
    n = edition_number(m)
    if n is None:
        cleaned = re.sub(r"\s*\b(edition|edn|ed)\b\.?", "", raw, flags=re.I).strip()
        return f"{cleaned} {word}" if cleaned else ""
    if n == 1:
        return ""
    return f"{ordinal(n, bluebook)} {word}"


def first_page(m: dict) -> str:
    pages = g(m, "pages")
    if not pages:
        return ""
    return re.split(r"\s*[-–—]\s*", pages)[0].strip()


def page_range(m: dict) -> str:
    return re.sub(r"\s*[-–—]+\s*", "–", g(m, "pages"))


def doi_url(m: dict) -> str:
    doi = g(m, "doi")
    return f"https://doi.org/{doi}" if doi else ""


def case_short_name(title: str) -> str:
    """'Donoghue v Stevenson' -> 'Donoghue'; 'R (Miller) v Prime Minister' -> 'Miller'."""
    first = re.split(r"\s+v\.?\s+", title, maxsplit=1)[0].strip()
    match = re.match(r"^R\s*\((?:on the application of\s+)?([^)]+)\)$", first, flags=re.I)
    if match:
        return match.group(1).strip()
    return first or title


def normalise_v(title: str, dotted: bool) -> str:
    return re.sub(r"\s+(?:v|vs|versus)\.?\s+", " v. " if dotted else " v ", title, count=1)


def report_has_year(report: str) -> bool:
    return bool(re.search(r"[\[(]\d{4}(?:[-–]\d{2,4})?[\])]", report))


def sort_key(m: dict) -> str:
    """Alphabetical key: first author's surname for secondary sources, otherwise the title."""
    key = ""
    if m.get("type") not in LEGAL_TYPES:
        ppl = people(m, "authors") or people(m, "editors")
        if ppl:
            key = family_of(ppl[0]) + " " + (ppl[0].get("given") or "")
    title = re.sub(r"^(the|a|an)\s+", "", g(m, "title"), flags=re.I)
    return re.sub(r"[^\w\s]", "", f"{key} {title}".lower()).strip()


REQUIRED: dict[str, list[Any]] = {
    # Each entry is a field name, or a tuple meaning "at least one of these".
    "case": ["title", ("neutral_citation", "report_citation", "court"), ("neutral_citation", "report_citation", "date", "year")],
    "legislation": ["title", ("year", "title_year")],
    "treaty": ["title", "adopted_date"],
    "book": [("authors", "editors"), "title", "publisher", "year"],
    "chapter": ["authors", "title", "container_title", "publisher", "year"],
    "article": ["authors", "title", "journal", "year", ("pages", "doi", "url")],
    "report": ["authors", "title", "year"],
    "thesis": ["authors", "title", "institution", "year"],
    "website": ["title", "url"],
}

RECOMMENDED: dict[str, list[str]] = {
    "case": ["court", "date"],
    "legislation": ["jurisdiction"],
    "treaty": ["entry_into_force_date", "treaty_series"],
    "book": [],
    "chapter": ["editors", "pages"],
    "article": ["volume"],
    "report": ["publisher"],
    "thesis": ["thesis_type"],
    "website": ["authors", "date", "accessed"],
}

FIELD_LABELS = {
    "title": "Title",
    "authors": "Author",
    "editors": "Editor",
    "year": "Year",
    "title_year": "Year",
    "date": "Date",
    "publisher": "Publisher",
    "place": "Place of publication",
    "edition": "Edition",
    "volume": "Volume",
    "issue": "Issue",
    "pages": "Pages",
    "journal": "Journal",
    "container_title": "Book title",
    "doi": "DOI",
    "isbn": "ISBN",
    "url": "URL",
    "accessed": "Access date",
    "court": "Court",
    "case_number": "Case number",
    "neutral_citation": "Neutral citation",
    "report_citation": "Law report citation",
    "jurisdiction": "Jurisdiction",
    "number": "Number",
    "adopted_date": "Adoption date",
    "entry_into_force_date": "Entry-into-force date",
    "treaty_series": "Treaty series reference",
    "short_title": "Short title",
    "institution": "Institution",
    "thesis_type": "Thesis type",
    "website": "Website name",
}


def has_field(m: dict, key: str) -> bool:
    if key in ("authors", "editors"):
        return bool(people(m, key))
    if key == "year":
        return bool(year_of(m))
    if key == "title_year":
        return bool(re.search(r"\b\d{4}\b", g(m, "title")))
    return bool(g(m, key))


def missing_fields(m: dict) -> dict[str, list[str]]:
    """Fields the citation needs but the metadata lacks, as human-readable labels."""
    kind = m.get("type") or "book"
    required, recommended = [], []
    for spec in REQUIRED.get(kind, ["title"]):
        options = spec if isinstance(spec, tuple) else (spec,)
        if not any(has_field(m, key) for key in options):
            label = " or ".join(dict.fromkeys(FIELD_LABELS.get(key, key) for key in options))
            if label not in required:
                required.append(label)
    for key in RECOMMENDED.get(kind, []):
        if not has_field(m, key):
            recommended.append(FIELD_LABELS.get(key, key))
    return {"required": required, "recommended": recommended}
