"""APA 7th edition formatter.

Titles are printed with the capitalisation stored in the metadata. APA asks for
sentence case, but converting automatically would corrupt proper nouns, so the
user controls the casing through the title field.
"""
from __future__ import annotations

import re

from .common import (
    I,
    Rich,
    doi_url,
    edition_number,
    end,
    family_of,
    format_date,
    g,
    initials,
    join,
    normalise_v,
    ordinal,
    page_range,
    people,
    report_has_year,
    year_of,
)

LABELS = {
    "full": "Reference entry",
    "footnote": "In-text citation (parenthetical)",
    "short": "In-text citation (narrative)",
    "bibliography": "Reference list entry",
}


def _name(p: dict) -> str:
    if p.get("literal"):
        return p["literal"].strip()
    family, given = (p.get("family") or "").strip(), (p.get("given") or "").strip()
    inits = initials(given, dot=".", sep=" ")
    return f"{family}, {inits}" if inits else family


def _names(ppl: list[dict], inverted: bool = True) -> str:
    if inverted:
        names = [_name(p) for p in ppl]
    else:  # editors inside "In A. Editor (Ed.)"
        names = [p.get("literal") or f"{initials(p.get('given') or '', dot='.', sep=' ')} {p.get('family') or ''}".strip() for p in ppl]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}" if inverted else f"{names[0]} & {names[1]}"
    if len(names) > 20:
        return ", ".join(names[:19]) + ", . . . " + names[-1]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def _stop(text: str) -> str:
    return text if text.endswith((".", "?", "!")) else text + "."


def _link(m: dict) -> str:
    return doi_url(m) or g(m, "url")


def _edition(m: dict) -> str:
    n = edition_number(m)
    if n is None:
        raw = g(m, "edition")
        return f"{raw} ed." if raw and not re.search(r"\bed\b|edition", raw, re.I) else raw
    return "" if n == 1 else f"{ordinal(n)} ed."


def _legal(m: dict) -> Rich:
    kind = m.get("type")
    if kind == "case":
        name = normalise_v(g(m, "title"), dotted=True)
        cite = g(m, "neutral_citation") or re.sub(r"(?<=\d) US (?=\d)", " U.S. ", g(m, "report_citation"))
        out = join(", ", [name, cite or g(m, "case_number")])
        tail = [] if (g(m, "neutral_citation") or re.search(r"\d+ U\.S\. \d+", cite)) else [g(m, "court")]
        if not report_has_year(cite):
            tail.append(year_of(m) if cite else format_date(g(m, "date"), "apa_long") or year_of(m))
        tail = [x for x in tail if x]
        if tail:
            out += f" ({' '.join(tail)})"
        return join(". ", [end(out), g(m, "url")])
    if kind == "treaty":
        out = join(", ", [g(m, "title"), format_date(g(m, "adopted_date"), "apa_long"), g(m, "treaty_series")])
        return join(". ", [end(out), g(m, "url")])
    title, year = g(m, "title"), g(m, "year")
    out = Rich(title)
    if year and year not in title:
        out += f" {year}"
    out = join(", ", [out, g(m, "number")])
    if g(m, "jurisdiction"):
        out += f" ({g(m, 'jurisdiction')})"
    return join(". ", [end(out), g(m, "url")])


