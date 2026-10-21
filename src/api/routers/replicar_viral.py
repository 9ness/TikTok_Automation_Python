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
from pydantic import BaseModel, Field

from src.replicar_viral import carrusel, catalogo, servicio, video

router = APIRouter(
    prefix="/api/v1/replicar-viral",
    tags=["tiktok-shop-ai-pro · replicar viral"],
    dependencies=[Depends(get_current_user)],
)


def _texto_a_lista(x: str) -> list[str]:
    """`prompts`/`hashtags` del formulario: JSON (lista) o texto, uno por línea."""
    import json

    x = (x or "").strip()
    if not x:
        return []
    if x.startswith("["):
        try:
            v = json.loads(x)
            if isinstance(v, list):
                return [str(i) for i in v]
        except ValueError:
            pass
    return [linea for linea in x.splitlines() if linea.strip()]


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
# Vídeo YA MONTADO («Replicar virales», `src/replicar_viral/video.py`): sale
# solo en Mis tandas como `rv|<id>`. Van ANTES de `/{id_}`.
# ---------------------------------------------------------------------------
@router.post("/video")
def video_subir(
    file: Annotated[UploadFile, File()],
    modo: Annotated[str, Form()] = "",
    titulo: Annotated[str, Form()] = "",
    url_viral: Annotated[str, Form()] = "",
    product_id: Annotated[str, Form()] = "",
    product_url: Annotated[str, Form()] = "",
    tienda: Annotated[str, Form()] = "",
    caption: Annotated[str, Form()] = "",
    hashtags: Annotated[str, Form()] = "",
    prompts: Annotated[str, Form()] = "",
    notas: Annotated[str, Form()] = "",
    replica_id: Annotated[str, Form()] = "",
    para: Annotated[str, Form()] = "",
    catalogo: Annotated[str, Form()] = "",
    carpeta: Annotated[str, Form()] = "",
    producto_ref: Annotated[str, Form()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Alta del MP4 montado de una réplica (`modo` con_ia | sin_ia). Con
    `replica_id` reemplaza el vídeo de esa réplica (rehecho). `para`: otro
    usuario (solo admin). `hashtags`/`prompts`: JSON o uno por línea."""
    tmp = Path(tempfile.mkdtemp(prefix="replica_video_"))
    try:
        fichero = tmp / "subido.mp4"
        with open(fichero, "wb") as f:
            shutil.copyfileobj(file.file, f)
        doc = video.registrar(
            carrusel.destino(usuario, para), modo=modo, origen=fichero, titulo=titulo,
            url_viral=url_viral, product_id=product_id, product_url=product_url, tienda=tienda,
            caption=caption, hashtags=_texto_a_lista(hashtags), prompts=_texto_a_lista(prompts),
            notas=notas, replica_id=replica_id,
            catalogo=catalogo, carpeta=carpeta, producto_ref=producto_ref,
        )
        return video.resumen(doc)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class VideoBandejaRequest(BaseModel):
    ruta: str
    modo: str = ""
    titulo: str = ""
    url_viral: str = ""
    product_id: str = ""
    product_url: str = ""
    tienda: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    notas: str = ""
    replica_id: str = ""
    para: str = ""
    catalogo: str = ""
    carpeta: str = ""
    producto_ref: str = ""


@router.post("/video/bandeja")
def video_bandeja(body: VideoBandejaRequest, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Como `POST /video` pero el MP4 lo coge de la bandeja del agente
    (`TIKTOK_SHOP_AI_PRO/_agente/<usuario>/<ruta>`) de quien llama, sin subirlo."""
    try:
        origen = video.ruta_bandeja(usuario, body.ruta)
        doc = video.registrar(
            carrusel.destino(usuario, body.para), modo=body.modo, origen=origen, titulo=body.titulo,
            url_viral=body.url_viral, product_id=body.product_id, product_url=body.product_url,
            tienda=body.tienda, caption=body.caption, hashtags=body.hashtags, prompts=body.prompts,
            notas=body.notas, replica_id=body.replica_id,
            catalogo=body.catalogo, carpeta=body.carpeta, producto_ref=body.producto_ref,
        )
        return video.resumen(doc)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/video")
def video_listar(modo: str = "", usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Las réplicas en vídeo del usuario (lo último primero)."""
    try:
        return {"modos": video.MODOS, "items": [video.resumen(d) for d in video.listar(usuario, modo)]}
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/video/{id_}")
def video_ver(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    try:
        doc = video.ver(usuario, id_)
        return {**video.resumen(doc), "prompts": doc.get("prompts") or []}
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/video/{id_}/mp4")
def video_mp4(id_: str, descargar: bool = False,
              usuario: Annotated[str, Depends(get_web_user)] = "") -> FileResponse:
    try:
        doc = video.ver(usuario, id_)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    p = Path(doc.get("video_path") or "")
    if not p.is_file():
        raise APIError("El vídeo ya no está en el Drive.", status_code=404)
    nombre = None
    if descargar:
        base = video_nombre(doc)
        nombre = f"{base}.mp4"
    return FileResponse(p, media_type="video/mp4", filename=nombre,
                        headers={"Cache-Control": "private, max-age=60"})


def video_nombre(doc: dict) -> str:
    import re

    titulo = (doc.get("producto") or {}).get("titulo", "") or "replica"
    return "replica_" + (re.sub(r"[^A-Za-z0-9]+", "_", titulo).strip("_")[:40] or "video") + f"_{doc.get('id', '')}"


@router.delete("/video/{id_}")
def video_borrar(id_: str, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Borra la réplica y su MP4 (sale también de Mis tandas)."""
    try:
        return video.borrar(usuario, id_)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


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


@router.post("/carrusel/{id_}/caption")
def carrusel_caption(
    id_: str, caption: Annotated[str, Body(embed=True)] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Cambia el caption del carrusel y el de sus publicaciones de Meta aún en cola."""
    from src.multiplataforma.services import carruseles as mp_carruseles

    try:
        doc = carrusel.cambiar_caption(usuario, id_, caption)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    doc["meta_actualizadas"] = mp_carruseles.actualizar_caption(id_, doc.get("caption", ""))
    return doc


@router.post("/carrusel/{id_}/estilo")
def carrusel_estilo(
    id_: str, estilo: Annotated[str, Body(embed=True)] = "",
    y: Annotated[float | None, Body(embed=True)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Letra del carrusel (`texto_foto.ESTILOS`) y altura del texto; se vuelven a quemar todas."""
    try:
        return carrusel.cambiar_estilo(usuario, id_, estilo, y)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/carrusel/{id_}/imagen/{n}")
def carrusel_imagen(
    id_: str, n: int, tipo: str = "final", descargar: bool = False, t: int = 0,
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
    if descargar:
        doc = carrusel.ver(usuario, id_)
        nombre = f"{carrusel.nombre_carrusel(doc)}_{n:02d}.jpg"
        # Los clientes antiguos no mandan `t`: antes recibían el JPEG sin
        # EXIF y la galería lo ordenaba según cuándo terminaba la descarga.
        # Una fecha común y estable del carrusel evita carreras entre peticiones
        # y permite bajar también las fotos sueltas en cualquier orden.
        # Conservamos `t + n` para los clientes que ya calculan su propia fecha.
        cuando = t + n if t > 0 else float(doc["creado_at"]) - 2 * (n - 1)
        return Response(carrusel.con_fecha(p.read_bytes(), cuando), media_type="image/jpeg",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                                 "Cache-Control": "no-store"})
    return FileResponse(p, media_type="image/jpeg",
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
