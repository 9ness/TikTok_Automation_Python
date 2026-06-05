"""Subida DIRECTA del cliente a Google Drive (los bytes no pasan por el VPS).

Usa OAuth del DUEÑO del Drive (la cuenta `nebulabsaimedia`, la misma del
rclone-mount) — NO la Service Account — porque las SA no tienen cuota en "Mi
unidad" y `files.create` fallaría con storageQuotaExceeded. Con el OAuth del
dueño, los archivos los posee el usuario (con cuota) y todo funciona.

Modelo: el box crea una sesión resumable para `entrada/<día>/` y devuelve la
URL al navegador. El navegador sube los bytes DIRECTO a Google (con %). El
rclone-mount ve el archivo on-demand y el runner lo procesa solo al editar.

Env (box):
    DRIVE_OAUTH_CLIENT_ID
    DRIVE_OAUTH_CLIENT_SECRET
    DRIVE_OAUTH_REFRESH_TOKEN   (consentimiento único — ver scripts/get_drive_refresh_token.py)
"""

from __future__ import annotations

import os
import threading
from typing import Any

import requests

DRIVE_ROOT_NAME = os.getenv("DRIVE_EDITOR_ROOT_NAME", "TIKTOK_EDITOR")
DRIVE_USERS_FOLDER = "Usuarios"
_SCOPE = "https://www.googleapis.com/auth/drive"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_RESUMABLE_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=resumable&supportsAllDrives=true"
)
_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")

_lock = threading.Lock()
_creds_cache: dict[str, Any] = {"v": None}
_svc_cache: dict[str, Any] = {"v": None}


def is_configured() -> bool:
    return bool(
        os.getenv("DRIVE_OAUTH_CLIENT_ID")
        and os.getenv("DRIVE_OAUTH_CLIENT_SECRET")
        and os.getenv("DRIVE_OAUTH_REFRESH_TOKEN")
    )


def _creds():
    if _creds_cache["v"] is not None:
        return _creds_cache["v"]
    with _lock:
        if _creds_cache["v"] is not None:
            return _creds_cache["v"]
        if not is_configured():
            raise RuntimeError(
                "Subida a Drive no configurada: faltan DRIVE_OAUTH_CLIENT_ID / "
                "DRIVE_OAUTH_CLIENT_SECRET / DRIVE_OAUTH_REFRESH_TOKEN."
            )
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None,
            refresh_token=os.getenv("DRIVE_OAUTH_REFRESH_TOKEN"),
            client_id=os.getenv("DRIVE_OAUTH_CLIENT_ID"),
            client_secret=os.getenv("DRIVE_OAUTH_CLIENT_SECRET"),
            token_uri=_TOKEN_URI,
            scopes=[_SCOPE],
        )
        _creds_cache["v"] = creds
        return creds


def access_token() -> str:
    creds = _creds()
    if not creds.valid:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds.token


def _service():
    if _svc_cache["v"] is not None:
        return _svc_cache["v"]
    with _lock:
        if _svc_cache["v"] is not None:
            return _svc_cache["v"]
        from googleapiclient.discovery import build
        svc = build("drive", "v3", credentials=_creds(), cache_discovery=False)
        _svc_cache["v"] = svc
        return svc


def _esc(s: str) -> str:
    return s.replace("'", "\\'")


def _find_child(parent_id: str | None, name: str) -> str | None:
    svc = _service()
    q = (
        f"name = '{_esc(name)}' and trashed = false "
        f"and mimeType = 'application/vnd.google-apps.folder'"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = svc.files().list(
        q=q, fields="files(id,name)", pageSize=10,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _entrada_id(username: str) -> str | None:
    root = _find_child(None, DRIVE_ROOT_NAME)
    if not root:
        return None
    users = _find_child(root, DRIVE_USERS_FOLDER)
    if not users:
        return None
    user = _find_child(users, username)
    if not user:
        return None
    return _find_child(user, "entrada")


def _create_folder(parent_id: str, name: str) -> str:
    svc = _service()
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    created = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return created["id"]


def ensure_day_folder(username: str, day: str) -> str:
    """ID de `entrada/<día>/`, creándolo si no existe. Lanza si falta entrada/."""
    entrada = _entrada_id(username)
    if not entrada:
        raise RuntimeError(
            f"No encuentro entrada/ de '{username}' en Drive. ¿Carpetas creadas/sincronizadas?"
        )
    existing = _find_child(entrada, day)
    return existing or _create_folder(entrada, day)


def _day_folder_id(username: str, day: str) -> str | None:
    entrada = _entrada_id(username)
    if not entrada:
        return None
    return _find_child(entrada, day)


def init_resumable_session(
    folder_id: str, filename: str, *, mime: str = "video/mp4", origin: str | None = None,
) -> str:
    """Crea una sesión resumable y devuelve la URL (header Location). `origin`
    se pasa para que Google habilite CORS y el navegador haga el PUT."""
    headers = {
        "Authorization": f"Bearer {access_token()}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    if origin:
        headers["Origin"] = origin
    body = {"name": filename, "parents": [folder_id]}
    r = requests.post(_RESUMABLE_URL, headers=headers, json=body, timeout=20)
    r.raise_for_status()
    location = r.headers.get("Location")
    if not location:
        raise RuntimeError("Google no devolvió URL de subida (Location).")
    return location


def list_day_files(username: str, day: str) -> list[dict[str, Any]]:
    fid = _day_folder_id(username, day)
    if not fid:
        return []
    svc = _service()
    res = svc.files().list(
        q=f"'{fid}' in parents and trashed = false",
        fields="files(id,name,size,mimeType)",
        supportsAllDrives=True, includeItemsFromAllDrives=True, pageSize=200,
    ).execute()
    out: list[dict[str, Any]] = []
    for f in res.get("files", []):
        name = f.get("name", "")
        if name.lower().endswith(_VIDEO_EXTS):
            out.append({"id": f["id"], "filename": name, "size_bytes": int(f.get("size") or 0)})
    return out


def delete_day_file(username: str, day: str, filename: str) -> bool:
    for f in list_day_files(username, day):
        if f["filename"] == filename:
            _service().files().delete(fileId=f["id"], supportsAllDrives=True).execute()
            return True
    return False
