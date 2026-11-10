"""Metadata providers.

Each provider maps an external record onto CiteRight's metadata shape and copies
only what the record states. Nothing is guessed: absent fields stay absent.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .. import config
from ..citation.common import parse_name


class ProviderError(Exception):
    pass


def candidate(metadata: dict, name: str, url: str, match: str, reliable: bool = True) -> dict[str, Any]:
    return {
        "metadata": {k: v for k, v in metadata.items() if v not in (None, "", [])},
        "source": {"name": name, "url": url, "reliable": reliable, "retrieved_at": date.today().isoformat()},
        "match": match,
    }


def _text(value: Any) -> str:
    """Plain text from a provider string that may carry markup."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))).strip()


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
    try:
        response = await client.get(url, params=params, headers=headers, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ProviderError(f"request failed ({type(exc).__name__})") from exc
    if response.status_code == 404:
        raise LookupError("not found")
    if response.status_code >= 400:
        raise ProviderError(f"HTTP {response.status_code}")
    return response


# --------------------------------------------------------------------------- Crossref

_CROSSREF_TYPES = {
    "journal-article": "article",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "book-chapter": "chapter",
    "book-section": "chapter",
    "book-part": "chapter",
    "proceedings-article": "chapter",
    "report": "report",
    "posted-content": "report",
    "dissertation": "thesis",
}


def _crossref_people(items: list | None) -> list[dict]:
    out = []
    for p in items or []:
        if p.get("family"):
            out.append({"family": _text(p["family"]), "given": _text(p.get("given"))})
        elif p.get("name"):
            out.append({"literal": _text(p["name"])})
    return out


def from_crossref(item: dict) -> dict:
    kind = _CROSSREF_TYPES.get(item.get("type", ""), "article" if item.get("container-title") else "book")
    title = _text(item.get("title"))
    subtitle = _text(item.get("subtitle"))
    if subtitle and subtitle.lower() not in title.lower():
        title = f"{title}: {subtitle}"
    parts = []
    for key in ("published-print", "published", "issued", "published-online"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            break
    m: dict[str, Any] = {
        "type": kind,
        "title": title,
        "authors": _crossref_people(item.get("author")),
        "editors": _crossref_people(item.get("editor")),
        "year": str(parts[0]) if parts and parts[0] else "",
        "publisher": _text(item.get("publisher")),
        "place": _text(item.get("publisher-location")),
        "volume": _text(item.get("volume")),
        "issue": _text(item.get("issue")),
        "pages": _text(item.get("page")),
        "doi": _text(item.get("DOI")),
        "isbn": _text(item.get("ISBN")),
        "edition": _text(item.get("edition-number")),
    }
    container = _text(item.get("container-title"))
    if kind == "article":
        m["journal"] = container
        m.pop("publisher")
        m.pop("place")
        m.pop("isbn")
    elif kind == "chapter":
        m["container_title"] = container
    elif kind == "thesis":
        m["institution"] = m.pop("publisher")
    if m["doi"]:
        m["url"] = f"https://doi.org/{m['doi']}"
    return m


def _crossref_params(extra: dict | None = None) -> dict:
    params = dict(extra or {})
    if config.CROSSREF_MAILTO:
        params["mailto"] = config.CROSSREF_MAILTO
    return params


async def crossref_doi(client: httpx.AsyncClient, doi: str) -> list[dict]:
    response = await _get(client, f"https://api.crossref.org/works/{quote(doi, safe='/')}", _crossref_params())
    item = response.json().get("message") or {}
    return [candidate(from_crossref(item), "Crossref", f"https://doi.org/{doi}", "identifier")]


async def crossref_search(client: httpx.AsyncClient, query: str, rows: int = 5) -> list[dict]:
    response = await _get(client, "https://api.crossref.org/works", _crossref_params({"query.bibliographic": query, "rows": rows}))
    items = (response.json().get("message") or {}).get("items") or []
    out = []
    for item in items:
        m = from_crossref(item)
        if m.get("title"):
            out.append(candidate(m, "Crossref", m.get("url", "https://search.crossref.org/"), "search"))
    return out


# --------------------------------------------------------------------------- Open Library

def _year(text: str) -> str:
    match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text or "")
    return match.group(1) if match else ""


async def openlibrary_isbn(client: httpx.AsyncClient, isbn: str) -> list[dict]:
    response = await _get(
        client,
        "https://openlibrary.org/api/books",
        {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
    )
    record = (response.json() or {}).get(f"ISBN:{isbn}")
    if not record:
        raise LookupError("not found")
    title = _text(record.get("title"))
    if record.get("subtitle"):
        title = f"{title}: {_text(record['subtitle'])}"
    m = {
        "type": "book",
        "title": title,
        "authors": [parse_name(_text(a.get("name"))) for a in record.get("authors") or [] if a.get("name")],
        "publisher": _text((record.get("publishers") or [{}])[0].get("name")),
        "place": _text((record.get("publish_places") or [{}])[0].get("name")),
        "year": _year(record.get("publish_date", "")),
        "isbn": isbn,
    }
    return [candidate(m, "Open Library", record.get("url") or f"https://openlibrary.org/isbn/{isbn}", "identifier")]


# --------------------------------------------------------------------------- Google Books

def _from_google(volume: dict) -> dict:
    info = volume.get("volumeInfo") or {}
    title = _text(info.get("title"))
    if info.get("subtitle"):
        title = f"{title}: {_text(info['subtitle'])}"
    isbns = {i.get("type"): i.get("identifier") for i in info.get("industryIdentifiers") or []}
    return {
        "type": "book",
        "title": title,
        "authors": [parse_name(_text(a)) for a in info.get("authors") or []],
        "publisher": _text(info.get("publisher")),
        "year": _year(info.get("publishedDate", "")),
        "isbn": isbns.get("ISBN_13") or isbns.get("ISBN_10") or "",
    }


async def google_books(client: httpx.AsyncClient, query: str, match: str, limit: int = 5) -> list[dict]:
    params = {"q": query, "maxResults": limit, "printType": "books"}
    if config.GOOGLE_BOOKS_API_KEY:
        params["key"] = config.GOOGLE_BOOKS_API_KEY
    response = await _get(client, "https://www.googleapis.com/books/v1/volumes", params)
    out = []
    for volume in response.json().get("items") or []:
        m = _from_google(volume)
        if m.get("title"):
            link = (volume.get("volumeInfo") or {}).get("canonicalVolumeLink") or "https://books.google.com/"
            out.append(candidate(m, "Google Books", link, match))
    if not out and match == "identifier":
        raise LookupError("not found")
    return out


# --------------------------------------------------------------------------- Case law

_NEUTRAL = re.compile(r"\[\d{4}\]\s+[A-Z][A-Za-z]+(?:\s+[A-Za-z]+)?\s+\d+(?:\s+\([A-Za-z]+\))?")
_TNA_COURTS = {"uksc": "UKSC", "ukpc": "UKPC", "ukhl": "UKHL", "ewca": "EWCA", "ewhc": "EWHC", "ukut": "UKUT", "ukftt": "UKFTT", "ewcop": "EWCOP", "ewfc": "EWFC", "eat": "EAT"}
_TNA_DIVISIONS = {"civ": "Civ", "crim": "Crim", "admin": "Admin", "ch": "Ch", "kb": "KB", "qb": "QB", "fam": "Fam", "comm": "Comm", "tcc": "TCC", "pat": "Pat", "ipec": "IPEC", "admlty": "Admlty", "iac": "IAC", "lc": "LC", "tcc ": "TCC", "aac": "AAC", "tc": "TC", "grc": "GRC"}


def neutral_from_tna_uri(uri: str) -> str:
    """'ewca/civ/2020/123' -> '[2020] EWCA Civ 123'; 'ewhc/ch/2021/7' -> '[2021] EWHC 7 (Ch)'."""
    parts = [p for p in urlsplit(uri).path.strip("/").split("/") if p]
    if len(parts) == 3 and parts[0] in _TNA_COURTS and parts[1].isdigit() and parts[2].isdigit():
        return f"[{parts[1]}] {_TNA_COURTS[parts[0]]} {parts[2]}"
    if len(parts) == 4 and parts[0] in _TNA_COURTS and parts[1] in _TNA_DIVISIONS and parts[2].isdigit() and parts[3].isdigit():
        court, division = _TNA_COURTS[parts[0]], _TNA_DIVISIONS[parts[1]]
        if parts[0] == "ewca":
            return f"[{parts[2]}] {court} {division} {parts[3]}"
        return f"[{parts[2]}] {court} {parts[3]} ({division})"
    return ""


async def national_archives_cases(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[dict]:
    """Find Case Law (The National Archives): official judgments of UK courts and tribunals."""
    response = await _get(client, "https://caselaw.nationalarchives.gov.uk/atom.xml", {"query": query, "per_page": limit, "order": "relevance"})
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise ProviderError("unreadable response") from exc
    atom = "{http://www.w3.org/2005/Atom}"
    out = []
    for entry in root.iter(f"{atom}entry"):
        title = _text(entry.findtext(f"{atom}title"))
        if not title:
            continue
        links = [link.get("href", "") for link in entry.iter(f"{atom}link")]
        page = next((href for href in links if href and not href.endswith((".xml", ".pdf"))), links[0] if links else "")
        neutral = ""
        for element in entry.iter():
            if element.tag.endswith("identifier") or element.tag.endswith("}uri"):
                found = _NEUTRAL.search(element.text or "")
                neutral = neutral or (found.group(0) if found else "")
        neutral = neutral or neutral_from_tna_uri(page)
        court = _text(entry.findtext(f"{atom}author/{atom}name"))
        published = (entry.findtext(f"{atom}published") or "")[:10]
        m = {"type": "case", "title": title, "neutral_citation": neutral, "court": court, "date": published, "jurisdiction": "UK", "url": page}
        out.append(candidate(m, "Find Case Law (The National Archives)", page or "https://caselaw.nationalarchives.gov.uk/", "search"))
        if len(out) >= limit:
            break
    return out


async def courtlistener_cases(client: httpx.AsyncClient, query: str, limit: int = 5) -> list[dict]:
    """CourtListener (Free Law Project): United States case law."""
    headers = {"Authorization": f"Token {config.COURTLISTENER_TOKEN}"} if config.COURTLISTENER_TOKEN else None
    response = await _get(client, "https://www.courtlistener.com/api/rest/v4/search/", {"q": query, "type": "o"}, headers)
    out = []
    for item in (response.json().get("results") or [])[:limit]:
        title = _text(item.get("caseName"))
        if not title:
            continue
        citations = [c for c in item.get("citation") or [] if isinstance(c, str)]
        official = next((c for c in citations if re.search(r"\bU\.S\.\s", c)), citations[0] if citations else "")
        link = urljoin("https://www.courtlistener.com", item.get("absolute_url") or "")
        m = {
            "type": "case",
            "title": title,
            "report_citation": re.sub(r"\bU\.S\.", "US", official),
            "court": _text(item.get("court")),
            "date": (item.get("dateFiled") or "")[:10],
            "case_number": _text(item.get("docketNumber")),
            "jurisdiction": "US",
            "url": link,
        }
        out.append(candidate(m, "CourtListener", link, "search"))
    return out


# --------------------------------------------------------------------------- Web pages

MAX_PAGE_BYTES = 2_000_000


def assert_public_host(host: str) -> None:
    """Refuse URLs that point at this machine or a private network (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError) as exc:
        raise ProviderError("the address could not be resolved") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise ProviderError("that address is not publicly reachable")


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            key = (a.get("name") or a.get("property") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, []).append(a["content"].strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def parse_page(markup: str, url: str) -> dict:
    """Bibliographic metadata declared by a web page (Highwire, Dublin Core, Open Graph tags)."""
    parser = _MetaParser()
    try:
        parser.feed(markup)
    except Exception:  # malformed markup: keep whatever was read
        pass
    meta = parser.meta

    def first(*names: str) -> str:
        for name in names:
            if meta.get(name):
                return _text(meta[name][0])
        return ""

    authors = meta.get("citation_author") or meta.get("dc.creator") or meta.get("author") or []
    published = first("citation_publication_date", "citation_date", "dc.date", "article:published_time")
    iso = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", published)
    m: dict[str, Any] = {
        "title": first("citation_title", "dc.title", "og:title") or _text(parser.title),
        "authors": [parse_name(_text(a)) for a in authors if _text(a)],
        "url": url,
        "accessed": date.today().isoformat(),
        "doi": re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", first("citation_doi", "dc.identifier.doi"), flags=re.I),
    }
    if iso:
        m["date"] = f"{iso.group(1)}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}"
    m["year"] = _year(published)
    if first("citation_journal_title"):
        first_page, last_page = first("citation_firstpage"), first("citation_lastpage")
        m.update(
            type="article",
            journal=first("citation_journal_title"),
            volume=first("citation_volume"),
            issue=first("citation_issue"),
            pages=f"{first_page}-{last_page}" if first_page and last_page else first_page,
        )
    else:
        m.update(type="website", website=first("og:site_name", "application-name"))
    return m


async def fetch_page(client: httpx.AsyncClient, url: str) -> dict:
    """Download a page (public hosts only, bounded size and redirects) and read its metadata."""
    for _ in range(5):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ProviderError("only http and https addresses are supported")
        assert_public_host(parts.hostname)
        try:
            async with client.stream("GET", url, headers={"Accept": "text/html,application/xhtml+xml"}) as response:
                if response.is_redirect and response.headers.get("location"):
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise ProviderError(f"the page returned HTTP {response.status_code}")
                if "html" not in response.headers.get("content-type", "html"):
                    raise ProviderError("the address is not a web page")
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_PAGE_BYTES:
                        break
                encoding = response.encoding or "utf-8"
        except httpx.HTTPError as exc:
            raise ProviderError(f"request failed ({type(exc).__name__})") from exc
        return parse_page(body.decode(encoding, errors="replace"), url)
    raise ProviderError("too many redirects")
