"""Endpoints de la Cuenta Piloto (Programa 4 — Tiktok Shop AI Pro).

- GET    /api/v1/cuenta-piloto/productos      → los productos DEL USUARIO
- POST   /api/v1/cuenta-piloto/productos      → alta subiendo las DOS fotos
- POST   /api/v1/cuenta-piloto/extraer-textos → relee las fichas con Gemini
- PATCH  /api/v1/cuenta-piloto/producto       → corrige los textos a mano
- POST   /api/v1/cuenta-piloto/producto/estado → mete/saca del escaparate
- DELETE /api/v1/cuenta-piloto/producto       → borra producto + ficheros
- GET    /api/v1/cuenta-piloto/foto           → sirve la foto limpia o la ficha
- POST   /api/v1/cuenta-piloto/video/upload   → sube un bruto y encola el montaje
- GET    /api/v1/cuenta-piloto/video          → sirve el vídeo montado nº N

Todo va por usuario: no hay documento compartido. El `usuario` sale del token
(`get_web_user`), nunca de un parámetro — si viniera del cliente, cualquiera
podría leer los productos de otro cambiando la query.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.cuenta_piloto import (
    EstadoPilotoRequest,
    ProductoPiloto,
    ProductoPilotoResponse,
    ProductosPilotoResponse,
    TextosPilotoRequest,
    VideoPiloto,
    VideoPilotoUploadResponse,
)
from src.cuenta_piloto import config
from src.cuenta_piloto.repos import product_repo
from src.cuenta_piloto.services import photo_store
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/cuenta-piloto",
    tags=["cuenta-piloto"],
    dependencies=[Depends(get_current_user)],
)


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


def _montandose(queue: JobQueue | None, usuario: str) -> set[str]:
    """Productos con un montaje en cola o en marcha, para no dejar al operador
    subiendo el mismo vídeo dos veces creyendo que no se enteró."""
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.CUENTA_PILOTO_VIDEO:
                continue
            p = job.params or {}
            if str(p.get("operator") or "") != usuario:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(p.get("producto")))
    except Exception:
        pass
    return activos


def _escaparate(usuario: str) -> set[str]:
    """Claves del escaparate del usuario, de una sola lectura.

    Se pide UNA vez por listado y se pasa a `_a_schema`: preguntar producto a
    producto serían N viajes a Redis para pintar la misma pantalla.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    return pov_repo.escaparate_index(usuario)


def _a_schema(
    prod: dict, *, montando: bool = False, escaparate: set[str] | None = None,
) -> ProductoPiloto:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado, textos_fijos
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof.services import emojis as emojis_svc

    pid = str(prod.get("id") or "")
    # Gancho y CTA son los mismos textos fijos que en el POV BOF, sorteados a
    # partir del id: el montaje es el mismo, así que la ficha tiene que
    # enseñar exactamente lo que se va a quemar.
    fijos = textos_fijos(f"cuenta_piloto {pid}")
    videos = [v for v in (prod.get("videos") or []) if isinstance(v, dict)]
    return ProductoPiloto(
        id=pid,
        titulo=prod.get("titulo", ""),
        titulo_tiktok_completo=prod.get("titulo_tiktok_completo", ""),
        tienda=prod.get("tienda", ""),
        caption=prod.get("caption", ""),
        emojis=prod.get("emojis") or emojis_svc.emojis_para(
            pid, prod.get("titulo", ""), prod.get("caption", ""),
        ),
        gancho=fijos["gancho"],
        cta=fijos["cta"],
        caption_riesgo=caption_arriesgado(prod.get("caption", "")) or "",
        # El escaparate es un índice ÚNICO por (tienda|nombre) compartido con
        # los demás nichos: el mismo producto se sube al Marketplace una vez.
        en_escaparate=bool(
            escaparate is not None
            and pov_repo.clave_escaparate(
                prod.get("tienda", ""), prod.get("titulo", ""),
            )
            in escaparate
        ),
        tiene_ficha=bool(prod.get("foto_ficha")),
        videos=[
            VideoPiloto(
                n=i + 1,
                sexo=str(v.get("sexo") or ""),
                job_id=str(v.get("job_id") or ""),
                at=int(v.get("at") or 0),
            )
            for i, v in enumerate(videos)
        ],
        creado_at=float(prod.get("creado_at") or 0),
        textos_at=str(prod.get("textos_at") or ""),
        montando=montando,
    )


