"""Personal library: references, collections, duplicates and dashboard statistics."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..citation.common import LEGAL_TYPES, SOURCE_TYPES, people, sort_key, year_of
from ..citation.engine import STYLES, cite, normalise_metadata, normalise_pinpoint
from ..db import Collection, Reference, User, get_db
from ..duplicates import duplicate_groups, find_duplicates
from ..verification import STATUS_LABELS, verify

router = APIRouter(prefix="/api", tags=["library"])


class ReferenceIn(BaseModel):
    metadata: dict[str, Any]
    retrieved: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    pinpoint: dict[str, Any] | None = None
    style: str | None = None
    notes: str = Field(default="", max_length=20000)
    tags: list[str] = []
    favorite: bool = False
    user_confirmed: bool = False
    collection_ids: list[int] = []
    allow_duplicate: bool = False


class ReferencePatch(BaseModel):
    metadata: dict[str, Any] | None = None
    pinpoint: dict[str, Any] | None = None
    clear_pinpoint: bool = False
    style: str | None = None
    notes: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None
    favorite: bool | None = None
    user_confirmed: bool | None = None
    collection_ids: list[int] | None = None


class DuplicateCheck(BaseModel):
    metadata: dict[str, Any]
    exclude_id: int | None = None


class MergeIn(BaseModel):
    source_id: int


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    kind: str = "research"


class CollectionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    kind: str | None = None


def clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        tag = " ".join(str(tag).split())[:60]
        if tag and tag.lower() not in [t.lower() for t in out]:
            out.append(tag)
    return out[:50]


def _source(source: dict | None) -> dict | None:
    if not source or not source.get("name"):
        return None
    return {
        "name": str(source["name"])[:200],
        "url": str(source.get("url") or "")[:2000],
        "reliable": bool(source.get("reliable")),
        "retrieved_at": str(source.get("retrieved_at") or "")[:32],
    }


def verification_of(ref: Reference) -> dict:
    return verify(ref.data, ref.retrieved, ref.source, ref.user_confirmed)


def serialize(ref: Reference, style: str | None = None) -> dict:
    style = style if style in STYLES else ref.style
    return {
        "id": ref.id,
        "type": ref.type,
        "metadata": ref.data,
        "retrieved": ref.retrieved,
        "source": ref.source,
        "pinpoint": ref.pinpoint,
        "style": ref.style,
        "notes": ref.notes,
        "tags": ref.tags or [],
        "favorite": ref.favorite,
        "user_confirmed": ref.user_confirmed,
        "collection_ids": [c.id for c in ref.collections],
        "created_at": ref.created_at.isoformat(),
        "updated_at": ref.updated_at.isoformat(),
        "citations": cite(ref.data, style, ref.pinpoint),
        "verification": verification_of(ref),
    }


def user_references(db: Session, user: User) -> list[Reference]:
    query = select(Reference).where(Reference.user_id == user.id).options(selectinload(Reference.collections))
    return list(db.scalars(query.order_by(Reference.created_at.desc(), Reference.id.desc())))


def get_reference(db: Session, user: User, ref_id: int) -> Reference:
    ref = db.scalar(select(Reference).where(Reference.id == ref_id, Reference.user_id == user.id))
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reference not found.")
    return ref


def _collections(db: Session, user: User, ids: list[int]) -> list[Collection]:
    if not ids:
        return []
    found = list(db.scalars(select(Collection).where(Collection.user_id == user.id, Collection.id.in_(ids))))
    if len(found) != len(set(ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found.")
    return found


def _describe_duplicates(matches: list[dict], refs: dict[int, Reference], style: str) -> list[dict]:
    out = []
    for match in matches:
        ref = refs[match["id"]]
        out.append({**match, "title": ref.data.get("title", ""), "type": ref.type, "citation": cite(ref.data, style)["forms"]["full"]})
    return out


# --------------------------------------------------------------------------- references

@router.get("/references")
def list_references(
    q: str = "",
    type: str = "",
    category: str = "",
    tag: str = "",
    collection_id: int | None = None,
    favorite: bool | None = None,
    verification: str = "",
    preferred_style: str = "",
    style: str = "",
    sort: str = Query("added", pattern="^(added|title|author|date)$"),
    order: str = Query("", pattern="^(asc|desc|)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    refs = user_references(db, user)
    total = len(refs)
    needle = q.strip().lower()

    def keep(ref: Reference) -> bool:
        if type and ref.type != type:
            return False
        if category == "legal" and ref.type not in LEGAL_TYPES:
            return False
        if category == "academic" and ref.type in LEGAL_TYPES:
            return False
        if tag and tag.lower() not in [t.lower() for t in ref.tags or []]:
            return False
        if collection_id is not None and collection_id not in [c.id for c in ref.collections]:
            return False
        if favorite is not None and ref.favorite != favorite:
            return False
        if preferred_style and ref.style != preferred_style:
            return False
        if verification and verification_of(ref)["status"] != verification:
            return False
        if needle:
            names = " ".join(f"{p.get('given', '')} {p.get('family', '')} {p.get('literal', '')}" for key in ("authors", "editors") for p in people(ref.data, key))
            haystack = " ".join([names, ref.notes or "", " ".join(ref.tags or [])] + [str(v) for v in ref.data.values() if isinstance(v, str)]).lower()
            return all(word in haystack for word in needle.split())
        return True

    refs = [r for r in refs if keep(r)]
    if sort == "title":
        refs.sort(key=lambda r: sort_key({"type": "case", "title": r.data.get("title", "")}), reverse=order == "desc")
    elif sort == "author":
        refs.sort(key=lambda r: sort_key(r.data), reverse=order == "desc")
    elif sort == "date":
        refs.sort(key=lambda r: year_of(r.data) or "0000", reverse=order != "asc")
    elif order == "asc":
        refs.reverse()
    tags = sorted({t for r in user_references(db, user) for t in r.tags or []}, key=str.lower)
    return {"total": total, "count": len(refs), "tags": tags, "items": [serialize(r, style or None) for r in refs]}


@router.post("/references", status_code=status.HTTP_201_CREATED)
def create_reference(body: ReferenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    metadata = normalise_metadata(body.metadata)
    if not metadata.get("title"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A title or case name is required.")
    style = body.style if body.style in STYLES else user.default_style
    existing = user_references(db, user)
    if not body.allow_duplicate:
        matches = find_duplicates(metadata, [(r.id, r.data) for r in existing])
        if matches:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "message": "This source may already be in your library.",
                    "duplicates": _describe_duplicates(matches, {r.id: r for r in existing}, style),
                },
            )
    source = _source(body.source)
    ref = Reference(
        user_id=user.id,
        type=metadata["type"],
        data=metadata,
        retrieved=normalise_metadata(body.retrieved) if source and body.retrieved else None,
        source=source,
        pinpoint=normalise_pinpoint(body.pinpoint),
        style=style,
        notes=body.notes.strip(),
        tags=clean_tags(body.tags),
        favorite=body.favorite,
        user_confirmed=body.user_confirmed,
        collections=_collections(db, user, body.collection_ids),
    )
    db.add(ref)
    db.commit()
    return serialize(ref)


@router.post("/references/duplicates")
def check_duplicates(body: DuplicateCheck, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    existing = [r for r in user_references(db, user) if r.id != body.exclude_id]
    matches = find_duplicates(normalise_metadata(body.metadata), [(r.id, r.data) for r in existing])
    return {"duplicates": _describe_duplicates(matches, {r.id: r for r in existing}, user.default_style)}


@router.get("/references/duplicates")
def library_duplicates(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    refs = {r.id: r for r in user_references(db, user)}
    groups = duplicate_groups([(r.id, r.data) for r in sorted(refs.values(), key=lambda r: r.id)])
    return {"groups": [{"reasons": gr["reasons"], "items": [serialize(refs[i]) for i in gr["ids"]]} for gr in groups]}


@router.get("/references/{ref_id}")
def read_reference(ref_id: int, style: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return serialize(get_reference(db, user, ref_id), style or None)


@router.patch("/references/{ref_id}")
def update_reference(ref_id: int, body: ReferencePatch, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ref = get_reference(db, user, ref_id)
    if body.metadata is not None:
        metadata = normalise_metadata(body.metadata)
        if not metadata.get("title"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A title or case name is required.")
        if metadata != ref.data and body.user_confirmed is None:
            ref.user_confirmed = False  # edited details need a fresh review
        ref.data, ref.type = metadata, metadata["type"]
    if body.clear_pinpoint:
        ref.pinpoint = None
    elif body.pinpoint is not None:
        ref.pinpoint = normalise_pinpoint(body.pinpoint)
    if body.style is not None:
        if body.style not in STYLES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown citation style.")
        ref.style = body.style
    if body.notes is not None:
        ref.notes = body.notes.strip()
    if body.tags is not None:
        ref.tags = clean_tags(body.tags)
    if body.favorite is not None:
        ref.favorite = body.favorite
    if body.user_confirmed is not None:
        ref.user_confirmed = body.user_confirmed
    if body.collection_ids is not None:
        ref.collections = _collections(db, user, body.collection_ids)
    db.commit()
    return serialize(ref)


@router.delete("/references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(ref_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    db.delete(get_reference(db, user, ref_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/references/{ref_id}/merge")
def merge_reference(ref_id: int, body: MergeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Merge ``source_id`` into ``ref_id``, at the user's request.

    The kept reference wins wherever both have a value; gaps are filled from the
    other, notes, tags and collections are combined, and the other is removed.
    """
    if body.source_id == ref_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose two different references.")
    target, other = get_reference(db, user, ref_id), get_reference(db, user, body.source_id)
    merged = dict(target.data)
    for key, value in other.data.items():
        if key != "type" and key not in merged:
            merged[key] = value
    target.data = normalise_metadata(merged)
    if target.retrieved is None and other.retrieved is not None:
        target.retrieved, target.source = other.retrieved, other.source
    target.tags = clean_tags((target.tags or []) + (other.tags or []))
    if other.notes and other.notes not in target.notes:
        target.notes = "\n\n".join(x for x in [target.notes, other.notes] if x)
    target.favorite = target.favorite or other.favorite
    target.pinpoint = target.pinpoint or other.pinpoint
    for collection in other.collections:
        if collection not in target.collections:
            target.collections.append(collection)
    db.delete(other)
    db.commit()
    return serialize(target)


