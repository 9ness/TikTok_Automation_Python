"""Endpoints de FASE 2 del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro):
automatización de los vídeos por producto.

- GET  /api/v1/nicho-pov-bof/prompts         → los 2 prompts fijos (imagen/vídeo)
- GET  /api/v1/nicho-pov-bof/productos       → productos emparejados + estado
- POST /api/v1/nicho-pov-bof/extraer-textos  → extrae título/tienda/caption con Gemini
- GET  /api/v1/nicho-pov-bof/foto-limpia     → descarga la foto limpia de un producto
- POST /api/v1/nicho-pov-bof/video/upload    → sube el bruto (Veo3/Kling) y encola el montaje
- POST /api/v1/nicho-pov-bof/producto/estado → marca Subido/Vendió
- POST /api/v1/nicho-pov-bof/producto/url    → averigua la ficha de TikTok Shop (1)
- POST /api/v1/nicho-pov-bof/productos/urls  → idem para toda la carpeta
- GET  /api/v1/nicho-pov-bof/buscar          → busca un producto en TODAS las carpetas
- GET  /api/v1/nicho-pov-bof/vendidos        → productos vendidos (referencia)

Fase 1 (navegación de carpetas/fotos) vive en `folders.py`, sobre el mismo
router prefix — este módulo se registra aparte para no mezclar los dos
momentos del flujo en un único archivo largo.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError, PhotoNotFoundError
from src.api.schemas.nicho_pov_bof import (
    BuscarProductosResponse,
    ExtraerTextosRequest,
    EchoTikCredsRequest,
    EchoTikCredsResponse,
    EchoTikCuenta,
    EchoTikCuentaRequest,
    EchoTikCuentasResponse,
    HashtagsRequest,
    HashtagsResponse,
    ProductoBuscado,
    ProductoEstadoRequest,
    ProductoUrlRequest,
    ProductosUrlsRequest,
    ProductosUrlsResponse,
    ProductoInfo,
    ProductosListResponse,
    PromptsResponse,
    SoldProductsResponse,
    UnidadesRequest,
    VideoUploadResponse,
)
import shutil

from src.nicho_pov_bof import config as nicho_config
from src.nicho_pov_bof.services import audience
from src.nicho_pov_bof.services import emojis as emojis_svc
from src.nicho_pov_bof.pipeline.video_editor import (
    caption_arriesgado,
    textos_fijos,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-pov-bof",
    tags=["nicho-pov-bof"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_ALLOWED_SEXOS = ("hombre", "mujer")


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


def _prompts_dir() -> Path:
    import src.nicho_pov_bof as _pkg

    return Path(_pkg.__file__).resolve().parent / "prompts"


@router.get("/prompts", response_model=PromptsResponse)
def get_prompts() -> PromptsResponse:
    """Los DOS prompts fijos que el operador copia fuera de la app (imagen y
    vídeo, para Veo3/Kling/generador de imágenes). Viven en `.md` — nunca
    hardcoded en el código (convención del proyecto)."""
    d = _prompts_dir()
    try:
        imagen = (d / "prompt_imagen.md").read_text(encoding="utf-8").strip()
        video = (d / "prompt_video.md").read_text(encoding="utf-8").strip()
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e
    return PromptsResponse(imagen=imagen, video=video)


def _aviso_foto(pair: dict) -> str:
    """Mensaje para el operador cuando la foto del producto no es de fiar.

    Distingue el caso "no sé cuál de las dos es" del caso "ninguna sirve":
    con lo segundo no hay nada que comprobar, hay que ir a la ficha y sacar
    una captura limpia a mano.
    """
    if pair.get("confident"):
        return ""

    from src.nicho_pov_bof.services import photo_pairing

    fotos = [f for f in (pair.get("clean"), pair.get("titled")) if f]
    fotos += pair.get("extras") or []
    if not fotos:
        return "Sin fotos en Drive — saca tú una captura limpia de la ficha"

    # Una foto de producto es prácticamente cuadrada. Si NINGUNA lo es, todo
    # lo que hay son pantallazos de la ficha (pasa: dos capturas del carrusel,
    # o solo la captura de la descripción).
    if not any(photo_pairing._is_squarish(f) for f in fotos):
        if len(fotos) == 1:
            cuantas = "La única foto de Drive es un pantallazo de la ficha y no vale"
        else:
            cuantas = (
                f"Las {len(fotos)} fotos de Drive son pantallazos de la ficha "
                "y ninguna vale"
            )
        return f"{cuantas} como imagen del producto — saca tú una captura limpia"

    if pair.get("reason") == "solo hay una foto":
        return (
            "Solo hay 1 foto en Drive — comprueba que sea la del producto y "
            "no la de la descripción"
        )
    return "No se distingue cuál es la foto del producto — compruébala"


def _fotos_del_producto(
    source: str, folder: str, producto: str,
) -> tuple[str | None, str | None, str]:
    """(id foto limpia, id captura con título, aviso) de un producto.

    El listado está cacheado, así que esto no vuelve a pegarle al Drive.
    """
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
        for pair in photo_pairing.pair_folder(fotos):
            if pair["producto"] == producto:
                pair = photo_pairing.desempatar_por_contenido(
                    pair, drive_client.fetch_photo,
                )
                return (
                    (pair.get("clean") or {}).get("id"),
                    (pair.get("titled") or {}).get("id"),
                    _aviso_foto(pair),
                )
    except (ValueError, RuntimeError):
        # Sin fotos se devuelve el resto del producto igualmente.
        pass
    return None, None, ""


def _producto_info(
    producto: str, prod: dict, source: str = "", folder: str = "",
    queue: JobQueue | None = None, usuario: str = "",
) -> ProductoInfo:
    """Documento de Redis → respuesta de la API.

    Lo usan los endpoints que devuelven UN producto ya actualizado. Con
    `source`/`folder` se rellenan también las fotos: el front SUSTITUYE el
    producto entero en la lista con esta respuesta, así que si viniera sin
    ellas la miniatura desaparecía hasta recargar (pasaba al buscar la URL
    de un producto suelto).
    """
    clean, titled, aviso = (
        _fotos_del_producto(source, folder, producto) if source and folder
        else (None, None, "")
    )
    return ProductoInfo(
        producto=producto,
        clean_photo_id=clean,
        titled_photo_id=titled,
        foto_aviso=aviso,
        titulo=prod.get("titulo", ""),
        titulo_tiktok_completo=prod.get("titulo_tiktok_completo", ""),
        tienda=prod.get("tienda", ""),
        caption=prod.get("caption", ""),
        emojis=prod.get("emojis") or emojis_svc.emojis_para(
            producto, prod.get("titulo", ""), prod.get("caption", ""),
        ),
        caption_riesgo=caption_arriesgado(prod.get("caption", "")) or "",
        gancho=textos_fijos(f"{producto} {folder}")["gancho"],
        cta=textos_fijos(f"{producto} {folder}")["cta"],
        sexo_sugerido=audience.sexo_sugerido(
            prod.get("titulo", ""), prod.get("titulo_tiktok_completo", ""),
        ),
        en_escaparate=bool(prod.get("en_escaparate")),
        uploaded=bool(prod.get("uploaded")),
        sold=bool(prod.get("sold")),
        video_path=prod.get("video_path"),
        video_listo_at=int(prod.get("video_listo_at") or 0),
        product_id=prod.get("product_id", ""),
        product_url=prod.get("product_url", ""),
        url_match_name=prod.get("url_match_name", ""),
        url_match_score=float(prod.get("url_match_score") or 0.0),
        url_ventas_30d=int(prod.get("url_ventas_30d") or 0),
        url_ventas_total=int(prod.get("url_ventas_total") or 0),
        montando=producto in _productos_montandose(queue, source, folder),
    )


def _productos_montandose(queue: JobQueue | None, source: str, folder: str) -> set[str]:
    """Números de producto de esta carpeta con un montaje en cola o en curso.

    El runner escribe `uploaded` y `video_path` A LA VEZ, al terminar, así que
    el estado guardado no distingue "montándose" de "sin empezar" y la ficha
    no tenía forma de saber cuándo refrescar. La cola sí lo sabe.
    """
    if queue is None:
        return set()
    try:
        jobs = queue.get_all()
    except Exception:
        return set()
    activos = {JobStatus.PENDING, JobStatus.RUNNING}
    return {
        str(j.params.get("producto"))
        for j in jobs
        if j.mode == JobMode.NICHO_POV_BOF_VIDEO
        and j.status in activos
        and j.params.get("source") == source
        and j.params.get("folder") == folder
        and j.params.get("producto")
    }


def _list_productos(
    source: str, folder: str, queue: JobQueue | None = None, usuario: str = "",
) -> ProductosListResponse:
    """Compone el emparejado de fotos (`photo_pairing`) con el estado
    guardado en Redis (`product_repo`). Reusada por `/productos` y
    `/extraer-textos` (que devuelve la lista ya actualizada)."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        photos = drive_client.list_photos(source, folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    # Las dimensiones son la señal principal para distinguir foto limpia de
    # captura con título; `probe_dimensions` descarga (cacheado) si hace falta.
    photos = [drive_client.probe_dimensions(p) for p in photos]
    pairs = photo_pairing.pair_folder(photos)

    # Vista del usuario: textos y enlaces compartidos, su progreso privado.
    folder_state = product_repo.load_folder_para(source, folder, usuario)
    guardados = folder_state.get("productos") or {}
    montandose = _productos_montandose(queue, source, folder)

    items: list[ProductoInfo] = []
    for pair in pairs:
        producto = pair["producto"]
        guardado = guardados.get(producto, {})
        clean = pair.get("clean") or {}
        titled = pair.get("titled") or {}
        items.append(
            ProductoInfo(
                producto=producto,
                clean_photo_id=clean.get("id"),
                titled_photo_id=titled.get("id"),
                foto_aviso=_aviso_foto(pair),
                titulo=guardado.get("titulo", ""),
                titulo_tiktok_completo=guardado.get("titulo_tiktok_completo", ""),
                tienda=guardado.get("tienda", ""),
                caption=guardado.get("caption", ""),
                emojis=guardado.get("emojis") or emojis_svc.emojis_para(
                    producto,
                    guardado.get("titulo", ""),
                    guardado.get("caption", ""),
                ),
                caption_riesgo=caption_arriesgado(
                    guardado.get("caption", "")
                ) or "",
                # Gancho y CTA son FIJOS (los dicta el mentor); lo único que
                # cambia por producto es el emoji. Se devuelven calculados, no
                # leídos de Redis, para que lo que copias sea exactamente lo
                # que se quema en el vídeo.
                gancho=textos_fijos(f"{producto} {folder}")["gancho"],
                cta=textos_fijos(f"{producto} {folder}")["cta"],
                sexo_sugerido=audience.sexo_sugerido(
                    guardado.get("titulo", ""),
                    guardado.get("titulo_tiktok_completo", ""),
                ),
                en_escaparate=bool(guardado.get("en_escaparate")),
                uploaded=bool(guardado.get("uploaded")),
                sold=bool(guardado.get("sold")),
                video_path=guardado.get("video_path"),
                video_listo_at=int(guardado.get("video_listo_at") or 0),
                product_id=guardado.get("product_id", ""),
                product_url=guardado.get("product_url", ""),
                url_match_name=guardado.get("url_match_name", ""),
                url_match_score=float(guardado.get("url_match_score") or 0.0),
                url_ventas_30d=int(guardado.get("url_ventas_30d") or 0),
                url_ventas_total=int(guardado.get("url_ventas_total") or 0),
                montando=producto in montandose,
            )
        )

    return ProductosListResponse(
        source=source,
        folder=folder,
        items=items,
        textos_extraidos=bool(folder_state.get("textos_extraidos")),
        montando=bool(montandose),
    )


