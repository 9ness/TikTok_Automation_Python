"""GET /api/v1/editor-auto/stickers — lista y sirve los assets de stickers.

Endpoints:
  - `GET  /arrows`              — lista de archivos en `Assets/flechas/`
  - `GET  /arrows/{filename}`   — sirve el archivo binario (para preview)

Estos endpoints son lectura pura sobre el filesystem montado del Drive.
NO permiten escritura — el operador deposita los assets a mano en la
carpeta. Anti path-traversal: solo aceptamos basenames sin `..` ni `/`.

Auth: el endpoint `/arrows/{filename}` acepta también `?api_key=` por
query string — el `<video src=>` del navegador no puede enviar headers
custom, mismo patrón que `fonts/file/{filename}`. El listado usa el
header normal vía dependency global del router.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, UnauthorizedError, ValidationError
from src.editor_auto.config import arrows_folder
from src.editor_auto.tools.sticker_arrow import STICKER_EXTS


router = APIRouter(
    prefix="/api/v1/editor-auto/stickers",
    tags=["editor-auto · stickers"],
)


def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


def _preview_cache_dir() -> str:
    """Carpeta cache de previews transcodificados. Vive en `temp/` del SO
    para no contaminar el Drive sincronizado."""
    d = os.path.join(tempfile.gettempdir(), "editor_auto_sticker_previews")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_key(src_path: str) -> str:
    """Hash por path + mtime + size → invalidación automática si el operador
    sustituye un sticker manteniendo el nombre."""
    try:
        st = os.stat(src_path)
        sig = f"{src_path}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        sig = src_path
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()[:16]


def _transcode_to_apng(src_path: str) -> str:
    """Transcodifica src (MOV ProRes / WebM / etc.) a APNG (animated PNG)
    para previsualización en el navegador. APNG tiene soporte universal de
    alpha en todos los browsers modernos y se renderiza con `<img>`.

    Por qué APNG y no WebM:
      Probamos libvpx-vp9 con `-pix_fmt yuva420p -auto-alt-ref 0
      -metadata:s:v:0 alpha_mode=1` (combo "oficial" de WebM alpha) y el
      Windows ffmpeg gyan-build encodea con yuva420p pero NO escribe los
      BlockAdditions que Chrome necesita para componer el alpha al
      decodificar → el browser muestra el sticker con fondo opaco.
      APNG no tiene esa ambigüedad: cada frame lleva su alpha nativo.

    Trade-off: APNG pesa más (~1.5MB vs ~20KB de WebM). Compensamos
    bajando fps y resolución para preview (no es el render final).

    Cache key incluye mtime+size del original. Devuelve la ruta cacheada.
    """
    key = _cache_key(src_path)
    base = os.path.splitext(os.path.basename(src_path))[0]
    out = os.path.join(_preview_cache_dir(), f"{base}_{key}.apng")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    # 15 fps + 200px de ancho → preview suave (~1.5MB para flecha 5s). El
    # render final NO usa esto, así que sacrificamos calidad por tamaño.
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", src_path,
        # `-2` (no `-1`): fuerza altura PAR. Con `-1` algunos assets dan
        # altura impar y el encoder APNG falla → preview en blanco (caso
        # flecha roja). `format=rgba` garantiza canal alpha aunque el
        # source no lo declare explícito.
        "-vf", "fps=15,scale=200:-2:flags=lanczos,format=rgba",
        "-plays", "0",          # loop infinito en APNG
        "-f", "apng",
        out,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0 or not os.path.isfile(out):
        err = proc.stderr.decode("utf-8", errors="ignore")[-400:]
        raise APIError(
            f"No se pudo transcodificar sticker a APNG: {err}",
            details={"src": os.path.basename(src_path)},
        )
    return out


_MIME_BY_EXT = {
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".gif": "image/gif",
    ".apng": "image/apng",
    ".png": "image/png",
}


@router.get("/arrows", dependencies=[Depends(get_current_user)])
def list_arrows() -> dict:
    """Devuelve `{folder, files: [{filename, size_bytes, ext}]}`.

    `folder` ayuda al operador a entender DÓNDE depositar nuevos
    stickers desde el cliente Drive si la lista sale vacía.
    """
    folder = arrows_folder()
    files: list[dict] = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            ext = os.path.splitext(name)[1].lower()
            if ext not in STICKER_EXTS:
                continue
            full = os.path.join(folder, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            files.append({"filename": name, "size_bytes": size, "ext": ext})
    return {"folder": folder, "files": files}


@router.get("/arrows/{filename}")
def serve_arrow(
    filename: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    as_: Annotated[str | None, Query(alias="as")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    """Sirve el archivo del sticker para previsualización en frontend.

    Auth vía header `X-API-Key` o query `?api_key=` — el `<video src=>`
    del navegador no puede inyectar headers, mismo patrón que
    `fonts/file/{filename}`.

    `?as=webm` transcodifica el original (típicamente MOV ProRes que el
    navegador no decodifica) a WebM VP9 con alpha, cacheado en disco. La
    pipeline de render sigue usando el MOV original; esto es solo para el
    preview en el editor.

    Anti path-traversal: rechazamos cualquier filename que no sea un
    basename limpio o cuya extensión no esté en `STICKER_EXTS`.
    """
    _auth_or_raise(settings, x_api_key, api_key)
    base = os.path.basename(filename)
    if base != filename or ".." in base or "/" in base or "\\" in base:
        raise ValidationError(
            f"Nombre de archivo inválido: '{filename}'",
            details={"filename": filename},
        )
    ext = os.path.splitext(base)[1].lower()
    if ext not in STICKER_EXTS:
        raise ValidationError(
            f"Extensión no permitida: '{ext}'",
            details={"allowed_exts": sorted(STICKER_EXTS)},
        )
    src_path = os.path.join(arrows_folder(), base)
    if not os.path.isfile(src_path):
        raise ValidationError(
            f"Sticker no encontrado: '{base}'",
            details={"folder": arrows_folder()},
        )

    if (as_ or "").lower() == "apng":
        apng_path = _transcode_to_apng(src_path)
        return FileResponse(
            apng_path,
            media_type="image/apng",
            filename=os.path.splitext(base)[0] + ".apng",
        )

    return FileResponse(
        src_path,
        media_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
        filename=base,
    )
