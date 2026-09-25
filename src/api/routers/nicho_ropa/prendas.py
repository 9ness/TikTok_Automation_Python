"""Endpoints del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

- GET  /api/v1/nicho-ropa/prompts        → imagen + vídeo (manos/percha/espejo)
- GET  /api/v1/nicho-ropa/prendas        → prendas emparejadas + textos
- POST /api/v1/nicho-ropa/extraer-textos → lee las capturas con Gemini
- POST /api/v1/nicho-ropa/guiones        → escribe el guion de cada prenda
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
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_ropa import (
    CarpetaEstadoRopaRequest,
    CarpetaRopa,
    CarpetasRopaResponse,
    GuionesRopaRequest,
    PrendaEstadoRequest,
    PrendaInfo,
    PrendasListResponse,
    PromptsRopaResponse,
    VideoRopaUploadResponse,
)
from src.nicho_ropa import config
from src.nicho_ropa.repos import product_repo
from src.nicho_ropa.services import drive_client, prendas_web, text_extractor, variantes
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-ropa",
    tags=["nicho-ropa"],
    dependencies=[Depends(get_current_user)],
)

logger = logging.getLogger(__name__)

# Con qué nombre entran estas prendas en el ranking de vendidos, que es común a
# todos los nichos. La referencia es `fuente|carpeta|producto`, así que basta
# con que la fuente sea la nuestra para no chocar con el Drive del curso.
SOURCE_VENDIDOS = "nicho_ropa"

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@router.get("/prompts", response_model=PromptsRopaResponse)
def get_prompts(
    carpeta: str = Query(""), plazos: bool = Query(False),
    modo: str = Query(""), duracion: str = Query("10"),
    modalidad: str = Query(""),
) -> PromptsRopaResponse:
    """Los prompts del curso. El de vídeo, en sus dos versiones.

    `carpeta` decide de quién es el vídeo: en las carpetas de hombre, la
    persona que sale es un hombre.

    `duracion` es la del clip que va a generar (10s en Omni, 8s en Veo). Baja
    el tope de caracteres del guion: la voz la pone el propio vídeo, así que
    lo que no entra sale cortado a media frase.

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
            sexo=sexo,
            mof10=config.prompts_mof10(sexo, plazos, modo, duracion),
            # Los modos de ESA modalidad: personajes aleatorios (los de
            # siempre) o marca personal. Son cuentas distintas, no un ajuste.
            modos=config.modos_de(sexo, modalidad or config.MODALIDAD_DEFECTO),
            familias=config.familias_para_pantalla(),
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


def _contar_colores(slug: str, modo: str) -> int:
    """Prendas de la carpeta que valen para el formato de la tienda."""
    from src.nicho_ropa.services import prendas_web

    minimo = config.minimo_variantes(modo)
    if minimo < 2:
        return 0
    try:
        return prendas_web.cuantas_con_colores(slug, minimo)
    except Exception:  # noqa: BLE001 — el contador es un adorno del chip
        return 0


def _contar_en_drive(slug: str) -> int:
    """Cuántas prendas hay en la carpeta según el Drive (memoizado). Solo para
    las que aún no tienen documento en Redis."""
    from src.nicho_ropa.services import prendas_web

    genero, carpeta = config.partes_web(slug)
    return prendas_web.cuantas_prendas(genero, carpeta)


def _contar(slug: str, modo: str, usuario: str = "") -> dict[str, int]:
    """Cuántas prendas tiene la carpeta y cómo van, para el chip del selector.

    `total` sale del propio Drive (listar la carpeta) y lo demás del documento
    de Redis. Se hace solo para las carpetas del sexo que se está mirando: son
    una decena, pero es una lectura por carpeta y con todas puestas se nota.
    """
    from src.nicho_ropa.services import prendas_web

    try:
        genero, carpeta = config.partes_web(slug)
        total = prendas_web.cuantas_prendas(genero, carpeta)
    except Exception:  # noqa: BLE001
        total = 0
    productos = (product_repo.load(slug, usuario).get("productos") or {}).values()
    return {
        "total": total,
        "con_url": sum(1 for p in productos if (p or {}).get("product_url")),
        "con_video": sum(
            1 for p in productos if product_repo.video_de(p, modo).get("video_path")
        ),
    }


