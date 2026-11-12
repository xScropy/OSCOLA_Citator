# CiteRight

Legal citation and authority management. Enter a case name, ISBN, DOI, title or URL;
CiteRight identifies the source, formats it in **OSCOLA**, **Bluebook** or **APA 7th**,
tells you how far the details are verified, and keeps it in a personal research library
from which you can generate bibliographies and moot-court Lists of Authorities.

> Stop formatting citations manually. Focus on the quality of your legal research.

This repository implements the MVP (1.0) of the product requirements document.

## What it does

| Area | Details |
| --- | --- |
| Source identification | DOI (Crossref), ISBN (Open Library, Google Books), title search (Crossref, Google Books), case name (Find Case Law – The National Archives, CourtListener), URL (metadata published by the page), plus a bundled list of landmark cases, treaties and UK statutes. Several matches are shown for you to choose from. |
| Citation engine | Deterministic formatters for OSCOLA, Bluebook and APA covering cases, legislation, treaties, books, chapters, journal articles, reports, theses and websites. Each source gets a full citation, footnote (with pinpoint), short/subsequent form and bibliography entry. |
| No fabrication | A detail the source record does not give is left out of the citation and listed as missing. Nothing is guessed. |
| Verification | Every reference is Verified, Partially Verified, Needs Review or User Confirmed, with a field-by-field comparison against the record that was retrieved and a link to where it came from. |
| Library | Search, filter (type, tag, collection, verification, style, favourites), sort, notes, tags, favourites and collections. |
| Duplicates | Detected on save and across the library (same DOI, ISBN, URL, neutral or report citation, or title). Merging only happens when you ask for it. |
| Bibliography | Grouped and ordered per style; List of Authorities with customisable categories; editable before export. |
| Document check | Upload a PDF or Word (.docx) document. CiteRight reads the footnotes, recognises the authorities cited (full citations, short forms, cross-references and ibid), records every page and pinpoint, suggests corrections you can accept, reject or edit, optionally shortens every citation after the first, and produces a Table of Authorities with page numbers. Word uploads can be downloaded with the corrected footnotes written back in. Extracted authorities can be added to the library. Uploads are processed in memory and not stored. |
| Export | DOCX, PDF, TXT, BibTeX, RIS, CSV, CSL-JSON, and copy to clipboard with italics. |

## Windows app

Download `CiteRight.exe` from the [latest release](../../releases/latest) and double-click
it. A window opens showing the local address and the app opens in your browser; close the
window to quit. Nothing else needs installing. Your library is stored on your computer in
`%APPDATA%\CiteRight`.

The file is not code-signed, so Windows may show "Windows protected your PC": choose
**More info**, then **Run anyway**.

The executable is built by the `Release` workflow (`.github/workflows/release.yml`), from
`backend/desktop.py` and `backend/citeright.spec`.

## Running it locally

Requirements: Python 3.11+ and Node.js 20+.

```bash
# 1. API (http://127.0.0.1:8000)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn app.main:app --reload

# 2. Web app (http://localhost:3000), in a second terminal
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>, create an account and start citing. The web app proxies
`/api/*` to the backend (`BACKEND_URL`, default `http://127.0.0.1:8000`), so API keys and
the database are never exposed to the browser.

Configuration is by environment variable: see `backend/.env.example` and
`frontend/.env.example`. The backend uses SQLite out of the box; set `DATABASE_URL` to a
PostgreSQL or Supabase connection string for production. Tables are created on start-up.

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The suite covers the formatters against style-guide examples, source identification
against provider-shaped responses (no network needed), and the API end to end.

## Project layout

```
backend/app/
  citation/        citation engine: common rules + oscola.py, bluebook.py, apa.py
  identify/        input classification, metadata providers, identification service
  data/            bundled landmark authorities
  verification.py  verification statuses and field checks
  duplicates.py    duplicate detection and grouping
  bibliography.py  bibliography / List of Authorities builder
  export.py        DOCX, PDF, TXT, BibTeX, RIS, CSV, CSL-JSON
  documents/       document check: footnote extraction, citation parser, analysis, Word rewriter
  routers/         auth, library, citations (identify, cite, export), documents (upload and analyse)
frontend/
  app/             Next.js pages: dashboard, generator, library, collections, bibliography, settings
  components/      shell, reference editor, metadata form, shared UI
```

## Things to know

- **Verification is bibliographic only.** It does not establish the legal authority,
  precedential value or continuing validity of a judgment.
- **Abbreviations are yours to apply.** Journal and court names are printed as stored;
  OSCOLA and Bluebook abbreviation tables are not applied automatically (except
  OUP/CUP in OSCOLA and `U.S.`/`U.N.T.S.` in Bluebook).
- **APA title case.** APA asks for sentence-case titles. Titles are printed as stored,
  because automatic conversion would damage proper nouns.
- **Web pages are a weak source.** A reference built from a page's own metadata is never
  more than Partially Verified until you confirm it.
- **Authentication** is email and password with signed tokens, built into the API, so
  the app runs without any external service. It can be replaced by Supabase Auth later.

- **Document check reads footnotes, conservatively.** Text is only treated as a citation
  when all of it fits a known citation shape; prose is left alone. It is tuned to OSCOLA,
  with partial Bluebook support. Page numbers for Word files come from the layout Word
  last saved, so confirm them against the final PDF; scanned PDFs need OCR first.
- **PDF reading uses PyMuPDF**, which is licensed under the AGPL (or a commercial licence
  from Artifex). Check that this suits how you plan to distribute CiteRight.

## Not in the MVP

Identifying a single source from an uploaded PDF, AI-assisted identification, Chicago and MLA styles,
HUDOC / EUR-Lex / UN Treaty Collection / OpenAlex integrations, browser extension,
collaboration, Word integration and memorial auditing (PRD roadmap 1.5–3.0).