@router.get("/productos", response_model=ProductosListResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosListResponse:
    return _list_productos(source, folder, queue, usuario)


@router.post("/extraer-textos", response_model=ProductosListResponse)
def extraer_textos(
    body: ExtraerTextosRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosListResponse:
    """Ejecuta la extracción de textos (Gemini, UNA llamada para toda la
    carpeta) y guarda el resultado. Síncrono a propósito — tarda ~1 min pero
    el operador lo pulsa una sola vez por carpeta."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import text_extractor

    try:
        textos = text_extractor.extract_folder_texts(body.source, body.folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e

    if textos:
        try:
            product_repo.save_extracted_texts(body.source, body.folder, textos)
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e

    return _list_productos(body.source, body.folder, queue, usuario)


@router.get("/foto-limpia")
def download_clean_photo(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
) -> FileResponse:
    """Descarga la FOTO LIMPIA (sin título) de un producto, con un nombre que
    agrupa por carpeta al ordenar en la galería del móvil.

    Auth por `?api_key=`: `get_current_user` (dependencia del router) ya
    acepta el api_key por query además de por header — necesario porque este
    endpoint va en un `<a download>` que no manda headers.
    """
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        photos = drive_client.list_photos(source, folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    photos = [drive_client.probe_dimensions(p) for p in photos]
    pairs = photo_pairing.pair_folder(photos)
    pair = next((pr for pr in pairs if pr["producto"] == producto), None)
    clean = (pair or {}).get("clean")
    if not clean:
        raise PhotoNotFoundError(
            f"No hay foto limpia para el producto {producto!r} en {folder!r}.",
            details={"source": source, "folder": folder, "producto": producto},
        )

    suffix = os.path.splitext(clean.get("name", ""))[1].lower() or ".jpg"
    try:
        path = drive_client.fetch_photo(clean["id"], suffix=suffix)
    except (ValueError, RuntimeError) as e:
        raise APIError(f"No se pudo descargar la foto: {e}", status_code=502) from e

    # Nombre de descarga: "<carpeta sin espacios>_<NN>.<ext>" — así, al bajar
    # varias fotos al móvil, quedan agrupadas y ordenadas por carpeta+número
    # en vez de mezcladas con el nombre suelto "3.png" que trae Drive.
    folder_slug = re.sub(r"\s+", "_", folder.strip())
    filename = f"{folder_slug}_{producto.zfill(2)}{suffix}"

    return FileResponse(
        path,
        media_type=clean.get("mime") or "image/jpeg",
        filename=filename,  # Starlette pone Content-Disposition: attachment
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/video/upload")
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_web_user)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    sexo: Annotated[str, Form()],
    # Ya no se elige (Veo3 dejó de poner marca de agua); se mantiene OPCIONAL
    # para los clientes que lo sigan enviando. Sin default daba 422 en cuanto
    # el frontend dejó de mandarlo.
    origen: Annotated[str, Form()] = "",
    # Herramientas de edición, cada una por separado. Todas marcadas = el
    # montaje completo; ninguna = vídeo limpio (solo la voz, y sin marca de
    # agua si es Veo3). `con_textos` se mantiene por compatibilidad: los
    # clientes viejos mandaban solo ese y ha de seguir apagándolo todo.
    con_gancho: Annotated[bool, Form()] = True,
    con_titulo: Annotated[bool, Form()] = True,
    con_cta: Annotated[bool, Form()] = True,
    con_flecha: Annotated[bool, Form()] = True,
    con_textos: Annotated[bool, Form()] = True,
) -> VideoUploadResponse:
    """Sube el vídeo bruto generado fuera (Veo3/Kling) y ENCOLA el montaje
    completo (quita marca de agua + normaliza + cuadra duración + textos +
    flecha + audio). El resultado se ve en la Cola; al terminar el producto
    queda marcado `uploaded=True` en Redis."""
    import shutil

    from src.api.temp_storage import upload_subdir

    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm not in _ALLOWED_SEXOS:
        raise _bad_request(f"sexo debe ser 'hombre' o 'mujer', recibido: {sexo!r}")
    # `origen` ya no se valida: no cambia nada del montaje desde que Veo3 dejó
    # de poner marca de agua. Se guarda tal cual llegue (vacío incluido) solo
    # como dato del job.
    origen_norm = (origen or "").strip().lower()

    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise _bad_request(
            f"Formato de vídeo no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}."
        )

    dest_dir = upload_subdir("nicho_pov_bof")
    # Nombre único por producto+timestamp: el operador puede resubir el mismo
    # producto (p. ej. tras un fallo) sin pisar el bruto anterior.
    safe_stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}_{producto}")
    raw_path = dest_dir / f"{safe_stub}_{int(time.time())}{ext}"
    try:
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise APIError(f"No se pudo guardar el vídeo: {e}", status_code=500) from e
    finally:
        await file.close()

    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_VIDEO,
        title=f"🎬 Nicho POV BOF: producto {producto} · {folder}",
        params={
            "source": source,
            "folder": folder,
            "producto": producto,
            "raw_path": str(raw_path),
            "sexo": sexo_norm,
            "origen": origen_norm,
            # `con_textos=False` de un cliente antiguo apaga las cuatro.
            "con_gancho": bool(con_gancho) and bool(con_textos),
            "con_titulo": bool(con_titulo) and bool(con_textos),
            "con_cta": bool(con_cta) and bool(con_textos),
            "con_flecha": bool(con_flecha) and bool(con_textos),
        },
        enqueued_by=operator or None,
    )
    return VideoUploadResponse(ok=True, job_id=job.id, message="En la cola, procesando…")


@router.post("/producto/estado", response_model=ProductoInfo)
def set_producto_estado(
    body: ProductoEstadoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoInfo:
    """Parche parcial de Escaparate/Subido/Vendió. `update_product` ya ignora
    los campos que vengan `None`, así que el caller puede mandar solo el que
    cambia.

    `en_escaparate` NO se deduce de `uploaded`, aunque en la vida real haya que
    meter el producto en el escaparate antes de publicar: `uploaded` lo pone
    solo el runner al terminar el MONTAJE, que no es lo mismo que publicar.
    Deducirlo daría por hecho trabajo que nadie ha hecho.
    """
    from src.nicho_pov_bof.repos import product_repo

    try:
        prod = product_repo.update_product(
            body.source, body.folder, body.producto, usuario=usuario,
            en_escaparate=body.en_escaparate,
            uploaded=body.uploaded, sold=body.sold,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    info = _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)

    # El ranking de vendidos lleva su propio índice con una copia de lo que
    # hace falta para pintarlo (foto incluida). Se escribe AQUÍ, en el único
    # sitio donde se marca la venta, y no recorriendo las 31 carpetas después.
    if body.sold is not None:
        try:
            if body.sold:
                product_repo.marcar_vendido(
                    body.source, body.folder, body.producto,
                    titulo=info.titulo or "", tienda=info.tienda or "",
                    clean_photo_id=info.clean_photo_id or "",
                    product_url=info.product_url or "",
                )
            else:
                product_repo.desmarcar_vendido(body.source, body.folder, body.producto)
        except Exception:
            # Que no se caiga el marcado por un fallo del ranking: el dato
            # bueno (`sold`) ya está guardado en el producto.
            pass

    return info


@router.post("/producto/url", response_model=ProductoInfo)
def buscar_producto_url(
    body: ProductoUrlRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoInfo:
    """Averigua la ficha de TikTok Shop del producto y la guarda.

    **Gasta una llamada del plan de EchoTik** (trial de 100), así que si el
    producto ya tiene URL guardada se devuelve tal cual sin volver a buscar.
    """
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import product_url

    prod = product_repo.get_product(body.source, body.folder, body.producto, usuario)
    if not prod:
        raise _bad_request(f"Producto {body.producto!r} no encontrado en {body.folder!r}.")
    if prod.get("product_url"):
        return _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)

    titulo = prod.get("titulo_tiktok_completo") or prod.get("titulo") or ""
    if not titulo.strip():
        raise _bad_request(
            "El producto no tiene título todavía — pulsa 'Obtener textos' primero."
        )

    hallado = product_url.find_product_url(titulo, prod.get("tienda", ""))
    if not hallado:
        # No es un error del servidor: EchoTik simplemente no lo indexa o el
        # parecido no daba para fiarse. Se devuelve el producto sin URL para
        # que la UI lo muestre como "no encontrado" en vez de romperse.
        return _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)

    try:
        prod = product_repo.update_product(body.source, body.folder, body.producto, **hallado)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)


@router.post("/productos/urls", response_model=ProductosUrlsResponse)
def buscar_urls_carpeta(
    body: ProductosUrlsRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosUrlsResponse:
    """Busca la ficha de TikTok Shop de toda la carpeta de una tacada.

    Equivalente de carpeta a `/producto/url`, igual que "Obtener textos" lo
    es de los textos. Gasta UNA llamada de EchoTik POR PRODUCTO sin URL: los
    que ya la tienen y los que aún no tienen título se saltan sin gastar.

    Si la cuota se agota a mitad se para y se devuelve lo conseguido hasta
    ahí con un aviso — seguir solo sumaría llamadas fallidas.
    """
    from src.tiktok_shop.api import echotik_cloud
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import product_url

    guardados = (product_repo.load_folder(body.source, body.folder).get("productos") or {})
    llamadas = encontrados = sin_resultado = 0
    aviso = ""

    # Pendientes: sin enlace y con título. Agrupados por MARCA, porque una
    # barrida de marca (3 llamadas) resuelve todos sus productos de golpe y
    # además encuentra fichas que la búsqueda por nombre no ve — EchoTik busca
    # por subcadena y los títulos del operador no coinciden literalmente.
    pendientes: dict[str, list[str]] = {}
    for producto, prod in sorted(guardados.items(), key=lambda kv: kv[0]):
        if prod.get("product_url"):
            continue
        if not (prod.get("titulo_tiktok_completo") or prod.get("titulo") or "").strip():
            continue
        pendientes.setdefault((prod.get("tienda") or "").strip().lower(), []).append(producto)

    PAGINAS_MARCA = 3
    for _marca, productos in pendientes.items():
        if echotik_cloud.quota_exhausted():
            # Distinguir los dos casos importa: parar a mitad es normal, pero
            # parar SIN haber llamado ni una vez significa que la cuenta en uso
            # ya estaba seca — y lo que hay que hacer es cambiarla, no reintentar.
            aviso = (
                "EchoTik se quedó sin cuota a mitad — los productos restantes "
                "se han dejado sin buscar."
                if llamadas
                else "La cuenta de EchoTik en uso está sin cuota — cambia a "
                     "otra en ⚙️ Configuración y vuelve a darle."
            )
            break

        ejemplo = guardados[productos[0]]
        # Con un solo producto de la marca sale más barato buscarlo por nombre
        # (1-2 llamadas) que barrer la marca entera (3).
        if len(productos) == 1:
            titulo = (ejemplo.get("titulo_tiktok_completo")
                      or ejemplo.get("titulo") or "")
            llamadas += 1
            hallado = product_url.find_product_url(titulo, ejemplo.get("tienda", ""))
            if hallado is None:
                llamadas += 1  # el reintento sin marca
                sin_resultado += 1
            else:
                try:
                    product_repo.update_product(
                        body.source, body.folder, productos[0], **hallado)
                except RuntimeError as e:
                    raise APIError(str(e), status_code=503) from e
                encontrados += 1
            continue

        candidatos = product_url.barrer_marca(
            ejemplo.get("tienda", ""), paginas=PAGINAS_MARCA)
        llamadas += PAGINAS_MARCA
        for producto in productos:
            prod = guardados[producto]
            titulo = prod.get("titulo_tiktok_completo") or prod.get("titulo") or ""
            hallado = product_url.elegir_de_candidatos(
                candidatos, titulo, prod.get("tienda", ""))
            if hallado:
                hallado["keyword"] = f"[marca] {ejemplo.get('tienda', '')}"
            else:
                # La barrida no lo tiene: se prueba por nombre, que a veces
                # llega a fichas que no salen listando la marca (le pasa a la
                # crema de manos de Bella Aurora).
                llamadas += 1
                hallado = product_url.find_product_url(titulo, prod.get("tienda", ""))
                if hallado is None:
                    llamadas += 1  # el reintento sin marca
            if not hallado:
                sin_resultado += 1
                continue
            try:
                product_repo.update_product(
                    body.source, body.folder, producto, **hallado)
            except RuntimeError as e:
                raise APIError(str(e), status_code=503) from e
            encontrados += 1

    lista = _list_productos(body.source, body.folder, queue, usuario)
    return ProductosUrlsResponse(
        source=lista.source,
        folder=lista.folder,
        items=lista.items,
        textos_extraidos=lista.textos_extraidos,
        llamadas=llamadas,
        encontrados=encontrados,
        sin_resultado=sin_resultado,
        aviso=aviso,
    )


def _mascara(usuario: str) -> str:
    """Deja ver los últimos dígitos para reconocer la cuenta sin exponerla."""
    u = (usuario or "").strip()
    return f"…{u[-6:]}" if len(u) > 6 else ("·" * len(u))


@router.get("/video")
def descargar_video(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve el vídeo YA montado del producto.

    Se lee del `video_path` guardado, que apunta al fichero publicado en Drive
    (el mount). Al remontar un producto se sobrescribe con el mismo nombre, así
    que esto devuelve SIEMPRE la última versión; el frontend añade
    `video_listo_at` a la URL para que el navegador no sirva la anterior de su
    caché.
    """
    from src.nicho_pov_bof.repos import product_repo

    prod = product_repo.get_product(source, folder, producto, usuario)
    ruta = (prod or {}).get("video_path") or ""
    if not ruta:
        raise APIError("Este producto todavía no tiene vídeo montado.", status_code=404)

    # Primero la copia LOCAL. Servir desde el mount de Drive cuesta ~36s hasta
    # el primer byte si el fichero no está en la caché de rclone (hay que
    # traerlo entero de Google); desde disco es instantáneo. Es lo que hacía
    # que al descargar varios seguidos alguno se quedara colgado.
    p = Path(nicho_config.video_cache_path(folder, producto, usuario))
    if not p.is_file():
        p = Path(ruta)
        # Se copia al vuelo para que la SIGUIENTE descarga ya sea rápida:
        # los vídeos montados antes de que existiera la caché no la tienen.
        if p.is_file():
            try:
                destino = Path(nicho_config.video_cache_path(folder, producto, usuario))
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, destino)
                p = destino
            except OSError:
                pass
    if not p.is_file():
        raise APIError(
            f"El vídeo ya no está en {ruta} (¿borrado de Drive?).", status_code=404,
        )
    return FileResponse(
        str(p), media_type="video/mp4",
        filename=p.name if descargar else None,
    )


@router.get("/echotik", response_model=EchoTikCredsResponse)
def estado_echotik() -> EchoTikCredsResponse:
    """Qué credenciales de EchoTik están puestas ahora mismo."""
    from src.tiktok_shop.api import echotik_cloud

    guardadas, _pwd = echotik_cloud._creds_de_redis()
    usuario, password = echotik_cloud._auth()
    return EchoTikCredsResponse(
        ok=True,
        configurado=bool(usuario and password),
        usuario_mascara=_mascara(usuario),
        origen="guardadas" if guardadas else ("env" if usuario else "ninguna"),
        mensaje=(
            echotik_cloud.last_quota_error_msg()
            if echotik_cloud.quota_exhausted() else ""
        ),
    )


@router.post("/echotik", response_model=EchoTikCredsResponse)
def guardar_echotik(body: EchoTikCredsRequest) -> EchoTikCredsResponse:
    """Guarda las credenciales de EchoTik. Se aplican al instante, sin
    redespliegue: el cliente las lee de Redis y el `.env` queda como respaldo.

    Con `probar=true` gasta UNA llamada verificando que funcionan; si no
    funcionan NO se guardan, para no dejar el Radar con una cuenta muerta.
    """
    from src.tiktok_shop.api import echotik_cloud

    usuario = body.usuario.strip()
    password = body.password.strip()

    if body.probar:
        anterior = echotik_cloud._CREDS_CACHE
        echotik_cloud._CREDS_CACHE = (time.monotonic(), (usuario, password))
        try:
            prueba = echotik_cloud.search_products("bella aurora", region="ES", limit=10)
        finally:
            echotik_cloud._CREDS_CACHE = anterior
        if not prueba:
            return EchoTikCredsResponse(
                ok=False, configurado=echotik_cloud.echotik_is_configured(),
                usuario_mascara=_mascara(echotik_cloud._auth()[0]),
                origen="guardadas" if echotik_cloud._creds_de_redis()[0] else "env",
                mensaje=("Esas credenciales no devuelven resultados: revisa "
                         "usuario y contraseña, o la cuota del plan. No se han "
                         "guardado."),
            )

    if not echotik_cloud.guardar_credenciales(usuario, password):
        raise APIError("No se pudieron guardar (¿Redis no configurado?)", status_code=503)

    return EchoTikCredsResponse(
        ok=True, configurado=True, usuario_mascara=_mascara(usuario),
        origen="guardadas",
        mensaje="Credenciales guardadas y en uso" + (" (verificadas)" if body.probar else ""),
    )


# ── Banco de cuentas ──────────────────────────────────────────────────
# El plan gratis da 100 llamadas al mes: una cuenta seca vuelve a servir al mes
# siguiente. Se guardan todas con la fecha de su primera llamada para saber a
# cuál volver en vez de tener que abrir una nueva cada vez.
def _a_schema(c: dict, activo: str) -> EchoTikCuenta:
    from src.tiktok_shop.repos import echotik_cuentas_repo

    return EchoTikCuenta(
        usuario=c["usuario"],
        usuario_mascara=_mascara(c["usuario"]),
        nota=c["nota"],
        activa=c["usuario"] == activo,
        llamadas=c["llamadas"],
        primer_uso_at=c["primer_uso_at"],
        ultimo_uso_at=c["ultimo_uso_at"],
        renueva_at=echotik_cuentas_repo.renueva_at(c),
        disponible=echotik_cuentas_repo.disponible(c),
        sin_cuota=bool(c["sin_cuota_at"]),
    )


@router.get("/echotik/cuentas", response_model=EchoTikCuentasResponse)
def listar_cuentas_echotik() -> EchoTikCuentasResponse:
    """Cuentas guardadas, con lo gastado y cuándo les renueva la cuota."""
    from src.tiktok_shop.api import echotik_cloud
    from src.tiktok_shop.repos import echotik_cuentas_repo

    activo, clave_activa = echotik_cloud._auth()
    # La cuenta que ya estaba en uso antes de existir el banco no está en él:
    # se apunta con su contraseña la primera vez que se mira la lista. Si no,
    # aparecería más tarde sin clave (al registrar su primera llamada) y no se
    # podría volver a ella.
    if activo and clave_activa and not echotik_cuentas_repo.buscar(activo):
        try:
            echotik_cuentas_repo.guardar(activo, clave_activa)
        except Exception:
            pass
    return EchoTikCuentasResponse(
        items=[_a_schema(c, activo) for c in echotik_cuentas_repo.listar()],
    )


@router.post("/echotik/cuentas", response_model=EchoTikCuentasResponse)
def guardar_cuenta_echotik(body: EchoTikCuentaRequest) -> EchoTikCuentasResponse:
    """Añade una cuenta al banco SIN ponerla en uso ni gastarle una llamada.

    Guardar y activar van por separado a propósito: así se puede ir apuntando
    cuentas de respaldo según se crean, sin tocar la que está funcionando.
    """
    from src.tiktok_shop.api import echotik_cloud
    from src.tiktok_shop.repos import echotik_cuentas_repo

    try:
        echotik_cuentas_repo.guardar(body.usuario, body.password, body.nota)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    activo = echotik_cloud._auth()[0]
    return EchoTikCuentasResponse(
        items=[_a_schema(c, activo) for c in echotik_cuentas_repo.listar()],
        mensaje="Cuenta guardada — actívala cuando la necesites.",
    )


@router.post("/echotik/cuentas/activar", response_model=EchoTikCuentasResponse)
def activar_cuenta_echotik(
    usuario: Annotated[str, Query(min_length=4)],
) -> EchoTikCuentasResponse:
    """Pone esa cuenta como la que se usa. No gasta ninguna llamada."""
    from src.tiktok_shop.api import echotik_cloud
    from src.tiktok_shop.repos import echotik_cuentas_repo

    cuenta = echotik_cuentas_repo.buscar(usuario)
    if not cuenta:
        raise APIError("Esa cuenta no está guardada.", status_code=404)
    if not cuenta["password"]:
        raise APIError(
            "De esa cuenta solo se guardó el usuario (venía del .env). Vuelve "
            "a guardarla con su contraseña para poder activarla.",
            status_code=400,
        )
    if not echotik_cloud.guardar_credenciales(cuenta["usuario"], cuenta["password"]):
        raise APIError("No se pudo activar (¿Redis no configurado?)", status_code=503)

    return EchoTikCuentasResponse(
        items=[_a_schema(c, cuenta["usuario"]) for c in echotik_cuentas_repo.listar()],
        mensaje=f"En uso: {_mascara(cuenta['usuario'])}",
    )


@router.delete("/echotik/cuentas", response_model=EchoTikCuentasResponse)
def borrar_cuenta_echotik(
    usuario: Annotated[str, Query(min_length=4)],
) -> EchoTikCuentasResponse:
    from src.tiktok_shop.api import echotik_cloud
    from src.tiktok_shop.repos import echotik_cuentas_repo

    if not echotik_cuentas_repo.borrar(usuario):
        raise APIError("Esa cuenta no está guardada.", status_code=404)
    activo = echotik_cloud._auth()[0]
    return EchoTikCuentasResponse(
        items=[_a_schema(c, activo) for c in echotik_cuentas_repo.listar()],
        mensaje="Cuenta borrada.",
    )


@router.get("/hashtags", response_model=HashtagsResponse)
def get_hashtags() -> HashtagsResponse:
    """Hashtags que se pegan al final de todos los captions."""
    from src.nicho_pov_bof.repos import product_repo

    return HashtagsResponse(ok=True, tags=product_repo.get_hashtags())


@router.post("/hashtags", response_model=HashtagsResponse)
def set_hashtags(body: HashtagsRequest) -> HashtagsResponse:
    """Guarda la lista completa (la UI manda siempre el conjunto entero)."""
    from src.nicho_pov_bof.repos import product_repo

    try:
        tags = product_repo.save_hashtags(body.tags)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return HashtagsResponse(ok=True, tags=tags)


@router.get("/buscar", response_model=BuscarProductosResponse)
def buscar_productos(
    q: Annotated[str, Query(min_length=2)],
    source: Annotated[str | None, Query()] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> BuscarProductosResponse:
    """Busca un producto por nombre, tienda o carpeta en TODAS las carpetas.

    La foto se resuelve DESPUÉS de recortar los resultados: emparejarlas
    cuesta ~0,25s por carpeta y hacerlo de las 35 para enseñar cinco sería
    pagar cuatro segundos de más en cada tecla.
    """
    from src.nicho_pov_bof.repos import product_repo

    try:
        encontrados, total = product_repo.buscar_productos(
            q, usuario=usuario, source=source,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    items: list[ProductoBuscado] = []
    for d in encontrados:
        clean, _titled, _aviso = _fotos_del_producto(
            d["source"], d["folder"], d["producto"],
        )
        items.append(
            ProductoBuscado(
                source=d["source"], folder=d["folder"], producto=d["producto"],
                titulo=d.get("titulo") or "",
                titulo_tiktok_completo=d.get("titulo_tiktok_completo") or "",
                tienda=d.get("tienda") or "",
                clean_photo_id=clean or "",
                product_url=d.get("product_url") or "",
                en_escaparate=bool(d.get("en_escaparate")),
                uploaded=bool(d.get("uploaded")),
                sold=bool(d.get("sold")),
                unidades=int(d.get("unidades") or 0),
            )
        )
    return BuscarProductosResponse(items=items, total=total)


@router.get("/vendidos", response_model=SoldProductsResponse)
def list_sold(source: Annotated[str | None, Query()] = None) -> SoldProductsResponse:
    """Ranking de vendidos, del que más unidades al que menos.

    Sale del índice propio (dos llamadas a Redis). Antes se recorrían las 31
    carpetas de cada fuente producto a producto: ocho segundos para encontrar
    dos ventas, y sin foto.
    """
    from src.nicho_pov_bof.repos import product_repo

    items = product_repo.ranking_vendidos()
    if source:
        items = [i for i in items if i.get("source") == source]
    return SoldProductsResponse(items=items)


@router.post("/vendidos/unidades", response_model=SoldProductsResponse)
def sumar_unidades_vendidas(body: UnidadesRequest) -> SoldProductsResponse:
    """Suma (o resta) unidades a un producto ya vendido.

    Un producto que REPITE venta es la señal más valiosa que hay aquí, y no
    había forma de anotarla: vendiera una vez o cinco, se veía igual.
    """
    from src.nicho_pov_bof.repos import product_repo

    try:
        product_repo.sumar_unidades(body.source, body.folder, body.producto, body.delta)
    except ValueError as e:
        raise APIError(str(e), status_code=404) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return SoldProductsResponse(items=product_repo.ranking_vendidos())
