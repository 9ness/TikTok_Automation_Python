"""Endpoints del Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro).

- GET  /api/v1/nicho-pov-bof-largo/voces          → banco de voces por sexo
- GET  /api/v1/nicho-pov-bof-largo/sources        → las fuentes de Drive
- GET  /api/v1/nicho-pov-bof-largo/folders        → carpetas + progreso PROPIO
- POST /api/v1/nicho-pov-bof-largo/complete       → marca carpeta hecha (propio)
- GET  /api/v1/nicho-pov-bof-largo/productos      → productos + guion + estado
- POST /api/v1/nicho-pov-bof-largo/producto/estado→ escaparate/subido/vendió
- POST /api/v1/nicho-pov-bof-largo/guion          → escribe (o reescribe) guion
- POST /api/v1/nicho-pov-bof-largo/clip/upload    → sube 1 de los 2 clips
- GET  /api/v1/nicho-pov-bof-largo/video          → sirve el vídeo montado

Las fotos y los TEXTOS del producto salen del Nicho POV BOF: aquí no se extrae
nada, solo se consulta (mismo Drive, mismas carpetas). Lo PROPIO —guion, clips,
vídeo montado y el progreso (carpeta hecha, escaparate, subido, vendió)— es
INDIVIDUAL de este nicho y va por usuario. El ranking de vendidos es el único
dato transversal: se apunta en el índice compartido con `nicho="pov_bof_largo"`.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_pov_bof_largo import (
    LoteLargoConfirmarRequest,
    LoteLargoConfirmarResponse,
    LoteLargoItem,
    LoteLargoResponse,
    ClipLargoUploadResponse,
    FolderLargo,
    FoldersLargoResponse,
    GuionLargoRequest,
    GuionesLoteRequest,
    GuionLargoResponse,
    MarkCompletedLargoRequest,
    MarkCompletedLargoResponse,
    ProductoEstadoLargoRequest,
    ProductoLargo,
    ProductosLargoResponse,
    VocesLargoResponse,
    VozLargo,
)
from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.repos import product_repo
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-pov-bof-largo",
    tags=["nicho-pov-bof-largo"],
    dependencies=[Depends(get_current_user)],
)

_EXTS_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}


def _precio(textos: dict, campo: str = "precio") -> float:
    from src.nicho_pov_bof import config as pov_config

    return pov_config.precio_num(textos.get(campo))


def _es_plazos(textos: dict) -> bool:
    """¿Al producto le toca el guion con la frase de financiación?

    El precio lo extrae el POV BOF (aquí solo se lee) y el umbral es el suyo:
    son el mismo producto y la misma cuenta, así que no puede haber dos
    criterios distintos según el nicho desde el que se grabe.
    """
    from src.nicho_pov_bof import config as pov_config

    return pov_config.precio_num(textos.get("precio")) >= pov_config.PRECIO_MIN_PLAZOS


def _bad(msg: str) -> APIError:
    return APIError(msg, status_code=400)


def _clip_puesto(ruta, desde: float = 0.0) -> bool:
    """¿Hay un clip de ESTA ronda en ese slot?

    Dos motivos para no fiarse del path guardado a secas:

    - Las subidas viven en `api_uploads/` y se purgan a las 24h, así que la ruta
      puede apuntar a un fichero que ya no está.
    - `desde` (el `video_listo_at` del último montaje) descarta los clips de la
      ronda ANTERIOR. Es lo que arregla solos a los productos de antes del
      cambio, que se quedaron con los paths de su montaje previo guardados: sin
      esto, resubir el clip 1 montaba otra vez con el clip 2 viejo.
    """
    if not ruta:
        return False
    f = Path(str(ruta))
    try:
        return f.is_file() and (not desde or f.stat().st_mtime >= desde - 1)
    except OSError:
        return False


@router.get("/voces", response_model=VocesLargoResponse)
def list_voces() -> VocesLargoResponse:
    return VocesLargoResponse(
        hombre=[VozLargo(**v) for v in config.VOCES["hombre"]],
        mujer=[VozLargo(**v) for v in config.VOCES["mujer"]],
    )


@router.get("/sources")
def list_sources() -> dict:
    return {"items": [
        {"slug": slug, "label": meta.get("label", slug)}
        for slug, meta in config.SOURCES.items()
    ]}


@router.get("/folders", response_model=FoldersLargoResponse)
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FoldersLargoResponse:
    """Carpetas del Drive COMPARTIDO con el progreso PROPIO de este nicho.

    Las carpetas son las mismas del POV BOF; qué está completado sale del
    progreso individual del Largo (`progress_repo` con prefijo propio).
    """
    from src.nicho_pov_bof.services import drive_client
    from src.nicho_pov_bof_largo.repos import progress_repo

    try:
        carpetas = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    completed = progress_repo.get_completed(source, usuario)
    items = [
        FolderLargo(
            name=c.get("name"), id=c.get("id", ""),
            completed=c.get("name") in completed,
            desde_copia=bool(c.get("desde_copia")),
        )
        for c in carpetas
    ]
    current = next((i.name for i in items if not i.completed), None)
    return FoldersLargoResponse(
        source=source,
        items=items,
        total=len(items),
        completed_count=sum(1 for i in items if i.completed),
        current=current,
    )


@router.post("/complete", response_model=MarkCompletedLargoResponse)
def mark_completed(
    body: MarkCompletedLargoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> MarkCompletedLargoResponse:
    """Marca/desmarca una carpeta como hecha EN ESTE NICHO. Progreso propio."""
    from src.nicho_pov_bof.services import drive_client
    from src.nicho_pov_bof_largo.repos import progress_repo

    try:
        carpetas = drive_client.list_product_folders(body.source)
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    names = [c["name"] for c in carpetas]
    if body.folder not in names:
        raise _bad(f"Carpeta desconocida en {body.source!r}: {body.folder!r}")

    try:
        if body.completed:
            progress_repo.mark_completed(body.source, body.folder, usuario)
        else:
            progress_repo.unmark_completed(body.source, body.folder, usuario)
        completed = progress_repo.get_completed(body.source, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    next_folder = next((n for n in names if n not in completed), None)
    return MarkCompletedLargoResponse(
        source=body.source,
        folder=body.folder,
        completed=body.completed,
        completed_count=sum(1 for n in names if n in completed),
        total=len(names),
        next_folder=next_folder,
    )


def _montandose(queue: JobQueue | None, source: str, folder: str) -> set[str]:
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.NICHO_POV_BOF_LARGO_VIDEO:
                continue
            p = job.params or {}
            if str(p.get("source")) != source or str(p.get("folder")) != folder:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(p.get("producto")))
    except Exception:
        pass
    return activos


def _listar(
    source: str, folder: str, queue: JobQueue | None, usuario: str,
    refresh: bool = False,
) -> ProductosLargoResponse:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado, textos_fijos
    from src.nicho_pov_bof.services import audience, drive_client, photo_pairing
    from src.nicho_pov_bof.services import emojis as emojis_svc
    from src.nicho_pov_bof.services import top_vendidos

    try:
        # `refresh` salta la caché de listados: una carpeta que se listó vacía
        # (Drive lento, fotos aún sin subir) se quedaba vacía en pantalla hasta
        # que caducara, sin forma de forzarlo desde la app.
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder, refresh=refresh)
        ]
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    # Si el Drive del curso vació la carpeta, las fotos vienen de nuestra copia.
    desde_copia = drive_client.desde_la_copia(fotos)
    pares = photo_pairing.pair_folder(fotos)
    propio = (product_repo.load_folder(source, folder, usuario).get("productos") or {})
    # Los textos del POV BOF, de UNA lectura para toda la carpeta. Pedirlos
    # producto a producto eran diez viajes a Redis por carpeta —cuarenta en el
    # ranking completo— y ahí se iban los segundos que hacían que la pantalla
    # siguiera enseñando lo de la vez anterior.
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    textos_carpeta = (
        pov_repo.load_folder_para(source, folder, usuario).get("productos") or {}
    )
    activos = _montandose(queue, source, folder)
    # Escaparate GLOBAL por (tienda|nombre): un producto marcado en cualquier
    # carpeta sale marcado en todas las que sean el mismo producto.
    esc_index = product_repo.escaparate_index(usuario)
    # La ficha de TikTok Shop es del producto y es común a los tres usuarios.
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    urls = pov_repo.urls_index()
    # Solo devuelve algo en "Top vendidos"; en las demás fuentes es {}.
    ventas = top_vendidos.ventas_por_producto(source)

    items: list[ProductoLargo] = []
    for par in pares:
        pid = str(par["producto"])
        # Los textos del producto son del POV BOF; lo de este nicho es `mio`.
        textos = textos_carpeta.get(pid) or {}
        mio = propio.get(pid) or {}
        fijos = textos_fijos(f"{pid} {folder}")
        guion = str(mio.get("guion") or "")
        items.append(ProductoLargo(
            producto=pid,
            desde_copia=desde_copia,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            subida_at=min(
                (
                    str((par.get(k) or {}).get("mtime") or "")
                    for k in ("clean", "titled")
                    if str((par.get(k) or {}).get("mtime") or "")
                ),
                default="",
            ),
            # Textos y enlaces: compartidos con el POV BOF (los extrae/busca él).
            titulo=textos.get("titulo", ""),
            titulo_tiktok_completo=textos.get("titulo_tiktok_completo", ""),
            tienda=textos.get("tienda", ""),
            caption=textos.get("caption", ""),
            emojis=textos.get("emojis") or emojis_svc.emojis_para(
                pid, textos.get("titulo", ""), textos.get("caption", ""),
            ),
            gancho=fijos["gancho"],
            cta=fijos["cta"],
            caption_riesgo=caption_arriesgado(textos.get("caption", "")) or "",
            sexo_sugerido=audience.sexo_sugerido(
                textos.get("titulo", ""), textos.get("titulo_tiktok_completo", ""),
            ),
            product_url=pov_repo.url_de(textos, urls),
            url_match_name=str(textos.get("url_match_name") or ""),
            url_match_score=float(textos.get("url_match_score") or 0.0),
            ventas=int((ventas.get(f"{folder}|{pid}") or {}).get("ventas") or 0),
            vendido_at=float((ventas.get(f"{folder}|{pid}") or {}).get("vendido_at") or 0),
            precio=_precio(textos),
            precio_lista=_precio(textos, "precio_lista"),
            modo_plazos=_es_plazos(textos),
            guion_plazos=bool(mio.get("guion_plazos")),
            # Lo propio: guion, clips, voz, vídeo y estado INDIVIDUAL.
            guion=guion,
            subliminal=str(mio.get("subliminal") or ""),
            guion_caracteres=len(guion),
            clip1=_clip_puesto(mio.get("clip1_path"), float(mio.get("video_listo_at") or 0)),
            clip2=_clip_puesto(mio.get("clip2_path"), float(mio.get("video_listo_at") or 0)),
            clip3=_clip_puesto(mio.get("clip3_path"), float(mio.get("video_listo_at") or 0)),
            # Con guiones largos dos clips se quedan cortos y el montaje tendría
            # que estirarlos hasta deformar el gesto: ahí se pide un tercero.
            clips_necesarios=config.clips_necesarios(guion),
            voz_label=str(mio.get("voz_label") or ""),
            voz_sexo=str(mio.get("voz_sexo") or ""),
            # Mismo criterio que el POV BOF y Creativos (índice compartido o
            # marca antigua). Antes aquí solo se miraba el índice y la misma
            # carpeta salía llena en un nicho y a cero en este.
            en_escaparate=product_repo.marcado_en_escaparate(
                {**textos, "en_escaparate": mio.get("en_escaparate")}, esc_index
            ),
            uploaded=bool(mio.get("uploaded")),
            uploaded_at=float(mio.get("uploaded_at") or 0),
            sold=bool(mio.get("sold")),
            video_path=mio.get("video_path"),
            video_listo_at=int(mio.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return ProductosLargoResponse(
        source=source, folder=folder, items=items, montando=bool(activos),
    )


@router.get("/productos", response_model=ProductosLargoResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
    refresh: Annotated[bool, Query()] = False,
) -> ProductosLargoResponse:
    return _listar(source, folder, queue, usuario, refresh=refresh)


@router.get("/productos-todos", response_model=ProductosLargoResponse)
def list_productos_todos(
    source: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosLargoResponse:
    """Todos los productos de la fuente, de MÁS a MENOS ventas.

    Mismo motivo que en el POV BOF: en Top vendidos el sitio de cada producto
    es fijo (moverlo perdería el progreso), así que el ranking solo se ve
    juntando las carpetas. Solo vale para esa fuente.
    """
    from src.nicho_pov_bof.services import top_vendidos

    if source != top_vendidos.SOURCE:
        raise APIError(
            "El listado global solo existe en Top vendidos: en las demás "
            "fuentes hay demasiadas carpetas que leer.",
            status_code=400,
        )
    # Las carpetas se listan A LA VEZ: son cuatro y en fila iban sumando sus
    # segundos, que es lo que hacía que el ranking tardara en aparecer. Cada
    # una es independiente (su Drive, su documento de Redis).
    from concurrent.futures import ThreadPoolExecutor

    carpetas = top_vendidos.carpetas()

    def _una(carpeta: str):
        try:
            return carpeta, _listar(source, carpeta, queue, usuario)
        except Exception:  # noqa: BLE001
            # Una carpeta ilegible no deja sin lista a las demás.
            return carpeta, None

    items: list[ProductoLargo] = []
    montando = False
    with ThreadPoolExecutor(max_workers=min(4, len(carpetas) or 1)) as pool:
        for carpeta, parcial in pool.map(_una, carpetas):
            if parcial is None:
                continue
            montando = montando or parcial.montando
            items.extend(x.model_copy(update={"folder": carpeta}) for x in parcial.items)
    items.sort(key=lambda p: (p.ventas, p.vendido_at), reverse=True)
    return ProductosLargoResponse(source=source, folder="", items=items, montando=montando)


@router.post("/producto/estado", response_model=ProductoLargo)
def set_producto_estado(
    body: ProductoEstadoLargoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoLargo:
    """Escaparate / Subido / Vendió.

    - **Subido**: progreso INDIVIDUAL de este nicho (documento propio del Largo).
    - **Escaparate**: índice GLOBAL por (tienda|nombre). Meter un producto en el
      escaparate es una acción única por producto (da igual la carpeta), así que
      marcado en una carpeta aparece marcado en todas las que sean el mismo
      producto.
    - **Vendió**: ranking de vendidos, que es un índice ÚNICO y GLOBAL entre
      todos los nichos (no se clasifica por nicho): una venta marcada aquí se ve
      igual en el POV BOF y viceversa (ver `product_repo.marcar_vendido`).
    """
    textos = product_repo.textos_producto(
        body.source, body.folder, body.producto, usuario
    )
    try:
        campos: dict = {}
        if body.uploaded is not None:
            campos["uploaded"] = body.uploaded
            # La hora la sella el servidor: es lo que deja comprobar que un
            # producto repetido se marcó bien (si cambia, el toque entró).
            campos["uploaded_at"] = time.time() if body.uploaded else 0
        if body.sold is not None:
            campos["sold"] = body.sold
            # Vender implica haberlo subido — mismo criterio que el POV BOF.
            if body.sold:
                campos["uploaded"] = True
        if body.en_escaparate is not None:
            # Se guarda TAMBIÉN en el documento de este nicho (que es lo que
            # lee el listado): la clave del índice es `tienda|titulo`, así que
            # al re-extraer los textos la marca se quedaría huérfana.
            campos["en_escaparate"] = body.en_escaparate
        if campos:
            product_repo.update_product(
                body.source, body.folder, body.producto, usuario=usuario, **campos,
            )
        if body.en_escaparate is not None:
            product_repo.marcar_escaparate_producto(
                textos, body.en_escaparate, usuario,
            )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # "Subido" lo marca el operador al publicar: es lo que alimenta el tope
    # diario de la cuenta (el mismo para todos los nichos).
    if body.uploaded is not None:
        try:
            from src.cuotas.repos import cuota_repo

            cuota_repo.marcar(
                "videos",
                f"pov_bof_largo|{body.source}|{body.folder}|{body.producto}",
                usuario, body.uploaded,
            )
        except Exception:
            pass

    # Marcar Escaparate o Subido NO necesita releer nada del Drive: se responde
    # con lo guardado. Antes se relistaba la carpeta ENTERA (emparejar las
    # fotos de sus diez productos, leyéndolas del Drive montado) y el botón
    # tardaba 10-15 segundos en la acción que más se repite del día. Solo se
    # paga ese listado al marcar "Vendió", que sí necesita título, tienda y
    # foto para escribirlos en el ranking.
    if body.sold is None:
        mio = product_repo.get_product(body.source, body.folder, body.producto, usuario)
        # El escaparate NO se guarda en el producto: vive en el índice global
        # por (tienda|nombre), porque el mismo producto se graba con varios
        # nichos y al Marketplace se sube una sola vez. Leyéndolo del producto
        # salía siempre `false`, así que marcar "Subido" apagaba el botón de
        # escaparate en la pantalla.
        en_escaparate = (
            body.en_escaparate
            if body.en_escaparate is not None
            else product_repo.marcado_en_escaparate(
                {**textos, **mio}, product_repo.escaparate_index(usuario),
            )
        )
        return ProductoLargo(
            producto=body.producto,
            titulo=textos.get("titulo", ""),
            tienda=textos.get("tienda", ""),
            en_escaparate=bool(en_escaparate),
            uploaded=bool(mio.get("uploaded")),
            uploaded_at=float(mio.get("uploaded_at") or 0),
            sold=bool(mio.get("sold")),
        )

    listado = _listar(body.source, body.folder, queue, usuario)
    item = next((x for x in listado.items if x.producto == body.producto), None)
    if item is None:
        raise APIError(f"No existe el producto {body.producto}.", status_code=404)

    # Ranking de vendidos: índice único y GLOBAL, sin clasificar por nicho.
    if body.sold is not None:
        from src.nicho_pov_bof.repos import product_repo as pov_repo

        try:
            if body.sold:
                pov_repo.marcar_vendido(
                    body.source, body.folder, body.producto,
                    titulo=item.titulo or "", tienda=item.tienda or "",
                    clean_photo_id=item.clean_photo_id or "",
                    product_url=item.product_url or "",
                )
            else:
                pov_repo.desmarcar_vendido(body.source, body.folder, body.producto)
        except Exception:
            # El dato bueno (`sold`) ya está guardado; que no se caiga por el
            # ranking.
            pass

    return item


@router.post("/guion", response_model=GuionLargoResponse)
def escribir_guion(
    body: GuionLargoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> GuionLargoResponse:
    """Escribe el guion locutado de UN producto con el prompt del curso.

    Se guarda: remontar el mismo producto reutiliza el guion en vez de gastar
    otra llamada y salir distinto. Con `rehacer=True` se fuerza uno nuevo.
    """
    from src.nicho_pov_bof_largo.services import guionista

    guardado = product_repo.get_product(
        body.source, body.folder, body.producto, usuario
    )
    textos = product_repo.textos_producto(
        body.source, body.folder, body.producto, usuario
    )
    plazos = _es_plazos(textos)
    # Se reaprovecha el guion salvo que sea del otro modo: un producto de
    # plazos con un guion escrito sin la frase de financiación no vale.
    if (
        guardado.get("guion")
        and not body.rehacer
        and bool(guardado.get("guion_plazos")) == plazos
    ):
        return _uno(body, queue, usuario)

    if not textos.get("titulo"):
        raise _bad(
            "Este producto no tiene textos extraídos todavía. Pásale "
            "'Obtener textos' en el Nicho POV BOF y vuelve."
        )

    foto = None
    try:
        from src.nicho_pov_bof.services import drive_client, photo_pairing

        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(body.source, body.folder)
        ]
        par = next(
            (x for x in photo_pairing.pair_folder(fotos)
             if str(x.get("producto")) == body.producto), None,
        )
        limpia = (par or {}).get("clean") or {}
        if limpia.get("id"):
            foto = drive_client.fetch_photo(limpia["id"], suffix=".jpg")
    except Exception:
        foto = None

    try:
        escrito = guionista.escribir(
            titulo=textos.get("titulo", ""),
            tienda=textos.get("tienda", ""),
            caption=textos.get("caption", ""),
            foto=foto,
            plazos=plazos,
        )
    except ValueError as e:
        raise APIError(str(e), status_code=422) from e
    except Exception as e:
        raise APIError(f"Gemini no pudo escribir el guion: {e}", status_code=502) from e

    try:
        product_repo.update_product(
            body.source, body.folder, body.producto, usuario=usuario,
            guion=escrito["guion"], subliminal=escrito["subliminal"],
            nombre_guion=escrito["nombre"], guion_plazos=plazos,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _uno(body, queue, usuario)


@router.post("/guiones/lote", status_code=201)
def guiones_lote(
    body: GuionesLoteRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola los guiones de una carpeta o de TODO el catálogo (sin `folder`).

    Es lo único de este nicho que no se puede compartir: el guion habla de ESE
    producto, así que son diez llamadas a Gemini por carpeta. De una en una
    desde la pantalla son diez esperas seguidas; por la cola se lanza y se
    sigue trabajando.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.queue.models import JobMode, JobStatus

    alcance = body.folder or (
        pov_config.SOURCES.get(body.source, {}).get("label") or body.source
    ) + " · todas"
    title = f"✍️ Guiones · {alcance}" + (" (rehacer)" if body.rehacer else "")
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_LARGO_GUIONES,
        title=title,
        params={
            "source": body.source,
            "folder": body.folder,
            "usuario": usuario,
            "rehacer": bool(body.rehacer),
            "productos": [str(x) for x in (body.productos or [])],
        },
    )
    pendientes = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    return {
        "job_id": job.id,
        "title": title,
        "position_in_queue": next(
            (i for i, j in enumerate(pendientes) if j.id == job.id), 0
        ),
    }


def _uno(body: GuionLargoRequest, queue, usuario: str) -> GuionLargoResponse:
    listado = _listar(body.source, body.folder, queue, usuario)
    for item in listado.items:
        if item.producto == body.producto:
            return GuionLargoResponse(producto=item)
    raise APIError(f"No existe el producto {body.producto}.", status_code=404)


# ---------------------------------------------------------------------------
# Subida en tanda: los clips de toda la carpeta de golpe
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _ruta_de_token(token: str) -> Path:
    """Resuelve un bruto ya subido, sin dejar que se escape de su carpeta."""
    from src.api.temp_storage import upload_subdir

    if not _TOKEN_RE.match(token or ""):
        raise _bad(f"identificador de vídeo inválido: {token!r}")
    base = upload_subdir("nicho_pov_bof_largo").resolve()
    ruta = (base / token).resolve()
    if base not in ruta.parents or not ruta.is_file():
        raise _bad("ese vídeo ya no está (se purgan a las 24h). Vuelve a subirlo.")
    return ruta


@router.post("/video/lote/subir")
async def subir_uno_del_lote(
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Guarda UN vídeo de la tanda y devuelve su identificador.

    Van de uno en uno para poder enseñar el porcentaje de cada fichero: en una
    sola petición el botón se quedaba minutos diciendo "subiendo" sin que se
    supiera si quedaba mucho. Aquí no se reconoce nada todavía.
    """
    from src.api.temp_storage import upload_subdir

    nombre = (file.filename or "").lower()
    ext = next((e for e in _EXTS_VIDEO if nombre.endswith(e)), "")
    if not ext:
        raise _bad(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_EXTS_VIDEO))}."
        )
    dest = upload_subdir("nicho_pov_bof_largo")
    stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}")
    token = f"lote_{stub}_{int(time.time() * 1000)}_{os.getpid()}{ext}"
    try:
        with (dest / token).open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:
        raise APIError(f"No se pudo guardar {file.filename!r}: {e}", status_code=500) from e
    finally:
        await file.close()
    return {"token": token, "archivo": file.filename or token}