# --------------------------------------------------------------------------- collections

def _collection(c: Collection) -> dict:
    return {"id": c.id, "name": c.name, "description": c.description, "kind": c.kind, "count": len(c.references), "created_at": c.created_at.isoformat()}


def _get_collection(db: Session, user: User, collection_id: int) -> Collection:
    collection = db.scalar(select(Collection).where(Collection.id == collection_id, Collection.user_id == user.id))
    if collection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found.")
    return collection


def _kind(kind: str) -> str:
    if kind not in ("research", "moot"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Collection kind must be 'research' or 'moot'.")
    return kind


@router.get("/collections")
def list_collections(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    query = select(Collection).where(Collection.user_id == user.id).order_by(Collection.name)
    return [_collection(c) for c in db.scalars(query)]


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    collection = Collection(user_id=user.id, name=body.name.strip(), description=body.description.strip(), kind=_kind(body.kind))
    db.add(collection)
    db.commit()
    return _collection(collection)


@router.patch("/collections/{collection_id}")
def update_collection(collection_id: int, body: CollectionPatch, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    collection = _get_collection(db, user, collection_id)
    if body.name is not None:
        collection.name = body.name.strip()
    if body.description is not None:
        collection.description = body.description.strip()
    if body.kind is not None:
        collection.kind = _kind(body.kind)
    db.commit()
    return _collection(collection)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Delete a collection. The references in it stay in the library."""
    db.delete(_get_collection(db, user, collection_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/collections/{collection_id}/references/{ref_id}")
def add_to_collection(collection_id: int, ref_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    collection, ref = _get_collection(db, user, collection_id), get_reference(db, user, ref_id)
    if ref not in collection.references:
        collection.references.append(ref)
        db.commit()
    return _collection(collection)


@router.delete("/collections/{collection_id}/references/{ref_id}")
def remove_from_collection(collection_id: int, ref_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    collection, ref = _get_collection(db, user, collection_id), get_reference(db, user, ref_id)
    if ref in collection.references:
        collection.references.remove(ref)
        db.commit()
    return _collection(collection)


# --------------------------------------------------------------------------- dashboard

@router.get("/stats")
def stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    refs = user_references(db, user)
    by_status = {key: 0 for key in STATUS_LABELS}
    for ref in refs:
        by_status[verification_of(ref)["status"]] += 1
    return {
        "total": len(refs),
        "legal": sum(r.type in LEGAL_TYPES for r in refs),
        "academic": sum(r.type not in LEGAL_TYPES for r in refs),
        "by_type": {t: sum(r.type == t for r in refs) for t in SOURCE_TYPES},
        "verification": by_status,
        "collections": len(user.collections),
        "recent": [serialize(r, user.default_style) for r in refs[:5]],
        "favorites": [serialize(r, user.default_style) for r in refs if r.favorite][:5],
    }