@router.get("/carpetas", response_model=CarpetasRopaResponse)
def list_carpetas(
    # De qué pantalla se pregunta. Con él se devuelven SOLO sus carpetas y con
    # los contadores puestos; sin él, todas y sin contar (es lo que necesita
    # "Sin humanos", que no tiene sexo ni chips).
    sexo: Annotated[str, Query()] = "",
    modo: Annotated[str, Query()] = "",
    # Qué catálogo está mirando la pantalla ("web", "muestras" o "tareas").
    # Solo se cuentan las carpetas de ESE: las demás no se ven, y contarlas
    # eran siete segundos por carga — se agotaba hasta el presupuesto.
    catalogo: Annotated[str, Query()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CarpetasRopaResponse:
    """Carpetas de producto disponibles.

    Las de mujer (mono, pantalón corto, bikinis) son las del nicho CON
    personas, pero la misma prenda vale aquí colgada en percha: lo que cambia
    es el prompt, no la foto.
    """
    from src.nicho_ropa.services import prendas_web

    items = [
        CarpetaRopa(
            slug=slug, label=meta["label"], web=False,
            sexo=config.sexo_de_carpeta(slug),
        )
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
                sexo=config.sexo_de_carpeta(config.slug_web(genero, carpeta)),
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
                sexo=config.sexo_de_carpeta(config.slug_web(genero, carpeta)),
            )
            for genero, carpeta in prendas_web.carpetas_del_operador()
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning("[nicho_ropa] no se pudieron listar las carpetas propias: %s", e)

    if sexo in ("mujer", "hombre"):
        items = [i for i in items if i.web and i.sexo == sexo]
        # Con un presupuesto: los contadores son un adorno del chip y el Drive
        # montado en frío tarda lo que quiere. Antes de esto, un listado llegó
        # a 25 s y la pantalla se quedaba cargando sin enseñar NADA. Lo que no
        # dé tiempo sale a cero y la siguiente carga ya lo trae memoizado.
        limite = time.monotonic() + 6.0
        # Las que de verdad se van a ver. Sin esto se contaban las 29 (27 del
        # inventario más muestras y tareas) para enseñar una.
        def _se_ve(c) -> bool:
            if not catalogo:
                return True
            propio = (c.genero or "").endswith(("_muestras", "_tareas"))
            if catalogo == "web":
                return not propio
            return (c.genero or "").endswith(f"_{catalogo}")

        # Como en el POV BOF: los tres contadores salen de Redis con UNA
        # lectura (`resumen_por_carpeta`), sin listar el Drive. Contar en
        # serie contra el mount (~0,8 s por carpeta) dejaba a Moda Mujer sin
        # contadores de la carpeta 11 en adelante teniendo las URLs puestas.
        visibles = [x for x in items if _se_ve(x)]
        try:
            resumen = product_repo.resumen_por_carpeta([x.slug for x in visibles], usuario, modo)
        except Exception as e:  # noqa: BLE001 — los contadores son un adorno
            logger.warning("[nicho_ropa] no se pudo resumir las carpetas: %s", e)
            resumen = {}
        for i in visibles:
            for campo, valor in (resumen.get(i.slug) or {}).items():
                setattr(i, campo, valor)
        # Las que valen para el formato de la tienda. Va aparte del resumen
        # de Redis porque se cuenta en el disco (las fotos del ZIP), y solo
        # cuando el modo lo pide: en los demás no se lee nada.
        if config.minimo_variantes(modo) >= 2:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=8, thread_name_prefix="colores-ropa") as pool:
                for i, n in zip(visibles, pool.map(lambda x: _contar_colores(x.slug, modo), visibles)):
                    i.con_colores = n
        # Solo las carpetas SIN documento (nunca abiertas) se cuentan en el
        # Drive, en paralelo y con el presupuesto: son las recién importadas.
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FuturesTimeout

        vacias = [x for x in visibles if not (resumen.get(x.slug) or {}).get("total")]
        if vacias:
            pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="contar-ropa")
            futuros = [(i, pool.submit(_contar_en_drive, i.slug)) for i in vacias]
            sin_contar = 0
            for i, fut in futuros:
                try:
                    i.total = fut.result(timeout=max(0.0, limite - time.monotonic()))
                except FuturesTimeout:
                    sin_contar += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning("[nicho_ropa] no se pudo contar %s: %s", i.slug, e)
            # Sin esperar a los rezagados: dejan memoizado su listado.
            pool.shutdown(wait=False, cancel_futures=False)
            if sin_contar:
                logger.warning(
                    "[nicho_ropa] contando carpetas se agotó el tiempo; "
                    "%d van sin contadores", sin_contar,
                )
    # Lo marcado a mano. Una sola lectura para todas: no depende del Drive,
    # así que va FUERA del presupuesto de los contadores y sale siempre.
    try:
        from src.nicho_ropa.repos import progress_repo

        hechas, pendientes = progress_repo.estado(usuario, config.modo_valido(modo))
        for i in items:
            i.completada = i.slug in hechas
            i.pendiente = i.slug in pendientes
    except Exception as e:  # noqa: BLE001 — el progreso es un adorno del chip
        logger.warning("[nicho_ropa] no se pudo leer el progreso: %s", e)
    return CarpetasRopaResponse(items=items)


