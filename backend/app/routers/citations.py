"""Source identification, citation preview, bibliography generation and export."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import bibliography, export
from ..auth import current_user
from ..citation.common import FIELD_LABELS, PINPOINT_KINDS, SOURCE_TYPES
from ..citation.engine import STYLES, cite, normalise_metadata, normalise_pinpoint
from ..db import User, get_db
from ..identify import service
from ..verification import STATUS_LABELS, verify
from .library import user_references, verification_of

router = APIRouter(prefix="/api", tags=["citations"])


class IdentifyIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    type: str | None = None


class CiteIn(BaseModel):
    metadata: dict[str, Any]
    pinpoint: dict[str, Any] | None = None
    style: str = "oscola"
    retrieved: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    user_confirmed: bool = False


class Category(BaseModel):
    heading: str = Field(max_length=200)
    types: list[str]


class Entry(BaseModel):
    id: int | None = None
    text: str = ""
    html: str = Field(default="", max_length=20000)


class Section(BaseModel):
    heading: str = Field(default="", max_length=200)
    entries: list[Entry]


class BibliographyIn(BaseModel):
    reference_ids: list[int] = Field(min_length=1)
    style: str = "oscola"
    mode: str = Field("bibliography", pattern="^(bibliography|authorities)$")
    categories: list[Category] | None = None


class ExportIn(BibliographyIn):
    format: str = "docx"
    title: str | None = Field(default=None, max_length=200)
    sections: list[Section] | None = None  # the user's edited version of the generated list


@router.get("/meta")
def meta() -> dict:
    """Static vocabulary the interface needs: styles, source types, fields."""
    return {
        "styles": [{"id": key, "name": value["name"]} for key, value in STYLES.items()],
        "source_types": list(SOURCE_TYPES),
        "pinpoint_kinds": list(PINPOINT_KINDS),
        "field_labels": FIELD_LABELS,
        "verification_statuses": STATUS_LABELS,
        "export_formats": list(export.FORMATS),
        "authority_categories": bibliography.AUTHORITY_CATEGORIES,
    }


@router.post("/identify")
async def identify(body: IdentifyIn, user: User = Depends(current_user)) -> dict:
    type_hint = body.type if body.type in SOURCE_TYPES else None
    result = await service.identify(body.query, type_hint)
    for c in result["candidates"]:
        c["citations"] = cite(c["metadata"], user.default_style)
        c["verification"] = verify(c["metadata"], c["metadata"], c["source"])
    return result


@router.post("/cite")
def preview(body: CiteIn, user: User = Depends(current_user)) -> dict:
    """Regenerate the citation after any metadata, pinpoint or style change."""
    metadata = normalise_metadata(body.metadata)
    retrieved = normalise_metadata(body.retrieved) if body.retrieved else None
    return {
        "metadata": metadata,
        "citations": cite(metadata, body.style, normalise_pinpoint(body.pinpoint)),
        "verification": verify(metadata, retrieved, body.source, body.user_confirmed),
    }


def _selected(db: Session, user: User, ids: list[int]) -> list:
    refs = {r.id: r for r in user_references(db, user)}
    missing = [i for i in ids if i not in refs]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some of the selected references no longer exist.")
    return [refs[i] for i in dict.fromkeys(ids)]


def _style(style: str) -> str:
    if style not in STYLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown citation style.")
    return style


@router.post("/bibliography")
def generate_bibliography(body: BibliographyIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    style = _style(body.style)
    refs = _selected(db, user, body.reference_ids)
    categories = [c.model_dump() for c in body.categories] if body.categories else None
    sections = bibliography.build([{"id": r.id, "metadata": r.data} for r in refs], style, body.mode, categories)
    incomplete = [
        {"id": r.id, "title": r.data.get("title", ""), "missing": v["missing"]["required"], "status": v["status"]}
        for r in refs
        for v in [verification_of(r)]
        if v["missing"]["required"] or v["status"] == "needs_review"
    ]
    return {
        "title": bibliography.default_title(body.mode, style),
        "style": style,
        "mode": body.mode,
        "sections": sections,
        "needs_attention": incomplete,
    }


@router.post("/export")
def export_references(body: ExportIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    style = _style(body.style)
    if body.format not in export.FORMATS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown export format.")
    refs = _selected(db, user, body.reference_ids)
    title = body.title if body.title is not None else bibliography.default_title(body.mode, style)

    if body.format in export.DOCUMENT_FORMATS:
        if body.sections is not None:
            sections = [s.model_dump() for s in body.sections]
        else:
            categories = [c.model_dump() for c in body.categories] if body.categories else None
            sections = bibliography.build([{"id": r.id, "metadata": r.data} for r in refs], style, body.mode, categories)
        payload = {"docx": export.to_docx, "pdf": export.to_pdf, "txt": export.to_txt}[body.format](title, sections)
    elif body.format == "bibtex":
        payload = export.to_bibtex([r.data for r in refs])
    elif body.format == "ris":
        payload = export.to_ris([r.data for r in refs])
    elif body.format == "csl-json":
        payload = export.to_csl_json([r.data for r in refs], [r.id for r in refs])
    else:
        rows = [{"metadata": r.data, "tags": r.tags, "notes": r.notes, "verification": verification_of(r)["label"]} for r in refs]
        payload = export.to_csv(rows, style)

    media_type, extension = export.FORMATS[body.format]
    stem = re.sub(r"[^a-z0-9]+", "-", (title or "references").lower()).strip("-") or "references"
    return Response(payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{stem}-{style}.{extension}"'})
