"""Classify free-form user input: DOI, ISBN, URL or descriptive text."""
from __future__ import annotations

import re

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def valid_isbn(isbn: str) -> bool:
    if len(isbn) == 10 and re.fullmatch(r"\d{9}[\dX]", isbn):
        total = sum((10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(isbn))
        return total % 11 == 0
    if len(isbn) == 13 and isbn.isdigit():
        total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(isbn))
        return total % 10 == 0
    return False


def classify(query: str) -> tuple[str, str]:
    """Return (kind, value) where kind is 'doi', 'isbn', 'url' or 'text'."""
    query = (query or "").strip()
    doi = _DOI.search(query)
    if doi and re.match(r"^(doi:\s*10\.|10\.|https?://(dx\.)?doi\.org/)", query, re.I):
        return ("doi", doi.group(1).rstrip(".,;)"))
    if re.match(r"^(https?://|www\.)\S+$", query, re.I):
        return ("url", query if query.lower().startswith("http") else "https://" + query)
    stripped = re.sub(r"^isbn(-1[03])?:?\s*", "", query, flags=re.I)
    if re.fullmatch(r"[\dXx\s-]+", stripped):
        candidate = re.sub(r"[\s-]", "", stripped).upper()
        # A mistyped check digit is still an ISBN attempt; the service warns about it.
        if re.fullmatch(r"\d{9}[\dX]|97[89]\d{10}", candidate):
            return ("isbn", candidate)
    return ("text", query)


def looks_like_case(query: str) -> bool:
    return bool(re.search(r"\S\s+(v|vs|versus)\.?\s+\S", query, re.I)) or bool(
        re.match(r"^(re|in re|ex parte)\s", query, re.I)
    )
