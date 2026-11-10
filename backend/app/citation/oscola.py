"""OSCOLA (4th edn) formatter."""
from __future__ import annotations

import re

from .common import (
    I,
    Rich,
    case_short_name,
    doi_url,
    edition_text,
    end,
    family_of,
    first_page,
    format_date,
    g,
    initials,
    join,
    normalise_v,
    people,
    report_has_year,
    year_of,
)

LABELS = {
    "full": "Full citation",
    "footnote": "Footnote",
    "short": "Subsequent citation",
    "bibliography": "Bibliography entry",
}

_PUBLISHERS = {"oxford university press": "OUP", "cambridge university press": "CUP"}
_UK = {"uk", "united kingdom", "gb", "great britain", "england and wales", "england"}


def _name(p: dict, bib: bool) -> str:
    if p.get("literal"):
        return p["literal"].strip()
    given, family = (p.get("given") or "").strip(), (p.get("family") or "").strip()
    if bib:
        return f"{family} {initials(given)}".strip()
    tokens = [t for t in re.split(r"[\s.]+", given) if t]
    if tokens and all(len(t) == 1 for t in tokens):
        given = "".join(tokens)  # 'H. L. A.' -> 'HLA'
    else:
        given = given.replace(".", "")
    return f"{given} {family}".strip()


def _names(ppl: list[dict], bib: bool) -> str:
    names = [_name(p, bib) for p in ppl]
    if not names:
        return ""
    if len(names) > 3:
        return f"{names[0]} and others"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _creators(m: dict, bib: bool) -> str:
    authors = people(m, "authors")
    if authors:
        return _names(authors, bib)
    editors = people(m, "editors")
    if editors and m.get("type") != "chapter":
        return _names(editors, bib) + (" (eds)" if len(editors) > 1 else " (ed)")
    return ""


def _publisher(m: dict) -> str:
    publisher = g(m, "publisher")
    return _PUBLISHERS.get(publisher.lower(), publisher)


def _pub_paren(m: dict, lead: str = "") -> str:
    inner = ", ".join(x for x in [lead, edition_text(m, "edn"), " ".join(x for x in [_publisher(m), year_of(m)] if x)] if x)
    return f"({inner})" if inner else ""


def _pin(pin: dict | None) -> tuple[str, str]:
    if not pin:
        return ("", "")
    return (pin.get("kind") or "page", str(pin.get("value") or "").strip())


def _statute_pin(kind: str, value: str) -> str:
    prefix = {"section": "s", "article": "art", "para": "para", "page": "p"}[kind]
    if re.search(r"[-–,]| and ", value):
        prefix = {"s": "ss", "art": "arts", "para": "paras", "p": "pp"}[prefix]
    return f"{prefix} {value}"


def _generic_pin(kind: str, value: str) -> str:
    return value if kind == "page" else _statute_pin(kind, value)


def _case(m: dict, pin: dict | None, bib: bool) -> Rich:
    title = normalise_v(g(m, "title"), dotted=False)
    name = Rich(title) if bib else I(title)
    neutral, report, court = g(m, "neutral_citation"), g(m, "report_citation"), g(m, "court")
    kind, value = _pin(pin)
    if neutral:
        out = join(" ", [name, join(", ", [neutral, report])])
        if value:
            out += f" [{value}]" if kind == "para" else f" {_generic_pin(kind, value)}"
        return out
    if report:
        out = join(" ", [name, report])
        us_report = bool(re.search(r"\d+ US \d+", report))
        tail = [] if us_report else [court]
        if not report_has_year(report):
            tail.append(year_of(m))
        tail = [x for x in tail if x]
        if tail:
            out += f" ({' '.join(tail)})"
        if value:
            out += f" [{value}]" if kind == "para" else f" {_generic_pin(kind, value)}"
        return out
    out = join(" ", [name, g(m, "case_number")])
    tail = ", ".join(x for x in [court, format_date(g(m, "date"), "oscola") or year_of(m)] if x)
    if tail:
        out += f" ({tail})"
    if value:
        out += f" para {value}" if kind == "para" else f" {_generic_pin(kind, value)}"
    return out


def _legislation(m: dict, pin: dict | None) -> Rich:
    title, year = g(m, "title"), g(m, "year")
    out = Rich(title)
    if year and year not in title:
        out += f" {year}"
    jurisdiction = g(m, "jurisdiction")
    if jurisdiction and jurisdiction.lower() not in _UK:
        out += f" ({jurisdiction})"
    kind, value = _pin(pin)
    if value:
        out += f", {_statute_pin(kind, value)}"
    return out


