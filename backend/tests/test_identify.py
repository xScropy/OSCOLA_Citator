"""Source identification against recorded-shape provider responses (no network)."""
import asyncio

import httpx
import pytest

from app.identify import providers, service
from app.identify.detect import classify, looks_like_case

CROSSREF_WORK = {
    "type": "journal-article",
    "title": ["The Rule of Law and <i>Its</i> Virtue"],
    "author": [{"given": "Joseph", "family": "Raz"}],
    "container-title": ["Law Quarterly Review"],
    "volume": "93",
    "issue": "2",
    "page": "195-211",
    "published-print": {"date-parts": [[1977, 4]]},
    "DOI": "10.1000/xyz",
    "publisher": "Sweet & Maxwell",
}
OPENLIBRARY = {
    "ISBN:9780198864473": {
        "title": "Modern Treaty Law and Practice",
        "authors": [{"name": "Anthony Aust"}],
        "publishers": [{"name": "Cambridge University Press"}],
        "publish_date": "March 2013",
        "url": "https://openlibrary.org/books/OL1M",
    }
}
TNA_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:tna="https://caselaw.nationalarchives.gov.uk">
  <entry>
    <title>R (Miller) v The Prime Minister</title>
    <link href="https://caselaw.nationalarchives.gov.uk/uksc/2019/41"/>
    <link href="https://caselaw.nationalarchives.gov.uk/uksc/2019/41/data.xml" type="application/akn+xml"/>
    <published>2019-09-24T00:00:00+00:00</published>
    <author><name>United Kingdom Supreme Court</name></author>
  </entry>
</feed>"""
PAGE = """<html><head><title>Fallback</title>
<meta property="og:title" content="Virtual Friend Fires Employee">
<meta name="author" content="Sarah Cole">
<meta property="og:site_name" content="Naked Law">
<meta property="article:published_time" content="2009-05-01T10:00:00Z">
</head><body></body></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.startswith("https://api.crossref.org/works/10.1000/xyz"):
        return httpx.Response(200, json={"message": CROSSREF_WORK})
    if url.startswith("https://api.crossref.org/works/"):
        return httpx.Response(404)
    if url.startswith("https://api.crossref.org/works?"):
        return httpx.Response(200, json={"message": {"items": [CROSSREF_WORK]}})
    if "openlibrary.org/api/books" in url:
        return httpx.Response(200, json=OPENLIBRARY if "9780198864473" in url else {})
    if "googleapis.com/books" in url:
        return httpx.Response(503)
    if "caselaw.nationalarchives.gov.uk/atom.xml" in url:
        return httpx.Response(200, content=TNA_FEED)
    if "courtlistener.com" in url:
        return httpx.Response(200, json={"results": [{"caseName": "Brown v. Board of Education", "citation": ["74 S. Ct. 686", "347 U.S. 483"], "court": "Supreme Court of the United States", "dateFiled": "1954-05-17", "absolute_url": "/opinion/105221/brown-v-board-of-education/"}]})
    if url == "https://blog.example.org/post":
        return httpx.Response(200, text=PAGE, headers={"content-type": "text/html; charset=utf-8"})
    return httpx.Response(404)


def run(query, type_hint=None):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service.identify(query, type_hint, client=client)
    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _public_hosts(monkeypatch):
    monkeypatch.setattr(providers, "assert_public_host", lambda host: None)


def test_classify():
    assert classify("9780198864473") == ("isbn", "9780198864473")
    assert classify("ISBN 978-0-19-886447-3") == ("isbn", "9780198864473")
    assert classify("0-19-825946-9")[0] == "isbn"
    assert classify("12345")[0] == "text"
    assert classify("10.1093/oso/9780198864473.001.0001") == ("doi", "10.1093/oso/9780198864473.001.0001")
    assert classify("https://doi.org/10.1000/xyz") == ("doi", "10.1000/xyz")
    assert classify("https://www.bailii.org/uk/cases/UKHL/1932/100.html")[0] == "url"
    assert classify("Donoghue v Stevenson") == ("text", "Donoghue v Stevenson")
    assert looks_like_case("Brown v. Board of Education") and not looks_like_case("The Law of Treaties")


def test_doi_lookup():
    result = run("10.1000/xyz")
    assert result["input_kind"] == "doi"
    [c] = result["candidates"]
    assert c["match"] == "identifier" and c["source"]["name"] == "Crossref" and c["source"]["reliable"]
    m = c["metadata"]
    assert m["type"] == "article" and m["title"] == "The Rule of Law and Its Virtue"
    assert m["authors"] == [{"family": "Raz", "given": "Joseph"}]
    assert (m["journal"], m["volume"], m["year"], m["pages"]) == ("Law Quarterly Review", "93", "1977", "195-211")
    assert "publisher" not in m


def test_unknown_doi_asks_for_more_information():
    result = run("10.9999/missing")
    assert result["candidates"] == [] and "no record" in result["message"]


def test_isbn_lookup_reports_failed_provider_without_inventing_data():
    result = run("9780198864473")
    [c] = result["candidates"]
    assert c["metadata"] == {
        "type": "book", "title": "Modern Treaty Law and Practice", "authors": [{"given": "Anthony", "family": "Aust"}],
        "publisher": "Cambridge University Press", "year": "2013", "isbn": "9780198864473",
    }
    assert any("Google Books" in w for w in result["warnings"])
    assert any("check digit" in w for w in result["warnings"])  # the number is looked up, but flagged


def test_case_search_by_name_uses_curated_list_and_official_sources():
    result = run("Donoghue v Stevenson")
    first = result["candidates"][0]
    assert first["match"] == "exact_title"
    assert first["metadata"]["report_citation"] == "[1932] AC 562"
    names = {c["source"]["name"] for c in result["candidates"]}
    assert {"Find Case Law (The National Archives)", "CourtListener"} <= names
    tna = next(c for c in result["candidates"] if "National Archives" in c["source"]["name"])
    assert tna["metadata"]["neutral_citation"] == "[2019] UKSC 41" and tna["metadata"]["date"] == "2019-09-24"
    us = next(c for c in result["candidates"] if c["source"]["name"] == "CourtListener")
    assert us["metadata"]["report_citation"] == "347 US 483"


def test_treaty_alias_and_title_search():
    assert run("VCLT")["candidates"][0]["metadata"]["treaty_series"] == "1155 UNTS 331"
    result = run("Vienna Convention on the Law of Treaties")
    assert result["candidates"][0]["metadata"]["type"] == "treaty"
    assert result["candidates"][0]["match"] == "exact_title"


def test_url_metadata_is_marked_unreliable():
    result = run("https://blog.example.org/post")
    [c] = result["candidates"]
    assert c["source"]["reliable"] is False
    m = c["metadata"]
    assert (m["type"], m["title"], m["website"], m["date"]) == ("website", "Virtual Friend Fires Employee", "Naked Law", "2009-05-01")
    assert m["accessed"]


def test_private_addresses_are_refused(monkeypatch):
    monkeypatch.undo()
    for url in ("http://127.0.0.1:8000/admin", "http://localhost/", "http://169.254.169.254/latest/meta-data"):
        result = run(url)
        assert result["candidates"] == [] and result["warnings"], url


def test_neutral_citation_from_uri():
    assert providers.neutral_from_tna_uri("https://caselaw.nationalarchives.gov.uk/ewca/civ/2020/123") == "[2020] EWCA Civ 123"
    assert providers.neutral_from_tna_uri("ewhc/ch/2021/7") == "[2021] EWHC 7 (Ch)"
    assert providers.neutral_from_tna_uri("https://example.org/other") == ""
