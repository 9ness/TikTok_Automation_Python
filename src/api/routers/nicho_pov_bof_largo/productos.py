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
) -> ProductosLargoResponse:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado, textos_fijos
    from src.nicho_pov_bof.services import audience, drive_client, photo_pairing
    from src.nicho_pov_bof.services import emojis as emojis_svc
    from src.nicho_pov_bof.services import top_vendidos

    try:
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    pares = photo_pairing.pair_folder(fotos)
    propio = (product_repo.load_folder(source, folder, usuario).get("productos") or {})
    activos = _montandose(queue, source, folder)
    # Escaparate GLOBAL por (tienda|nombre): un producto marcado en cualquier
    # carpeta sale marcado en todas las que sean el mismo producto.
    esc_index = product_repo.escaparate_index(usuario)
    # Solo devuelve algo en "Top vendidos"; en las demás fuentes es {}.
    ventas = top_vendidos.ventas_por_producto(source)

    items: list[ProductoLargo] = []
    for par in pares:
        pid = str(par["producto"])
        # Los textos del producto son del POV BOF; lo de este nicho es `mio`.
        textos = product_repo.textos_producto(source, folder, pid, usuario)
        mio = propio.get(pid) or {}
        fijos = textos_fijos(f"{pid} {folder}")
        guion = str(mio.get("guion") or "")
        items.append(ProductoLargo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
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
            product_url=str(textos.get("product_url") or ""),
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
) -> ProductosLargoResponse:
    return _listar(source, folder, queue, usuario)


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
        if campos:
            product_repo.update_product(
                body.source, body.folder, body.producto, usuario=usuario, **campos,
            )
        if body.en_escaparate is not None:
            product_repo.set_escaparate(
                textos.get("tienda", ""), textos.get("titulo", ""),
                body.en_escaparate, usuario,
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


@router.post("/video/lote", response_model=LoteLargoResponse)
async def subir_lote(
    files: Annotated[list[UploadFile], File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> LoteLargoResponse:
    """Sube los clips de la carpeta de golpe y dice de qué producto es cada uno.

    Aquí TODOS los productos llevan dos clips, así que cada uno puede llevarse
    dos vídeos de la tanda. No encola nada: el operador repasa y confirma.
    """
    from src.api.temp_storage import upload_subdir
    from src.nicho_pov_bof.services import emparejador

    dest = upload_subdir("nicho_pov_bof_largo")
    guardados: list[tuple[str, str]] = []
    for f in files:
        nombre = (f.filename or "").lower()
        ext = next((e for e in _EXTS_VIDEO if nombre.endswith(e)), "")
        if not ext:
            raise _bad(
                f"Formato de vídeo no soportado: {f.filename!r}. "
                f"Acepta: {', '.join(sorted(_EXTS_VIDEO))}."
            )
        stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}")
        token = f"lote_{stub}_{int(time.time() * 1000)}_{len(guardados)}{ext}"
        try:
            with (dest / token).open("wb") as out:
                shutil.copyfileobj(f.file, out)
        except Exception as e:
            raise APIError(f"No se pudo guardar {f.filename!r}: {e}", status_code=500) from e
        finally:
            await f.close()
        guardados.append((token, f.filename or token))

    fichas = _listar(source, folder, queue, usuario).items
    candidatos = [p.producto for p in fichas if p.clean_photo_id]
    reparto = emparejador.emparejar(
        source, folder, [dest / t for t, _ in guardados], candidatos,
        dobles=set(candidatos),
    )
    items = [
        LoteLargoItem(
            token=token, archivo=nombre,
            producto=str(r.get("producto") or ""), por_que=str(r.get("por_que") or ""),
        )
        for (token, nombre), r in zip(guardados, reparto)
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
    """Guarda cada clip en su sitio y encola los productos que ya tengan los dos.

    El orden de la tanda manda: el primer vídeo de un producto es su clip 1 y
    el segundo el clip 2. Un producto con un solo vídeo se queda esperando al
    otro, que es lo mismo que pasa subiéndolos a mano.
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
        if vistos[item.producto] >= 2:
            slot = 2
        else:
            slot = 1 if not _clip_puesto(prod.get("clip1_path"), montado_at) else 2
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

    if slot not in (1, 2):
        raise _bad(f"slot debe ser 1 o 2, recibido: {slot}")
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
    if not (
        _clip_puesto(prod.get("clip1_path"), montado_at)
        and _clip_puesto(prod.get("clip2_path"), montado_at)
    ):
        falta = 2 if slot == 1 else 1
        return ClipLargoUploadResponse(
            encolado=False, message=f"Clip {slot} guardado. Falta el clip {falta}.",
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
            clip1_path="", clip2_path="",
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
        filename=f"povlargo_{producto}_{folder}.mp4" if descargar else None,
    )