def _reference(m: dict) -> Rich:
    kind = m.get("type")
    if kind in ("case", "treaty", "legislation"):
        return _legal(m)

    authors, editors = people(m, "authors"), people(m, "editors")
    title = g(m, "title")
    year = year_of(m)
    date = f"({format_date(g(m, 'date'), 'apa') if kind == 'website' and g(m, 'date') else year or 'n.d.'})."

    if authors:
        lead = Rich(_stop(_names(authors)))
    elif editors and kind in ("book", "report"):
        lead = Rich(f"{_names(editors)} ({'Eds.' if len(editors) > 1 else 'Ed.'}).")
    else:
        lead = Rich()

    if kind == "article":
        title_part = Rich(_stop(title)) if title else Rich()
        ref = I(g(m, "journal"))
        if g(m, "volume"):
            ref = join(", ", [ref, I(g(m, "volume"))])
            if g(m, "issue"):
                ref += f"({g(m, 'issue')})"
        ref = end(join(", ", [ref, page_range(m)]))
        parts = [lead, date, title_part, ref] if lead else [title_part, date, ref]
        return join(" ", parts + [_link(m)])

    if kind == "chapter":
        title_part = Rich(_stop(title)) if title else Rich()
        container = I(g(m, "container_title"))
        detail = ", ".join(x for x in [_edition(m), f"pp. {page_range(m)}" if page_range(m) else ""] if x)
        if detail:
            container += f" ({detail})"
        if editors:
            container = Rich(f"{_names(editors, inverted=False)} ({'Eds.' if len(editors) > 1 else 'Ed.'}), ") + container
        in_part = end("In " + container) if g(m, "container_title") else Rich()
        publisher = _stop(g(m, "publisher")) if g(m, "publisher") else ""
        parts = [lead, date, title_part] if lead else [title_part, date]
        return join(" ", parts + [in_part, publisher, _link(m)])

    # book, report, thesis, website: italic title
    title_part = I(title)
    if kind == "book" and _edition(m):
        title_part += f" ({_edition(m)})"
    if kind == "report" and g(m, "number"):
        title_part += f" ({g(m, 'number')})"
    if kind == "thesis":
        bracket = ", ".join(x for x in [g(m, "thesis_type") or "Thesis", g(m, "institution")] if x)
        title_part += f" [{bracket}]"
    title_part = end(title_part)
    publisher = g(m, "website") if kind == "website" else "" if kind == "thesis" else g(m, "publisher")
    if publisher and authors and publisher == (authors[0].get("literal") or ""):
        publisher = ""  # APA: omit the publisher when it is the same as the author
    parts = [lead, date, title_part] if lead else [title_part, date]
    return join(" ", parts + [_stop(publisher) if publisher else "", _link(m)])


def _in_text_lead(m: dict) -> Rich:
    kind = m.get("type")
    if kind == "case":
        return I(normalise_v(g(m, "title"), dotted=True))
    if kind in ("treaty", "legislation"):
        return Rich(g(m, "short_title") or g(m, "title"))
    ppl = people(m, "authors") or (people(m, "editors") if kind in ("book", "report") else [])
    if ppl:
        names = [family_of(p) for p in ppl]
        if len(names) == 1:
            return Rich(names[0])
        if len(names) == 2:
            return Rich(f"{names[0]} & {names[1]}")
        return Rich(f"{names[0]} et al.")
    title = g(m, "title")
    return I(title) if kind in ("book", "report", "thesis", "website") else Rich(f"“{title}”")


def _pin_text(pin: dict | None) -> str:
    if not pin or not str(pin.get("value") or "").strip():
        return ""
    kind, value = pin.get("kind") or "page", str(pin["value"]).strip()
    multiple = bool(re.search(r"[-–,]| and ", value))
    prefix = {
        "page": "pp." if multiple else "p.",
        "para": "paras." if multiple else "para.",
        "article": "arts." if multiple else "art.",
        "section": "§§" if multiple else "§",
    }[kind]
    return f"{prefix} {value}"


def _year_in_text(m: dict) -> str:
    year = year_of(m)
    if year:
        return year
    if m.get("type") == "legislation":
        match = re.search(r"\b(\d{4})\b", g(m, "title"))
        if match:
            return ""  # the year is already part of the title
    return "" if m.get("type") in ("case", "treaty", "legislation") else "n.d."


def format(m: dict, pin: dict | None = None) -> dict[str, Rich]:
    reference = _reference(m)
    lead, year, pin_text = _in_text_lead(m), _year_in_text(m), _pin_text(pin)
    parenthetical = "(" + join(", ", [lead, year, pin_text]) + ")"
    narrative = lead + (f" ({', '.join(x for x in [year, pin_text] if x)})" if year or pin_text else "")
    return {
        "full": reference,
        "footnote": parenthetical,
        "short": narrative,
        "bibliography": reference,
    }