@router.post("/carpeta/estado")
def set_carpeta_estado(
    body: CarpetaEstadoRopaRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Da una carpeta por hecha, o la deja pendiente de subir (por modo)."""
    from src.nicho_ropa.repos import progress_repo

    modo = config.modo_valido(body.modo)
    try:
        hechas, pendientes = progress_repo.marcar(
            usuario, modo, body.carpeta,
            completada=body.completada, pendiente=body.pendiente,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {
        "ok": True,
        "carpeta": body.carpeta,
        "completada": body.carpeta in hechas,
        "pendiente": body.carpeta in pendientes,
    }


@router.post("/prendas/copiar-de-pov-bof")
def copiar_de_pov_bof(
    genero: Annotated[str, Query()],
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
) -> dict:
    """Trae a Moda un producto de "Muestras/Tareas" del POV BOF.

    Se copia, no se mueve: la misma prenda puede dar un vídeo en cada nicho y
    lo que ya tenga hecho en el POV BOF —textos, guion, escaparate, vídeos—
    cuelga de su número en su carpeta de allí.
    """
    # El import va DENTRO, como en el resto del router: el módulo toca el Drive
    # montado al cargarse y a nivel de fichero encarece el arranque de la API.
    from src.nicho_ropa.services import prendas_web

    try:
        return prendas_web.copiar_desde_pov_bof(genero, source, folder, producto)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except OSError as e:
        raise APIError(f"No se pudieron copiar las fotos: {e}", status_code=500) from e


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


@router.post("/prendas-web/importar-lote", status_code=201)
async def importar_prendas_web_lote(
    queue: Annotated[JobQueue, Depends(get_queue)],
    archivos: Annotated[list[UploadFile], File()],
    genero: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola la importación de VARIOS ZIP del inventario de ropa.

    Igual que en el POV BOF y por lo mismo: son 31 ficheros de varios MB, y de
    uno en uno por HTTP se corta a mitad sin decir por dónde iba — con 27 ZIP
    de mujer entró UNO. En la cola se ve el avance y un ZIP roto no para a los
    demás.
    """
    import time
    import uuid

    from src.api.temp_storage import upload_subdir

    if genero not in config.GENEROS_WEB:
        raise APIError(
            f"Género desconocido: {genero!r}. Válidos: {sorted(config.GENEROS_WEB)}.",
            status_code=400,
        )
    if not archivos:
        raise APIError("No llegó ningún ZIP.", status_code=400)

    destino = (
        upload_subdir("nicho_ropa") / f"web_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    )
    destino.mkdir(parents=True, exist_ok=True)
    guardados = 0
    for f in archivos:
        nombre = Path(f.filename or "").name
        if not nombre.lower().endswith(".zip"):
            continue
        datos = await f.read()
        await f.close()
        if not datos:
            continue
        (destino / nombre).write_bytes(datos)
        guardados += 1

    if not guardados:
        raise APIError("Ninguno de los ficheros era un ZIP.", status_code=400)

    etiqueta = config.GENEROS_WEB.get(genero, genero)
    title = f"👗 Importar {guardados} ZIP(s) · {etiqueta}"
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_WEB_IMPORT,
        title=title,
        params={"temp_folder": str(destino), "total": guardados, "genero": genero},
        enqueued_by=usuario or None,
    )
    return {"job_id": job.id, "title": title, "zips": guardados}


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


def _montando(queue: JobQueue | None, carpeta: str, usuario: str = "") -> set[str]:
    """Prendas con un montaje DE ESE USUARIO en cola o en curso.

    Sale de la COLA y no del estado guardado, por lo mismo que en el otro
    nicho: el runner escribe `uploaded` y `video_path` a la vez al terminar,
    así que lo guardado no distingue "montándose" de "sin empezar". Y solo lo
    suyo: el vídeo es de cada uno, y ver "montando…" por el de otro engaña.
    """
    if queue is None:
        return set()
    activos = set()
    try:
        for job in queue.get_all():
            if job.mode != JobMode.NICHO_ROPA_VIDEO:
                continue
            if str(job.params.get("carpeta") or config.CARPETA_DEFECTO) != carpeta:
                continue
            duenio = str(job.params.get("operator") or job.enqueued_by or "")
            if usuario and duenio and duenio != usuario:
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
    # Con qué modo de grabación se está trabajando: cada uno tiene su vídeo.
    modo: Annotated[str, Query()] = "",
) -> PrendasListResponse:
    """Prendas de la carpeta, con su foto limpia, su captura y sus textos."""
    from src.nicho_pov_bof import config as pov_config
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

    doc = product_repo.load(carpeta, usuario)
    guardados = doc.get("productos") or {}
    activos = _montando(queue, carpeta, usuario)
    # Una sola lectura del índice de escaparate para toda la carpeta.
    escaparate = pov_repo.escaparate_index(usuario)

    items = []
    guiones = {
        pid: product_repo.guion_de(prod, modo)
        for pid, prod in guardados.items()
    }
    con_variantes = variantes.tienen(carpeta)
    fotos_color = variantes.colores_con_foto(carpeta)
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
            # Manda la ficha; la corrección a mano solo si existe. Mismo
            # criterio que el POV BOF (`hay_plazos`): lo que diga la captura y,
            # si no se ve, el precio.
            plazos=(
                bool(prod["plazos_manual"])
                if prod.get("plazos_manual") is not None
                else pov_config.hay_plazos(prod)
            ),
            plazos_manual=prod.get("plazos_manual"),
            precio=str(prod.get("precio") or ""),
            # El guion escrito para ESTE modo: cada formato lleva dentro su
            # movimiento, así que el del espejo no vale para el del coche.
            guion=guiones.get(pid, {}).get("video", ""),
            guiones=guiones.get(pid, {}).get("videos", []),
            clips_subidos=sorted(
                int(k) for k in product_repo.clips_de(prod, modo) if str(k).isdigit()
            ),
            guion_colores=guiones.get(pid, {}).get("colores", []),
            variantes_foto=pid in con_variantes,
            variantes_colores=variantes.leidos(prod)["colores"],
            colores_con_foto=[
                c for c in guiones.get(pid, {}).get("colores", [])
                if variantes._slug_color(c) in fotos_color.get(pid, set())
            ],
            fotos_color_producto=len(prendas_web.fotos_color(carpeta, pid)),
            # La principal más las del ZIP: los colores en que se vende.
            variantes_producto=1 + len(prendas_web.fotos_color(carpeta, pid)),
            familia=config.familia_de(str(prod.get("titulo") or "")),
            miniaturas_variantes=variantes.miniaturas_de(carpeta, pid, variantes.leidos(prod)["colores"]),
            guion_dice=guiones.get(pid, {}).get("dice", ""),
            guion_at=guiones.get(pid, {}).get("guion_at", 0),
            uploaded=bool(prod.get("uploaded")),
            uploaded_at=int(prod.get("uploaded_at") or 0),
            sold=bool(prod.get("sold")),
            # El vídeo es de ESTE modo de grabación: la misma prenda tiene
            # uno por modo, como los estilos de guion del POV BOF Largo.
            **product_repo.video_de(prod, modo),
            montando=pid in activos,
        ))
    return PrendasListResponse(
        carpeta=carpeta,
        items=items,
        textos_extraidos=bool(doc.get("textos_extraidos")),
        # Con los guiones en la cola, la lista también se sondea mientras se
        # escriben: si no, había que recargar para ver aparecer los botones.
        montando=(
            bool(activos)
            or _escribiendo_guiones(queue, carpeta)
            or _extrayendo_textos(queue, carpeta)
        ),
    )


