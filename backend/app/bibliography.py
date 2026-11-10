"""Bibliography and List of Authorities generation."""
from __future__ import annotations

from typing import Any

from .citation.common import SOURCE_TYPES, sort_key
from .citation.engine import cite_rich

AUTHORITY_CATEGORIES = [
    {"heading": "Treaties and International Instruments", "types": ["treaty"]},
    {"heading": "Cases and Judicial Decisions", "types": ["case"]},
    {"heading": "Legislation", "types": ["legislation"]},
    {"heading": "Books and Academic Publications", "types": ["book", "chapter", "article", "thesis"]},
    {"heading": "Other Authorities", "types": ["report", "website"]},
]

# OSCOLA separates primary sources into tables and lists secondary sources alphabetically.
LEGAL_BIBLIOGRAPHY_CATEGORIES = [
    {"heading": "Table of Cases", "types": ["case"]},
    {"heading": "Table of Legislation", "types": ["legislation"]},
    {"heading": "Treaties and International Instruments", "types": ["treaty"]},
    {"heading": "Secondary Sources", "types": ["book", "chapter", "article", "report", "thesis", "website"]},
]

TITLES = {"bibliography": {"apa": "References"}, "authorities": {}}


def default_categories(mode: str, style: str) -> list[dict[str, Any]]:
    if mode == "authorities":
        return AUTHORITY_CATEGORIES
    if style == "apa":  # one alphabetical reference list
        return [{"heading": "", "types": list(SOURCE_TYPES)}]
    return LEGAL_BIBLIOGRAPHY_CATEGORIES


def default_title(mode: str, style: str) -> str:
    if mode == "authorities":
        return "List of Authorities"
    return TITLES["bibliography"].get(style, "Bibliography")


def build(references: list[dict[str, Any]], style: str, mode: str = "bibliography", categories: list[dict] | None = None) -> list[dict[str, Any]]:
    """Group, order and format references.

    ``references`` are dicts with ``id`` and ``metadata``. Sources of a type that no
    category claims are never dropped: they are collected under "Other Authorities".
    """
    categories = categories or default_categories(mode, style)
    claimed: set[str] = set()
    sections = []
    for category in categories:
        types = [t for t in category.get("types", []) if t in SOURCE_TYPES and t not in claimed]
        claimed.update(types)
        sections.append({"heading": category.get("heading", ""), "types": types})
    leftover = [t for t in SOURCE_TYPES if t not in claimed]
    if leftover and any(r["metadata"].get("type") in leftover for r in references):
        other = next((s for s in sections if s["heading"] == "Other Authorities"), None)
        if other:
            other["types"] += leftover
        else:
            sections.append({"heading": "Other Authorities", "types": leftover})

    out = []
    for section in sections:
        members = [r for r in references if r["metadata"].get("type") in section["types"]]
        if not members:
            continue
        members.sort(key=lambda r: sort_key(r["metadata"]))
        entries = []
        for r in members:
            rich = cite_rich(r["metadata"], style)["bibliography"]
            entries.append({"id": r["id"], "text": rich.text, "html": rich.html})
        out.append({"heading": section["heading"], "entries": entries})
    return out
