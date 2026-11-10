"""Duplicate detection: the same source reached through different inputs."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from .citation.common import g

REASONS = {
    "doi": "Same DOI",
    "isbn": "Same ISBN",
    "url": "Same URL",
    "neutral": "Same neutral citation",
    "report": "Same law report citation",
    "title": "Same title",
}


def isbn13(isbn: str) -> str:
    isbn = re.sub(r"[^0-9Xx]", "", isbn or "").upper()
    if len(isbn) == 10:
        core = "978" + isbn[:9]
        check = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core)) % 10) % 10
        return core + str(check)
    return isbn


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _norm_title(m: dict) -> str:
    title = g(m, "title")
    if m.get("type") == "case":
        title = re.sub(r"\s+(?:v|vs|versus)\.?\s+", " v ", title, flags=re.I)
    return re.sub(r"^(the|a|an) ", "", _norm(title))


def _norm_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}" + (f"?{parts.query}" if parts.query else "")


def keys(m: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if g(m, "doi"):
        out.add(("doi", g(m, "doi").lower()))
    if g(m, "isbn"):
        out.add(("isbn", isbn13(g(m, "isbn"))))
    if g(m, "url"):
        out.add(("url", _norm_url(g(m, "url"))))
    if g(m, "neutral_citation"):
        out.add(("neutral", _norm(g(m, "neutral_citation"))))
    if g(m, "report_citation"):
        out.add(("report", _norm(g(m, "report_citation"))))
    title = _norm_title(m)
    if title:
        out.add(("title", f"{m.get('type')}|{title}"))
    return out


def _same_source(a: dict, b: dict, shared: set[tuple[str, str]]) -> bool:
    kinds = {kind for kind, _ in shared}
    if kinds - {"title"}:
        return True
    if not kinds:
        return False
    # Title-only match: reject when a hard identifier clearly disagrees.
    for field in ("doi", "neutral_citation"):
        if g(a, field) and g(b, field) and g(a, field).lower() != g(b, field).lower():
            return False
    if g(a, "isbn") and g(b, "isbn") and isbn13(g(a, "isbn")) != isbn13(g(b, "isbn")):
        return False
    return True


def find_duplicates(m: dict, existing: list[tuple[int, dict]]) -> list[dict[str, Any]]:
    """References in ``existing`` that may be the same source as ``m``."""
    mine = keys(m)
    out = []
    for ref_id, other in existing:
        shared = mine & keys(other)
        if _same_source(m, other, shared):
            order = list(REASONS)
            reasons = [REASONS[k] for k in sorted({kind for kind, _ in shared}, key=order.index)]
            out.append({"id": ref_id, "reasons": reasons})
    return out


def duplicate_groups(existing: list[tuple[int, dict]]) -> list[dict[str, Any]]:
    """Cluster a whole library into groups of probable duplicates."""
    parent = {ref_id: ref_id for ref_id, _ in existing}
    reasons: dict[tuple[int, int], list[str]] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, (id_a, a) in enumerate(existing):
        for match in find_duplicates(a, existing[i + 1:]):
            reasons[(id_a, match["id"])] = match["reasons"]
            parent[find(match["id"])] = find(id_a)

    groups: dict[int, dict[str, Any]] = {}
    for (id_a, id_b), why in reasons.items():
        group = groups.setdefault(find(id_a), {"ids": [], "reasons": []})
        for ref_id in (id_a, id_b):
            if ref_id not in group["ids"]:
                group["ids"].append(ref_id)
        for reason in why:
            if reason not in group["reasons"]:
                group["reasons"].append(reason)
    return list(groups.values())
