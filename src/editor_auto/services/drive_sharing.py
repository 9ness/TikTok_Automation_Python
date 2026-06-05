"""Wrapper de Google Drive API para compartir carpetas del Editor Auto.

Caso de uso: el admin entra al panel del usuario `bugalleitor`, pulsa
"Compartir" en una carpeta, mete un gmail y la persona recibe acceso
de solo lectura (Drive "viewer") a `entrada/` y `salida/` — pero NO a
las otras carpetas (cola, recuperacion) ni a las carpetas de otros
usuarios.

Diseño:
- Autenticación con Service Account (clave JSON local en
  `GOOGLE_SA_KEY_PATH`). Sin OAuth flow, sin refresh tokens.
- Resolución de folder IDs por navegación: buscamos por nombre dentro
  del padre. Los IDs se cachean en memoria (LRU) — invalidamos si una
  operación falla por 404.
- Permissions: `type=user role=reader` con `sendNotificationEmail=True`
  para que la persona reciba el email de Drive con el link.

Scopes:
- `https://www.googleapis.com/auth/drive` — necesario porque queremos
  manejar carpetas que NO ha creado el SA (compartidas por ness4b).

Pre-requisito (one-time setup):
1. Crear SA en GCP → descargar JSON key.
2. Compartir `TIKTOK_EDITOR/` con el email del SA como Editor desde
   drive.google.com. Sin esto el SA no ve ninguna carpeta.
3. Subir JSON a `secrets/google-sa.json` del server + bind-mount al
   container + `GOOGLE_SA_KEY_PATH=/app/secrets/google-sa.json` en .env.
"""

from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any

# La carpeta raíz del Editor Auto en Drive. Sus subcarpetas son
# `Usuarios/<user>/{entrada,cola,recuperacion,salida}/`. Cambiable por
# env si en el futuro tenemos varios entornos.
DRIVE_ROOT_NAME = os.getenv("DRIVE_EDITOR_ROOT_NAME", "TIKTOK_EDITOR")
DRIVE_USERS_FOLDER = "Usuarios"

# Carpetas que se pueden compartir desde la UI. cola/recuperacion quedan
# fuera por defecto — son internas del flujo. El admin puede pedir share
# de cualquiera vía el endpoint, pero la UI solo ofrece estas dos.
SHAREABLE_FOLDERS = {"entrada", "cola", "recuperacion", "salida"}
DEFAULT_SHARE_FOLDERS = ("entrada", "salida")

# Rol que NECESITA cada carpeta según su función:
#  - `entrada`: el cliente SUBE sus vídeos → necesita ESCRITURA (writer). Con
#    solo lectura no puede subir nada.
#  - `salida`: el cliente solo DESCARGA el vídeo editado → con lectura basta.
#  - `cola`/`recuperacion`: internas; si se comparten, lectura.
# Se usa cuando no se pasa un `role` explícito → cada carpeta recibe el suyo.
_FOLDER_DEFAULT_ROLE = {
    "entrada": "writer",
    "cola": "reader",
    "recuperacion": "reader",
    "salida": "reader",
}


class DriveSharingError(Exception):
    """Error de operación Drive (autenticación, folder not found,
    quota). El router lo traduce a HTTP 400/404/500."""


# ---------------------------------------------------------------------------
# Authentication — Service Account
# ---------------------------------------------------------------------------
_service_lock = threading.Lock()
_service_cache: dict[str, Any] = {"v": None}


def is_configured() -> bool:
    """¿Hay un SA key file configurado? Permite a la UI ocultar la
    sección de sharing si el operador aún no completó el setup."""
    path = os.getenv("GOOGLE_SA_KEY_PATH")
    return bool(path and os.path.isfile(path))


def _service():
    """Cliente `drive.v3` reusable. Cacheado a nivel proceso. Thread-safe
    para el JobQueue worker + las requests FastAPI concurrentes."""
    if _service_cache["v"] is not None:
        return _service_cache["v"]
    with _service_lock:
        if _service_cache["v"] is not None:
            return _service_cache["v"]
        path = os.getenv("GOOGLE_SA_KEY_PATH")
        if not path or not os.path.isfile(path):
            raise DriveSharingError(
                "GOOGLE_SA_KEY_PATH no configurada o el archivo no existe. "
                "Sube la JSON del Service Account a secrets/google-sa.json "
                "del server y define la env var."
            )
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as e:
            raise DriveSharingError(
                f"Faltan deps google-api-python-client / google-auth: {e}"
            )
        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/drive"],
        )
        # `cache_discovery=False` evita el warning de googleapiclient
        # `file_cache is only supported with oauth2client<4.0.0`.
        svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        _service_cache["v"] = svc
        return svc


