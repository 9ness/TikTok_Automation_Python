"""Provisión de EditorUser a partir de una cuenta web (nebulabs-media).

Convierte una cuenta del front de cliente (guardada en `nebulabs:user:{email}`)
en un EditorUser de config, vinculado por `account_email`. Lo usan tanto el
botón manual del panel ("Cuentas web → Crear usuario") como la subida web
(auto-provisión la primera vez que el cliente contacta con el box).

Idempotente: si ya existe un EditorUser vinculado a ese email, lo devuelve.
"""

from __future__ import annotations

import re
import unicodedata

from src.editor_auto.config import ensure_user_folders, user_folder
from src.editor_auto.models import EditorUser
from src.editor_auto.repos import UserRepo
from src.editor_auto.repos.web_account_repo import get_web_account_repo
from src.editor_auto.services.style_mapper import build_tool_flow


def unique_user_name(base: str) -> str:
    """Slug único para el nombre de carpeta. Añade sufijo si ya existe."""
    s = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "cliente"
    repo = UserRepo()
    if repo.get_by_name(s) is None:
        return s
    n = 2
    while repo.get_by_name(f"{s}_{n}") is not None:
        n += 1
    return f"{s}_{n}"


def provision_from_web(email: str) -> EditorUser | None:
    """Crea (o devuelve) el EditorUser vinculado a `email`.

    - Si ya hay uno vinculado por account_email → lo devuelve (no duplica).
    - Si existe la cuenta web → crea el EditorUser (carpeta + flujo del estilo).
    - Si NO existe cuenta web con ese email → devuelve None.
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return None

    repo = UserRepo()
    account = get_web_account_repo().get(email)
    existing = repo.get_by_account_email(email)
    if existing is not None and not existing.deleted:
        # Re-sincroniza el flujo con el estilo ACTUAL de la web (fuente de
        # verdad) — así el preview del panel refleja lo que el cliente eligió
        # sin esperar a un "Mandar a edición".
        if account is not None:
            new_flow = build_tool_flow(account.get("styleConfig"))
            if [s.model_dump() for s in existing.tool_flow] != [s.model_dump() for s in new_flow]:
                existing.tool_flow = new_flow
                repo.save(existing)
        return existing

    if account is None:
        return None

    username = (account.get("username") or "").strip()
    web_name = (account.get("name") or email.split("@")[0]).strip()
    name = unique_user_name(username or web_name or email.split("@")[0])

    try:
        ensure_user_folders(name)
    except OSError as e:
        print(f"[provision_service] ensure_user_folders falló: {e}")

    user = EditorUser(
        name=name,
        display_name=web_name or name,
        description="Creado automáticamente desde la web de cliente",
        tool_flow=build_tool_flow(account.get("styleConfig")),
        account_email=email,
        drive_folder=user_folder(name),
    )
    repo.save(user)
    return user
