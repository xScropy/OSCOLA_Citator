"""End-to-end API tests covering the MVP acceptance criteria."""
import io
import json

BOOK = {"type": "book", "title": "Modern Treaty Law and Practice", "authors": [{"given": "Anthony", "family": "Aust"}], "publisher": "Cambridge University Press", "year": "2013", "isbn": "9780198864473", "edition": "3"}
SOURCE = {"name": "Open Library", "url": "https://openlibrary.org/isbn/9780198864473", "reliable": True}
DONOGHUE = {"type": "case", "title": "Donoghue v Stevenson", "report_citation": "[1932] AC 562", "court": "HL", "year": "1932"}
VCLT = {"type": "treaty", "title": "Vienna Convention on the Law of Treaties", "adopted_date": "1969-05-23", "entry_into_force_date": "1980-01-27", "treaty_series": "1155 UNTS 331"}


def save(client, metadata, **extra):
    response = client.post("/api/references", json={"metadata": metadata, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_is_required_and_libraries_are_private(client):
    assert client.get("/api/references").status_code == 401
    assert client.post("/api/identify", json={"query": "Donoghue v Stevenson"}).status_code == 401
    a = client.post("/api/auth/register", json={"email": "a@example.org", "password": "password-a"}).json()["token"]
    b = client.post("/api/auth/register", json={"email": "b@example.org", "password": "password-b"}).json()["token"]
    ref = client.post("/api/references", json={"metadata": BOOK}, headers={"Authorization": f"Bearer {a}"}).json()
    other = {"Authorization": f"Bearer {b}"}
    assert client.get(f"/api/references/{ref['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/references/{ref['id']}", headers=other).status_code == 404
    assert client.get("/api/references", headers=other).json()["items"] == []
    assert client.post("/api/auth/register", json={"email": "A@example.org", "password": "password-a"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "a@example.org", "password": "wrong-password"}).status_code == 401


def test_cite_preview_regenerates_and_switches_style(auth):
    body = {"metadata": BOOK, "retrieved": BOOK, "source": SOURCE, "style": "oscola", "pinpoint": {"kind": "page", "value": "45"}}
    oscola = auth.post("/api/cite", json=body).json()
    assert oscola["citations"]["forms"]["footnote"]["text"] == "Anthony Aust, Modern Treaty Law and Practice (3rd edn, CUP 2013) 45."
    assert oscola["verification"]["status"] == "verified"
    apa = auth.post("/api/cite", json={**body, "style": "apa"}).json()
    assert apa["citations"]["forms"]["full"]["text"] == "Aust, A. (2013). Modern Treaty Law and Practice (3rd ed.). Cambridge University Press."
    edited = auth.post("/api/cite", json={**body, "metadata": {**BOOK, "year": "2014"}}).json()
    assert "2014" in edited["citations"]["forms"]["full"]["text"]
    assert edited["verification"]["status"] == "partially_verified"
    assert {"field": "year", "label": "Year", "state": "edited"} in edited["verification"]["checks"]


def test_verification_statuses(auth):
    manual = save(auth, {"type": "book", "title": "The Law of Treaties"})
    assert manual["verification"]["status"] == "needs_review"
    assert manual["verification"]["missing"]["required"] == ["Author or Editor", "Publisher", "Year"]
    assert manual["citations"]["forms"]["full"]["text"] == "The Law of Treaties"
    verified = save(auth, BOOK, retrieved=BOOK, source=SOURCE)
    assert verified["verification"]["status"] == "verified"
    assert verified["verification"]["source"]["name"] == "Open Library"
    assert "legal authority" in verified["verification"]["disclaimer"]
    confirmed = auth.patch(f"/api/references/{manual['id']}", json={"user_confirmed": True}).json()
    assert confirmed["verification"]["status"] == "user_confirmed"
    # editing metadata afterwards withdraws the confirmation
    again = auth.patch(f"/api/references/{manual['id']}", json={"metadata": {"type": "book", "title": "The Law of Treaties", "year": "1961"}}).json()
    assert again["verification"]["status"] == "needs_review"


def test_library_search_filter_sort(auth):
    save(auth, BOOK, tags=["Treaties", "treaties", "Interpretation"], notes="Supports the good-faith argument.", favorite=True)
    save(auth, DONOGHUE, tags=["Negligence"])
    save(auth, VCLT, style="bluebook")
    everything = auth.get("/api/references").json()
    assert everything["total"] == 3 and everything["tags"] == ["Interpretation", "Negligence", "Treaties"]
    titles = lambda q: [i["metadata"]["title"] for i in auth.get(f"/api/references?{q}").json()["items"]]  # noqa: E731
    assert titles("q=aust") == ["Modern Treaty Law and Practice"]
    assert titles("q=good-faith") == ["Modern Treaty Law and Practice"]
    assert titles("type=case") == ["Donoghue v Stevenson"]
    assert set(titles("category=legal")) == {"Donoghue v Stevenson", "Vienna Convention on the Law of Treaties"}
    assert titles("tag=negligence") == ["Donoghue v Stevenson"]
    assert titles("favorite=true") == ["Modern Treaty Law and Practice"]
    assert titles("preferred_style=bluebook") == ["Vienna Convention on the Law of Treaties"]
    assert titles("sort=title") == ["Donoghue v Stevenson", "Modern Treaty Law and Practice", "Vienna Convention on the Law of Treaties"]
    assert titles("sort=date&order=asc")[0] == "Donoghue v Stevenson"
    assert auth.get("/api/references?style=apa").json()["items"][0]["citations"]["style"] == "apa"


def test_duplicates_are_detected_and_merged_only_on_request(auth):
    first = save(auth, DONOGHUE, tags=["Negligence"])
    # same case reached through a URL, with different punctuation in the name
    variant = {"type": "case", "title": "Donoghue v. Stevenson", "url": "https://www.bailii.org/uk/cases/UKHL/1932/100.html", "date": "1932-05-26"}
    conflict = auth.post("/api/references", json={"metadata": variant})
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["duplicates"][0]["id"] == first["id"] and detail["duplicates"][0]["reasons"] == ["Same title"]
    assert auth.get("/api/references").json()["total"] == 1  # nothing was merged or saved silently
    second = save(auth, variant, allow_duplicate=True, tags=["Duty of care"], notes="Neighbour principle at 580.")
    groups = auth.get("/api/references/duplicates").json()["groups"]
    assert len(groups) == 1 and {i["id"] for i in groups[0]["items"]} == {first["id"], second["id"]}
    merged = auth.post(f"/api/references/{first['id']}/merge", json={"source_id": second["id"]}).json()
    assert merged["metadata"]["report_citation"] == "[1932] AC 562" and merged["metadata"]["url"].endswith("100.html")
    assert merged["metadata"]["title"] == "Donoghue v Stevenson"
    assert merged["tags"] == ["Negligence", "Duty of care"] and "Neighbour" in merged["notes"]
    assert auth.get("/api/references").json()["total"] == 1
    assert auth.get("/api/references/duplicates").json()["groups"] == []
    # ISBN-10 and ISBN-13 of the same book
    save(auth, {"type": "book", "title": "Some Title", "isbn": "0198259468"})
    dup = auth.post("/api/references/duplicates", json={"metadata": {"type": "book", "title": "Another Title", "isbn": "978-0-19-825946-6"}}).json()
    assert dup["duplicates"][0]["reasons"] == ["Same ISBN"]
    # different editions (same title, different ISBN) are not flagged
    assert auth.post("/api/references/duplicates", json={"metadata": {"type": "book", "title": "Some Title", "isbn": "9780198864473"}}).json()["duplicates"] == []


def test_collections(auth):
    moot = auth.post("/api/collections", json={"name": "Moot Court 2026–2027", "kind": "moot"}).json()
    ref = save(auth, VCLT, collection_ids=[moot["id"]])
    other = save(auth, DONOGHUE)
    assert auth.get("/api/collections").json()[0]["count"] == 1
    assert auth.put(f"/api/collections/{moot['id']}/references/{other['id']}").json()["count"] == 2
    in_collection = auth.get(f"/api/references?collection_id={moot['id']}").json()
    assert in_collection["count"] == 2
    assert auth.delete(f"/api/collections/{moot['id']}/references/{ref['id']}").json()["count"] == 1
    assert auth.delete(f"/api/collections/{moot['id']}").status_code == 204
    assert auth.get("/api/references").json()["total"] == 2  # references survive
    assert auth.post("/api/references", json={"metadata": BOOK, "collection_ids": [9999]}).status_code == 404


def test_bibliography_and_list_of_authorities(auth):
    ids = [save(auth, m)["id"] for m in (BOOK, DONOGHUE, VCLT, {"type": "book", "title": "Administrative Law", "authors": ["Timothy Endicott"], "publisher": "Oxford University Press", "year": "2018"})]
    bib = auth.post("/api/bibliography", json={"reference_ids": ids, "style": "oscola"}).json()
    assert [s["heading"] for s in bib["sections"]] == ["Table of Cases", "Treaties and International Instruments", "Secondary Sources"]
    assert [e["text"] for e in bib["sections"][2]["entries"]] == [
        "Aust A, Modern Treaty Law and Practice (3rd edn, CUP 2013)",
        "Endicott T, Administrative Law (OUP 2018)",
    ]
    apa = auth.post("/api/bibliography", json={"reference_ids": ids, "style": "apa"}).json()
    assert apa["title"] == "References" and len(apa["sections"]) == 1 and len(apa["sections"][0]["entries"]) == 4
    loa = auth.post("/api/bibliography", json={"reference_ids": ids, "style": "oscola", "mode": "authorities"}).json()
    assert loa["title"] == "List of Authorities"
    assert [s["heading"] for s in loa["sections"]] == ["Treaties and International Instruments", "Cases and Judicial Decisions", "Books and Academic Publications"]
    custom = auth.post("/api/bibliography", json={"reference_ids": ids, "mode": "authorities", "categories": [{"heading": "International Law", "types": ["treaty", "case"]}]}).json()
    assert [(s["heading"], len(s["entries"])) for s in custom["sections"]] == [("International Law", 2), ("Other Authorities", 2)]
    assert bib["needs_attention"][0]["status"] == "needs_review"


def test_exports(auth):
    ids = [save(auth, m)["id"] for m in (BOOK, DONOGHUE, VCLT)]
    base = {"reference_ids": ids, "style": "oscola"}

    txt = auth.post("/api/export", json={**base, "format": "txt"})
    assert txt.status_code == 200 and "attachment" in txt.headers["content-disposition"]
    assert "Aust A, Modern Treaty Law and Practice (3rd edn, CUP 2013)" in txt.text and "Table of Cases" in txt.text

    docx = auth.post("/api/export", json={**base, "format": "docx"})
    from docx import Document
    document = Document(io.BytesIO(docx.content))
    paragraphs = {p.text: p for p in document.paragraphs}
    entry = paragraphs["Aust A, Modern Treaty Law and Practice (3rd edn, CUP 2013)"]
    assert [r.text for r in entry.runs if r.italic] == ["Modern Treaty Law and Practice"]

    pdf = auth.post("/api/export", json={**base, "format": "pdf"})
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 1500

    edited = {"heading": "Authorities", "entries": [{"html": "Edited <i>entry</i><script>alert(1)</script> &amp; more"}]}
    custom = auth.post("/api/export", json={**base, "format": "txt", "title": "My List", "sections": [edited]})
    assert "Edited entryalert(1) & more" in custom.text and custom.text.startswith("My List")

    bibtex = auth.post("/api/export", json={**base, "format": "bibtex"}).text
    assert "@book{Aust2013," in bibtex and "author = {Aust, Anthony}" in bibtex and "note = {[1932] AC 562, HL}" in bibtex

    ris = auth.post("/api/export", json={**base, "format": "ris"}).text
    assert "TY  - BOOK" in ris and "AU  - Aust, Anthony" in ris and "TY  - CASE" in ris and ris.count("ER  - ") == 3

    csl = json.loads(auth.post("/api/export", json={**base, "format": "csl-json"}).content)
    assert csl[0]["type"] == "book" and csl[0]["issued"] == {"date-parts": [[2013]]}
    assert csl[2]["type"] == "treaty" and csl[2]["issued"] == {"date-parts": [[1969, 5, 23]]}

    csv_text = auth.post("/api/export", json={**base, "format": "csv"}).content.decode("utf-8-sig")
    assert csv_text.splitlines()[0].startswith("type,authors") and "Needs Review" in csv_text

    assert auth.post("/api/export", json={**base, "format": "exe"}).status_code == 422
    assert auth.post("/api/export", json={"reference_ids": [99999], "format": "txt"}).status_code == 404


def test_stats_settings_and_account_deletion(auth):
    save(auth, BOOK, retrieved=BOOK, source=SOURCE, favorite=True)
    save(auth, DONOGHUE)
    stats = auth.get("/api/stats").json()
    assert (stats["total"], stats["legal"], stats["academic"]) == (2, 1, 1)
    assert stats["verification"]["verified"] == 1 and stats["verification"]["needs_review"] == 1
    assert len(stats["favorites"]) == 1 and len(stats["recent"]) == 2
    assert auth.patch("/api/auth/me", json={"default_style": "apa"}).json()["default_style"] == "apa"
    assert auth.patch("/api/auth/me", json={"default_style": "nope"}).status_code == 422
    assert auth.post("/api/auth/me/delete", json={"password": "wrong password"}).status_code == 403
    assert auth.post("/api/auth/me/delete", json={"password": "correct horse"}).status_code == 204
    assert auth.get("/api/auth/me").status_code == 401
    assert auth.post("/api/auth/login", json={"email": "student@example.org", "password": "correct horse"}).status_code == 401