@router.get("/video/lote/archivo")
def ver_video_del_lote(
    token: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve un bruto ya subido para poder verlo antes de asignarlo.

    Cuando el reparto no reconoce un vídeo, con el nombre del fichero no hay
    forma de saber cuál es: hay que verlo. Auth por `?api_key=` porque va en un
    `<video src>`, que no manda cabeceras.
    """
    ruta = _ruta_de_token(token)
    return FileResponse(
        ruta, media_type="video/mp4", headers={"Cache-Control": "no-store"},
    )


@router.post("/video/lote/repartir", response_model=LoteLargoResponse)
def repartir_lote(
    body: dict,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> LoteLargoResponse:
    """Dice de qué producto es cada vídeo ya subido. No encola nada.

    Recibe los identificadores que devolvió `/video/lote/subir`, así que los
    vídeos no viajan dos veces.
    """
    from src.nicho_pov_bof.services import emparejador

    source = str(body.get("source") or "")
    folder = str(body.get("folder") or "")
    tokens = [str(x) for x in (body.get("tokens") or [])]
    if not tokens:
        raise _bad("no llegó ningún vídeo que repartir.")
    rutas = [_ruta_de_token(t) for t in tokens]

    fichas = _listar(source, folder, queue, usuario).items
    candidatos = [p.producto for p in fichas if p.clean_photo_id]
    # Aquí TODOS llevan al menos dos clips, y los de guion largo TRES: sin
    # decírselo, el reparto dejaba el tercer vídeo sin asignar (creía que ese
    # producto ya estaba servido).
    dobles = set(candidatos)
    cupos = {
        p.producto: int(p.clips_necesarios or 2)
        for p in fichas if p.clean_photo_id
    }
    reparto = emparejador.emparejar(
        source, folder, rutas, candidatos, dobles=dobles, cupos=cupos,
    )
    items = [
        LoteLargoItem(
            token=tok, archivo=tok,
            producto=str(r.get("producto") or ""), por_que=str(r.get("por_que") or ""),
        )
        for tok, r in zip(tokens, reparto)
    ]
    return LoteLargoResponse(
        source=source, folder=folder, items=items,
        reconocidos=sum(1 for i in items if i.producto),
    )


@router.post("/video/lote/confirmar", response_model=LoteLargoConfirmarResponse)
def confirmar_lote(
    body: LoteLargoConfirmarRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> LoteLargoConfirmarResponse:
    """Guarda cada clip en su sitio y encola los que ya tengan todos los suyos.

    El orden de la tanda manda: el primer vídeo de un producto es su clip 1, el
    segundo el 2 y el tercero el 3 (los guiones largos piden tres). Un producto
    al que le falte alguno se queda esperando, igual que subiéndolos a mano.
    """
    encolados, pendientes, mensajes = 0, 0, []
    vistos: dict[str, int] = {}
    for item in body.items:
        if not item.producto:
            continue
        vistos[item.producto] = vistos.get(item.producto, 0) + 1
        ruta = _ruta_de_token(item.token)
        prod = product_repo.get_product(body.source, body.folder, item.producto, usuario)
        if not prod.get("guion"):
            pendientes += 1
            mensajes.append(f"Producto {item.producto}: escribe antes el guion.")
            continue
        montado_at = float(prod.get("video_listo_at") or 0)
        hacen_falta = config.clips_necesarios(str(prod.get("guion") or ""))
        if vistos[item.producto] >= 2:
            # El enésimo vídeo de este producto en ESTA tanda va al hueco n.
            slot = min(vistos[item.producto], hacen_falta)
        else:
            # El primero va al primer hueco libre: puede que ya hubiera clips
            # subidos a mano antes de la tanda.
            slot = next(
                (
                    n for n in range(1, hacen_falta + 1)
                    if not _clip_puesto(prod.get(f"clip{n}_path"), montado_at)
                ),
                1,
            )
        r = _encolar_clip(
            queue, body.source, body.folder, item.producto, slot, ruta,
            body.sexo, usuario,
            con_gancho=body.con_gancho, con_titulo=body.con_titulo,
            con_cta=body.con_cta, con_flecha=body.con_flecha,
        )
        if r.encolado:
            encolados += 1
        else:
            pendientes += 1
            mensajes.append(f"Producto {item.producto}: {r.message}")
    return LoteLargoConfirmarResponse(
        encolados=encolados, pendientes=pendientes, mensajes=mensajes[:6],
    )


@router.post("/clip/quitar", response_model=ProductoLargo)
def quitar_clip(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    slot: Annotated[int, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoLargo:
    """Quita un clip subido por error, para poder poner otro.

    Hasta ahora un clip mal subido se quedaba puesto: la única salida era
    subir encima el bueno, y si el vídeo era de dos clips y el error estaba en
    el segundo, el montaje arrancaba con el equivocado.

    Solo borra el hueco. No toca el vídeo ya montado ni el guion.
    """
    if slot not in (1, 2, 3):
        raise _bad(f"slot debe ser 1, 2 o 3, recibido: {slot}")
    prod = product_repo.get_product(source, folder, producto, usuario)
    ruta = str(prod.get(f"clip{slot}_path") or "")
    try:
        product_repo.update_product(
            source, folder, producto, usuario=usuario, **{f"clip{slot}_path": ""},
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    # El bruto vive en `api_uploads/`, que se purga solo a las 24h; se borra ya
    # para no dejar ficheros de vídeo ocupando sitio sin motivo.
    if ruta:
        try:
            Path(ruta).unlink(missing_ok=True)
        except OSError:
            pass

    listado = _listar(source, folder, queue, usuario)
    item = next((x for x in listado.items if x.producto == producto), None)
    if item is None:
        raise APIError(f"No existe el producto {producto}.", status_code=404)
    return item


@router.post("/clip/upload", response_model=ClipLargoUploadResponse)
async def upload_clip(
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    slot: Annotated[int, Form()],
    sexo: Annotated[str, Form()],
    con_gancho: Annotated[bool, Form()] = True,
    con_titulo: Annotated[bool, Form()] = True,
    con_cta: Annotated[bool, Form()] = True,
    con_flecha: Annotated[bool, Form()] = True,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ClipLargoUploadResponse:
    """Sube UNO de los dos clips. Solo encola cuando están los dos.

    Con un solo clip no hay nada que montar: el guion dura ~20s y un clip son
    10s, así que faltaría medio vídeo.

    **Cada montaje empieza de cero.** Al encolar se olvidan los dos clips
    (`clipN_path=""`), así que subir una versión nueva de un producto YA montado
    vuelve a pedir los DOS clips. Antes no era así y salía caro: los paths
    viejos seguían guardados para siempre, así que al resubir el clip 1 se
    encolaba al instante un montaje con *clip1 nuevo + clip2 viejo*, y al
    resubir el clip 2 se encolaba OTRO — dos trabajos por producto, el primero
    con material mezclado.
    """
    from src.api.temp_storage import upload_subdir

    if slot not in (1, 2, 3):
        raise _bad(f"slot debe ser 1, 2 o 3, recibido: {slot}")
    sexo_norm = (sexo or "").strip().lower()
    # "auto" no está en `config.SEXOS` (eso son las voces de Fish): lo resuelve
    # el montaje mirando la mano del clip 1.
    if sexo_norm != "auto" and sexo_norm not in config.SEXOS:
        raise _bad(
            f"sexo debe ser {' o '.join(config.SEXOS)} o 'auto', recibido: {sexo!r}"
        )

    guardado = product_repo.get_product(source, folder, producto, usuario)
    if not guardado.get("guion"):
        raise _bad(
            "Primero escribe el guion de este producto: la voz sale de ahí y "
            "es la que decide cuánto dura el vídeo."
        )

    nombre = (file.filename or "").lower()
    ext = next((e for e in _EXTS_VIDEO if nombre.endswith(e)), "")
    if not ext:
        raise _bad(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_EXTS_VIDEO))}."
        )

    stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}_{producto}")
    destino = upload_subdir("nicho_pov_bof_largo") / (
        f"{stub}_clip{slot}_{int(time.time())}{ext}"
    )
    try:
        with destino.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:
        raise APIError(f"No se pudo guardar el clip: {e}", status_code=500) from e
    finally:
        await file.close()

    return _encolar_clip(
        queue, source, folder, producto, slot, destino, sexo_norm, usuario,
        con_gancho=con_gancho, con_titulo=con_titulo,
        con_cta=con_cta, con_flecha=con_flecha,
    )


def _encolar_clip(
    queue: JobQueue,
    source: str,
    folder: str,
    producto: str,
    slot: int,
    destino: Path,
    sexo: str,
    usuario: str,
    *,
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
) -> ClipLargoUploadResponse:
    """Guarda el clip en su hueco y encola el montaje si ya están los dos.

    Sale aparte de `upload_clip` porque lo usan los DOS caminos: subir un clip
    suelto y la subida en tanda. Duplicarlo habría acabado en dos versiones de
    la regla de "no montar hasta tener los dos".
    """
    try:
        prod = product_repo.update_product(
            source, folder, producto, usuario=usuario,
            **{f"clip{slot}_path": str(destino)},
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    montado_at = float(prod.get("video_listo_at") or 0)
    # Cuántos clips pide ESTE guion (dos, o tres si la voz no cabe en dos).
    hacen_falta = config.clips_necesarios(str(prod.get("guion") or ""))
    rutas = [
        prod.get(f"clip{n}_path") for n in range(1, hacen_falta + 1)
    ]
    puestos = [r for r in rutas if _clip_puesto(r, montado_at)]
    if len(puestos) < hacen_falta:
        faltan = [
            n for n in range(1, hacen_falta + 1)
            if not _clip_puesto(prod.get(f"clip{n}_path"), montado_at)
        ]
        return ClipLargoUploadResponse(
            encolado=False,
            message=(
                f"Clip {slot} guardado. Falta el clip "
                + " y el ".join(str(n) for n in faltan)
                + (f" (este guion necesita {hacen_falta})" if hacen_falta > 2 else "")
                + "."
            ),
        )

    # Red de seguridad para la carrera de los dos clips subidos a la vez: si el
    # otro ya disparó el montaje, no se encola un segundo trabajo igual.
    if producto in _montandose(queue, source, folder):
        return ClipLargoUploadResponse(
            encolado=False,
            message=f"Clip {slot} guardado. Ya hay un montaje en marcha para este producto.",
        )

    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_LARGO_VIDEO,
        title=f"🎙️ POV BOF Largo: producto {producto} · {folder}",
        params={
            "source": source, "folder": folder, "producto": producto,
            "clip1_path": prod["clip1_path"], "clip2_path": prod["clip2_path"],
            # Solo cuando el guion no cabe en dos.
            **({"clip3_path": prod.get("clip3_path") or ""} if hacen_falta > 2 else {}),
            "sexo": sexo, "operator": usuario,
            "con_gancho": bool(con_gancho), "con_titulo": bool(con_titulo),
            "con_cta": bool(con_cta), "con_flecha": bool(con_flecha),
        },
        enqueued_by=usuario or None,
    )

    # Ronda consumida: los clips ya viajan en los params del job, así que
    # olvidarlos aquí no afecta al montaje en curso y deja el producto listo
    # para una versión nueva (que volverá a pedir los dos clips).
    try:
        product_repo.update_product(
            source, folder, producto, usuario=usuario,
            clip1_path="", clip2_path="", clip3_path="",
        )
    except RuntimeError:
        # El montaje ya está encolado; que no falle la respuesta por esto.
        pass

    return ClipLargoUploadResponse(
        job_id=job.id, encolado=True,
        message="Los dos clips están: locutando y montando.",
    )


@router.get("/video")
def get_video(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    prod = product_repo.get_product(source, folder, producto, usuario)
    ruta = prod.get("video_path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(
            f"El producto {producto} no tiene vídeo montado.", status_code=404,
        )
    return FileResponse(
        ruta, media_type="video/mp4",
        filename=Path(ruta).name if descargar else None,
    )
