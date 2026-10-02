"""«Replicar viral» (Programa 4): un vídeo viral de TikTok + un producto nuestro
→ guion de voz en off y prompts de los DOS clips mudos de 8 s. Ver
`src/replicar_viral/servicio.py`."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.replicar_viral import servicio

router = APIRouter(
    prefix="/api/v1/replicar-viral",
    tags=["tiktok-shop-ai-pro · replicar viral"],
    dependencies=[Depends(get_current_user)],
)


def _error(e: Exception) -> APIError:
    if isinstance(e, servicio.ErrorReplica):
        return APIError(str(e), status_code=e.status)
    return APIError(f"{type(e).__name__}: {e}", status_code=500)


@router.post("/analizar")
def analizar(
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Analiza el vídeo (enlace de TikTok o fichero) y lo adapta al producto
    `source/folder/producto` del catálogo del POV BOF. Una llamada de Gemini
    Flash; no genera imágenes ni vídeos. Tarda ~1 min."""
    tmp = Path(tempfile.mkdtemp(prefix="replica_up_"))
    try:
        fichero = None
        if file is not None and file.filename:
            fichero = tmp / "subido.mp4"
            with open(fichero, "wb") as f:
                shutil.copyfileobj(file.file, f)
        return servicio.replicar(usuario, source=source, folder=folder, producto=producto,
                                 url=url, fichero=fichero)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@router.get("")
def listar(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Las últimas réplicas del usuario (resumen)."""
    return {"items": servicio.lista(usuario)}


@router.get("/{id_}")
def ver(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    try:
        return servicio.ver(usuario, id_)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
