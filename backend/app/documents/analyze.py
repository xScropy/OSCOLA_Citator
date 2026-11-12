"""Analyse a document's footnotes: which authorities are cited, where, and how to fix the citations."""
from __future__ import annotations

import re
from typing import Any

from ..bibliography import AUTHORITY_CATEGORIES
from ..citation.common import SOURCE_TYPES, Rich, case_short_name, family_of, g, people, sort_key
from ..citation.engine import cite_rich, normalise_metadata
from ..duplicates import find_duplicates
from .extract import Extracted, Footnote
from .parse import find_case_mentions, parse_segment, parse_tail, split_segments

STYLES = ("oscola", "bluebook")  # footnote-based styles

CHANGE_LABELS = {
    "format": "Formatting corrected",
    "italics": "Italics corrected",
    "cross-reference": "Cross-reference number corrected",
    "shortened": "Shortened (already cited in full)",
    "ibid": "Replaced with ibid",
    "expanded": "Given in full (first citation)",
    "full stop": "Closing full stop added",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _names(meta: dict) -> list[str]:
    """Names a short citation may use for this source."""
    kind, title = meta.get("type"), g(meta, "title")
    names = [title, g(meta, "short_title")]
    if kind == "case":
        plain = re.sub(r"\s+v\.\s+", " v ", title)
        names += [plain, case_short_name(plain)]
    elif kind not in ("treaty", "legislation"):
        families = [family_of(p) for p in (people(meta, "authors") or people(meta, "editors"))]
        if families:
            names += [families[0], " and ".join(families), " ".join(families)]
            if len(families) > 2:
                names.append(f"{families[0]} and others")
    return [n for n in dict.fromkeys(_norm(n) for n in names) if len(n) >= 2]


def _match_score(lead: str, meta: dict) -> int:
    lead = _norm(lead)
    if not lead:
        return 0
    names = _names(meta)
    if lead in names:
        return 3
    tokens = lead.split()
    for name in names:
        words = name.split()
        if all(token in words for token in tokens):
            return 2
    return 0


def _rich_from_flags(text: str, flags: list[bool]) -> Rich:
    out, start = Rich(), 0
    for index in range(1, len(text) + 1):
        if index == len(text) or flags[index] != flags[start]:
            out += (text[start:index], "i" if flags[start] else "")
            start = index
    return out


def _pages_text(pages: list[str]) -> str:
    """'3, 5–7, 12' for numeric pages; document order otherwise (e.g. roman numerals)."""
    unique = list(dict.fromkeys(pages))
    if not unique or not all(p.isdigit() for p in unique):
        return ", ".join(unique)
    numbers = sorted({int(p) for p in unique})
    out, start, previous = [], numbers[0], numbers[0]
    for n in numbers[1:] + [None]:
        if n is not None and n == previous + 1:
            previous = n
            continue
        out.append(str(start) if start == previous else f"{start}–{previous}")
        if n is not None:
            start = previous = n
    return ", ".join(out)


def _inline(meta: dict, style: str, pin: dict | None) -> Rich:
    """The footnote form of a full citation, without the closing full stop."""
    rich = cite_rich(meta, style, pin)["footnote"]
    if rich.parts and rich.parts[-1][0].endswith("."):
        text, mark = rich.parts[-1]
        rich = Rich(*rich.parts[:-1], (text[:-1], mark))
    return rich


def _short(meta: dict, style: str, pin: dict | None, first_note: int) -> Rich:
    rich = cite_rich(meta, style, pin)["short"]
    parts = [(text.replace("#", str(first_note)), mark) for text, mark in rich.parts]
    if parts and parts[-1][0].endswith("."):
        parts[-1] = (parts[-1][0][:-1], parts[-1][1])
    return Rich(*parts)


def _ibid(meta: dict, style: str, pin: dict | None) -> Rich | None:
    short = cite_rich(meta, style, pin)["short"].text.rstrip(".")
    if style == "bluebook":
        if "note #" not in short:
            return None  # Bluebook case short forms do not take 'id.' this simply
        tail = short.split("note #", 1)[1].lstrip(", ")
        return Rich(("Id.", "i")) + (f" {tail}" if tail else "")
    if "(n #)" not in short:
        return None
    return Rich("ibid" + short.split("(n #)", 1)[1])


def analyze(extracted: Extracted, style: str = "oscola", options: dict | None = None, library: list[tuple[int, dict]] | None = None) -> dict[str, Any]:
    options = options or {}
    style = style if style in STYLES else "oscola"
    shorten, use_ibid = bool(options.get("shorten")), options.get("use_ibid", True)
    skip, overrides = set(options.get("skip") or []), dict(options.get("overrides") or {})
    library = library or []

    authorities: list[dict[str, Any]] = []

    def authority_for(meta: dict, confident: bool, note: Footnote) -> int:
        meta = normalise_metadata(meta)
        found = find_duplicates(meta, [(a["id"], a["metadata"]) for a in authorities])
        if found:
            existing = authorities[found[0]["id"]]
            for key, value in meta.items():
                existing["metadata"].setdefault(key, value)
            existing["confident"] = existing["confident"] or confident
            return existing["id"]
        authorities.append({"id": len(authorities), "metadata": meta, "confident": confident, "first_footnote": note.number, "occurrences": []})
        return len(authorities) - 1

    # ---- pass 1: recognise citations and resolve them to authorities
    notes: list[dict[str, Any]] = []
    last_authority: int | None = None
    cited_in: dict[int, list[int]] = {}
    for note in extracted.footnotes:
        citations: list[dict[str, Any]] = []
        for index, (start, end) in enumerate(split_segments(note.text)):
            parsed = parse_segment(note.text[start:end])
            body_start = start + len(parsed["signal"])
            entry: dict[str, Any] = {
                "key": f"{note.number}:{index}", "start": body_start, "end": end, "raw": note.text[body_start:end],
                "form": parsed["form"], "authority": None, "pinpoint": parsed.get("pinpoint"), "suffix": parsed.get("suffix", ""),
                "issue": None, "mentions": [],
            }
            if parsed["form"] == "full":
                entry["authority"] = authority_for(parsed["metadata"], parsed.get("confident", True), note)
            elif parsed["form"] == "short":
                entry["note"] = parsed["note"]
                candidates = [(a, _match_score(parsed["lead"], authorities[a]["metadata"])) for a in cited_in.get(parsed["note"], [])]
                best = max(candidates, key=lambda c: c[1], default=None)
                if best and (best[1] > 0 or len(set(a for a, _ in candidates)) == 1):
                    entry["authority"] = best[0]
                else:
                    scored = [(a["id"], _match_score(parsed["lead"], a["metadata"])) for a in authorities]
                    top = max((s for _, s in scored), default=0)
                    winners = [a for a, s in scored if s == top and top > 0]
                    if len(winners) == 1:
                        entry["authority"] = winners[0]
                    else:
                        entry["issue"] = f"The cross-reference to footnote {parsed['note']} could not be matched to a source cited there."
            elif parsed["form"] == "ibid":
                if last_authority is not None:
                    entry["authority"] = last_authority
                else:
                    entry["issue"] = "‘ibid’ has no earlier citation to refer to."
            else:
                body = parsed["body"]
                best_name, best_authority = "", None
                for a in authorities:
                    for name in _names(a["metadata"]):
                        pattern = r"\s+(?:v\.?\s+)?".join(re.escape(w) for w in name.split()) if a["metadata"]["type"] == "case" else r"\W+".join(re.escape(w) for w in name.split())
                        match = re.match(rf"^{pattern}(?=$|[\s,])", body, re.I)
                        if match and len(name) > len(best_name):
                            pin, suffix = parse_tail(body[match.end():])
                            if not suffix and (pin or not body[match.end():].strip()):
                                best_name, best_authority = name, a["id"]
                                entry["pinpoint"] = pin
                if best_authority is not None:
                    entry["form"], entry["authority"] = "short", best_authority
                else:
                    for _, _, mention in find_case_mentions(body):
                        entry["mentions"].append((authority_for(mention["metadata"], True, note), mention.get("pinpoint")))
                    squashed = _squash(body)
                    for a in authorities:
                        for field in ("neutral_citation", "report_citation", "treaty_series"):
                            value = g(a["metadata"], field)
                            if value and value in squashed and a["id"] not in [m[0] for m in entry["mentions"]]:
                                entry["mentions"].append((a["id"], None))

            involved = ([entry["authority"]] if entry["authority"] is not None else []) + [m[0] for m in entry["mentions"]]
            for authority_id in involved:
                cited_in.setdefault(note.number, []).append(authority_id)
                last_authority = authority_id
            if entry["authority"] is not None:
                authorities[entry["authority"]]["occurrences"].append({"footnote": note.number, "page": note.page, "form": entry["form"], "pinpoint": entry["pinpoint"], "raw": entry["raw"]})
            for authority_id, pin in entry["mentions"]:
                authorities[authority_id]["occurrences"].append({"footnote": note.number, "page": note.page, "form": "mention", "pinpoint": pin, "raw": entry["raw"]})
            citations.append(entry)
        notes.append({"note": note, "citations": citations})

    # ---- match against the user's library; saved (reviewed) details take precedence when formatting
    for a in authorities:
        found = find_duplicates(a["metadata"], library)
        a["library_id"] = found[0]["id"] if found else None
        saved = next((m for i, m in library if i == a["library_id"]), None)
        a["format_metadata"] = saved or a["metadata"]

    # ---- pass 2: corrections
    seen: set[int] = set()
    previous: tuple[int, int] | None = None  # (authority, footnote number) of the citation just before
    counts = {n["note"].number: sum(1 for c in n["citations"] if c["authority"] is not None or c["mentions"]) for n in notes}
    any_italics = any(any(n["note"].italic) for n in notes)
    out_notes = []
    changed_total = 0
    for item in notes:
        note: Footnote = item["note"]
        replacements: list[tuple[int, int, Rich]] = []
        out_citations = []
        for c in item["citations"]:
            change = None
            authority = authorities[c["authority"]] if c["authority"] is not None else None
            if authority is not None and c["form"] in ("full", "short", "ibid"):
                meta, kind = authority["format_metadata"], authority["metadata"]["type"]
                first = authority["id"] not in seen
                follows = previous is not None and previous[0] == authority["id"] and (
                    previous[1] == note.number or (previous[1] == note.number - 1 and counts.get(previous[1]) == 1)
                )
                if kind == "legislation":
                    target = "full"
                elif shorten:
                    target = "full" if first else ("ibid" if use_ibid and follows else "short")
                else:
                    target = c["form"] if not first or c["form"] == "full" else c["form"]
                expected = None
                if authority["confident"] or authority["library_id"] is not None:
                    if target == "ibid":
                        expected = _ibid(meta, style, c["pinpoint"])
                        target = "ibid" if expected is not None else "short"
                    if target == "short":
                        expected = _short(meta, style, c["pinpoint"], authority["first_footnote"])
                    elif target == "full":
                        expected = _inline(meta, style, c["pinpoint"])
                    if c["suffix"]:
                        expected = expected + (c["suffix"] if c["suffix"][0] in ",.;:" else f" {c['suffix']}")
                if expected is not None:
                    kinds = []
                    if _squash(expected.text) != _squash(c["raw"]):
                        if target != c["form"]:
                            kinds.append("ibid" if target == "ibid" else "shortened" if target == "short" else "expanded")
                        elif c["form"] == "short" and c.get("note") not in (None, authority["first_footnote"]) and style == "oscola":
                            kinds.append("cross-reference")
                        else:
                            kinds.append("format")
                    elif any_italics:
                        original = _squash("".join(ch for ch, flag in zip(note.text[c["start"]:c["end"]], note.italic[c["start"]:c["end"]]) if flag))
                        wanted = _squash("".join(text for text, mark in expected.parts if mark == "i"))
                        if original != wanted:
                            kinds.append("italics")
                    if kinds:
                        override = overrides.get(c["key"])
                        suggestion = Rich(override) if override is not None else expected
                        accepted = c["key"] not in skip
                        change = {"types": kinds, "labels": [CHANGE_LABELS[k] for k in kinds], "suggested": suggestion.to_dict(), "accepted": accepted, "edited": override is not None}
                        if accepted:
                            replacements.append((c["start"], c["end"], suggestion))
                elif c["form"] == "full":
                    c["issue"] = c["issue"] or "Some details of this citation could not be read with confidence, so no correction is suggested."
            involved = ([c["authority"]] if c["authority"] is not None else []) + [m[0] for m in c["mentions"]]
            for authority_id in involved:
                seen.add(authority_id)
                previous = (authority_id, note.number)
            out_citations.append({
                "key": c["key"], "raw": c["raw"], "form": c["form"], "authority_id": c["authority"],
                "mention_ids": [m[0] for m in c["mentions"]], "pinpoint": c["pinpoint"], "change": change, "issue": c["issue"],
            })

        end_change = None
        stripped = note.text.rstrip().rstrip("’”)\"'")
        if style == "oscola" and stripped and stripped[-1] not in ".?!":
            key = f"{note.number}:end"
            end_change = {"key": key, "label": CHANGE_LABELS["full stop"], "accepted": key not in skip}

        revised, cursor = Rich(), 0
        for start, end, rich in sorted(replacements, key=lambda r: r[0]):
            revised = revised + _rich_from_flags(note.text[cursor:start], note.italic[cursor:start]) + rich
            cursor = end
        revised = revised + _rich_from_flags(note.text[cursor:], note.italic[cursor:])
        if end_change and end_change["accepted"]:
            revised = revised + "."
        original = _rich_from_flags(note.text, note.italic)
        changed = bool(replacements) or bool(end_change and end_change["accepted"])
        changed_total += changed
        out_notes.append({
            "number": note.number, "page": note.page, "source_id": note.source_id,
            "original": original.to_dict(), "revised": revised.to_dict(), "revised_runs": revised.runs,
            "changed": changed, "citations": out_citations, "end_change": end_change,
        })

    # ---- authorities and the table
    unit = "page" if extracted.pages_available else "footnote"
    out_authorities = []
    for a in authorities:
        meta = a["format_metadata"]
        locations = [str(o["page"] if extracted.pages_available else o["footnote"]) for o in a["occurrences"]]
        forms = cite_rich(meta, style)
        out_authorities.append({
            "id": a["id"], "type": a["metadata"]["type"], "metadata": a["metadata"], "confident": a["confident"],
            "library_id": a["library_id"], "first_footnote": a["first_footnote"],
            "citation": forms["bibliography"].to_dict(), "full": forms["full"].to_dict(),
            "locations": _pages_text(locations), "footnotes": list(dict.fromkeys(o["footnote"] for o in a["occurrences"])),
            "occurrences": a["occurrences"], "sort": sort_key(meta),
        })

    sections = []
    claimed: set[str] = set()
    for category in options.get("categories") or AUTHORITY_CATEGORIES:
        types = [t for t in category.get("types", []) if t in SOURCE_TYPES and t not in claimed]
        claimed.update(types)
        members = sorted((a for a in out_authorities if a["type"] in types), key=lambda a: a["sort"])
        if members:
            sections.append({"heading": category.get("heading", ""), "entries": [{"id": a["id"], **a["citation"], "pages": a["locations"]} for a in members]})
    leftover = sorted((a for a in out_authorities if a["type"] not in claimed), key=lambda a: a["sort"])
    if leftover:
        sections.append({"heading": "Other Authorities", "entries": [{"id": a["id"], **a["citation"], "pages": a["locations"]} for a in leftover]})

    recognised = sum(1 for n in out_notes for c in n["citations"] if c["authority_id"] is not None)
    unrecognised = sum(1 for n in out_notes for c in n["citations"] if c["authority_id"] is None and not c["mention_ids"])
    return {
        "style": style,
        "document": {"kind": extracted.kind, "footnotes": len(out_notes), "pages": extracted.page_count, "pages_available": extracted.pages_available, "location_unit": unit},
        "warnings": extracted.warnings,
        "options": {"shorten": shorten, "use_ibid": bool(use_ibid)},
        "stats": {"authorities": len(out_authorities), "citations": recognised, "unrecognised": unrecognised, "footnotes_changed": changed_total, "in_library": sum(a["library_id"] is not None for a in out_authorities)},
        "authorities": out_authorities,
        "footnotes": out_notes,
        "table": {"title": "Table of Authorities", "location_heading": "Page" if unit == "page" else "Footnote", "sections": sections},
    }