@router.get("/productos", response_model=ProductosPilotoResponse)
def list_productos(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosPilotoResponse:
    activos = _montandose(queue, usuario)
    escaparate = _escaparate(usuario)
    return ProductosPilotoResponse(items=[
        _a_schema(p, montando=str(p.get("id")) in activos, escaparate=escaparate)
        for p in product_repo.listar(usuario)
    ])


@router.post("/productos", response_model=ProductoPilotoResponse)
async def crear_producto(
    foto_limpia: Annotated[UploadFile, File()],
    foto_ficha: Annotated[UploadFile | None, File()] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoPilotoResponse:
    """Da de alta un producto con sus dos fotos y le saca los textos.

    La ficha es OPCIONAL: sin ella el producto queda creado igualmente y el
    operador escribe el título a mano. Con ella, se lee al vuelo con Gemini —
    es una sola llamada de un par de segundos, así que no merece una cola.
    """
    limpia = await _leer_foto(foto_limpia, "la foto limpia")
    ficha = await _leer_foto(foto_ficha, "la captura de la ficha") if foto_ficha else b""

    ruta_limpia = photo_store.guardar(
        usuario, limpia, filename=foto_limpia.filename or "", etiqueta="limpia",
    )
    ruta_ficha = ""
    if ficha:
        ruta_ficha = str(photo_store.guardar(
            usuario, ficha, filename=(foto_ficha.filename or ""), etiqueta="ficha",
        ))

    try:
        prod = product_repo.crear_producto(
            usuario, foto_limpia=str(ruta_limpia), foto_ficha=ruta_ficha,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    if ruta_ficha:
        # Si Gemini falla, el producto NO se pierde: queda creado sin textos y
        # el operador puede reintentar con "Obtener textos" sin volver a subir
        # las fotos.
        try:
            textos = _extraer([prod])
            if textos:
                product_repo.save_extracted_texts(usuario, textos)
                prod = product_repo.get_product(usuario, prod["id"])
        except Exception:
            pass

    return ProductoPilotoResponse(
        producto=_a_schema(prod, escaparate=_escaparate(usuario)),
    )


async def _leer_foto(archivo: UploadFile, que: str) -> bytes:
    if not photo_store.es_foto(archivo.filename or ""):
        raise _bad_request(
            f"{que.capitalize()} tiene un formato no soportado "
            f"({archivo.filename!r}). Acepta: "
            f"{', '.join(sorted(config.FOTO_EXTS))}."
        )
    datos = await archivo.read()
    if not datos:
        raise _bad_request(f"{que.capitalize()} llegó vacía.")
    if len(datos) > config.MAX_FOTO_BYTES:
        raise _bad_request(
            f"{que.capitalize()} pesa {len(datos) / 1e6:.0f} MB; el tope son "
            f"{config.MAX_FOTO_BYTES // 1024 // 1024} MB."
        )
    return datos


def _extraer(productos: list[dict]) -> dict[str, dict]:
    from src.cuenta_piloto.services import text_extractor

    return text_extractor.extraer(productos)


@router.post("/extraer-textos", response_model=ProductosPilotoResponse)
def extraer_textos(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
    producto: Annotated[str, Query()] = "",
) -> ProductosPilotoResponse:
    """Relee las fichas con Gemini. Sin `producto`, todos los que tengan ficha
    y sigan sin título — no se re-gastan llamadas en los que ya están."""
    todos = product_repo.listar(usuario)
    if producto:
        pendientes = [p for p in todos if str(p.get("id")) == producto]
        if not pendientes:
            raise APIError(f"No existe el producto {producto}.", status_code=404)
    else:
        pendientes = [
            p for p in todos
            if p.get("foto_ficha") and not str(p.get("titulo") or "").strip()
        ]
    if not pendientes:
        return list_productos(queue, usuario)

    con_ficha = [p for p in pendientes if p.get("foto_ficha")]
    if not con_ficha:
        raise _bad_request(
            "Ese producto no tiene captura de la ficha — escribe el título a mano."
        )

    try:
        textos = _extraer(con_ficha)
    except Exception as e:
        raise APIError(f"Gemini no pudo leer las fichas: {e}", status_code=502) from e
    if textos:
        try:
            product_repo.save_extracted_texts(usuario, textos)
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e
    return list_productos(queue, usuario)


@router.patch("/producto", response_model=ProductoPilotoResponse)
def editar_textos(
    body: TextosPilotoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoPilotoResponse:
    """Corrección a mano. Los campos que no se manden se dejan como estaban."""
    if not product_repo.get_product(usuario, body.producto):
        raise APIError(f"No existe el producto {body.producto}.", status_code=404)
    try:
        prod = product_repo.update_product(
            usuario, body.producto,
            titulo=body.titulo, tienda=body.tienda,
            caption=body.caption, emojis=body.emojis,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return ProductoPilotoResponse(
        producto=_a_schema(prod, escaparate=_escaparate(usuario)),
    )


@router.post("/producto/estado", response_model=ProductoPilotoResponse)
def set_producto_estado(
    body: EstadoPilotoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoPilotoResponse:
    """Mete o saca el producto del escaparate.

    No se guarda en el producto sino en el índice ÚNICO por (tienda|nombre):
    el mismo producto se graba con varios nichos, pero al Marketplace se sube
    UNA vez. Marcado aquí, sale marcado en el POV BOF y en el resto.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    prod = product_repo.get_product(usuario, body.producto)
    if not prod:
        raise APIError(f"No existe el producto {body.producto}.", status_code=404)
    if not prod.get("titulo"):
        raise APIError(
            "Este producto no tiene textos todavía: sin el nombre y la tienda no "
            "se puede saber si ya está en el escaparate.",
            status_code=400,
        )
    pov_repo.set_escaparate(
        prod.get("tienda", ""), prod.get("titulo", ""),
        body.en_escaparate, usuario,
    )
    return ProductoPilotoResponse(
        producto=_a_schema(prod, escaparate=_escaparate(usuario)),
    )


@router.delete("/producto", response_model=ProductosPilotoResponse)
def borrar_producto(
    producto: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosPilotoResponse:
    try:
        if not product_repo.borrar_producto(usuario, producto):
            raise APIError(f"No existe el producto {producto}.", status_code=404)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return list_productos(queue, usuario)


@router.get("/foto")
def get_foto(
    producto: Annotated[str, Query()],
    cual: Annotated[str, Query()] = "limpia",
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    if cual not in ("limpia", "ficha"):
        raise _bad_request("`cual` debe ser 'limpia' o 'ficha'.")
    prod = product_repo.get_product(usuario, producto)
    ruta = prod.get("foto_limpia" if cual == "limpia" else "foto_ficha")
    if not ruta or not Path(ruta).is_file():
        raise APIError(
            f"El producto {producto} no tiene foto {cual}.", status_code=404,
        )
    return FileResponse(
        ruta,
        media_type="image/jpeg",
        filename=f"piloto_{producto}_{cual}{Path(ruta).suffix}" if descargar else None,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.post("/video/upload", response_model=VideoPilotoUploadResponse)
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File()],
    producto: Annotated[str, Form()],
    sexo: Annotated[str, Form()],
    con_gancho: Annotated[bool, Form()] = True,
    con_titulo: Annotated[bool, Form()] = True,
    con_cta: Annotated[bool, Form()] = True,
    con_flecha: Annotated[bool, Form()] = True,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> VideoPilotoUploadResponse:
    """Sube UN vídeo orgánico y encola su montaje.

    Se puede repetir con el mismo producto tantas veces como se quiera: cada
    montaje se AÑADE a la lista, no sustituye al anterior.
    """
    from src.api.temp_storage import upload_subdir

    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm not in config.SEXOS:
        raise _bad_request(f"sexo debe ser 'hombre' o 'mujer', recibido: {sexo!r}")
    if not product_repo.get_product(usuario, producto):
        raise APIError(f"No existe el producto {producto}.", status_code=404)

    nombre = (file.filename or "").lower()
    ext = next((e for e in config.VIDEO_EXTS if nombre.endswith(e)), "")
    if not ext:
        raise _bad_request(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(config.VIDEO_EXTS))}."
        )

    # El bruto sí puede vivir en `api_uploads/` (se purga a las 24h): para
    # entonces el montaje ya terminó y lo que se conserva es el resultado.
    destino = upload_subdir("cuenta_piloto") / (
        f"{config._slug_usuario(usuario)}_{producto}_{int(time.time())}{ext}"
    )
    try:
        with destino.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:
        raise APIError(f"No se pudo guardar el vídeo: {e}", status_code=500) from e
    finally:
        await file.close()

    job = queue.enqueue(
        JobMode.CUENTA_PILOTO_VIDEO,
        title=f"🧪 Cuenta Piloto: producto {producto}",
        params={
            "producto": producto,
            "raw_path": str(destino),
            "sexo": sexo_norm,
            "operator": usuario,
            "con_gancho": bool(con_gancho),
            "con_titulo": bool(con_titulo),
            "con_cta": bool(con_cta),
            "con_flecha": bool(con_flecha),
        },
        enqueued_by=usuario or None,
    )
    return VideoPilotoUploadResponse(
        job_id=job.id, message="En la cola, procesando…",
    )


@router.get("/video")
def get_video(
    producto: Annotated[str, Query()],
    n: Annotated[int, Query()] = 1,
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve el vídeo montado número `n` del producto (1 = el primero)."""
    prod = product_repo.get_product(usuario, producto)
    videos = [v for v in (prod.get("videos") or []) if isinstance(v, dict)]
    if n < 1 or n > len(videos):
        raise APIError(
            f"El producto {producto} no tiene un vídeo nº {n} "
            f"(tiene {len(videos)}).",
            status_code=404,
        )
    ruta = videos[n - 1].get("path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(
            f"El vídeo nº {n} del producto {producto} ya no está en disco.",
            status_code=404,
        )
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=f"piloto_{producto}_v{n}.mp4" if descargar else None,
    )
