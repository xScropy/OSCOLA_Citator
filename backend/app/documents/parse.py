"""Recognise the citations written in a footnote.

The parser is deliberately conservative. A piece of footnote text is only read as
a citation when the whole of it fits a known citation shape; anything else is
left untouched and reported as unrecognised, never guessed at.
"""
from __future__ import annotations

import re
from typing import Any

from ..citation.common import parse_name

_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}

NEUTRAL_COURTS = (
    "UKSC|UKHL|UKPC|EWCA\\s+(?:Civ|Crim)|EWHC|UKUT|UKFTT|UKEAT|EAT|EWCOP|EWFC|UKIPTrib|CSIH|CSOH|HCJAC|NICA|NIQB|NIKB|NICh|NIFam|"
    "HCA|FCAFC|FCA|NSWCA|NSWSC|VSCA|VSC|QCA|SCC|ONCA|BCCA|NZSC|NZCA|NZHC|ZACC|ZASCA|SGCA|SGHC|HKCFA|HKCA|IESC|IECA|IEHC"
)
NEUTRAL = rf"\[\d{{4}}\]\s+(?:{NEUTRAL_COURTS})\s+\d+(?:\s+\((?:Admin|Ch|QB|KB|Fam|Comm|TCC|Pat|IPEC|Admlty|Costs|IAC|AAC|TC|LC|Mercantile)\))?"
REPORT = r"(?:\[\d{4}\]|\(\d{4}(?:[-–]\d{2,4})?\))\s+(?:\d+\s+)?[A-Z][A-Za-z&.']*(?:\s+(?:[A-Z][A-Za-z&.']*|\d+))*\s+\d+"
US_REPORT = r"\d+\s+U\.?\s?S\.?\s+(?:\(\d+\s+[A-Z][a-z]+\.?\)\s+)?\d+"
_NEUTRAL_RE, _REPORT_RE = re.compile(NEUTRAL), re.compile(REPORT)

SIGNALS = re.compile(
    r"^(?:(?:but\s+)?see(?:,?\s+(?:also|generally|especially|further|eg|e\.g\.|for example))?,?|cf\.?|compare|contra|eg,?|e\.g\.,?|also|and|accord)\s+",
    re.I,
)

OPEN, CLOSE = "([<‘“", ")]>’”"


def split_segments(text: str) -> list[tuple[int, int]]:
    """Spans of the separate citations in a footnote (split on ';', paragraph breaks and '. See …')."""
    spans, depth, start = [], 0, 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE and depth:
            depth -= 1
        elif ch == "\n":
            spans.append((start, i))
            start, depth = i + 1, 0
        elif ch == ";" and depth == 0:
            spans.append((start, i))
            start = i + 1
        elif ch == "." and depth == 0 and re.match(r"\.\s+(?:(?:But\s+)?See\b|Cf\b|Compare\b|Ibid\b|ibid\b)", text[i:]):
            spans.append((start, i))
            start = i + 1
        i += 1
    spans.append((start, len(text)))
    out = []
    for a, b in spans:
        while a < b and text[a].isspace():
            a += 1
        while b > a and (text[b - 1].isspace() or text[b - 1] == "."):
            b -= 1
        if b > a:
            out.append((a, b))
    return out


