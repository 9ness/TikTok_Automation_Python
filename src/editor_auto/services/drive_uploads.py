"""Subida DIRECTA del cliente a Google Drive (los bytes no pasan por el VPS).

Modelo: el box (con la Service Account) crea una **sesión resumable** para un
archivo dentro de `entrada/<día>/` del usuario y devuelve la URL de subida al
navegador. El navegador sube los bytes DIRECTO a Google (con % de progreso).
Luego el rclone-mount del box ve el archivo (vfs-cache on-demand) y el runner
lo procesa solo cuando edita — nunca durante la subida. Así se reserva la
potencia del servidor para el procesamiento, no para las subidas.

Reutiliza la Service Account de `drive_sharing` (mismo scope drive). Requiere
`GOOGLE_SA_KEY_PATH` configurada (igual que el sharing).
"""

from __future__ import annotations

from typing import Any

import requests

from . import drive_sharing

_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
_RESUMABLE_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=resumable&supportsAllDrives=true"
)


def is_configured() -> bool:
    return drive_sharing.is_configured()


def ensure_day_folder(username: str, day: str) -> str:
    """Devuelve el ID de Drive de `entrada/<día>/`, creándolo si no existe."""
    svc = drive_sharing._service()  # noqa: SLF001
    entrada_id = drive_sharing._subfolder_id(username, "entrada")  # noqa: SLF001
    fid = drive_sharing._find_child_folder_id(entrada_id, day)  # noqa: SLF001
    if fid:
        return fid
    meta = {
        "name": day,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [entrada_id],
    }
    created = svc.files().create(
        body=meta, fields="id", supportsAllDrives=True,
    ).execute()
    return created["id"]


def _day_folder_id(username: str, day: str) -> str | None:
    entrada_id = drive_sharing._subfolder_id(username, "entrada")  # noqa: SLF001
    return drive_sharing._find_child_folder_id(entrada_id, day)  # noqa: SLF001


def init_resumable_session(
    folder_id: str, filename: str, *, mime: str = "video/mp4", origin: str | None = None,
) -> str:
    """Crea una sesión de subida resumable y devuelve la URL (header Location).

    `origin` debe ser el origen web del cliente (https://nebulabsmedia.com) —
    se pasa para que Google habilite CORS en la sesión y el navegador pueda
    hacer el PUT cross-origin."""
    token = drive_sharing.access_token()
    headers = {
        "Authorization": f"Bearer {token}",
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
    """Lista los vídeos subidos a `entrada/<día>/` (fuente de verdad = Drive)."""
    fid = _day_folder_id(username, day)
    if not fid:
        return []
    svc = drive_sharing._service()  # noqa: SLF001
    res = svc.files().list(
        q=f"'{fid}' in parents and trashed=false",
        fields="files(id,name,size,mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=200,
    ).execute()
    out: list[dict[str, Any]] = []
    for f in res.get("files", []):
        name = f.get("name", "")
        if not name.lower().endswith(_VIDEO_EXTS):
            continue
        out.append({"id": f["id"], "filename": name, "size_bytes": int(f.get("size") or 0)})
    return out


def delete_day_file(username: str, day: str, filename: str) -> bool:
    """Borra un vídeo del día (por nombre) en Drive. True si se borró."""
    for f in list_day_files(username, day):
        if f["filename"] == filename:
            drive_sharing._service().files().delete(  # noqa: SLF001
                fileId=f["id"], supportsAllDrives=True,
            ).execute()
            return True
    return False