def _extrayendo_textos(queue: JobQueue | None, carpeta: str) -> bool:
    """Si hay una lectura de textos de esta carpeta en cola o en curso."""
    if queue is None:
        return False
    try:
        return any(
            job.mode == JobMode.NICHO_ROPA_TEXTOS
            and str(job.params.get("carpeta") or "") == carpeta
            and job.status in (JobStatus.PENDING, JobStatus.RUNNING)
            for job in queue.get_all()
        )
    except Exception:  # noqa: BLE001 — el sondeo es un adorno
        return False


def _escribiendo_guiones(queue: JobQueue | None, carpeta: str) -> bool:
    """Si hay una tanda de guiones de esta carpeta en cola o en curso."""
    if queue is None:
        return False
    try:
        return any(
            job.mode == JobMode.NICHO_ROPA_GUIONES
            and str(job.params.get("carpeta") or "") == carpeta
            and job.status in (JobStatus.PENDING, JobStatus.RUNNING)
            for job in queue.get_all()
        )
    except Exception:  # noqa: BLE001 — el sondeo es un adorno
        return False


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

    # El pago a plazos lo dice la ficha, pero se puede corregir: la captura
    # puede venir cortada, o el vendedor cambiarlo. `plazos_auto` devuelve el
    # control a la ficha.
    if body.plazos_auto or body.plazos is not None:
        try:
            if body.plazos_auto:
                product_repo.quitar_campos(carpeta, body.producto, "plazos_manual")
            else:
                product_repo.update_product(
                    carpeta, body.producto, plazos_manual=bool(body.plazos),
                )
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e

    if body.uploaded is not None:
        try:
            # Con la FECHA: sin ella el chip decía "subido" y no había forma de
            # saber si fue hoy o hace una semana — que es justo lo que se
            # mira al preparar la publicación del día.
            product_repo.update_personal(
                carpeta, body.producto, usuario, uploaded=bool(body.uploaded),
                uploaded_at=int(time.time()) if body.uploaded else 0,
            )
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e
        # Al contador de publicaciones del día (la barra "Vídeos N/25"),
        # como hacen el POV BOF, el Largo, Carruseles y Creativos. Faltaba:
        # Ana marcaba vídeos de moda como subidos y su contador no se movía.
        _contar_subida(f"ropa:{carpeta}:{body.producto}", bool(body.uploaded), usuario)

    # El ranking de vendidos es POR USUARIO y común a todos los nichos: la
    # venta es de la cuenta de quien la hizo, no del catálogo de donde saliera
    # la prenda. Se guarda además en el documento para poder pintarlo sin leer
    # el índice entero.
    if body.sold is not None:
        try:
            product_repo.update_personal(
                carpeta, body.producto, usuario, sold=bool(body.sold),
            )
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e
        guardado = product_repo.get_product(carpeta, body.producto)
        try:
            if body.sold:
                pov_repo.marcar_vendido(
                    SOURCE_VENDIDOS, carpeta, body.producto,
                    titulo=guardado.get("titulo") or "",
                    tienda=guardado.get("tienda") or "",
                    product_url=guardado.get("product_url") or "",
                    usuario=usuario,
                )
            else:
                pov_repo.desmarcar_vendido(
                    SOURCE_VENDIDOS, carpeta, body.producto, usuario,
                )
        except Exception:  # noqa: BLE001
            # El dato bueno (`sold`) ya está guardado; que no se caiga por el
            # ranking, igual que en el POV BOF Largo.
            pass

    if body.en_escaparate is not None:
        guardado = product_repo.get_product(carpeta, body.producto)
        if not guardado.get("titulo"):
            raise APIError(
                "Este producto no tiene textos todavía: sin el nombre y la tienda "
                "no se puede saber si ya está en el escaparate.",
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
    # Con `cola=1` se encola y se contesta al momento: la lectura son varias
    # llamadas con imágenes y tarda minutos, así que salirse de la pantalla
    # (o que el móvil corte la petición) dejaba el trabajo a medias.
    cola: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasListResponse:
    """Lee las capturas con Gemini y guarda título, tienda, caption y emojis."""
    carpeta = carpeta or config.CARPETA_DEFECTO
    if cola:
        from src.queue.models import JobMode

        if _extrayendo_textos(queue, carpeta):
            raise APIError("Esa carpeta ya está leyéndose.", status_code=409)
        queue.enqueue(
            JobMode.NICHO_ROPA_TEXTOS,
            title=f"🔤 Textos · {config.carpeta_label(carpeta)}",
            params={"carpeta": carpeta},
            enqueued_by=usuario or None,
        )
        return list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)
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