def _iso_date(text: str) -> str:
    match = re.match(r"\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text or "")
    if match and match.group(2).lower() in _MONTHS:
        return f"{match.group(3)}-{_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"
    match = re.search(r"\b(\d{4})\b", text or "")
    return match.group(1) if match else ""


def parse_tail(rest: str) -> tuple[dict | None, str]:
    """Split what follows a citation into a pinpoint and a verbatim remainder (e.g. '(Lord Atkin)')."""
    rest = rest.strip()
    rest = re.sub(r"^,\s*", "", rest)
    rest = re.sub(r"^at\s+", "", rest)
    if not rest:
        return None, ""
    patterns = [
        ("para", r"(\[\d+[A-Za-z]?\](?:\s*(?:[-–]|,|and)\s*\[\d+[A-Za-z]?\])*)"),
        ("para", r"(?:paras?\.?|¶+)\s*(\d[\d.]*(?:\s*[-–,]\s*\d[\d.]*)*)"),
        ("article", r"(?:arts?\.?|articles?)\s+(\d+[A-Za-z]?(?:\(\w+\))*(?:\s*[-–,]\s*\d+[A-Za-z]?(?:\(\w+\))*)*)"),
        ("section", r"(?:ss?\.?|sections?|§+)\s*(\d+[A-Za-z]?(?:\(\w+\))*(?:\s*[-–,]\s*\d+[A-Za-z]?(?:\(\w+\))*)*)"),
        ("page", r"(?:pp?\.?\s*)?(\d+(?:\s*[-–]\s*\d+)?(?:,\s*\d+(?:\s*[-–]\s*\d+)?)*)"),
    ]
    for kind, pattern in patterns:
        match = re.match(pattern + r"(?=$|[\s,.(])", rest)
        if match:
            value = match.group(1)
            if kind == "para" and value.startswith("["):
                value = re.sub(r"[\[\]]", "", value)
            value = re.sub(r"\s*([-–])\s*", "–", value)
            value = re.sub(r"\s*,\s*", ", ", value)
            return {"kind": kind, "value": value.strip()}, rest[match.end():].strip()
    return None, rest


def _people(text: str) -> tuple[list[dict], bool]:
    """Author names from 'A One, B Two and C Three'. Second value: False when the list is not fully known."""
    text = text.strip().rstrip(",")
    if re.search(r"\b(and others|et al\.?)$", text):
        return [{"literal": text}], False
    names = [n.strip() for n in re.split(r",\s*|\s+and\s+|\s*&\s*", text) if n.strip()]
    people = []
    for name in names:
        if len(name.split()) > 6 or not re.match(r"^[^\W\d]", name):
            return [{"literal": text}], False
        people.append(parse_name(name) if " " in name else {"literal": name})
    return people, True


_QUOTE_OPEN, _QUOTE_CLOSE = "[‘“\"']", "[’”\"']"


# Words a case name is made of: capitalised words, bracketed parts and a few connectors.
_NAME_TOKEN = r"(?:[A-Z0-9][\w.'’&/-]*,?|\([^()]{1,60}\),?|of|the|and|or|for|in|on|to|by|a|an|at|against|concerning|between|de|la|le|du|des|del|di|van|von|der|den|ex|p|plc|ltd|v\.?)"
_CASE_NAME = re.compile(rf"^{_NAME_TOKEN}(?:\s+{_NAME_TOKEN})*$")
_PROSE_LEAD = r"(?:In|As|Per|Applying|Following|Citing|Quoting|Contrast|Unlike|Like|Under|Since|After|Before|Although|While|When|Where|That|This|These|Those|And|But|Also|For|Thus|Hence|However|Both)"


def _case(seg: str) -> dict | None:
    if re.search(r"[‘“]", seg) or re.match(rf"^{_PROSE_LEAD}\s", seg):
        return None
    lead = re.search(rf"\s+(?:App(?:lication)?\s+nos?\b|{NEUTRAL}|{REPORT}|{US_REPORT})", seg)
    if lead and not _CASE_NAME.match(seg[: lead.start()].strip().rstrip(",")):
        return None  # running prose that happens to contain a citation
    # Unreported judgment: Name App no 123/45 (ECtHR, 20 July 2004)
    match = re.match(r"^(?P<name>.+?\sv\.?\s.+?)\s+(?P<number>App(?:lication)?\s+nos?\.?\s+[\d/]+(?:(?:,| and)\s*[\d/]+)*)\s+\((?P<court>[^,()]+),\s*(?P<date>[^()]+)\)(?P<rest>.*)$", seg)
    if match:
        meta = {"type": "case", "title": match.group("name"), "case_number": re.sub(r"^Application", "App", match.group("number")), "court": match.group("court").strip(), "date": _iso_date(match.group("date"))}
        return {"metadata": meta, "rest": match.group("rest")}
    # United States reports: Name, 347 US 483, 495 (1954)
    match = re.match(rf"^(?P<name>.+?\sv\.?\s.+?),?\s+(?P<report>{US_REPORT})(?:,\s*(?P<pin>\d+(?:[-–]\d+)?))?\s*\((?:[^()]*?\s)?(?P<year>\d{{4}})\)(?P<rest>.*)$", seg)
    if match:
        report = re.sub(r"U\.?\s?S\.?", "US", match.group("report"))
        meta = {"type": "case", "title": match.group("name"), "report_citation": re.sub(r"\s+", " ", report), "year": match.group("year")}
        rest = (match.group("pin") or "") + " " + match.group("rest")
        return {"metadata": meta, "rest": rest}
    first = re.search(rf"{NEUTRAL}|{REPORT}", seg)
    if not first:
        return None
    name = seg[: first.start()].strip().rstrip(",").strip()
    if not name or len(name) > 300 or not re.match(r"^[A-Z(]", name):
        return None
    has_v = bool(re.search(r"\sv\.?\s", name)) or bool(re.match(r"^(Re|In re|Ex p(?:arte)?)\s", name))
    if not has_v and (", " in name and not re.search(r"\b(Case|Opinion|Ltd|Limited|Inc|plc|Rep)\b|\(", name)):
        return None  # 'Author, Title' rather than a case name
    meta: dict[str, Any] = {"type": "case", "title": name}
    position = first.start()
    neutral = _NEUTRAL_RE.match(seg, position)
    if neutral:
        meta["neutral_citation"] = re.sub(r"\s+", " ", neutral.group(0))
        position = neutral.end()
        comma = re.match(r"\s*,\s*", seg[position:])
        if comma:
            report = _REPORT_RE.match(seg, position + comma.end())
            if report:
                meta["report_citation"] = re.sub(r"\s+", " ", report.group(0))
                position = report.end()
    else:
        report = _REPORT_RE.match(seg, position)
        meta["report_citation"] = re.sub(r"\s+", " ", report.group(0))
        position = report.end()
        court = re.match(r"\s*\(([A-Z][A-Za-z]{0,5}(?:\s[A-Z][A-Za-z]{0,5})?)\)", seg[position:])
        if court:
            meta["court"] = court.group(1)
            position += court.end()
    year = re.search(r"\d{4}", meta.get("neutral_citation") or meta.get("report_citation") or "")
    if year:
        meta["year"] = year.group(0)
    return {"metadata": meta, "rest": seg[position:]}


def _legislation(seg: str) -> dict | None:
    match = re.match(
        r"^(?P<title>(?:[A-Z][\w'’&-]*|of|the|and|for|to|in|on|\([A-Z][\w ]*\))(?:\s+(?:[A-Z][\w'’&-]*|of|the|and|for|to|in|on|etc|\([A-Z][\w ,]*\)))*"
        r"\s+(?:Act|Regulations|Order|Rules|Ordinance|Code|Measure)\s+(?P<year>\d{4}))(?:\s*\((?P<jurisdiction>[A-Z][A-Za-z ]{1,30})\))?(?P<rest>.*)$",
        seg,
    )
    if not match:
        return None
    pin, remainder = parse_tail(match.group("rest"))
    if match.group("rest").strip() and (pin is None or remainder):
        if not re.match(r"^,?\s*(sch|pt|reg|r|ch)\s", match.group("rest").strip()):
            return None
    meta = {"type": "legislation", "title": match.group("title"), "year": match.group("year")}
    if match.group("jurisdiction"):
        meta["jurisdiction"] = match.group("jurisdiction")
    return {"metadata": meta, "rest": match.group("rest")}


_SERIES = r"\d+\s+(?:UNTS|LNTS|UKTS|ETS|CETS|ILM|UST|TIAS|OJ)\s+[\w/]+|UNGA\s+Res\s+\S+(?:\s+\([IVXLC]+\))?|ETS\s+No\.?\s*\d+|CETS\s+No\.?\s*\d+"


def _treaty(seg: str) -> dict | None:
    match = re.match(
        rf"^(?P<title>[A-Z][^()\[\]‘“<>]{{5,250}}?)\s*\((?P<dates>(?:adopted|opened for signature|signed|concluded|done)\b[^()]*)\)\s*(?P<series>{_SERIES})?\s*(?:\((?P<short>[^()]{{2,60}})\))?(?P<rest>.*)$",
        seg,
    )
    if not match:
        match = re.match(rf"^(?P<title>[A-Z][^()\[\]‘“<>,]{{5,250}}?),?\s+(?P<series>{_SERIES})\s*(?:\((?P<short>[^()]{{2,60}})\))?(?P<rest>.*)$", seg)
        if not match:
            return None
    meta: dict[str, Any] = {"type": "treaty", "title": match.group("title").strip().rstrip(",")}
    dates = match.groupdict().get("dates") or ""
    adopted = re.match(r"(?:adopted|opened for signature|signed|concluded|done)\s+(?:on\s+)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", dates)
    if adopted:
        meta["adopted_date"] = _iso_date(adopted.group(1))
    force = re.search(r"entered into force\s+(?:on\s+)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})", dates)
    if force:
        meta["entry_into_force_date"] = _iso_date(force.group(1))
    if dates and not adopted:
        return None
    if match.group("series"):
        meta["treaty_series"] = re.sub(r"\s+", " ", match.group("series"))
    if match.group("short"):
        meta["short_title"] = match.group("short").strip()
    return {"metadata": meta, "rest": match.group("rest")}


def _book_paren(paren: str) -> tuple[dict, bool]:
    """'(4th edn, OUP 2018)' -> edition/publisher/year. Second value: False when a part is not understood."""
    out: dict[str, str] = {}
    known = True
    pieces = [p.strip() for p in paren.split(",")]
    last = re.match(r"^(?P<publisher>.*?)\s*(?P<year>\d{4})$", pieces[-1])
    if not last:
        return out, False
    out["year"] = last.group("year")
    if last.group("publisher"):
        out["publisher"] = last.group("publisher")
    for piece in pieces[:-1]:
        edition = re.match(r"^(\d+)(?:st|nd|rd|th|d)?\s+edn?\.?$|^(rev(?:ised)?|new)\s+edn?\.?$", piece, re.I)
        if edition:
            out["edition"] = edition.group(1) or edition.group(2)
        elif not out.get("publisher") or piece:
            known = False
    return out, known


def _secondary(seg: str) -> dict | None:
    quoted = re.match(rf"^(?P<authors>[^‘’“”<>\[\]]{{2,200}}?),\s*{_QUOTE_OPEN}(?P<title>.+){_QUOTE_CLOSE}\s*(?P<after>.*)$", seg)
    if quoted and re.search(r"[‘“]", seg):
        authors, sure = _people(quoted.group("authors"))
        after = quoted.group("after")
        base: dict[str, Any] = {"authors": authors, "title": quoted.group("title").strip()}
        # journal article: (2005) 68 MLR 100  |  [2005] PL 440
        article = re.match(r"^(?P<bracket>[\[(])(?P<year>\d{4})[\])]\s*(?:(?P<volume>\d+)(?:\((?P<issue>[\w-]+)\))?\s+)?(?P<journal>[A-Z][^\d<>()\[\],;]*?)\s+(?P<page>\d+)(?P<rest>.*)$", after)
        if article and (article.group("bracket") == "[" or article.group("volume")):
            meta = {**base, "type": "article", "year": article.group("year"), "journal": article.group("journal").strip(), "pages": article.group("page")}
            if article.group("volume"):
                meta["volume"] = article.group("volume")
            if article.group("issue"):
                meta["issue"] = article.group("issue")
            return {"metadata": meta, "rest": article.group("rest"), "confident": sure}
        chapter = re.match(r"^in\s+(?P<editors>.+?)\s+\((?P<role>eds?)\),\s*(?P<book>[^()]+?)\s*\((?P<paren>[^()]*\d{4})\)(?P<rest>.*)$", after)
        if chapter:
            editors, sure_editors = _people(chapter.group("editors"))
            details, known = _book_paren(chapter.group("paren"))
            meta = {**base, "type": "chapter", "editors": editors, "container_title": chapter.group("book").strip(), **details}
            return {"metadata": meta, "rest": chapter.group("rest"), "confident": sure and sure_editors and known}
        other = re.match(r"^\((?P<paren>[^()]*)\)\s*(?:<(?P<url>[^<>\s]+)>)?(?:\s*accessed\s+(?P<accessed>\d{1,2}\s+[A-Za-z]+\s+\d{4}))?(?P<rest>.*)$", after)
        if other and re.search(r"thesis|dissertation", other.group("paren"), re.I):
            parts = [p.strip() for p in other.group("paren").split(",", 1)]
            tail = re.match(r"^(?P<institution>.*?)\s*(?P<year>\d{4})$", parts[1]) if len(parts) > 1 else None
            if tail:
                meta = {**base, "type": "thesis", "thesis_type": parts[0], "institution": tail.group("institution"), "year": tail.group("year")}
                return {"metadata": meta, "rest": other.group("rest"), "confident": sure}
        if other and other.group("url"):
            parts = [p.strip() for p in other.group("paren").split(",")]
            meta = {**base, "type": "website", "url": other.group("url")}
            if parts and parts[0]:
                meta["website"] = parts[0]
            if len(parts) > 1:
                meta["date"] = _iso_date(parts[-1])
            if other.group("accessed"):
                meta["accessed"] = _iso_date(other.group("accessed"))
            return {"metadata": meta, "rest": other.group("rest"), "confident": sure and len(parts) <= 2}
        return None
    if re.search(r"[‘“]", seg):
        return None
    book = re.match(r"^(?P<authors>[^()<>\[\]]{2,200}?)(?P<eds>\s+\(eds?\))?,\s*(?P<title>[^()<>\[\]]{2,300}?)\s*\((?P<paren>[^()]*\b\d{4})\)(?P<rest>.*)$", seg)
    if book:
        people, sure = _people(book.group("authors"))
        details, known = _book_paren(book.group("paren"))
        if not details:
            return None
        meta = {"type": "book", "title": book.group("title").strip(), "editors" if book.group("eds") else "authors": people, **details}
        return {"metadata": meta, "rest": book.group("rest"), "confident": sure and known}
    return None


def parse_segment(seg: str) -> dict:
    """Classify one citation: full, short (cross-reference), ibid or unknown."""
    signal = ""
    match = SIGNALS.match(seg)
    while match:
        signal += match.group(0)
        seg = seg[match.end():]
        match = SIGNALS.match(seg)
    base = {"signal": signal, "body": seg}

    ibid = re.match(r"^(?:ibid|ibidem|id)\b\.?,?\s*(?P<rest>.*)$", seg, re.I)
    if ibid:
        pin, suffix = parse_tail(ibid.group("rest"))
        return {**base, "form": "ibid", "pinpoint": pin, "suffix": suffix}

    cross = re.match(r"^(?P<lead>.*?)\s*,?\s*\((?:n|fn|note)\.?\s*(?P<note>\d+)\)\s*(?P<rest>.*)$", seg) or re.match(
        r"^(?P<lead>.*?),?\s+(?:supra|above)\s+(?:n|note|fn)\.?\s*(?P<note>\d+)\s*(?P<rest>.*)$", seg
    )
    if cross and len(cross.group("lead")) <= 200:
        pin, suffix = parse_tail(cross.group("rest"))
        return {**base, "form": "short", "lead": cross.group("lead").strip(), "note": int(cross.group("note")), "pinpoint": pin, "suffix": suffix}

    for parser in (_treaty, _legislation, _case, _secondary):
        found = parser(seg)
        if found:
            pin, suffix = parse_tail(found["rest"])
            return {**base, "form": "full", "metadata": found["metadata"], "pinpoint": pin, "suffix": suffix, "confident": found.get("confident", True)}
    return {**base, "form": "unknown"}


CASE_MENTION = re.compile(
    rf"(?<![\w.'’&-])(?!{_PROSE_LEAD}\s)(?P<name>[A-Z][\w.'’&/-]*(?:\s+{_NAME_TOKEN}){{0,12}}?\s+v\.?\s+{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,14}}?)\s+(?={NEUTRAL}|{REPORT})"
)


def find_case_mentions(text: str) -> list[tuple[int, int, dict]]:
    """Case citations embedded in running prose: (start, end, parsed citation)."""
    out = []
    for match in CASE_MENTION.finditer(text):
        end = text.find(";", match.start())
        chunk = text[match.start(): end if end != -1 else len(text)]
        found = _case(chunk)
        if found:
            pin, _ = parse_tail(found["rest"])
            out.append((match.start(), match.start() + len(chunk) - len(found["rest"]), {"form": "mention", "metadata": found["metadata"], "pinpoint": pin}))
    return out
