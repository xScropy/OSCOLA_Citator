"""Central citation engine: metadata normalisation and style dispatch."""
from __future__ import annotations

import re
from typing import Any

from . import apa, bluebook, oscola
from .common import PINPOINT_KINDS, SOURCE_TYPES, Rich, missing_fields, parse_name

STYLES = {
    "oscola": {"name": "OSCOLA", "module": oscola},
    "bluebook": {"name": "Bluebook", "module": bluebook},
    "apa": {"name": "APA 7th", "module": apa},
}
DEFAULT_STYLE = "oscola"

TEXT_FIELDS = (
    "title", "year", "date", "publisher", "place", "edition", "volume", "issue", "pages",
    "journal", "container_title", "doi", "isbn", "url", "accessed", "court", "case_number",
    "neutral_citation", "report_citation", "jurisdiction", "number", "adopted_date",
    "entry_into_force_date", "treaty_series", "short_title", "institution", "thesis_type", "website",
)
PEOPLE_FIELDS = ("authors", "editors")


def clean_doi(value: str) -> str:
    value = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", (value or "").strip(), flags=re.I)
    return value.rstrip(".,;")


def clean_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def normalise_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce arbitrary input into the canonical metadata shape, dropping empty values."""
    raw = raw or {}
    kind = raw.get("type") if raw.get("type") in SOURCE_TYPES else "book"
    out: dict[str, Any] = {"type": kind}
    for key in TEXT_FIELDS:
        value = raw.get(key)
        if value is None:
            continue
        value = re.sub(r"\s+", " ", str(value)).strip()
        if value:
            out[key] = value
    for key in PEOPLE_FIELDS:
        ppl = []
        for p in raw.get(key) or []:
            if isinstance(p, str):
                p = parse_name(p)
            if not isinstance(p, dict):
                continue
            person = {k: re.sub(r"\s+", " ", str(p[k])).strip() for k in ("given", "family", "literal") if p.get(k)}
            if person:
                ppl.append(person)
        if ppl:
            out[key] = ppl
    if "doi" in out:
        out["doi"] = clean_doi(out["doi"])
    if "isbn" in out:
        out["isbn"] = clean_isbn(out["isbn"])
    return out


def normalise_pinpoint(raw: dict[str, Any] | None) -> dict[str, str] | None:
    if not raw:
        return None
    value = str(raw.get("value") or "").strip()
    if not value:
        return None
    kind = raw.get("kind") if raw.get("kind") in PINPOINT_KINDS else "page"
    return {"kind": kind, "value": value}


def cite_rich(metadata: dict, style: str, pinpoint: dict | None = None) -> dict[str, Rich]:
    module = STYLES.get(style, STYLES[DEFAULT_STYLE])["module"]
    return module.format(metadata, pinpoint)


def cite(metadata: dict, style: str, pinpoint: dict | None = None) -> dict[str, Any]:
    """Format every citation form for one source in one style."""
    style = style if style in STYLES else DEFAULT_STYLE
    module = STYLES[style]["module"]
    forms = module.format(metadata, pinpoint)
    return {
        "style": style,
        "forms": {key: {"label": module.LABELS[key], **value.to_dict()} for key, value in forms.items()},
        "missing": missing_fields(metadata),
    }