def _treaty(m: dict, pin: dict | None) -> Rich:
    dates = []
    if g(m, "adopted_date"):
        dates.append(f"adopted {format_date(g(m, 'adopted_date'), 'oscola')}")
    if g(m, "entry_into_force_date"):
        dates.append(f"entered into force {format_date(g(m, 'entry_into_force_date'), 'oscola')}")
    out = Rich(g(m, "title"))
    if dates:
        out += f" ({', '.join(dates)})"
    out = join(" ", [out, g(m, "treaty_series")])
    if g(m, "short_title"):
        out += f" ({g(m, 'short_title')})"
    kind, value = _pin(pin)
    if value:
        out += " " + _statute_pin("article" if kind == "page" else kind, value)
    return out


def _online(m: dict) -> str:
    url = g(m, "url") or doi_url(m)
    if not url:
        return ""
    out = f"<{url}>"
    if g(m, "accessed"):
        out += f" accessed {format_date(g(m, 'accessed'), 'oscola')}"
    return out


def _secondary(m: dict, pin: dict | None, bib: bool) -> Rich:
    kind = m.get("type")
    creators = _creators(m, bib)
    title = g(m, "title")
    pin_kind, pin_value = _pin(pin)
    pin_text = _generic_pin(pin_kind, pin_value) if pin_value else ""

    if kind == "article":
        year, volume, issue = year_of(m), g(m, "volume"), g(m, "issue")
        if volume:
            ref = " ".join(x for x in [f"({year})" if year else "", volume + (f"({issue})" if issue else "")] if x)
        else:
            ref = f"[{year}]" if year else ""
        out = join(", ", [creators, f"‘{title}’" if title else ""])
        out = join(" ", [out, ref, g(m, "journal"), first_page(m)])
        if not first_page(m):
            out = join(" ", [out, _online(m)])
        if pin_text:
            out += f", {pin_text}" if first_page(m) else f" {pin_text}"
        return out

    if kind == "chapter":
        editors = people(m, "editors")
        eds = _names(editors, False) + (" (eds)" if len(editors) > 1 else " (ed)") if editors else ""
        container = join(", ", [eds, I(g(m, "container_title"))])
        out = join(", ", [creators, f"‘{title}’" if title else ""])
        if container:
            out = join(" in ", [out, container])
        out = join(" ", [out, _pub_paren(m)])
        return out + f" {pin_text}" if pin_text else out

    if kind == "thesis":
        thesis_type = g(m, "thesis_type") or "thesis"
        if "thesis" not in thesis_type.lower() and "dissertation" not in thesis_type.lower():
            thesis_type += " thesis"
        inner = ", ".join(x for x in [thesis_type, " ".join(x for x in [g(m, "institution"), year_of(m)] if x)] if x)
        out = join(" ", [join(", ", [creators, f"‘{title}’" if title else ""]), f"({inner})"])
        return out + f" {pin_text}" if pin_text else out

    if kind == "website":
        inner = join(", ", [I(g(m, "website")), format_date(g(m, "date"), "oscola") or year_of(m)])
        out = join(", ", [creators, f"‘{title}’" if title else ""])
        if inner:
            out = join(" ", [out, "(" + inner + ")"])
        out = join(" ", [out, _online(m)])
        return out + f" {pin_text}" if pin_text else out

    # book and report
    paren = _pub_paren(m, lead=g(m, "number") if kind == "report" else "")
    out = join(" ", [join(", ", [creators, I(title)]), paren])
    return out + f" {pin_text}" if pin_text else out


def _body(m: dict, pin: dict | None, bib: bool = False) -> Rich:
    kind = m.get("type")
    if kind == "case":
        return _case(m, pin, bib)
    if kind == "legislation":
        return _legislation(m, pin)
    if kind == "treaty":
        return _treaty(m, pin)
    return _secondary(m, pin, bib)


def _short(m: dict, pin: dict | None) -> Rich:
    kind = m.get("type")
    pin_kind, pin_value = _pin(pin)
    if kind == "legislation":
        return _legislation(m, pin)
    if kind == "treaty":
        out = Rich(g(m, "short_title") or g(m, "title")) + " (n #)"
        if pin_value:
            out += " " + _statute_pin("article" if pin_kind == "page" else pin_kind, pin_value)
        return out
    if kind == "case":
        out = I(case_short_name(normalise_v(g(m, "title"), dotted=False))) + " (n #)"
        if pin_value:
            out += f" [{pin_value}]" if pin_kind == "para" else f" {_generic_pin(pin_kind, pin_value)}"
        return out
    ppl = people(m, "authors") or people(m, "editors")
    if ppl:
        names = [family_of(p) for p in ppl]
        lead = Rich(f"{names[0]} and others" if len(names) > 3 else " and ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else names[0])
    else:
        lead = I(g(m, "title")) if kind in ("book", "report") else Rich(f"‘{g(m, 'title')}’")
    out = lead + " (n #)"
    if pin_value:
        out += f" {_generic_pin(pin_kind, pin_value)}"
    return out


def format(m: dict, pin: dict | None = None) -> dict[str, Rich]:
    return {
        "full": _body(m, None),
        "footnote": end(_body(m, pin)),
        "short": end(_short(m, pin)),
        "bibliography": _body(m, None, bib=True),
    }
