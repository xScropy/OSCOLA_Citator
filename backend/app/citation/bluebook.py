"""Bluebook (21st edn, law-review footnote typeface) formatter.

Covers the common source categories. Bluebook abbreviation tables (journal and
court names, T6/T13) are not applied automatically: names are printed as
stored, so the user can abbreviate them in the metadata.
"""
from __future__ import annotations

import re

from .common import (
    I,
    SC,
    Rich,
    case_short_name,
    doi_url,
    edition_text,
    end,
    family_of,
    first_page,
    format_date,
    g,
    join,
    normalise_v,
    people,
    report_has_year,
    year_of,
)

LABELS = {
    "full": "Full citation",
    "footnote": "Footnote",
    "short": "Short form",
    "bibliography": "Bibliography entry",
}


def _name(p: dict) -> str:
    if p.get("literal"):
        return p["literal"].strip()
    return f"{(p.get('given') or '').strip()} {(p.get('family') or '').strip()}".strip()


def _names(ppl: list[dict]) -> str:
    names = [_name(p) for p in ppl]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} et al."


def _dot_reporter(report: str) -> str:
    report = re.sub(r"(?<=\d) US (?=\d)", " U.S. ", report)
    return re.sub(r"(?<=\d) UNTS (?=\d|[IVXL])", " U.N.T.S. ", report)


def _pin(pin: dict | None) -> tuple[str, str]:
    if not pin:
        return ("", "")
    return (pin.get("kind") or "page", str(pin.get("value") or "").strip())


def _pin_text(kind: str, value: str) -> str:
    multiple = bool(re.search(r"[-–,]| and ", value))
    if kind == "page":
        return value
    if kind == "para":
        return f"{'¶¶' if multiple else '¶'} {value}"
    if kind == "section":
        return f"{'§§' if multiple else '§'} {value}"
    return f"{'arts.' if multiple else 'art.'} {value}"


def _case(m: dict, pin: dict | None) -> Rich:
    name = normalise_v(g(m, "title"), dotted=True)
    neutral, report = g(m, "neutral_citation"), _dot_reporter(g(m, "report_citation"))
    court, year = g(m, "court"), year_of(m)
    kind, value = _pin(pin)
    cite = neutral or report
    if cite:
        out = join(", ", [name, cite])
        if value:
            out += f", [{value}]" if kind == "para" and neutral else f", {_pin_text(kind, value)}"
        if neutral:
            return out
        tail = [] if re.search(r"\d+ U\.S\. \d+", report) else [court]
        if not report_has_year(report):
            tail.append(year)
        tail = [x for x in tail if x]
        return out + f" ({' '.join(tail)})" if tail else out
    out = join(", ", [name, g(m, "case_number")])
    if value:
        out += f", {_pin_text(kind, value)}"
    tail = " ".join(x for x in [court, format_date(g(m, "date"), "bluebook") or year] if x)
    return out + f" ({tail})" if tail else out


def _legislation(m: dict, pin: dict | None) -> Rich:
    title, year = g(m, "title"), g(m, "year")
    out = Rich(title)
    if year and year not in title:
        out += f" {year}"
    out = join(", ", [out, g(m, "number")])
    kind, value = _pin(pin)
    if value:
        out += f", {_pin_text('section' if kind == 'page' else kind, value)}"
    if g(m, "jurisdiction"):
        out += f" ({g(m, 'jurisdiction')})"
    return out


def _treaty(m: dict, pin: dict | None) -> Rich:
    out = Rich(g(m, "title"))
    kind, value = _pin(pin)
    if value:
        out += f" {_pin_text('article' if kind == 'page' else kind, value)}"
    return join(", ", [out, format_date(g(m, "adopted_date"), "bluebook"), _dot_reporter(g(m, "treaty_series"))])