@router.post("/guiones", status_code=201)
def escribir_guiones(
    body: GuionesRopaRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola los guiones de unas prendas, con el prompt del curso.

    Es lo que el curso manda hacer a mano en ChatGPT: su "pront base" + la
    foto de la ficha, y lo que devuelve se pega en el generador. Son diez
    llamadas a Gemini por carpeta y cada una tarda lo suyo, así que va por la
    COLA —como los guiones del POV BOF Largo— y no dentro de la petición: así
    se lanza y se sigue trabajando, y se ve por dónde va.

    Solo tiene sentido en los formatos cuyo guion se escribe FUERA (los de
    diálogo cerrado ya vienen con el texto puesto): si se pide en uno de esos,
    se contesta con un aviso en vez de encolar un trabajo que no hará nada.
    """
    from src.queue.models import JobMode

    carpeta = body.carpeta or config.CARPETA_DEFECTO
    sexo = config.sexo_de_carpeta(carpeta)
    modo = config.modo_valido(body.modo)
    estilos = config.prompts_mof10(sexo, False, modo, body.duracion)
    if not estilos:
        raise APIError(f"El modo {modo} no tiene prompt.", status_code=400)
    if not estilos[0].get("escrito_fuera"):
        raise APIError(
            "Este formato trae el guion cerrado del curso: se pega tal cual, "
            "no hay nada que escribir.",
            status_code=400,
        )

    cuantas = len(body.productos) if body.productos else 0
    alcance = f"{cuantas} prenda(s)" if cuantas else "la carpeta"
    job = queue.enqueue(
        JobMode.NICHO_ROPA_GUIONES,
        title=(
            f"✍️ Guiones · {config.carpeta_label(carpeta)} · "
            f"{estilos[0]['label']}" + (" (rehacer)" if body.rehacer else "")
        ),
        params={
            "carpeta": carpeta,
            # El modo con el que se pidió: el guion se guarda en SU hueco y la
            # cola tarda, así que resolverlo al guardar metería los guiones en
            # el modo que estuviera abierto entonces.
            "modo": modo,
            "duracion": body.duracion,
            "productos": [str(x) for x in (body.productos or [])],
            "rehacer": bool(body.rehacer),
            "usuario": usuario,
        },
        enqueued_by=usuario or None,
    )
    return {"job_id": job.id, "message": f"Guiones de {alcance}, en la cola."}


def _contar_subida(referencia: str, subido: bool, usuario: str) -> None:
    """Suma (o resta) el vídeo en el tope diario de la cuenta.

    Nunca tumba la petición: el dato bueno es el de la prenda, y quedarse sin
    contador es molesto pero no impide trabajar.
    """
    try:
        from src.cuotas.repos import cuota_repo

        cuota_repo.marcar("videos", referencia, usuario, subido)
    except Exception as e:  # noqa: BLE001
        logger.warning("[nicho_ropa] no se pudo apuntar en el contador: %s", e)


def _servir_foto(
    file_id: str, descargar: bool, nombre: str, ancho: int = 0,
) -> FileResponse:
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
    # Encogida para las miniaturas, como en el POV BOF: la tarjeta pinta un
    # cuadrado de 64px y mandaba la foto entera —uno o dos megas por prenda—,
    # así que una carpeta de diez eran veinte megas cada vez que se entraba.
    if ancho and not descargar:
        try:
            from src.nicho_pov_bof.services import thumbs

            path = thumbs.miniatura(path, ancho) or path
        except Exception:  # noqa: BLE001 — sin miniatura se sirve la original
            pass
    return FileResponse(
        str(path),
        media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
        filename=nombre if descargar else None,
        # Una foto de Drive es inmutable (su ID lo es), pero una RUTA se
        # reutiliza: borras una prenda, subes otra y `Tareas 1/1.jpg` es otra
        # foto con la misma URL. Cachearla un día enseñaba la vieja — pasó en
        # el POV BOF y allí se resolvió igual.
        headers={
            # Las de los catálogos propios llevan la fecha del fichero pegada
            # al id (`ruta#mtime`), así que al sustituir una foto cambia la URL
            # y se puede cachear igual que las de Drive. Solo van sin caché las
            # que llegan sin esa marca, que son las que sí pueden repetir ruta.
            "Cache-Control": (
                "public, max-age=86400"
                if (not propia or "#" in str(file_id))
                else "no-cache"
            ),
        },
    )


@router.get("/foto")
def get_foto(
    file_id: Annotated[str, Query()],
    w: Annotated[int, Query()] = 0,
) -> FileResponse:
    """Miniatura/foto por file ID (el nombre no vale: hay duplicados).

    Con `w` sale encogida a ese ancho: es lo que pide la tarjeta, que solo
    necesita reconocer la prenda.
    """
    return _servir_foto(file_id, descargar=False, nombre="", ancho=w)


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


# ---------------------------------------------------------------------------
# Personaje fijo de Marca Personal (el que se adjunta en Flow con la prenda)
# ---------------------------------------------------------------------------
@router.get("/personaje-marca/estado")
def estado_personaje_marca(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_ropa.services import personaje_marca

    return personaje_marca.estado(usuario)


@router.get("/personaje-marca")
def ver_personaje_marca(
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve la foto del personaje. Auth por `?api_key=` (va en un `<img src>`)."""
    from src.nicho_ropa.services import personaje_marca

    ruta = personaje_marca.obtener(usuario)
    if not ruta:
        raise APIError(
            "No hay personaje de Marca Personal. Súbelo desde la pantalla.",
            status_code=404,
        )
    media = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    headers = {"Cache-Control": "private, max-age=86400"}
    if descargar:
        headers["Content-Disposition"] = (
            f'attachment; filename="personaje_marca{ruta.suffix.lower()}"'
        )
    return FileResponse(ruta, media_type=media, headers=headers)


@router.post("/personaje-marca")
async def subir_personaje_marca(
    archivo: Annotated[UploadFile, File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_ropa.services import personaje_marca

    nombre = (archivo.filename or "").lower()
    if not any(nombre.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")):
        raise APIError(
            f"Formato no soportado ({archivo.filename!r}). Acepta jpg, jpeg, png o webp.",
            status_code=400,
        )
    datos = await archivo.read()
    if not datos:
        raise APIError("La foto llegó vacía.", status_code=400)
    if len(datos) > 12 * 1024 * 1024:
        raise APIError(
            f"La foto pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.",
            status_code=400,
        )
    try:
        await run_in_threadpool(
            personaje_marca.guardar, usuario, datos, archivo.filename or "",
        )
    except OSError as e:
        raise APIError(f"No se pudo guardar el personaje: {e}", status_code=500) from e
    return personaje_marca.estado(usuario)


@router.delete("/personaje-marca")
def borrar_personaje_marca(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_ropa.services import personaje_marca

    personaje_marca.borrar(usuario)
    return personaje_marca.estado(usuario)


@router.post("/variantes/upload")
async def subir_variantes(
    carpeta: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """La captura del selector de colores de la ficha (formato Tienda Colores).

    Se sube ANTES de escribir los guiones: es de donde salen los nombres
    exactos de las variantes. Una por prenda; subir otra sustituye la anterior.
    """
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    datos = await file.read()
    try:
        ruta = variantes.guardar(carpeta, producto, datos, file.filename or "")
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except OSError as e:
        raise APIError(f"No se pudo guardar la captura: {e}", status_code=500) from e
    # Los colores se leen AQUÍ (una llamada con solo esta imagen) y se
    # guardan en la ficha: al guion le llegan como texto. Si Gemini falla, la
    # captura queda guardada y el guion los volverá a intentar leer.
    leido: dict = {"colores": [], "hex": {}}
    aviso = ""
    try:
        leido = await run_in_threadpool(variantes.extraer, ruta)
        variantes.guardar_leidos(carpeta, producto, leido)
        if not leido["colores"]:
            aviso = "En la captura no se ve ningún selector de color."
        else:
            # Las miniaturas recortadas: la foto del producto en cada color
            # para adjuntar en Flow. Si no cuadran, se avisa y ya.
            recortes = await run_in_threadpool(
                variantes.recortar_miniaturas, ruta, leido["colores"], carpeta, producto,
            )
            if not recortes:
                aviso = "Colores leídos, pero no se pudieron recortar las miniaturas de la captura."
    except Exception as e:  # noqa: BLE001 — la captura ya está guardada
        aviso = f"Captura guardada, pero no se pudieron leer los colores: {str(e)[:120]}"
    return {
        "ok": True, "producto": producto, "variantes_foto": True,
        "colores": leido["colores"], "aviso": aviso,
    }


@router.post("/variantes/quitar")
def quitar_variantes(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
) -> dict:
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    quitada = variantes.quitar(carpeta, producto)
    product_repo.quitar_campos(carpeta, producto, "variantes")
    return {"ok": True, "producto": producto, "quitada": quitada}


@router.post("/variantes/color/upload")
async def subir_foto_color(
    carpeta: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    color: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """La imagen 1 con el pantalón en ESE color (hecha en Flow): es la foto
    que el montaje corta cuando la creadora nombra el color. Una por color."""
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    datos = await file.read()
    try:
        variantes.guardar_color(carpeta, producto, color, datos, file.filename or "")
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except OSError as e:
        raise APIError(f"No se pudo guardar la foto: {e}", status_code=500) from e
    return {"ok": True, "producto": producto, "color": color}


@router.post("/variantes/color/quitar")
def quitar_foto_color(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    color: Annotated[str, Query()],
) -> dict:
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    return {"ok": True, "quitada": variantes.quitar_color(carpeta, producto, color)}


@router.get("/variantes/color/foto")
def ver_foto_color(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    color: Annotated[str, Query()],
):
    from fastapi.responses import FileResponse

    f = variantes.ruta_color(carpeta, producto, color)
    if not f:
        raise APIError("Ese color no tiene foto.", status_code=404)
    return FileResponse(str(f), headers={"Cache-Control": "no-cache"})


@router.get("/foto-color-producto")
def ver_foto_color_producto(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    k: Annotated[int, Query()] = 1,
    descargar: Annotated[bool, Query()] = False,
):
    """La foto k-ésima (1…) del producto en otro color, tal como vino en el ZIP."""
    from fastapi.responses import FileResponse

    fotos = prendas_web.fotos_color(carpeta, producto)
    if k < 1 or k > len(fotos):
        raise APIError("Esa prenda no tiene esa foto de color.", status_code=404)
    f = fotos[k - 1]
    cabeceras = {"Cache-Control": "public, max-age=86400"}
    if descargar:
        # Con nombre: en el móvil, sin esto la foto se guarda como
        # "foto-color-producto" y no se sabe de qué prenda es.
        cabeceras["Content-Disposition"] = (
            f'attachment; filename="{producto}_color_{k}{f.suffix.lower()}"'
        )
    return FileResponse(str(f), headers=cabeceras)


@router.get("/variantes/miniatura")
def ver_miniatura_variante(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    color: Annotated[str, Query()],
):
    """La miniatura de esa variante recortada de la captura del selector."""
    from fastapi.responses import FileResponse

    f = variantes.ruta_miniatura(carpeta, producto, color)
    if not f:
        raise APIError("Esa variante no tiene miniatura recortada.", status_code=404)
    return FileResponse(str(f), headers={"Cache-Control": "no-cache"})


@router.get("/variantes/foto")
def ver_variantes(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
):
    """La captura subida, para comprobarla desde la tarjeta."""
    from fastapi.responses import FileResponse

    f = variantes.ruta(carpeta, producto)
    if not f:
        raise APIError("Esa prenda no tiene captura de variantes.", status_code=404)
    return FileResponse(str(f), headers={"Cache-Control": "no-cache"})


@router.post("/video/quitar-clip")
def quitar_clip(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    modo: Annotated[str, Query()],
    parte: Annotated[int, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Quita un clip subido por error de su hueco, antes de que se monte."""
    try:
        quedan = product_repo.quitar_clip(
            carpeta or config.CARPETA_DEFECTO, producto, config.modo_valido(modo), parte,
            usuario,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True, "clips_subidos": sorted(int(k) for k in quedan if k.isdigit())}


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
    # Dónde está la cámara en este vídeo. Cada modo guarda el suyo.
    modo: Annotated[str, Form()] = "",
    # Qué mitad del vídeo es, en los formatos que se graban en dos clips
    # (calle dividido). 0 o 1 en los de siempre, que son de un clip.
    parte: Annotated[int, Form()] = 0,
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

    # Los formatos que se graban por partes esperan a tenerlas todas: con un
    # solo clip no hay nada que pegar, y montar la primera mitad sola sería
    # publicar medio vídeo.
    modo_norm = config.modo_valido(modo)
    partes = config.partes_de_modo(modo_norm)
    rutas = [str(destino)]
    if partes > 1:
        n = parte if 1 <= parte <= partes else 1
        clips = product_repo.guardar_clip(
            slug, producto, modo_norm, n, str(destino), operator,
        )
        faltan = [str(i) for i in range(1, partes + 1) if not clips.get(str(i))]
        if faltan:
            return VideoRopaUploadResponse(
                ok=True, job_id=None,
                message=(
                    f"Clip {n} guardado. Falta el {', '.join(faltan)} para montar."
                ),
            )
        rutas = [clips[str(i)] for i in range(1, partes + 1)]

    job = queue.enqueue(
        JobMode.NICHO_ROPA_VIDEO,
        title=(
            f"👕 Vídeo Nicho Ropa · {config.carpeta_label(slug)}"
            f" · prenda {producto}"
        ),
        params={
            "producto": producto,
            "carpeta": slug,
            # `raw_path` se mantiene por los trabajos ya encolados; `raw_paths`
            # es el que manda cuando el formato son varios clips.
            "raw_path": rutas[0],
            "raw_paths": rutas,
            "sexo": sexo_norm,
            "conservar_audio": con_audio,
            "modo": modo_norm,
            "operator": operator,
        },
        enqueued_by=operator or None,
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
    modo: Annotated[str, Query()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve el vídeo ya montado de ese modo de grabación (el de ese usuario)."""
    prod = product_repo.get_product(carpeta or config.CARPETA_DEFECTO, producto, usuario)
    ruta = product_repo.video_de(prod, modo)["video_path"]
    if not ruta or not Path(ruta).is_file():
        raise APIError(f"La prenda {producto} no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=Path(ruta).name if descargar else None,
    )