_creds_cache: dict[str, Any] = {"v": None}


def access_token() -> str:
    """Token OAuth de la Service Account (refrescado). Lo usa el broker de
    subida directa a Drive para crear sesiones resumable que el navegador
    del cliente sube directamente (los bytes no pasan por el VPS)."""
    path = os.getenv("GOOGLE_SA_KEY_PATH")
    if not path or not os.path.isfile(path):
        raise DriveSharingError("GOOGLE_SA_KEY_PATH no configurada.")
    creds = _creds_cache["v"]
    if creds is None:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/drive"],
        )
        _creds_cache["v"] = creds
    if not creds.valid:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds.token


def sa_email() -> str | None:
    """Email del SA según la JSON — útil para mostrarlo en la UI
    ("compartido por nebulabs-editor@…") y para diagnóstico."""
    path = os.getenv("GOOGLE_SA_KEY_PATH")
    if not path or not os.path.isfile(path):
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("client_email")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Folder resolution
# ---------------------------------------------------------------------------
def _escape_q(s: str) -> str:
    """Escapa apóstrofos para las queries Drive `q=`. Las querys usan
    delimitadores `'…'`, así que `O'Brien` rompería el parser."""
    return s.replace("'", "\\'")


def _find_child_folder_id(parent_id: str | None, name: str) -> str | None:
    """Busca una carpeta hija por nombre exacto. `parent_id=None` busca
    a nivel global del SA (cualquier carpeta visible)."""
    svc = _service()
    name_safe = _escape_q(name)
    q_parts = [
        f"name = '{name_safe}'",
        "mimeType = 'application/vnd.google-apps.folder'",
        "trashed = false",
    ]
    if parent_id:
        q_parts.append(f"'{parent_id}' in parents")
    results = svc.files().list(
        q=" and ".join(q_parts),
        fields="files(id, name)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    if not files:
        return None
    return files[0]["id"]


@lru_cache(maxsize=1)
def _root_folder_id() -> str:
    """ID del folder raíz `TIKTOK_EDITOR/`. Cacheado para vida del proceso
    porque el ID no cambia salvo que el operador re-cree la carpeta."""
    fid = _find_child_folder_id(parent_id=None, name=DRIVE_ROOT_NAME)
    if not fid:
        raise DriveSharingError(
            f"No encuentro la carpeta {DRIVE_ROOT_NAME!r} en el Drive del "
            f"Service Account. Comprueba que has compartido esa carpeta "
            f"con {sa_email() or '<SA email>'} como Editor."
        )
    return fid


@lru_cache(maxsize=256)
def _users_folder_id() -> str:
    """ID del folder `TIKTOK_EDITOR/Usuarios/`."""
    fid = _find_child_folder_id(_root_folder_id(), DRIVE_USERS_FOLDER)
    if not fid:
        raise DriveSharingError(
            f"No encuentro {DRIVE_USERS_FOLDER!r} dentro de "
            f"{DRIVE_ROOT_NAME!r}. ¿Está la carpeta sincronizada en Drive?"
        )
    return fid


@lru_cache(maxsize=512)
def _user_folder_id(username: str) -> str:
    """ID del folder del usuario `Usuarios/<username>/`."""
    fid = _find_child_folder_id(_users_folder_id(), username)
    if not fid:
        raise DriveSharingError(
            f"No encuentro la carpeta del usuario {username!r} en Drive. "
            f"¿El cliente rclone del server la ha sincronizado ya?"
        )
    return fid


def _subfolder_id(username: str, folder: str) -> str:
    """ID de una subcarpeta concreta: entrada/cola/recuperacion/salida."""
    if folder not in SHAREABLE_FOLDERS:
        raise DriveSharingError(f"Carpeta inválida: {folder!r}")
    parent = _user_folder_id(username)
    fid = _find_child_folder_id(parent, folder)
    if not fid:
        raise DriveSharingError(
            f"No encuentro {folder!r} en {username!r}/ en Drive."
        )
    return fid


def invalidate_cache_for_user(username: str) -> None:
    """Invalida el cache de IDs si una operación falla con 404 (carpeta
    fue movida/borrada). El siguiente lookup re-buscará."""
    # functools.lru_cache no permite invalidar entradas individuales →
    # limpiamos todos los caches relacionados.
    _user_folder_id.cache_clear()
    _users_folder_id.cache_clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def share_folders(
    username: str,
    email: str,
    folders: list[str] | None = None,
    role: str | None = None,
    notify: bool = True,
) -> list[dict[str, Any]]:
    """Comparte las subcarpetas indicadas de `username` con `email`.

    Por defecto comparte `entrada` y `salida` (lo que el cliente
    necesita ver). Devuelve lista de permissions creados — uno por
    carpeta, con `{folder, permission_id, role, email}`.

    `role`:
      - None (default) → cada carpeta recibe el rol que NECESITA según su
        función (`entrada` writer para que el cliente pueda SUBIR, `salida`
        reader porque solo DESCARGA). Es lo correcto en el 99% de los casos.
      - "reader"/"commenter"/"writer" → fuerza ESE rol en todas las carpetas
        (override manual).

    Si el email ya tiene acceso a alguna carpeta, la API devuelve un
    permiso existente — no falla. `notify=False` evita el email
    automático de Drive (útil para re-shares silenciosos).
    """
    if role is not None and role not in ("reader", "commenter", "writer"):
        raise DriveSharingError(f"Role no permitido: {role!r}")
    targets = folders or list(DEFAULT_SHARE_FOLDERS)
    invalid = [f for f in targets if f not in SHAREABLE_FOLDERS]
    if invalid:
        raise DriveSharingError(
            f"Carpetas no permitidas: {invalid}. Válidas: {sorted(SHAREABLE_FOLDERS)}"
        )
    svc = _service()
    results: list[dict[str, Any]] = []
    for folder in targets:
        folder_id = _subfolder_id(username, folder)
        # Rol efectivo: el forzado, o el que necesita la carpeta por su función.
        eff_role = role or _FOLDER_DEFAULT_ROLE.get(folder, "reader")
        body = {"type": "user", "role": eff_role, "emailAddress": email}
        try:
            perm = svc.permissions().create(
                fileId=folder_id,
                body=body,
                sendNotificationEmail=notify,
                supportsAllDrives=True,
                fields="id,emailAddress,role,type,displayName",
            ).execute()
        except Exception as e:
            raise DriveSharingError(
                f"Fallo compartiendo {folder!r} con {email!r}: {e}"
            )
        results.append({
            "folder": folder,
            "folder_id": folder_id,
            "permission_id": perm.get("id"),
            "email": perm.get("emailAddress", email),
            "role": perm.get("role", eff_role),
            "type": perm.get("type", "user"),
            "display_name": perm.get("displayName"),
        })
    return results


def _list_folder_perms(folder_id: str) -> list[dict[str, Any]]:
    """Lista permissions de un folder concreto. Filtra owner + SA + tipos
    no-user (domain, anyone). Devuelve lista normalizada."""
    svc = _service()
    sa = sa_email()
    try:
        resp = svc.permissions().list(
            fileId=folder_id,
            supportsAllDrives=True,
            fields="permissions(id,emailAddress,role,type,displayName)",
            pageSize=100,
        ).execute()
    except Exception as e:
        raise DriveSharingError(f"Fallo listando perms: {e}")
    perms = resp.get("permissions", []) or []
    return [
        {
            "permission_id": p.get("id"),
            "email": p.get("emailAddress"),
            "role": p.get("role"),
            "type": p.get("type"),
            "display_name": p.get("displayName"),
            "folder_id": folder_id,
        }
        for p in perms
        if p.get("role") != "owner"
        and p.get("emailAddress") != sa
        and p.get("type") == "user"
    ]


def list_shares(username: str) -> dict[str, list[dict[str, Any]]]:
    """Lista permissions DIRECTOS sobre cada subcarpeta del usuario.

    Returns:
        {entrada: [{id, email, role, ...}, ...], cola: […], ...}
    Filtra el owner y el SA. NO incluye perms heredados de carpetas
    padre — para eso usar `list_inherited_shares()`.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for folder in SHAREABLE_FOLDERS:
        try:
            folder_id = _subfolder_id(username, folder)
        except DriveSharingError:
            out[folder] = []
            continue
        out[folder] = _list_folder_perms(folder_id)
    return out


def list_inherited_shares(username: str) -> list[dict[str, Any]]:
    """Permisos en carpetas PADRE que se heredan a entrada/salida del
    usuario. Drive no marca explícitamente la herencia: si compartes
    TIKTOK_EDITOR/ con `X@gmail.com`, ese email tiene acceso efectivo a
    todas las subcarpetas pero NO aparece en `permissions.list(entrada/)`.

    Esta función recorre los 3 niveles padre:
        TIKTOK_EDITOR/ → todos los usuarios + carpetas
        TIKTOK_EDITOR/Usuarios/ → todos los usuarios + carpetas
        TIKTOK_EDITOR/Usuarios/<user>/ → entrada, cola, recuperacion, salida

    Para cada permission devuelve `{..., inherited_from}` indicando el
    nivel padre. El frontend lo muestra como read-only (revocar
    requeriría tocar la carpeta padre, riesgo de cascada).
    """
    items: list[dict[str, Any]] = []
    seen_emails_per_level: dict[str, set[str]] = {}

    levels: list[tuple[str, str]] = []
    try:
        levels.append(("TIKTOK_EDITOR", _root_folder_id()))
    except DriveSharingError:
        return items  # sin acceso al root, no hay nada
    try:
        levels.append(("Usuarios", _users_folder_id()))
    except DriveSharingError:
        pass
    try:
        levels.append((username, _user_folder_id(username)))
    except DriveSharingError:
        pass

    for level_name, folder_id in levels:
        try:
            perms = _list_folder_perms(folder_id)
        except DriveSharingError:
            continue
        seen = set()
        for p in perms:
            email = (p.get("email") or "").lower()
            if not email:
                continue
            # Si ya lo vimos en un nivel SUPERIOR, lo skip — atribuimos al
            # padre más cercano (más específico).
            if any(email in s for s in seen_emails_per_level.values()):
                continue
            seen.add(email)
            items.append({
                **p,
                "inherited_from": level_name,
            })
        seen_emails_per_level[level_name] = seen
    return items


def revoke_permission(
    username: str,
    folder: str,
    permission_id: str,
) -> str:
    """Revoca un permission. Devuelve el nivel donde se revocó realmente.

    Cascade automático: si el permiso es heredado de una carpeta padre
    (Drive devuelve `cannotDeletePermission` con código 403), intenta
    revocarlo desde el nivel padre más próximo. Esto es necesario porque
    el `permission_id` que el frontend ve en una subcarpeta es el MISMO
    perm que vive en la padre — Drive no permite "des-heredar" en el
    hijo; solo se puede borrar donde realmente está.

    Niveles en orden (de hijo a padre):
      1. `entrada/` o `salida/` (subcarpeta — el caso normal)
      2. `<usuario>/` (raíz del usuario — afecta a todas sus subcarpetas)
      3. `Usuarios/` (todos los usuarios)
      4. `TIKTOK_EDITOR/` (toda la app)

    Devuelve el nombre del nivel donde el delete tuvo éxito (`"subcarpeta"`,
    `"usuario"`, `"Usuarios"` o `"TIKTOK_EDITOR"`) para que el caller
    pueda avisar al operador si la revocación cascadeó más arriba de lo
    esperado.
    """
    svc = _service()

    # Construimos la lista de candidatos hijo→padre.
    levels: list[tuple[str, str]] = []
    try:
        levels.append(("subcarpeta", _subfolder_id(username, folder)))
    except DriveSharingError:
        pass
    try:
        levels.append(("usuario", _user_folder_id(username)))
    except DriveSharingError:
        pass
    try:
        levels.append(("Usuarios", _users_folder_id()))
    except DriveSharingError:
        pass
    try:
        levels.append(("TIKTOK_EDITOR", _root_folder_id()))
    except DriveSharingError:
        pass

    if not levels:
        raise DriveSharingError(
            f"No se resolvió ningún folder_id para usuario {username!r} "
            f"/ carpeta {folder!r}."
        )

    last_err: Exception | None = None
    for level_name, folder_id in levels:
        try:
            svc.permissions().delete(
                fileId=folder_id,
                permissionId=permission_id,
                supportsAllDrives=True,
            ).execute()
            return level_name
        except Exception as e:
            err_str = str(e)
            last_err = e
            # Errores recuperables que indican "el perm no está en ESTE
            # nivel" → seguimos cascadeando al padre:
            #   - cannotDeletePermission: heredado, no se puede borrar aquí
            #   - 404 / notFound: el perm no existe en este folder
            recoverable_markers = (
                "cannotDeletePermission",
                "permissionNotFound",
                "notFound",
                "404",
            )
            if any(m.lower() in err_str.lower() for m in recoverable_markers):
                continue
            # Cualquier otro error es fatal — no seguimos cascadeando.
            raise DriveSharingError(
                f"Fallo revocando perm {permission_id!r} en nivel "
                f"{level_name!r}: {e}"
            )

    raise DriveSharingError(
        f"No se pudo revocar perm {permission_id!r} en ningún nivel "
        f"(probé {[n for n, _ in levels]}). Último error: {last_err}"
    )
