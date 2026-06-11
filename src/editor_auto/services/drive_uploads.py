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
# Timeout DURO (s) de toda llamada HTTP a Drive. googleapiclient (httplib2) NO
# trae timeout por defecto → un cuelgue de red bloquea el request para siempre
# (y, por el _lock global, encadena a TODOS). Con timeout, falla rápido y libera.
_HTTP_TIMEOUT_S = int(os.getenv("DRIVE_HTTP_TIMEOUT_S", "25"))
_SCOPE = "https://www.googleapis.com/auth/drive"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_RESUMABLE_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=resumable&supportsAllDrives=true"
)
_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")

_DRIVE_API = "https://www.googleapis.com/drive/v3/files"

_lock = threading.Lock()
_creds_cache: dict[str, Any] = {"v": None}
# requests.Session compartida: thread-safe para requests independientes y con
# pool de conexiones. Reemplaza a googleapiclient/httplib2 (NO thread-safe, su
# objeto compartido entre requests concurrentes del panel deadlockeaba y
# agotaba el threadpool → el server parecía "caído").
_session_cache: dict[str, Any] = {"v": None}


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


class _TimeoutSession:
    """requests.Session-like que fuerza timeout en cada request. Usado tanto
    para el refresh OAuth como para las llamadas a la Drive API. Sin timeout,
    una llamada colgada bloquearía el worker para siempre."""

    def __init__(self) -> None:
        import requests as _rq
        self._s = _rq.Session()

    def request(self, *args: Any, **kwargs: Any):
        if not kwargs.get("timeout"):
            kwargs["timeout"] = _HTTP_TIMEOUT_S
        return self._s.request(*args, **kwargs)

    def get(self, url: str, **kwargs: Any):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any):
        return self.request("POST", url, **kwargs)

    def delete(self, url: str, **kwargs: Any):
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._s.close()


def _session() -> "_TimeoutSession":
    if _session_cache["v"] is not None:
        return _session_cache["v"]
    with _lock:
        if _session_cache["v"] is None:
            _session_cache["v"] = _TimeoutSession()
        return _session_cache["v"]


def access_token() -> str:
    creds = _creds()
    if not creds.valid:
        import google.auth.transport.requests as gatr
        creds.refresh(gatr.Request(session=_TimeoutSession()))
    return creds.token


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token()}"}


def _esc(s: str) -> str:
    return s.replace("'", "\\'")


def _find_child(parent_id: str | None, name: str) -> str | None:
    q = (
        f"name = '{_esc(name)}' and trashed = false "
        f"and mimeType = 'application/vnd.google-apps.folder'"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"
    r = _session().get(
        _DRIVE_API,
        headers=_auth_headers(),
        params={
            "q": q, "fields": "files(id,name,createdTime)", "pageSize": 10,
            # CRÍTICO: Google Drive PERMITE carpetas con el MISMO nombre. Si
            # alguna vez hay duplicados de '<día>' (p. ej. una race de subidas
            # concurrentes creó dos), hay que elegir SIEMPRE la misma — la más
            # ANTIGUA — para que la API y el mount de rclone (que también
            # resuelve por nombre) lean la MISMA carpeta. Sin orderBy, Drive
            # devolvía un orden arbitrario → la subida iba a una carpeta y el
            # pipeline leía la otra ("vídeo input no encontrado").
            "orderBy": "createdTime",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
        },
    )
    r.raise_for_status()
    files = r.json().get("files", [])
    # Google Drive busca por nombre CASE-INSENSITIVE (q `name='x'` trae tanto
    # 'Bugalleitor' como 'bugalleitor') PERO el mount de rclone resuelve rutas
    # CASE-SENSITIVE. Si no filtramos por case exacto, el upload de un usuario
    # 'bugalleitor' caía en la carpeta vieja 'Bugalleitor' (otro usuario) y el
    # pipeline, que lee la ruta literal 'bugalleitor', no encontraba el vídeo.
    # Filtramos al match EXACTO de nombre para que API y mount coincidan.
    exact = [f for f in files if f.get("name") == name]
    pick = exact or files  # si no hay exacto, mantenemos el comportamiento previo
    return pick[0]["id"] if pick else None


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
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    r = _session().post(
        _DRIVE_API,
        headers={**_auth_headers(), "Content-Type": "application/json"},
        params={"fields": "id", "supportsAllDrives": "true"},
        json=meta,
    )
    r.raise_for_status()
    return r.json()["id"]


# Lock + cache por (usuario, día): serializan la resolución/creación de la
# carpeta del día. Sin esto, N subidas concurrentes (el navegador pide N
# `upload-url` casi a la vez) corrían `ensure_day_folder` en paralelo; como
# Drive tiene consistencia EVENTUAL, la búsqueda de cada una no veía la carpeta
# que las otras acababan de crear → se creaban DUPLICADAS. El lock fuerza que
# solo la primera cree y las demás reusen; la cache evita además la race de
# propagación (una vez sabemos el ID, no volvemos a buscar en Drive).
_DAY_FOLDER_LOCK = threading.Lock()
_DAY_FOLDER_CACHE: dict[tuple[str, str], str] = {}


def ensure_day_folder(username: str, day: str) -> str:
    """ID de `entrada/<día>/`, creándolo si no existe. Idempotente y seguro
    ante subidas concurrentes (nunca crea carpetas duplicadas). Lanza si falta
    entrada/."""
    key = (username, day)
    cached = _DAY_FOLDER_CACHE.get(key)
    if cached:
        return cached
    with _DAY_FOLDER_LOCK:
        cached = _DAY_FOLDER_CACHE.get(key)
        if cached:
            return cached
        entrada = _entrada_id(username)
        if not entrada:
            raise RuntimeError(
                f"No encuentro entrada/ de '{username}' en Drive. ¿Carpetas creadas/sincronizadas?"
            )
        fid = _find_child(entrada, day) or _create_folder(entrada, day)
        _DAY_FOLDER_CACHE[key] = fid
        return fid


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
    r = _session().get(
        _DRIVE_API,
        headers=_auth_headers(),
        params={
            "q": f"'{fid}' in parents and trashed = false",
            "fields": "files(id,name,size,mimeType)",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            "pageSize": 200,
        },
    )
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for f in r.json().get("files", []):
        name = f.get("name", "")
        if name.lower().endswith(_VIDEO_EXTS):
            out.append({"id": f["id"], "filename": name, "size_bytes": int(f.get("size") or 0)})
    return out


def delete_day_file(username: str, day: str, filename: str) -> bool:
    for f in list_day_files(username, day):
        if f["filename"] == filename:
            r = _session().delete(
                f"{_DRIVE_API}/{f['id']}",
                headers=_auth_headers(),
                params={"supportsAllDrives": "true"},
            )
            r.raise_for_status()
            return True
    return False
