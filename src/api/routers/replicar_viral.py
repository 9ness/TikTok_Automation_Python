"""«Replicar viral» (Programa 4): un vídeo viral de TikTok + un producto nuestro
→ guion de voz en off y prompts de los DOS clips mudos de 8 s. Ver
`src/replicar_viral/servicio.py`."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.replicar_viral import carrusel, catalogo, servicio

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
def listar(tipo: str = "", usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Las últimas réplicas del usuario (resumen). `tipo`: video | carrusel."""
    return {"items": servicio.lista(usuario, tipo)}


# ---------------------------------------------------------------------------
# Carrusel (`src/replicar_viral/carrusel.py`). Van ANTES de `/{id_}`.
# ---------------------------------------------------------------------------
@router.post("/carrusel/analizar")
def carrusel_analizar(
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    url: Annotated[str, Form()],
    para: Annotated[str, Form()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Carrusel de TikTok (enlace) + producto del POV BOF → por diapositiva:
    papel, texto adaptado y prompt de imagen para Flow. Una llamada de Gemini
    Flash; no genera imágenes. Tarda ~1 min. `para`: otro usuario (solo admin)."""
    try:
        return carrusel.replicar(carrusel.destino(usuario, para), source=source, folder=folder,
                                 producto=producto, url=url)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/carrusel/catalogo")
def carrusel_catalogo() -> dict:
    """Productos del catálogo COMPARTIDO «Carruseles virales» (lo nuevo
    primero), con su `product_url` y el `carrusel_url` del viral de origen."""
    try:
        return {"source": catalogo.SOURCE, "items": catalogo.listar()}
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post("/carrusel/producto")
async def carrusel_crear_producto(
    foto_limpia: Annotated[UploadFile, File()],
    foto_ficha: Annotated[UploadFile, File()],
    product_url: Annotated[str, Form()],
    carrusel_url: Annotated[str, Form()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Alta de un producto en «Carruseles virales»: foto limpia + captura de la
    ficha + URL de TikTok Shop (+ el enlace del carrusel viral, opcional). Lee
    los textos de la ficha (una llamada de Gemini) y guarda la URL."""
    try:
        return catalogo.crear_producto(
            await foto_limpia.read(), await foto_ficha.read(),
            product_url=product_url, carrusel_url=carrusel_url,
            nombre_limpia=foto_limpia.filename or "", nombre_ficha=foto_ficha.filename or "",
            usuario=usuario,
        )
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post("/carrusel/producto/textos")
def carrusel_releer_textos(
    folder: Annotated[str, Body()], producto: Annotated[str, Body()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Reintenta leer la ficha de un producto de «Carruseles virales»."""
    try:
        return catalogo.releer_textos(folder, producto, usuario)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/carrusel/{id_}")
def carrusel_ver(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    try:
        return carrusel.con_estado(carrusel.ver(usuario, id_))
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post("/carrusel/{id_}/imagen/{n}")
def carrusel_subir(
    id_: str, n: int, file: Annotated[UploadFile, File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """La foto generada en Flow para la diapositiva `n`; se le quema su texto."""
    try:
        return carrusel.subir_imagen(usuario, id_, n, file.file.read())
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post("/carrusel/{id_}/texto/{n}")
def carrusel_texto(
    id_: str, n: int, texto: Annotated[str, Body(embed=True)] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Corrige el texto de la diapositiva `n` (se vuelve a quemar si hay foto)."""
    try:
        return carrusel.cambiar_texto(usuario, id_, n, texto)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/carrusel/{id_}/imagen/{n}")
def carrusel_imagen(
    id_: str, n: int, tipo: str = "final", descargar: bool = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
):
    """`tipo`: orig (la del viral) · base (la de Flow) · txt (con texto) ·
    final (txt si la hay, si no base)."""
    try:
        if tipo == "final":
            p = (carrusel.ruta_foto(usuario, id_, n, "txt")
                 or carrusel.ruta_foto(usuario, id_, n, "base"))
        else:
            p = carrusel.ruta_foto(usuario, id_, n, tipo)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    if not p:
        raise APIError("Esa foto todavía no está.", status_code=404)
    return FileResponse(p, media_type="image/jpeg",
                        filename=f"diapositiva_{n:02d}.jpg" if descargar else None,
                        headers={"Cache-Control": "private, max-age=60"})


@router.post("/carrusel/{id_}/replicar")
def carrusel_replicar_otra_vez(
    id_: str, para: Annotated[str, Body(embed=True)] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Vuelve a replicar el MISMO viral con el MISMO producto (Gemini otra vez:
    textos y prompts nuevos) para `para` (solo admin) o para uno mismo."""
    try:
        return carrusel.replicar_otra_vez(usuario, id_, para)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/carrusel/{id_}/zip")
def carrusel_zip(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> Response:
    """TODAS las diapositivas listas (con su texto) + caption.txt, en un ZIP."""
    try:
        datos, nombre = carrusel.zip_carrusel(usuario, id_)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    return Response(datos, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                             "Cache-Control": "no-store"})


@router.get("/{id_}")
def ver(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    try:
        return servicio.ver(usuario, id_)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
