"""Document check: analyse the footnotes of an uploaded PDF or Word document.

Nothing is stored. The file is processed in memory for the duration of the request,
so exports are produced by sending the file again together with the user's choices.
"""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from .. import export
from ..auth import current_user
from ..db import User, get_db
from ..documents.analyze import STYLES, analyze
from ..documents.extract import MAX_UPLOAD_BYTES, DocumentError, extract
from ..documents.writer import apply_corrections
from .library import user_references

router = APIRouter(prefix="/api/documents", tags=["documents"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def _read(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 25 MB.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file is empty.")
    return data


def _options(raw: str) -> dict:
    try:
        options = json.loads(raw or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The options could not be read.")
    if not isinstance(options, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The options could not be read.")
    try:
        first_page = int(options.get("first_page") or 1)
    except (TypeError, ValueError):
        first_page = 1
    return {
        "shorten": bool(options.get("shorten")),
        "use_ibid": options.get("use_ibid", True) is not False,
        "first_page": max(-10000, min(first_page, 100000)),
        "skip": [str(k) for k in options.get("skip") or [] if isinstance(k, (str, int))][:5000],
        "overrides": {str(k): str(v)[:2000] for k, v in (options.get("overrides") or {}).items()} if isinstance(options.get("overrides"), dict) else {},
    }


def _run(data: bytes, filename: str, style: str, options: dict, user: User, db: Session) -> dict:
    if style not in STYLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Document check supports the footnote styles OSCOLA and Bluebook.")
    try:
        extracted = extract(data, filename, options["first_page"])
    except DocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    library = [(r.id, r.data) for r in user_references(db, user)]
    return analyze(extracted, style, options, library)


def _public(result: dict) -> dict:
    for note in result["footnotes"]:
        note.pop("revised_runs", None)
        note.pop("source_id", None)
    for authority in result["authorities"]:
        authority.pop("sort", None)
    return result


@router.post("/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    style: str = Form("oscola"),
    options: str = Form("{}"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    data = await _read(file)
    result = _run(data, file.filename or "", style, _options(options), user, db)
    result["document"]["name"] = (file.filename or "document")[:200]
    return _public(result)


@router.post("/export")
async def export_document(
    file: UploadFile = File(...),
    style: str = Form("oscola"),
    options: str = Form("{}"),
    output: str = Form(...),
    format: str = Form("docx"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """output: 'corrected' (Word file with corrected footnotes), 'footnotes' (revised list) or 'table' (table of authorities)."""
    data = await _read(file)
    result = _run(data, file.filename or "", style, _options(options), user, db)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", re.sub(r"\.[A-Za-z]+$", "", file.filename or "document")).strip("-")[:60] or "document"

    if output == "corrected":
        if result["document"]["kind"] != "docx":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A corrected copy can only be produced for Word documents. Download the revised footnotes instead.")
        try:
            payload = apply_corrections(data, result["footnotes"])
        except DocumentError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        return Response(payload, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{stem}-corrected.docx"'})

    if format not in export.DOCUMENT_FORMATS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose DOCX, PDF or TXT.")
    if output == "footnotes":
        entries = [{"html": f"{note['number']}. {note['revised']['html']}".replace("\n", " ")} for note in result["footnotes"]]
        title, sections, name = "Revised footnotes", [{"heading": "", "entries": entries}], "footnotes"
    elif output == "table":
        title, sections, name = result["table"]["title"], result["table"]["sections"], "table-of-authorities"
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown export.")
    payload = {"docx": export.to_docx, "pdf": export.to_pdf, "txt": export.to_txt}[format](title, sections)
    media_type, extension = export.FORMATS[format]
    return Response(payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{stem}-{name}.{extension}"'})