def _secondary(m: dict, pin: dict | None) -> Rich:
    kind = m.get("type")
    authors, editors = people(m, "authors"), people(m, "editors")
    title, year = g(m, "title"), year_of(m)
    pin_kind, pin_value = _pin(pin)
    pin_text = _pin_text(pin_kind, pin_value) if pin_value else ""
    eds = f"{_names(editors)} {'eds.' if len(editors) > 1 else 'ed.'}" if editors else ""

    if kind == "article":
        volume, journal, first = g(m, "volume"), g(m, "journal"), first_page(m)
        ref = join(" ", [volume or (year if journal else ""), SC(journal), first])
        out = join(", ", [_names(authors), I(title), ref])
        if pin_text:
            out += f", {pin_text}"
        if volume and year:
            out += f" ({year})"
        if not first and doi_url(m):
            out = join(", ", [out, doi_url(m)])
        return out

    if kind == "chapter":
        ref = join(" ", [SC(g(m, "container_title")), first_page(m)])
        out = join(", ", [_names(authors), I(title)])
        if ref:
            out = join(", in ", [out, ref]) if out else "in " + ref
        if pin_text:
            out += f", {pin_text}" if first_page(m) else f" {pin_text}"
        inner = ", ".join(x for x in [eds, " ".join(x for x in [edition_text(m, "ed.", bluebook=True), year] if x)] if x)
        return out + f" ({inner})" if inner else out

    if kind == "thesis":
        out = join(", ", [_names(authors), title])
        if pin_text:
            out += f" {pin_text}"
        if year:
            out += f" ({year})"
        inner = ", ".join(x for x in [g(m, "thesis_type") or "thesis", g(m, "institution")] if x)
        return out + f" ({inner})"

    if kind == "website":
        out = join(", ", [_names(authors), I(title), SC(g(m, "website"))])
        date = format_date(g(m, "date"), "bluebook") or year
        if date:
            out += f" ({date})"
        out = join(", ", [out, g(m, "url")])
        if g(m, "accessed") and not date:
            out += f" (last visited {format_date(g(m, 'accessed'), 'bluebook')})"
        return out

    # book and report: author and title in small caps
    creators = _names(authors)
    out = join(", ", [SC(creators), SC(title)])
    if kind == "report" and g(m, "number"):
        out = join(", ", [out, g(m, "number")])
    if pin_text:
        out += f" {pin_text}"
    inner = ", ".join(x for x in [eds, " ".join(x for x in [edition_text(m, "ed.", bluebook=True), year] if x)] if x)
    return out + f" ({inner})" if inner else out


def _body(m: dict, pin: dict | None) -> Rich:
    kind = m.get("type")
    if kind == "case":
        return _case(m, pin)
    if kind == "legislation":
        return _legislation(m, pin)
    if kind == "treaty":
        return _treaty(m, pin)
    return _secondary(m, pin)


def _short(m: dict, pin: dict | None) -> Rich:
    kind = m.get("type")
    pin_kind, pin_value = _pin(pin)
    if kind == "legislation":
        return _legislation(m, pin)
    if kind == "case":
        out = I(case_short_name(normalise_v(g(m, "title"), dotted=True)))
        report = _dot_reporter(g(m, "report_citation"))
        if pin_value and pin_kind == "page":
            match = re.match(r"^(.*\S)\s+\d+$", report)
            out += f", {match.group(1)} at {pin_value}" if match and not g(m, "neutral_citation") else f", at {pin_value}"
        elif pin_value:
            out += f", {_pin_text(pin_kind, pin_value)}"
        return out
    if kind == "treaty":
        out = Rich(g(m, "short_title") or g(m, "title")) + ", "
        out += I("supra") + " note #"
        if pin_value:
            out += f", {_pin_text('article' if pin_kind == 'page' else pin_kind, pin_value)}"
        return out
    ppl = people(m, "authors") or people(m, "editors")
    if ppl:
        names = [family_of(p) for p in ppl]
        lead_text = names[0] if len(names) == 1 else f"{names[0]} & {names[1]}" if len(names) == 2 else f"{names[0]} et al."
    else:
        lead_text = g(m, "title")
    lead = SC(lead_text) if kind in ("book", "report") else Rich(lead_text)
    out = lead + ", " + I("supra") + " note #"
    if pin_value:
        out += f", at {pin_value}" if pin_kind == "page" else f", {_pin_text(pin_kind, pin_value)}"
    return out


def format(m: dict, pin: dict | None = None) -> dict[str, Rich]:
    full = _body(m, None)
    return {
        "full": full,
        "footnote": end(_body(m, pin)),
        "short": end(_short(m, pin)),
        "bibliography": end(full),
    }
