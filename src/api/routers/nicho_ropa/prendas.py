"""Endpoints del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

- GET  /api/v1/nicho-ropa/prompts        → imagen + vídeo (manos/percha/espejo)
- GET  /api/v1/nicho-ropa/prendas        → prendas emparejadas + textos
- POST /api/v1/nicho-ropa/extraer-textos → lee las capturas con Gemini
- POST /api/v1/nicho-ropa/producto/estado → mete/saca del escaparate
- GET  /api/v1/nicho-ropa/foto           → sirve una foto por file ID
- GET  /api/v1/nicho-ropa/foto-limpia    → descarga la foto de la prenda
- POST /api/v1/nicho-ropa/video/upload   → sube el bruto y encola el montaje
- GET  /api/v1/nicho-ropa/video          → sirve el vídeo ya montado

Es UNA sola carpeta de Drive, compartida por enlace, así que ningún endpoint
lleva `source`/`folder` — a diferencia del Nicho POV BOF.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_ropa import (
    CarpetaRopa,
    CarpetasRopaResponse,
    PrendaEstadoRequest,
    PrendaInfo,
    PrendasListResponse,
    PromptsRopaResponse,
    VideoRopaUploadResponse,
)
from src.nicho_ropa import config
from src.nicho_ropa.repos import product_repo
from src.nicho_ropa.services import drive_client, text_extractor
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-ropa",
    tags=["nicho-ropa"],
    dependencies=[Depends(get_current_user)],
)

logger = logging.getLogger(__name__)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@router.get("/prompts", response_model=PromptsRopaResponse)
def get_prompts(
    carpeta: str = Query(""), plazos: bool = Query(False),
) -> PromptsRopaResponse:
    """Los prompts del curso. El de vídeo, en sus dos versiones.

    `carpeta` solo decide el del espejo: es el único con una persona dentro, y
    en las carpetas de hombre esa persona tiene que ser un hombre.

    `plazos` mete la frase de la financiación en lo que dice la persona. Va
    apagado por defecto a propósito: aquí la voz la pone el propio vídeo, así
    que prometer plazos que la prenda no tiene no se puede corregir después —
    habría que volver a generarlo.
    """
    sexo = config.sexo_de_carpeta(carpeta)
    try:
        return PromptsRopaResponse(
            imagen=config.prompt_imagen(),
            video_con_manos=config.prompt_video(True),
            video_sin_manos=config.prompt_video(False),
            video_percha=config.prompt_video_percha(),
            video_espejo=config.prompt_video_espejo(sexo, plazos),
            sexo=sexo,
            mof10=config.prompts_mof10(sexo, plazos),
        )
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e


@router.post("/urls/importar")
def importar_urls(body: dict) -> dict:
    """Guarda de golpe las fichas copiadas del DOM de la web del curso.

    `genero` dice de qué inventario es el pegote (`mujer_web` / `hombre_web`):
    su página los tiene separados y las carpetas se llaman igual en los dos,
    así que sin el sexo no se sabría a cuál van.
    """
    from src.nicho_ropa.repos import product_repo as ropa_repo
    from src.nicho_ropa.services import prendas_web

    genero = str(body.get("genero") or "").strip()
    if genero not in config.GENEROS_WEB:
        raise APIError(
            f"Género desconocido: {genero!r}. Válidos: {sorted(config.GENEROS_WEB)}.",
            status_code=400,
        )

    filas = body.get("filas")
    if not isinstance(filas, list) or not filas:
        raise APIError("No llegó ninguna fila. Sube el fichero de la consola.", status_code=400)
    if len(filas) > 5000:
        raise APIError(f"Demasiadas filas ({len(filas)}).", status_code=400)

    reales = [config.slug_web(genero, c) for c in prendas_web.carpetas(genero)]
    if not reales:
        raise APIError(
            f"No hay ninguna carpeta de {config.GENEROS_WEB[genero]}: sube antes los ZIP.",
            status_code=400,
        )
    try:
        return ropa_repo.importar_urls(filas, reales)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e


@router.get("/carpetas", response_model=CarpetasRopaResponse)
def list_carpetas() -> CarpetasRopaResponse:
    """Carpetas de producto disponibles.

    Las de mujer (mono, pantalón corto, bikinis) son las del nicho CON
    personas, pero la misma prenda vale aquí colgada en percha: lo que cambia
    es el prompt, no la foto.
    """
    from src.nicho_ropa.services import prendas_web

    items = [
        CarpetaRopa(slug=slug, label=meta["label"], web=False)
        for slug, meta in config.CARPETAS.items()
    ]
    # Y las importadas por ZIP de la web, que son carpetas de diez como las de
    # allí. Se listan detrás para no mover de sitio las de siempre.
    try:
        items += [
            CarpetaRopa(
                slug=config.slug_web(genero, carpeta),
                label=config.carpeta_label(config.slug_web(genero, carpeta)),
                web=True,
            )
            for genero, carpeta in prendas_web.todas_las_carpetas()
        ]
    except Exception as e:  # noqa: BLE001
        # Un fallo leyendo el mount no puede dejar sin las cuatro de siempre,
        # pero tampoco puede pasar por "aún no has importado nada": son cosas
        # distintas y sin log no se distinguen (ya pasó con el Drive del curso).
        logger.warning("[nicho_ropa] no se pudieron listar las carpetas web: %s", e)

    # Y los catálogos del operador (mujer/hombre × muestras/tareas). Van con
    # `web=True` porque se trabajan igual que las de la web —la prenda va
    # puesta y el clip conserva su voz—; lo que las separa es que las sube él.
    try:
        items += [
            CarpetaRopa(
                slug=config.slug_web(genero, carpeta),
                label=config.carpeta_label(config.slug_web(genero, carpeta)),
                web=True, propia=True, genero=genero,
            )
            for genero, carpeta in prendas_web.carpetas_del_operador()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("[nicho_ropa] no se pudieron listar las carpetas propias: %s", e)
    return CarpetasRopaResponse(items=items)


@router.post("/mis-prendas")
async def crear_mi_prenda(
    genero: Annotated[str, Query()],
    foto_limpia: Annotated[UploadFile, File()],
    foto_ficha: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Alta de una prenda PROPIA en uno de los cuatro catálogos del operador.

    Mismo convenio de nombres que en todo el proyecto (`3.jpg` la limpia,
    `3(1).jpg` la ficha), así que a partir de aquí la prenda se comporta como
    una de la web: textos, prompts y montaje sin nada especial.

    El género va en el slug, así que lo que subes en mujer se queda en mujer.
    """
    from src.nicho_ropa.services import prendas_web

    if not config.es_genero_operador(genero):
        raise APIError(
            f"{genero!r} no es un catálogo tuyo. "
            f"Válidos: {sorted(config.GENEROS_OPERADOR)}.",
            status_code=400,
        )

    async def _leer(archivo: UploadFile, que: str) -> bytes:
        nombre = (archivo.filename or "").lower()
        if not any(nombre.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")):
            raise APIError(
                f"{que} tiene un formato no soportado ({archivo.filename!r}). "
                "Acepta jpg, jpeg, png o webp.",
                status_code=400,
            )
        datos = await archivo.read()
        if not datos:
            raise APIError(f"{que} llegó vacía.", status_code=400)
        if len(datos) > 12 * 1024 * 1024:
            raise APIError(
                f"{que} pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.",
                status_code=400,
            )
        return datos

    limpia = await _leer(foto_limpia, "La foto de la prenda")
    ficha = await _leer(foto_ficha, "La captura de la ficha") if foto_ficha else b""

    try:
        return prendas_web.guardar_prenda(
            genero, limpia, ficha or None,
            nombre_limpia=foto_limpia.filename or "",
            nombre_ficha=(foto_ficha.filename or "") if foto_ficha else "",
        )
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except OSError as e:
        raise APIError(f"No se pudieron guardar las fotos: {e}", status_code=500) from e


@router.post("/prendas-web/importar")
async def importar_prendas_web(
    genero: Annotated[str, Query()],
    archivo: Annotated[UploadFile | None, File()] = None,
    # La APP sube por su cuenta y manda el fichero como `file`: en el WebView
    # el selector no le devuelve los ficheros al `<input>`.
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Importa un ZIP de prendas de la web del curso, a mujer o a hombre."""
    from src.nicho_ropa.services import prendas_web

    subido = archivo or file
    if subido is None:
        raise APIError("No llegó ningún ZIP.", status_code=400)
    datos = await subido.read()
    await subido.close()
    if not datos:
        raise APIError("El ZIP llegó vacío.", status_code=400)
    try:
        return prendas_web.importar_zip(datos, subido.filename or "", genero)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except OSError as e:
        raise APIError(f"No se pudo escribir en el Drive: {e}", status_code=500) from e


def _montando(queue: JobQueue | None, carpeta: str) -> set[str]:
    """Prendas con un montaje en cola o en curso.

    Sale de la COLA y no del estado guardado, por lo mismo que en el otro
    nicho: el runner escribe `uploaded` y `video_path` a la vez al terminar,
    así que lo guardado no distingue "montándose" de "sin empezar".
    """
    if queue is None:
        return set()
    activos = set()
    try:
        for job in queue.list_jobs():
            if job.mode != JobMode.NICHO_ROPA_VIDEO:
                continue
            if str(job.params.get("carpeta") or config.CARPETA_DEFECTO) != carpeta:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(job.params.get("producto")))
    except Exception:
        pass
    return activos


@router.get("/prendas", response_model=PrendasListResponse)
def list_prendas(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasListResponse:
    """Prendas de la carpeta, con su foto limpia, su captura y sus textos."""
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof.services import emojis as emojis_svc

    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    try:
        pares = text_extractor.pares(carpeta, refresh=refresh)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    doc = product_repo.load(carpeta)
    guardados = doc.get("productos") or {}
    activos = _montando(queue, carpeta)
    # Una sola lectura del índice de escaparate para toda la carpeta.
    escaparate = pov_repo.escaparate_index(usuario)

    items = []
    for par in pares:
        pid = par["producto"]
        prod = guardados.get(pid) or {}
        items.append(PrendaInfo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            foto_aviso="" if par.get("confident") else (
                "No se distingue cuál es la foto de la prenda — compruébala"
            ),
            titulo=prod.get("titulo", ""),
            titulo_tiktok_completo=prod.get("titulo_tiktok_completo", ""),
            tienda=prod.get("tienda", ""),
            caption=prod.get("caption", ""),
            emojis=prod.get("emojis") or emojis_svc.emojis_para(
                pid, prod.get("titulo", ""), prod.get("caption", ""),
            ),
            caption_riesgo=caption_arriesgado(prod.get("caption", "")) or "",
            en_escaparate=pov_repo.marcado_en_escaparate(prod, escaparate),
            # `url_de` mira además el índice global: si la ficha se pegó desde
            # otro nicho, aquí ya sale enlazada.
            product_url=pov_repo.url_de(prod),
            sin_stock=bool(prod.get("sin_stock")),
            uploaded=bool(prod.get("uploaded")),
            video_path=prod.get("video_path"),
            video_listo_at=int(prod.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return PrendasListResponse(
        carpeta=carpeta,
        items=items,
        textos_extraidos=bool(doc.get("textos_extraidos")),
        montando=bool(activos),
    )


@router.post("/producto/estado", response_model=PrendaInfo)
def set_producto_estado(
    body: PrendaEstadoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendaInfo:
    """Mete o saca la prenda del escaparate.

    No se guarda en el producto sino en el índice ÚNICO por (tienda|nombre):
    el mismo producto sale en varias carpetas y se graba con varios nichos,
    pero al Marketplace se sube UNA vez. Marcado aquí, sale marcado en el POV
    BOF y en el resto.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    carpeta = body.carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    guardado = product_repo.get_product(carpeta, body.producto)
    if not guardado.get("titulo"):
        raise APIError(
            "Este producto no tiene textos todavía: sin el nombre y la tienda no "
            "se puede saber si ya está en el escaparate.",
            status_code=400,
        )
    pov_repo.marcar_escaparate_producto(guardado, body.en_escaparate, usuario)

    listado = list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)
    for item in listado.items:
        if item.producto == body.producto:
            return item
    raise APIError(f"No existe la prenda {body.producto}.", status_code=404)


@router.post("/extraer-textos", response_model=PrendasListResponse)
def extraer_textos(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasListResponse:
    """Lee las capturas con Gemini y guarda título, tienda, caption y emojis.

    Va síncrono como en el otro nicho: es UNA llamada con todas las imágenes.
    """
    carpeta = carpeta or config.CARPETA_DEFECTO
    logs: list[str] = []
    try:
        textos = text_extractor.extract_texts(carpeta, on_log=logs.append)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    if not textos:
        raise APIError(
            "No se pudo extraer ningún texto. " + (logs[-1] if logs else ""),
            status_code=502,
        )
    try:
        product_repo.save_extracted_texts(carpeta, textos)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)


def _servir_foto(file_id: str, descargar: bool, nombre: str) -> FileResponse:
    # Las fotos de la web y las de los catálogos propios llevan la RUTA como
    # id (no hay ID de Google), así que aquí NO vale el patrón de Drive: con él
    # la miniatura salía rota y el 400 no llegaba a verse en ningún sitio.
    propia = str(file_id).startswith("/")
    if not propia and not _FILE_ID_RE.match(file_id or ""):
        raise APIError(f"file_id no válido: {file_id!r}", status_code=400)
    try:
        path = drive_client.fetch_photo(file_id)
    except (RuntimeError, ValueError) as e:
        raise APIError(str(e), status_code=502) from e
    return FileResponse(
        str(path),
        media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
        filename=nombre if descargar else None,
        # Una foto de Drive es inmutable (su ID lo es), pero una RUTA se
        # reutiliza: borras una prenda, subes otra y `Tareas 1/1.jpg` es otra
        # foto con la misma URL. Cachearla un día enseñaba la vieja — pasó en
        # el POV BOF y allí se resolvió igual.
        headers={
            "Cache-Control": "no-cache" if propia else "public, max-age=86400",
        },
    )


@router.get("/foto")
def get_foto(file_id: Annotated[str, Query()]) -> FileResponse:
    """Miniatura/foto por file ID (el nombre no vale: hay duplicados)."""
    return _servir_foto(file_id, descargar=False, nombre="")


@router.get("/foto-limpia")
def get_foto_limpia(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
) -> FileResponse:
    """Descarga la foto de la prenda — la que se le da al generador."""
    for par in text_extractor.pares(carpeta or config.CARPETA_DEFECTO):
        if par["producto"] == producto:
            clean = par.get("clean") or par.get("titled")
            if not clean:
                raise APIError(f"La prenda {producto} no tiene fotos.", status_code=404)
            return _servir_foto(
                clean["id"], descargar=True, nombre=f"ropa_{producto}.jpg",
            )
    raise APIError(f"No existe la prenda {producto}.", status_code=404)


@router.post("/video/upload", response_model=VideoRopaUploadResponse)
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_web_user)],
    file: Annotated[UploadFile, File()],
    producto: Annotated[str, Form()],
    carpeta: Annotated[str, Form()] = "",
    # Vacío = mudo, que es el modo por defecto de este nicho.
    sexo: Annotated[str, Form()] = "",
    # "1"/"0" para forzarlo; vacío = lo decide la carpeta.
    conservar_audio: Annotated[str, Form()] = "",
) -> VideoRopaUploadResponse:
    """Sube el vídeo generado fuera y encola el encuadre.

    Sin `sexo` el vídeo sale MUDO a propósito: la música la pone el operador
    al publicar. Salvo en el catálogo de la web, donde el clip ya viene hablado
    por la creadora: ahí se conserva su audio o el vídeo se queda sin nada.
    """
    from src.api.temp_storage import upload_subdir

    nombre = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if nombre.endswith(e)), "")
    if not ext:
        raise APIError(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            status_code=400,
        )
    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm and sexo_norm not in ("hombre", "mujer"):
        raise APIError("sexo debe ser 'hombre', 'mujer' o vacío.", status_code=400)

    slug = carpeta or config.CARPETA_DEFECTO
    pedido = (conservar_audio or "").strip().lower()
    if pedido in ("1", "true", "si", "sí"):
        con_audio = True
    elif pedido in ("0", "false", "no"):
        con_audio = False
    else:
        con_audio = config.es_carpeta_web(slug)
    # Una voz del banco manda: no se pisa una voz con otra.
    con_audio = con_audio and not sexo_norm

    dest_dir = upload_subdir("nicho_ropa")
    destino = Path(dest_dir) / f"{producto}_{int(time.time())}{ext}"
    with destino.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = queue.enqueue(
        JobMode.NICHO_ROPA_VIDEO,
        title=(
            f"👕 Vídeo Nicho Ropa · {config.carpeta_label(slug)}"
            f" · prenda {producto}"
        ),
        params={
            "producto": producto,
            "carpeta": slug,
            "raw_path": str(destino),
            "sexo": sexo_norm,
            "conservar_audio": con_audio,
            "operator": operator,
        },
    )
    return VideoRopaUploadResponse(
        job_id=job.id,
        message=(
            f"Encolado con voz de {sexo_norm}" if sexo_norm
            else "Encolado con la voz del clip" if con_audio
            else "Encolado. Sale mudo"
        ),
    )


@router.get("/video")
def get_video(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
    descargar: Annotated[bool, Query()] = False,
) -> FileResponse:
    """Sirve el vídeo ya montado."""
    prod = product_repo.get_product(carpeta or config.CARPETA_DEFECTO, producto)
    ruta = prod.get("video_path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(f"La prenda {producto} no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=Path(ruta).name if descargar else None,
    )
