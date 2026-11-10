"""Universal source identification: route a query to the right providers."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Awaitable

import httpx

from .. import config
from ..citation.common import LEGAL_TYPES
from ..citation.engine import normalise_metadata
from . import providers
from .detect import classify, looks_like_case, valid_isbn

_AUTHORITIES: list[dict] = json.loads((Path(__file__).parent.parent / "data" / "authorities.json").read_text("utf-8"))
CURATED_SOURCE = "CiteRight reference list of landmark authorities"


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=config.HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": "CiteRight/1.0 (citation manager)"},
        follow_redirects=False,
    )


def _norm(text: str) -> str:
    text = re.sub(r"\s+(?:v|vs|versus)\.?\s+", " v ", text.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def curated_search(query: str, type_hint: str | None = None, limit: int = 5) -> list[dict]:
    """Search the bundled list of landmark cases, treaties and statutes."""
    q = _norm(query)
    tokens = [t for t in q.split() if t not in ("the", "of", "v", "and", "on", "in", "for", "case")]
    if not tokens:
        return []
    scored = []
    for record in _AUTHORITIES:
        if type_hint and record["type"] != type_hint:
            continue
        names = [_norm(record["title"])] + [_norm(a) for a in record.get("aliases", [])]
        if q in names:
            score, match = 3, "exact_title"
        elif any(name.startswith(q) or q in name for name in names):
            score, match = 2, "search"
        elif all(any(re.search(rf"\b{re.escape(t)}", name) for name in names) for t in tokens):
            score, match = 1, "search"
        else:
            continue
        metadata = {k: v for k, v in record.items() if k != "aliases"}
        scored.append((score, providers.candidate(metadata, CURATED_SOURCE, "", match)))
    scored.sort(key=lambda pair: -pair[0])
    return [c for _, c in scored[:limit]]


async def _run(tasks: dict[str, Awaitable[list[dict]]]) -> tuple[list[dict], list[str], int]:
    """Run providers concurrently. Failures become warnings instead of silent gaps."""
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    candidates, warnings, not_found = [], [], 0
    for name, result in zip(tasks, results):
        if isinstance(result, LookupError):
            not_found += 1
        elif isinstance(result, providers.ProviderError):
            warnings.append(f"{name} could not be reached: {result}.")
        elif isinstance(result, Exception):
            warnings.append(f"{name} returned an unexpected response.")
        else:
            candidates.extend(result)
    return candidates, warnings, not_found


def _dedupe(candidates: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in candidates:
        m = c["metadata"]
        key = (m.get("type"), _norm(m.get("title", "")), m.get("year") or m.get("neutral_citation") or m.get("report_citation"), c["source"]["name"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


async def identify(query: str, type_hint: str | None = None, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    kind, value = classify(query)
    own_client = client is None
    client = client or make_client()
    candidates: list[dict] = []
    warnings: list[str] = []
    message = ""
    try:
        if kind == "doi":
            candidates, warnings, not_found = await _run({"Crossref": providers.crossref_doi(client, value)})
            if not_found:
                message = "Crossref has no record of this DOI. Check the DOI, or enter the details manually."
        elif kind == "isbn":
            candidates, warnings, _ = await _run({
                "Open Library": providers.openlibrary_isbn(client, value),
                "Google Books": providers.google_books(client, f"isbn:{value}", "identifier", 1),
            })
            if not candidates and not warnings:
                message = "No book record was found for this ISBN. Check the number, or enter the details manually."
            if not valid_isbn(value):
                warnings.append("The check digit of this ISBN does not validate. Compare the number with the book's imprint page.")
        elif kind == "url":
            try:
                page = await providers.fetch_page(client, value)
            except providers.ProviderError as exc:
                page = None
                warnings.append(f"The page could not be read: {exc}.")
            if page and page.get("doi"):
                candidates, more, _ = await _run({"Crossref": providers.crossref_doi(client, page["doi"])})
                warnings += more
            if page and page.get("title") and not candidates:
                candidates = [providers.candidate(page, "Metadata published on the web page", value, "identifier", reliable=False)]
            if not candidates and not warnings:
                message = "The page does not publish bibliographic metadata. Enter the details manually."
        else:
            candidates = curated_search(value, type_hint if type_hint in LEGAL_TYPES else None) if type_hint in (None, *LEGAL_TYPES) else []
            tasks: dict[str, Awaitable[list[dict]]] = {}
            if type_hint == "case" or (type_hint is None and looks_like_case(value)):
                tasks["Find Case Law"] = providers.national_archives_cases(client, value)
                tasks["CourtListener"] = providers.courtlistener_cases(client, value)
            elif type_hint not in LEGAL_TYPES:
                if type_hint in (None, "article", "chapter", "report", "thesis"):
                    tasks["Crossref"] = providers.crossref_search(client, value)
                if type_hint in (None, "book"):
                    tasks["Google Books"] = providers.google_books(client, value, "search")
            found, warnings, _ = await _run(tasks)
            if type_hint:
                found = [c for c in found if c["metadata"].get("type") == type_hint]
            q = _norm(value)
            for c in found:
                if _norm(c["metadata"].get("title", "")) == q:
                    c["match"] = "exact_title"
            candidates += found
            candidates.sort(key=lambda c: c["match"] != "exact_title")
            if not candidates and not warnings:
                message = "No matching source was found. Add more detail (author, year, court) or enter the source manually."
    finally:
        if own_client:
            await client.aclose()

    candidates = _dedupe(candidates)
    for c in candidates:
        c["metadata"] = normalise_metadata(c["metadata"])
    if not candidates and not message:
        message = "The source could not be identified. Try again later or enter the details manually."
    elif len(candidates) > 1:
        message = "Several possible sources were found. Select the correct one."
    return {"input_kind": kind, "query": value, "candidates": candidates, "warnings": warnings, "message": message}
