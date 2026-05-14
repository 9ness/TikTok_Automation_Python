"""Compartir carpetas del usuario Editor Auto con emails concretos vía
Google Drive API.

Endpoints:
    GET    /users/{id}/shares           — lista perms activos (por carpeta)
    POST   /users/{id}/shares           — comparte (body: email, folders?)
    DELETE /users/{id}/shares/{pid}     — revoca perm
    GET    /sharing/status              — ¿SA configurado? (UI lo usa para
                                          mostrar/ocultar la sección)

Auth: header `X-API-Key` (dependencia del router). Permission IDs son
generados por Drive — opacos para nuestro backend.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.api.dependencies import get_current_user
from src.api.exceptions import ValidationError
from src.editor_auto.repos import UserRepo
from src.editor_auto.services import drive_sharing


router = APIRouter(
    prefix="/api/v1/editor-auto",
    tags=["editor-auto · sharing"],
    dependencies=[Depends(get_current_user)],
)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user_or_raise(user_id: str):
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None or u.deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario no encontrado o eliminado: {user_id}",
        )
    return u


def _validate_email(email: str) -> str:
    """Saneo básico — Drive valida estrictamente del lado servidor, pero
    rechazamos errores tipográficos obvios antes de hacer la llamada."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationError(f"Email inválido: {email!r}")
    return email


@router.get("/sharing/status")
def sharing_status() -> dict[str, Any]:
    """¿Está el Service Account configurado? La UI lo consume al cargar
    la pestaña para mostrar (si no): un mensaje con la guía de setup."""
    return {
        "configured": drive_sharing.is_configured(),
        "service_account_email": drive_sharing.sa_email(),
    }


@router.get("/users/{user_id}/shares")
def list_user_shares(user_id: str) -> dict[str, Any]:
    """Lista los permissions activos en `entrada`, `cola`, `recuperacion`,
    `salida` del usuario + el conjunto de `known_emails` (memorizados al
    compartir por primera vez). El frontend usa los known_emails para
    mostrar filas incluso si el email no tiene acceso activo a ninguna
    carpeta — facilita re-conceder con un click."""
    u = _user_or_raise(user_id)
    try:
        shares = drive_sharing.list_shares(u.name)
    except drive_sharing.DriveSharingError as e:
        raise ValidationError(str(e))
    return {
        "user_id": u.id,
        "user_name": u.name,
        "shares": shares,
        "known_emails": list(u.known_share_emails or []),
    }


@router.post("/users/{user_id}/shares")
def create_user_share(
    user_id: str,
    payload: Annotated[dict, Body(...)],
) -> dict[str, Any]:
    """Comparte una o varias subcarpetas con un email. Body:
        {
            email: "alguien@gmail.com",
            folders: ["entrada", "salida"]    // default si se omite
            role: "reader" | "commenter" | "writer"   // default "reader"
            notify: bool                       // default true (email Drive)
        }

    Side-effect: el email se añade a `user.known_share_emails` la primera
    vez que se comparte algo con él, para que la UI lo recuerde y permita
    re-conceder/revocar rápido sin re-tipearlo.
    """
    u = _user_or_raise(user_id)
    email = _validate_email(payload.get("email") or "")
    folders = payload.get("folders") or None
    role = (payload.get("role") or "reader").strip()
    notify = bool(payload.get("notify", True))
    try:
        results = drive_sharing.share_folders(
            username=u.name,
            email=email,
            folders=folders,
            role=role,
            notify=notify,
        )
    except drive_sharing.DriveSharingError as e:
        raise ValidationError(str(e))

    # Persistir el email en known_share_emails si es nuevo. Insensible a
    # mayúsculas (todos ya en lowercase por _validate_email).
    if email not in (u.known_share_emails or []):
        u.known_share_emails = [*(u.known_share_emails or []), email]
        UserRepo().save(u)

    return {
        "user_id": u.id,
        "user_name": u.name,
        "shared": results,
    }


@router.delete("/users/{user_id}/known-emails/{email}")
def forget_known_email(user_id: str, email: str) -> dict[str, Any]:
    """Elimina un email de la lista `known_share_emails` del usuario.

    NO revoca permisos activos en Drive — solo lo quita de la "agenda"
    para que la UI deje de mostrarlo. Si la persona tiene accesos
    activos, primero hay que revocarlos con DELETE /shares/{pid}.
    """
    u = _user_or_raise(user_id)
    e = (email or "").strip().lower()
    if not e:
        raise ValidationError("Email vacío.")
    if e in (u.known_share_emails or []):
        u.known_share_emails = [x for x in u.known_share_emails if x != e]
        UserRepo().save(u)
    return {"user_id": u.id, "email": e, "removed": True}


@router.delete("/users/{user_id}/shares/{permission_id}")
def revoke_user_share(
    user_id: str,
    permission_id: str,
    folder: str,
) -> dict[str, Any]:
    """Revoca un permission concreto. Query: `?folder=entrada` (necesario
    porque Drive scope-a los permission IDs por archivo)."""
    u = _user_or_raise(user_id)
    try:
        drive_sharing.revoke_permission(u.name, folder, permission_id)
    except drive_sharing.DriveSharingError as e:
        raise ValidationError(str(e))
    return {
        "user_id": u.id,
        "user_name": u.name,
        "folder": folder,
        "permission_id": permission_id,
        "revoked": True,
    }
