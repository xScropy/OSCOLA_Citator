"""Accounts: registration, sign-in, preferences and account deletion."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, hash_password, verify_password
from ..citation.engine import STYLES
from ..db import User, get_db
from ..export import FORMATS

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)


class Preferences(BaseModel):
    default_style: str | None = None
    default_export_format: str | None = None


class PasswordConfirmation(BaseModel):
    password: str


def _user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "default_style": user.default_style,
        "default_export_format": user.default_export_format,
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a valid email address.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": create_token(user.id), "user": _user(user)}


@router.post("/login")
def login(body: Credentials, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return {"token": create_token(user.id), "user": _user(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user(user)


@router.patch("/me")
def update_me(body: Preferences, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.default_style is not None:
        if body.default_style not in STYLES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown citation style.")
        user.default_style = body.default_style
    if body.default_export_format is not None:
        if body.default_export_format not in FORMATS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown export format.")
        user.default_export_format = body.default_export_format
    db.add(user)
    db.commit()
    return _user(user)


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(body: PasswordConfirmation, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Permanently delete the account with every saved reference and collection."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password.")
    db.delete(db.get(User, user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
