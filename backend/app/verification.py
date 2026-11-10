"""Citation verification engine.

Compares the metadata being cited with the record originally retrieved from an
external source, field by field. It only assesses bibliographic accuracy.
"""
from __future__ import annotations

import re
from typing import Any

from .citation.common import FIELD_LABELS, RECOMMENDED, REQUIRED, has_field, missing_fields, people

DISCLAIMER = (
    "Verification covers bibliographic details only. It does not establish the legal authority, "
    "precedential value or continuing validity of a source."
)

STATUS_LABELS = {
    "verified": "Verified",
    "partially_verified": "Partially Verified",
    "needs_review": "Needs Review",
    "user_confirmed": "User Confirmed",
}

_IDENTIFIERS = {
    "case": ["case_number"],
    "book": ["isbn", "edition"],
    "chapter": ["isbn", "editors"],
    "article": ["doi", "volume", "issue"],
    "report": ["doi", "number"],
    "thesis": [],
    "website": [],
    "legislation": ["number"],
    "treaty": [],
}


def _fields_for(kind: str) -> list[str]:
    fields: list[str] = []
    for spec in REQUIRED.get(kind, ["title"]):
        for key in spec if isinstance(spec, tuple) else (spec,):
            if key != "title_year" and key not in fields:
                fields.append(key)
    for key in RECOMMENDED.get(kind, []) + _IDENTIFIERS.get(kind, []):
        if key not in fields:
            fields.append(key)
    return fields


def _comparable(m: dict, key: str) -> Any:
    if key in ("authors", "editors"):
        return [re.sub(r"\W+", "", (p.get("family") or p.get("literal") or "").lower()) for p in people(m, key)]
    if key == "year":
        value = str(m.get("year") or "")
        if not value:
            match = re.match(r"\d{4}", str(m.get("date") or m.get("adopted_date") or ""))
            value = match.group() if match else ""
        return value
    return re.sub(r"[\s\W]+", " ", str(m.get(key) or "").lower()).strip()


def verify(metadata: dict, retrieved: dict | None, source: dict | None, user_confirmed: bool = False) -> dict[str, Any]:
    kind = metadata.get("type") or "book"
    missing = missing_fields(metadata)
    has_source = bool(source and retrieved)
    # A missing field is only worth reporting when the citation needs it: skip
    # unused alternatives (e.g. no neutral citation where a law report is given).
    wanted = set(RECOMMENDED.get(kind, []))
    for spec in REQUIRED.get(kind, ["title"]):
        options = spec if isinstance(spec, tuple) else (spec,)
        if not any(has_field(metadata, key) for key in options):
            wanted.update(options)
    checks = []
    for key in _fields_for(kind):
        present = has_field(metadata, key)
        if not present and key not in wanted:
            continue
        if not present:
            state = "missing"
        elif not has_source or not has_field(retrieved, key):
            state = "unverified"
        elif _comparable(metadata, key) == _comparable(retrieved, key):
            state = "confirmed"
        else:
            state = "edited"
        checks.append({"field": key, "label": FIELD_LABELS.get(key, key), "state": state})

    confirmed = [c for c in checks if c["state"] == "confirmed"]
    unconfirmed = [c for c in checks if c["state"] in ("edited", "unverified")]

    if user_confirmed:
        status = "user_confirmed"
        summary = "You reviewed and approved this citation."
    elif not has_source:
        status = "needs_review"
        summary = "Entered manually. No external source has confirmed these details."
    elif not confirmed:
        status = "needs_review"
        summary = "None of the cited details match the retrieved record."
    elif missing["required"] or unconfirmed or not source.get("reliable", False):
        status = "partially_verified"
        reasons = []
        if missing["required"]:
            reasons.append("missing: " + ", ".join(missing["required"]))
        if unconfirmed:
            reasons.append("not confirmed by the source: " + ", ".join(c["label"] for c in unconfirmed))
        if not source.get("reliable", False):
            reasons.append("the source is not an authoritative bibliographic record")
        summary = "Some details are confirmed; " + "; ".join(reasons) + "."
    else:
        status = "verified"
        summary = f"All cited details match the record from {source.get('name', 'the source')}."

    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "summary": summary,
        "checks": checks,
        "missing": missing,
        "source": source,
        "disclaimer": DISCLAIMER,
    }
