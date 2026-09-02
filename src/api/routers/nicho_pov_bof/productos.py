"""Endpoints de FASE 2 del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro):
automatización de los vídeos por producto.

- GET  /api/v1/nicho-pov-bof/prompts         → los 2 prompts fijos (imagen/vídeo)
- GET  /api/v1/nicho-pov-bof/productos       → productos emparejados + estado
- POST /api/v1/nicho-pov-bof/extraer-textos  → extrae título/tienda/caption con Gemini
- GET  /api/v1/nicho-pov-bof/foto-limpia     → descarga una foto del producto
                                              (`variante=limpia|ficha`)
- POST /api/v1/nicho-pov-bof/video/upload    → sube el bruto (Veo3/Kling) y encola el montaje
- POST /api/v1/nicho-pov-bof/producto/estado → marca Subido/Vendió
- POST /api/v1/nicho-pov-bof/producto/url    → averigua la ficha de TikTok Shop (1)
- POST /api/v1/nicho-pov-bof/productos/urls  → idem para toda la carpeta
- GET  /api/v1/nicho-pov-bof/buscar          → busca un producto en TODAS las carpetas
- GET  /api/v1/nicho-pov-bof/recuperados     → productos que aparecieron tarde (temporal)
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
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError, PhotoNotFoundError
from src.api.schemas.nicho_pov_bof import (
    GuardarUrlRequest,
    GuionPlazosRequest,
    VideoLoteConfirmarRequest,
    VideoLoteConfirmarResponse,
    VideoLoteItem,
    VideoLoteResponse,
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
    ProductoRecuperado,
    ProductoEstadoRequest,
    ProductoUrlRequest,
    ProductosUrlsRequest,
    ProductosUrlsResponse,
    ProductoInfo,
    ProductosListResponse,
    PromptsResponse,
    RecuperadosResponse,
    SoldProductsResponse,
    UnidadesRequest,
    VideoUploadResponse,
)
import shutil

from src.nicho_pov_bof import config as nicho_config
from src.nicho_pov_bof.services import audience
from src.nicho_pov_bof.services import top_vendidos
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
# "auto" = que lo decida mirando la mano del vídeo (`services/mano.py`). Se
# resuelve en el montaje, no aquí: el bruto ya está en disco y sacar los
# fotogramas ahí no hace esperar a quien sube.
_ALLOWED_SEXOS = ("hombre", "mujer", "auto")


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


def _precio_y_modo(prod: dict) -> tuple[float, bool]:
    """Precio del producto y si le toca el guion de plazos.

    Sin precio leído NO se asume nada: se queda con el guion de siempre. Es
    preferible a colar un guion que promete financiación en un producto de 12 €
    (el operador puede escribir el precio a mano si Gemini no lo pilló).
    """
    precio = nicho_config.precio_num(prod.get("precio"))
    return precio, nicho_config.hay_plazos(prod)


def _clip_vigente(ruta, desde: float = 0.0) -> bool:
    """¿Hay un clip de ESTA ronda en ese slot?

    No basta con que el path esté guardado: el fichero se purga a las 24h y,
    sobre todo, un clip anterior al último montaje ya se consumió. Sin esto,
    resubir el clip 1 encolaría un montaje con el clip 2 de la ronda pasada.
    """
    if not ruta:
        return False
    f = Path(str(ruta))
    if not f.is_file():
        return False
    return f.stat().st_mtime >= desde


def _contar_subida(tipo: str, referencia: str, subido: bool, usuario: str) -> None:
    """Suma (o resta) la publicación en el tope diario de la cuenta.

    Nunca tumba la petición: el dato bueno es el del producto, y quedarse sin
    contador es molesto pero no impide trabajar.
    """
    try:
        from src.cuotas.repos import cuota_repo

        cuota_repo.marcar(tipo, referencia, usuario, subido)
    except Exception:
        pass


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
        from src.nicho_pov_bof.config import limpiar_prompt

        imagen = limpiar_prompt((d / "prompt_imagen.md").read_text(encoding="utf-8"))
        video = limpiar_prompt((d / "prompt_video.md").read_text(encoding="utf-8"))
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
) -> tuple[str | None, str | None, str, str]:
    """(id foto limpia, id captura, aviso, fecha de subida) de un producto.

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
                    _subida_de(pair),
                )
    except (ValueError, RuntimeError):
        # Sin fotos se devuelve el resto del producto igualmente.
        pass
    return None, None, "", ""


def _subida_de(pair: dict) -> str:
    """Cuándo entró el producto en el Drive: la fecha de su foto más ANTIGUA.

    Sirve para lo de siempre: una carpeta ya trabajada a la que el curso le
    añade dos productos más por la tarde. Sin esta fecha no hay forma de saber
    cuáles son los nuevos.
    """
    fechas = [
        str((pair.get(k) or {}).get("mtime") or "")
        for k in ("clean", "titled")
    ]
    return min((f for f in fechas if f), default="")


def _clips_que_pide(prod: dict) -> int:
    """Cuántos clips hay que subir para este producto.

    Con guion propio se pregunta con cuántos clips queda alguna voz sorteable
    (`voz.clips_para`), no cuánto tardaría la más lenta del banco: esa ya no
    entra en el sorteo, y contar con ella pedía dos clips donde con once voces
    distintas cabía en uno. 223 caracteres caben en UNO de 10 s.

    Sin guion son dos, que es lo que pedía el banco de audios: su frase se
    sortea al montar y hay que ponerse en la más larga.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof_largo import config as largo_config
    from src.nicho_pov_bof_largo.services import voz as voz_svc

    guion = _guion_hablado(prod)
    if not guion:
        return 2
    return voz_svc.clips_para(
        len(guion),
        float(prod.get("clip_s") or largo_config.CLIP_TARGET_S),
        segundos_min=pov_config.DURACION_MINIMA_S,
    )


def _guion_hablado(prod: dict) -> str:
    """El guion que va a decir la voz: siempre el escrito para ESTE producto.

    Los de plazos también. Antes se iban por uno de los cinco textos de Klarna
    del curso, que no nombran el producto y duran 253-274 caracteres (13-20s
    de vídeo); ahora la frase de la financiación va DENTRO del guion propio,
    con la CTA original del curso, y el vídeo se queda en los ~10s de siempre.
    """
    return str(prod.get("guion_producto") or "").strip()


def _segundos_pov(prod: dict) -> tuple[float, float]:
    """`(mínimo, máximo)` de lo que va a durar el vídeo, en segundos.

    Mismo cálculo que el POV BOF Largo: el vídeo dura lo que dure la voz, y la
    voz sale sorteada entre las que caben en los clips y llegan al mínimo del
    reto. Sin guion propio manda el banco de audios y no hay nada que estimar.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof_largo import config as largo_config
    from src.nicho_pov_bof_largo.services import voz as voz_svc

    guion = _guion_hablado(prod)
    if not guion:
        return (0.0, 0.0)
    return voz_svc.duracion_estimada(
        len(guion),
        float(prod.get("clip_s") or largo_config.CLIP_TARGET_S),
        _clips_que_pide(prod),
        segundos_min=pov_config.DURACION_MINIMA_S,
    )


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
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof_largo import config as largo_config

    clean, titled, aviso, subida = (
        _fotos_del_producto(source, folder, producto) if source and folder
        else (None, None, "", "")
    )
    return ProductoInfo(
        producto=producto,
        clean_photo_id=clean,
        titled_photo_id=titled,
        foto_aviso=aviso,
        subida_at=subida,
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
        precio=_precio_y_modo(prod)[0],
        precio_lista=nicho_config.precio_num(prod.get("precio_lista")),
        modo_plazos=_precio_y_modo(prod)[1],
        # Vigente, no "guardado": el fichero temporal se purga a las 24h y un
        # clip anterior al último montaje ya se consumió. Marcarlo con ✓ haría
        # creer que solo falta el otro.
        guion=str(prod.get("guion_plazos") or ""),
        guion_caracteres=len(str(prod.get("guion_plazos") or "")),
        clip1=_clip_vigente(prod.get("clip1_path"), float(prod.get("video_listo_at") or 0)),
        clip2=_clip_vigente(prod.get("clip2_path"), float(prod.get("video_listo_at") or 0)),
        # El escaparate sale del índice ÚNICO por (tienda|nombre): el mismo
        # producto está repetido en varias carpetas y se graba con varios
        # nichos, pero al Marketplace se sube UNA vez. El flag viejo por
        # producto se sigue mirando para no perder lo ya marcado.
        en_escaparate=product_repo.marcado_en_escaparate(
            prod, product_repo.escaparate_index(usuario),
        ),
        tambien_en_drive=product_repo.tambien_en_drive(prod),
        sin_stock=bool(prod.get("sin_stock")),
        guion_producto=str(prod.get("guion_producto") or ""),
        clips_necesarios=_clips_que_pide(prod),
        **dict(zip(("segundos_min", "segundos_max"), _segundos_pov(prod))),
        clip_s=int(prod.get("clip_s") or largo_config.CLIP_TARGET_S),
        uploaded=bool(prod.get("uploaded")),
        uploaded_at=float(prod.get("uploaded_at") or 0),
        sold=bool(prod.get("sold")),
        video_path=prod.get("video_path"),
        video_listo_at=int(prod.get("video_listo_at") or 0),
        product_id=prod.get("product_id", ""),
        product_url=product_repo.url_de(prod),
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
        # Los dos modos montan en esta carpeta: el normal (un vídeo) y el de
        # plazos (dos clips). Si solo se mirara uno, el de plazos no pintaría
        # el "montando…" y la guardia contra el doble encolado no vería nada.
        if j.mode in (JobMode.NICHO_POV_BOF_VIDEO, JobMode.NICHO_POV_BOF_PLAZOS_VIDEO)
        and j.status in activos
        and j.params.get("source") == source
        and j.params.get("folder") == folder
        and j.params.get("producto")
    }


def _list_productos(
    source: str, folder: str, queue: JobQueue | None = None, usuario: str = "",
    refresh: bool = False,
) -> ProductosListResponse:
    """Compone el emparejado de fotos (`photo_pairing`) con el estado
    guardado en Redis (`product_repo`). Reusada por `/productos` y
    `/extraer-textos` (que devuelve la lista ya actualizada)."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        # `refresh` se salta la caché de listados. Hace falta porque una
        # carpeta que se listó vacía (Drive lento, fotos aún sin subir) se
        # quedaba vacía en pantalla hasta que caducara el listado, sin manera
        # de forzarlo desde la app.
        photos = drive_client.list_photos(source, folder, refresh=refresh)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    # Si el Drive del curso vació la carpeta, las fotos salen de nuestra copia.
    # La pantalla lo dice: el operador tiene que saber que eso ya no está en el
    # origen (y que si aún no ha grabado el producto, corre prisa).
    desde_copia = drive_client.desde_la_copia(photos)

    # Las dimensiones son la señal principal para distinguir foto limpia de
    # captura con título; `probe_dimensions` descarga (cacheado) si hace falta.
    photos = [drive_client.probe_dimensions(p) for p in photos]
    pairs = photo_pairing.pair_folder(photos)

    # El curso renumera carpetas de vez en cuando (lo que era `IMG_0245.jpg`
    # pasa a `4.png`) y con el número cambia la identidad del producto. Aquí se
    # reengancha por el file ID de las fotos, que Google no toca al renombrar:
    # si no ha cambiado nada, no hace nada.
    from src.nicho_pov_bof.services import reanclaje

    reanclaje.sincronizar(source, folder, pairs, usuario)

    # Qué productos tiene HOY la carpeta. Se apunta aquí, que es donde se sabe,
    # para que el listado de carpetas pueda decir cuántos llevan ficha sin
    # tener que listar el Drive de cada una (ver `guardar_ids_vigentes`).
    try:
        product_repo.guardar_ids_vigentes(
            source, folder, [str(par["producto"]) for par in pairs],
        )
    except Exception:  # noqa: BLE001
        pass

    # Vista del usuario: textos y enlaces compartidos, su progreso privado.
    folder_state = product_repo.load_folder_para(source, folder, usuario)
    guardados = folder_state.get("productos") or {}
    montandose = _productos_montandose(queue, source, folder)
    # Una sola lectura del índice para toda la carpeta, no una por producto.
    escaparate = product_repo.escaparate_index(usuario)
    # La ficha de TikTok es del producto y la comparten los tres usuarios: se
    # lee el índice entero una vez, no producto a producto.
    urls = product_repo.urls_index()
    ventas = top_vendidos.ventas_por_producto(source, usuario)

    from src.nicho_pov_bof_largo import config as largo_config

    # Una sola lectura para toda la carpeta: dentro del bucle serían 10.
    titulos_del_drive = (
        product_repo.titulos_drive()
        if source not in product_repo.FUENTES_DRIVE else set()
    )

    items: list[ProductoInfo] = []
    for pair in pairs:
        producto = pair["producto"]
        venta = ventas.get(f"{folder}|{producto}") or {}
        guardado = guardados.get(producto, {})
        clean = pair.get("clean") or {}
        titled = pair.get("titled") or {}
        items.append(
            ProductoInfo(
                producto=producto,
                desde_copia=desde_copia,
                clean_photo_id=clean.get("id"),
                titled_photo_id=titled.get("id"),
                foto_aviso=_aviso_foto(pair),
                subida_at=_subida_de(pair),
                titulo=guardado.get("titulo", ""),
                titulo_tiktok_completo=guardado.get("titulo_tiktok_completo", ""),
                tienda=guardado.get("tienda", ""),
                tambien_en_drive=bool(titulos_del_drive) and product_repo.tambien_en_drive(
                    guardado, titulos_del_drive,
                ),
                sin_stock=bool(guardado.get("sin_stock")),
                guion_producto=str(guardado.get("guion_producto") or ""),
                clips_necesarios=_clips_que_pide(guardado),
                **dict(zip(("segundos_min", "segundos_max"), _segundos_pov(guardado))),
                clip_s=int(guardado.get("clip_s") or largo_config.CLIP_TARGET_S),
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
                ventas=int(venta.get("ventas") or 0),
                vendido_at=float(venta.get("vendido_at") or 0),
                precio=_precio_y_modo(guardado)[0],
                precio_lista=nicho_config.precio_num(guardado.get("precio_lista")),
                modo_plazos=_precio_y_modo(guardado)[1],
                guion=str(guardado.get("guion_plazos") or ""),
                guion_caracteres=len(str(guardado.get("guion_plazos") or "")),
                clip1=_clip_vigente(
                    guardado.get("clip1_path"), float(guardado.get("video_listo_at") or 0),
                ),
                clip2=_clip_vigente(
                    guardado.get("clip2_path"), float(guardado.get("video_listo_at") or 0),
                ),
                en_escaparate=product_repo.marcado_en_escaparate(guardado, escaparate),
                uploaded=bool(guardado.get("uploaded")),
                uploaded_at=float(guardado.get("uploaded_at") or 0),
                sold=bool(guardado.get("sold")),
                video_path=guardado.get("video_path"),
                video_listo_at=int(guardado.get("video_listo_at") or 0),
                product_id=guardado.get("product_id", ""),
                product_url=product_repo.url_de(guardado, urls),
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
    refresh: Annotated[bool, Query()] = False,
) -> ProductosListResponse:
    if nicho_config.es_carpeta_virtual(folder):
        return _list_esperando_stock(source, queue, usuario, refresh=refresh)
    return _list_productos(source, folder, queue, usuario, refresh=refresh)


def _list_esperando_stock(
    source: str, queue, usuario: str, *, refresh: bool = False,
) -> ProductosListResponse:
    """Los productos con el vídeo hecho que esperan a que vuelva el stock.

    No es una carpeta de Drive: se juntan de varias. Solo se leen las carpetas
    que Redis dice que tienen alguno —normalmente dos o tres—, porque listar
    las fotos de todas cuesta una llamada al Drive por carpeta y aquí se entra
    a menudo, solo para mirar si alguno ha vuelto.
    """
    from concurrent.futures import ThreadPoolExecutor

    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client

    try:
        nombres = [f["name"] for f in drive_client.list_product_folders(source)]
    except Exception as e:  # noqa: BLE001
        raise APIError(f"No se pudo leer el catálogo: {e}", status_code=502) from e

    esperando = product_repo.esperando_stock(source, nombres, usuario)
    if not esperando:
        return ProductosListResponse(
            source=source, folder=nicho_config.CARPETA_ESPERANDO_STOCK,
            items=[], textos_extraidos=True, montando=False,
        )

    def _una(carpeta: str):
        try:
            return carpeta, _list_productos(source, carpeta, queue, usuario, refresh=refresh)
        except Exception:  # noqa: BLE001 — una carpeta ilegible no deja sin lista al resto
            return carpeta, None

    items: list[ProductoInfo] = []
    carpetas = sorted(esperando)
    with ThreadPoolExecutor(max_workers=min(4, len(carpetas))) as pool:
        for carpeta, parcial in pool.map(_una, carpetas):
            if parcial is None:
                continue
            quiero = set(esperando.get(carpeta) or [])
            items.extend(
                x.model_copy(update={"folder": carpeta})
                for x in parcial.items if str(x.producto) in quiero
            )
    return ProductosListResponse(
        source=source, folder=nicho_config.CARPETA_ESPERANDO_STOCK,
        items=items, textos_extraidos=True,
        montando=any(p.montando for p in items),
    )


@router.get("/productos-todos", response_model=ProductosListResponse)
def list_productos_todos(
    source: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosListResponse:
    """Todos los productos de la fuente, de MÁS a MENOS ventas.

    Existe por "Top vendidos": ahí los productos entran en carpetas de diez y
    el sitio de cada uno es fijo de por vida (moverlo perdería el progreso),
    así que ordenar dentro de una carpeta no da el ranking — un producto de
    tres ventas puede estar en la carpeta 3 mientras miras la 1. Esto las junta
    todas y las ordena de verdad.

    Solo para `top_vendidos`: en las fuentes del curso son 30+ carpetas de
    Drive remoto y listarlas todas costaría minutos.
    """
    if source != top_vendidos.SOURCE:
        raise _bad_request(
            "El listado global solo existe en Top vendidos: en las demás "
            "fuentes hay demasiadas carpetas que leer."
        )
    # A la vez, no en fila: cada carpeta es independiente y en serie sumaban
    # sus segundos (ver el mismo cambio en el POV BOF Largo).
    from concurrent.futures import ThreadPoolExecutor

    carpetas = top_vendidos.carpetas()

    def _una(carpeta: str):
        try:
            return carpeta, _list_productos(source, carpeta, queue, usuario)
        except Exception:  # noqa: BLE001
            # Una carpeta ilegible no puede dejar sin lista a las demás.
            return carpeta, None

    items: list[ProductoInfo] = []
    with ThreadPoolExecutor(max_workers=min(4, len(carpetas) or 1)) as pool:
        for carpeta, parcial in pool.map(_una, carpetas):
            if parcial is None:
                continue
            items.extend(x.model_copy(update={"folder": carpeta}) for x in parcial.items)
    items.sort(key=lambda p: (p.ventas, p.vendido_at), reverse=True)
    return ProductosListResponse(
        source=source, folder="", items=items,
        textos_extraidos=True,
        montando=any(p.montando for p in items),
    )


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

    # En "Top vendidos" los textos NO se extraen: los productos son copias de
    # otros que ya pasaron por Gemini, así que se traen del original. Leer sus
    # capturas otra vez costaba una llamada de más y, sobre todo, el modelo
    # llegó a cruzar los textos entre las imágenes de una tanda y dejó media
    # carpeta con el título del producto de al lado.
    if body.source == top_vendidos.SOURCE:
        textos = top_vendidos.recopiar_textos(body.folder)
    else:
        try:
            textos = text_extractor.extract_folder_texts(body.source, body.folder)
        except ValueError as e:
            raise _bad_request(str(e)) from e

    if not textos:
        # Antes se devolvía la lista igual y la pantalla decía "textos
        # extraídos" sin haber extraído nada: el operador vuelve a pulsar sin
        # saber que la cuota de Gemini está agotada.
        raise APIError(
            "Gemini no ha devuelto ningún texto. Suele ser la cuota agotada "
            "(revisa el tope del proyecto de pago) o una captura ilegible.",
            status_code=502,
        )
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
    variante: Annotated[Literal["limpia", "ficha"], Query()] = "limpia",
    w: Annotated[int | None, Query(ge=32, le=4000)] = None,
) -> FileResponse:
    """Descarga una de las dos fotos del producto, con un nombre que agrupa por
    carpeta al ordenar en la galería del móvil.

    `variante` decide cuál, y el default es "limpia" porque es lo que quiere el
    POV BOF: la foto sin texto encima, que es la que se anima. Creativos Pro
    pide la "ficha" (la captura con la descripción): su prompt tiene que sacar
    los beneficios del producto de algún sitio, y en la foto limpia no están.

    Auth por `?api_key=`: `get_current_user` (dependencia del router) ya
    acepta el api_key por query además de por header — necesario porque este
    endpoint va en un `<a download>` que no manda headers.

    Y por eso este endpoint existe en vez de tirar del `/photo` de ver: el
    atributo `download` de un `<a>` **se ignora cuando la URL es de otro
    origen**, y la API lo es. Lo que fuerza la descarga es el
    `Content-Disposition: attachment` que pone `FileResponse(filename=...)`.
    Con `/photo` el móvil abre la imagen en una pestaña y no baja nada.
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
    clean = (pair or {}).get("clean" if variante == "limpia" else "titled")
    if not clean:
        que = "foto limpia" if variante == "limpia" else "foto de la ficha"
        raise PhotoNotFoundError(
            f"No hay {que} para el producto {producto!r} en {folder!r}.",
            details={
                "source": source, "folder": folder,
                "producto": producto, "variante": variante,
            },
        )

    suffix = os.path.splitext(clean.get("name", ""))[1].lower() or ".jpg"
    try:
        path = drive_client.fetch_photo(clean["id"], suffix=suffix)
    except (ValueError, RuntimeError) as e:
        raise APIError(f"No se pudo descargar la foto: {e}", status_code=502) from e

    # Nombre de descarga: "<carpeta sin espacios>_<NN>.<ext>" — así, al bajar
    # varias fotos al móvil, quedan agrupadas y ordenadas por carpeta+número
    # en vez de mezcladas con el nombre suelto "3.png" que trae Drive. La ficha
    # lleva sufijo para que no pise a la limpia del mismo producto si se bajan
    # las dos (mismo nombre = "archivo(1)" y ya no se sabe cuál es cuál).
    folder_slug = re.sub(r"\s+", "_", folder.strip())
    marca = "" if variante == "limpia" else "_ficha"
    filename = f"{folder_slug}_{producto.zfill(2)}{marca}{suffix}"

    # Con `w` sale encogida y SIN forzar la descarga: así el mismo endpoint
    # sirve de miniatura donde solo hace falta reconocer el producto (la
    # pantalla de las fichas de TikTok), sin tener que resolver el file ID
    # fuera. Sin `w` se comporta como siempre: original y `attachment`.
    if w:
        from src.nicho_pov_bof.services import thumbs

        encogida = thumbs.miniatura(path, w)
        return FileResponse(
            encogida,
            media_type="image/jpeg" if encogida != path else (clean.get("mime") or "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return FileResponse(
        path,
        media_type=clean.get("mime") or "image/jpeg",
        filename=filename,  # Starlette pone Content-Disposition: attachment
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------
# Subida en tanda: varios vídeos de golpe, repartidos solos
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _ruta_de_token(token: str) -> Path:
    """Resuelve el identificador de un bruto ya subido.

    El cliente devuelve el token tal cual se lo dimos, así que hay que tratarlo
    como lo que es: texto que llega de fuera. Se valida el formato y se
    comprueba que el fichero cae DENTRO de la carpeta de subidas — sin esto, un
    `../` apuntaría a cualquier sitio del disco.
    """
    from src.api.temp_storage import upload_subdir

    if not _TOKEN_RE.match(token or ""):
        raise _bad_request(f"identificador de vídeo inválido: {token!r}")
    base = upload_subdir("nicho_pov_bof").resolve()
    ruta = (base / token).resolve()
    if base not in ruta.parents or not ruta.is_file():
        raise _bad_request("ese vídeo ya no está (se purgan a las 24h). Vuelve a subirlo.")
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
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if nombre.endswith(e)), "")
    if not ext:
        raise _bad_request(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}."
        )
    dest = upload_subdir("nicho_pov_bof")
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


@router.post("/video/lote/repartir", response_model=VideoLoteResponse)
def repartir_lote(
    body: dict,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> VideoLoteResponse:
    """Dice de qué producto es cada vídeo ya subido. No encola nada.

    Recibe los identificadores que devolvió `/video/lote/subir`, así que los
    vídeos no viajan dos veces.
    """
    from src.nicho_pov_bof.services import emparejador

    source = str(body.get("source") or "")
    folder = str(body.get("folder") or "")
    tokens = [str(x) for x in (body.get("tokens") or [])]
    if not tokens:
        raise _bad_request("no llegó ningún vídeo que repartir.")
    rutas = [_ruta_de_token(t) for t in tokens]

    fichas = _list_productos(source, folder, None, usuario).items
    candidatos = [p.producto for p in fichas if p.clean_photo_id]
    # Acotar a los que tienen la ficha enlazada cuando se pide. No es solo un
    # filtro: si se han subido los vídeos de los cinco que se van a publicar, el
    # reconocimiento no tiene por qué elegir entre los diez de la carpeta —y
    # cuando se equivoca es justo ahí, con productos parecidos. Menos
    # candidatos, menos formas de fallar.
    if bool(body.get("solo_con_url")):
        con_url = [p.producto for p in fichas if p.clean_photo_id and p.product_url]
        # Si ninguno la tuviera, se ignora: mejor repartir entre todos que
        # dejar la tanda sin repartir.
        if con_url:
            candidatos = con_url
    # Los de plazos llevan DOS clips: pueden llevarse dos vídeos de la tanda.
    dobles = {p.producto for p in fichas if p.modo_plazos}
    reparto = emparejador.emparejar(
        source, folder, rutas, candidatos, dobles=dobles,
    )
    items = [
        VideoLoteItem(
            token=tok, archivo=tok,
            producto=str(r.get("producto") or ""), por_que=str(r.get("por_que") or ""),
        )
        for tok, r in zip(tokens, reparto)
    ]
    return VideoLoteResponse(
        source=source, folder=folder, items=items,
        reconocidos=sum(1 for i in items if i.producto),
        candidatos=len(candidatos),
    )


@router.post("/video/lote/confirmar", response_model=VideoLoteConfirmarResponse)
def confirmar_lote(
    body: VideoLoteConfirmarRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> VideoLoteConfirmarResponse:
    """Encola el montaje de cada vídeo ya repasado por el operador.

    Los productos de plazos llevan DOS clips, así que ahí el vídeo se guarda en
    el primer hueco libre y solo se encola cuando están los dos — igual que al
    subirlos de uno en uno.
    """
    from src.nicho_pov_bof.repos import product_repo

    encolados, pendientes, mensajes = 0, 0, []
    # Cuántos vídeos van ya de cada producto en ESTA tanda: el segundo de un
    # producto de plazos es su clip 2, y sin llevar la cuenta los dos se
    # guardaban en el mismo hueco y el montaje nunca arrancaba.
    vistos: dict[str, int] = {}
    for item in body.items:
        if not item.producto:
            continue
        vistos[item.producto] = vistos.get(item.producto, 0) + 1
        ruta = _ruta_de_token(item.token)
        prod = product_repo.get_product(body.source, body.folder, item.producto, usuario)
        flags = {
            "con_gancho": bool(body.con_gancho), "con_titulo": bool(body.con_titulo),
            "con_cta": bool(body.con_cta), "con_flecha": bool(body.con_flecha),
        }
        # Todos los productos llevan DOS clips (ver `_guardar_clip`), así que
        # la tanda ya no reparte por precio, sino por hueco libre.
        montado_at = float(prod.get("video_listo_at") or 0)
        # El orden de la tanda manda: el primer vídeo de este producto es el
        # clip 1 y el segundo el clip 2. Solo si ya tenía uno subido de antes se
        # respeta el hueco que quede libre.
        if vistos[item.producto] >= 2:
            slot = 2
        else:
            slot = 1 if not _clip_vigente(prod.get("clip1_path"), montado_at) else 2
        r = _guardar_clip(
            queue, body.source, body.folder, item.producto, slot, ruta,
            body.sexo, usuario, **flags,
        )
        if r.job_id:
            encolados += 1
        else:
            pendientes += 1
            mensajes.append(f"Producto {item.producto}: {r.message}")

    return VideoLoteConfirmarResponse(
        encolados=encolados, pendientes=pendientes, mensajes=mensajes[:6],
    )


@router.post("/clip/quitar", response_model=ProductoInfo)
def quitar_clip(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    slot: Annotated[int, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoInfo:
    """Quita un clip subido por error (solo productos de plazos, que llevan dos).

    Sin esto, un clip mal subido se quedaba puesto y el montaje arrancaba con
    él en cuanto entraba el otro. Solo se borra el hueco: ni el vídeo montado
    ni el guion se tocan.
    """
    from src.nicho_pov_bof.repos import product_repo

    if slot not in (1, 2):
        raise _bad_request(f"slot debe ser 1 o 2, recibido: {slot}")
    prod = product_repo.get_product(source, folder, producto, usuario)
    ruta = str(prod.get(f"clip{slot}_path") or "")
    try:
        prod = product_repo.update_product(
            source, folder, producto, usuario=usuario, **{f"clip{slot}_path": ""},
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    if ruta:
        # Vive en `api_uploads/` (se purga a las 24h); se borra ya para no
        # dejar vídeos ocupando sitio.
        try:
            Path(ruta).unlink(missing_ok=True)
        except OSError:
            pass
    return _producto_info(producto, prod, queue=queue, usuario=usuario)


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
    # Solo en productos de plazos (precio >= PRECIO_MIN_PLAZOS): el vídeo son
    # DOS clips, así que cada subida dice cuál es. 0 = producto normal, un
    # único vídeo, como toda la vida.
    slot: Annotated[int, Form()] = 0,
) -> VideoUploadResponse:
    """Sube el vídeo bruto generado fuera (Veo3/Kling) y ENCOLA el montaje
    completo (quita marca de agua + normaliza + cuadra duración + textos +
    flecha + audio). El resultado se ve en la Cola; al terminar el producto
    queda marcado `uploaded=True` en Redis."""
    import shutil

    from src.api.temp_storage import upload_subdir

    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm not in _ALLOWED_SEXOS:
        raise _bad_request(
            f"sexo debe ser 'hombre', 'mujer' o 'auto', recibido: {sexo!r}"
        )
    # `origen` ya no se valida: no cambia nada del montaje desde que Veo3 dejó
    # de poner marca de agua. Se guarda tal cual llegue (vacío incluido) solo
    # como dato del job.
    origen_norm = (origen or "").strip().lower()
    if slot not in (0, 1, 2):
        raise _bad_request(f"slot debe ser 0, 1 o 2, recibido: {slot}")

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

    if slot:
        return _guardar_clip(
            queue, source, folder, producto, slot, raw_path, sexo_norm, operator,
            con_gancho=bool(con_gancho) and bool(con_textos),
            con_titulo=bool(con_titulo) and bool(con_textos),
            con_cta=bool(con_cta) and bool(con_textos),
            con_flecha=bool(con_flecha) and bool(con_textos),
        )

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


def _guardar_clip(
    queue: JobQueue,
    source: str,
    folder: str,
    producto: str,
    slot: int,
    raw_path: Path,
    sexo: str,
    operator: str,
    **flags: bool,
) -> VideoUploadResponse:
    """Guarda uno de los dos clips y encola el montaje cuando están los dos.

    TODOS los productos van con dos clips, no solo los de plazos. El motivo es
    medido: los audios del banco duran entre 9,7s y 13,9s (mediana 12s) y un
    clip da 8s, o 9,6s estirado un 20%, que es el margen aceptado. Con uno solo
    faltaba casi siempre, y ese hueco lo rellenaba `_build_pingpong` repitiendo
    el final del clip hacia atrás y hacia delante: en un vídeo de 12s, un
    tercio era ese rebote. Con dos clips (16s de material) no hace falta
    ninguno. Es además la MISMA regla del POV BOF Largo —`techo(segundos/9,6)`—
    aplicada a este banco de audios.

    Lo que cambia entre uno y otro es de dónde sale la VOZ, no el número de
    clips: los caros llevan el guion de Klarna locutado con Fish y el resto un
    audio del banco.

    Cada montaje empieza de cero — al encolar se olvidan los dos paths, igual
    que en el POV BOF Largo, para que resubir un producto ya montado vuelva a
    pedir los dos clips en vez de mezclar uno nuevo con otro viejo.
    """
    from src.nicho_pov_bof.repos import product_repo

    try:
        prod = product_repo.update_product(
            source, folder, producto, usuario=operator,
            **{f"clip{slot}_path": str(raw_path)},
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    montado_at = float(prod.get("video_listo_at") or 0)
    # Cuántos clips pide ESTE producto. Con guion propio se calcula igual que
    # en el Largo (la voz manda); con la frase del banco siguen siendo dos,
    # porque no se sabe cuál va a tocar hasta el montaje.
    hacen_falta = _clips_que_pide(prod)
    rutas = [prod.get(f"clip{n}_path") for n in range(1, hacen_falta + 1)]
    puestos = [r for r in rutas if _clip_vigente(r, montado_at)]
    if len(puestos) < hacen_falta:
        faltan = [
            n for n in range(1, hacen_falta + 1)
            if not _clip_vigente(prod.get(f"clip{n}_path"), montado_at)
        ]
        return VideoUploadResponse(
            ok=True, job_id="",
            message=(
                f"Clip {slot} guardado. Falta el clip "
                f"{', '.join(map(str, faltan))}."
            ),
        )

    # Los dos clips subidos a la vez: si el otro ya disparó el montaje, no se
    # encola un segundo trabajo con el mismo material.
    if producto in _productos_montandose(queue, source, folder):
        return VideoUploadResponse(
            ok=True, job_id="",
            message=f"Clip {slot} guardado. Ya hay un montaje en marcha para este producto.",
        )

    # Todos por el mismo runner: la voz locuta el guion escrito para ESTE
    # producto, lleve la frase de plazos o no (la CTA del curso la trae ya el
    # prompt cuando la ficha ofrece financiación). Antes los caros se iban por
    # `NICHO_POV_BOF_PLAZOS_VIDEO`, que locuta uno de los cinco textos de
    # Klarna: genéricos —no nombran el producto— y de 253-274 caracteres, o sea
    # vídeos de 13-20s donde se pedían 10.
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_VIDEO,
        title=f"🎬 Nicho POV BOF: producto {producto} · {folder}",
        params={
            "source": source, "folder": folder, "producto": producto,
            **{f"clip{n}_path": prod[f"clip{n}_path"] for n in range(1, hacen_falta + 1)},
            "sexo": sexo, "operator": operator,
            **{k: bool(v) for k, v in flags.items()},
        },
        enqueued_by=operator or None,
    )
    # Las rutas se CONSERVAN. Antes se borraban aquí para que un clip ya
    # consumido no disparase otro montaje, pero de eso se encarga ya
    # `_clip_vigente` (compara la fecha del fichero con la del último montaje).
    # Borrarlas tenía un precio que solo se ve cuando el trabajo FALLA: el
    # producto se quedaba sin referencia a unos clips que siguen en disco, y
    # había que volver a generarlos y subirlos por un JSON mal cerrado.
    return VideoUploadResponse(
        ok=True, job_id=job.id,
        message="Los clips están: montando el vídeo.",
    )


@router.post("/video/montar", response_model=VideoUploadResponse)
def montar_con_los_clips(
    body: dict,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    operator: Annotated[str, Depends(get_web_user)] = "",
) -> VideoUploadResponse:
    """Vuelve a montar con los clips que YA están subidos.

    Existe para el trabajo que falla por algo ajeno a los clips —Gemini sin
    cuota, un JSON mal cerrado, la voz sin decidir—: los ficheros siguen en
    disco, así que volver a generarlos y resubirlos era tirar el trabajo de
    verdad. Con esto se cambia lo que haya que cambiar (normalmente el sexo de
    la voz) y se relanza.

    Solo monta con clips VIGENTES: si el vídeo ya se montó, los de esa ronda
    quedaron consumidos y hay que subir otros.
    """
    from src.nicho_pov_bof.repos import product_repo

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    producto = str(body.get("producto") or "").strip()
    sexo = str(body.get("sexo") or "auto").strip().lower()
    if not (source and folder and producto):
        raise _bad_request("Faltan source, folder o producto.")

    prod = product_repo.get_product(source, folder, producto, operator)
    if not prod:
        raise _bad_request(f"Producto {producto!r} no encontrado en {folder!r}.")

    montado_at = float(prod.get("video_listo_at") or 0)
    hacen_falta = _clips_que_pide(prod)
    faltan = [
        n for n in range(1, hacen_falta + 1)
        if not _clip_vigente(prod.get(f"clip{n}_path"), montado_at)
    ]
    if faltan:
        raise _bad_request(
            f"No están los clips {', '.join(map(str, faltan))}: súbelos y se "
            "monta solo."
        )
    if producto in _productos_montandose(queue, source, folder):
        return VideoUploadResponse(
            ok=True, job_id="",
            message="Ya hay un montaje en marcha para este producto.",
        )

    flags = {k: bool(v) for k, v in (body.get("flags") or {}).items()}
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_VIDEO,
        title=f"🎬 Nicho POV BOF: producto {producto} · {folder}",
        params={
            "source": source, "folder": folder, "producto": producto,
            **{f"clip{n}_path": prod[f"clip{n}_path"] for n in range(1, hacen_falta + 1)},
            "sexo": sexo, "operator": operator, **flags,
        },
        enqueued_by=operator or None,
    )
    return VideoUploadResponse(
        ok=True, job_id=job.id, message="Montando con los clips que ya estaban.",
    )


@router.post("/productos-web/importar-lote", status_code=status.HTTP_201_CREATED)
async def importar_productos_web_lote(
    queue: Annotated[JobQueue, Depends(get_queue)],
    archivos: Annotated[list[UploadFile], File()],
) -> dict:
    """Encola la importación de VARIOS ZIP de la web del curso.

    A la cola y no aquí porque son 31 ficheros de varios MB: hacerlo en la
    propia petición agotaría el tiempo a mitad y encima no se vería el avance.
    Los ZIP se dejan en una carpeta temporal y el runner los procesa y la
    borra.
    """
    import time
    import uuid

    from src.api.temp_storage import upload_subdir

    if not archivos:
        raise _bad_request("no llegó ningún ZIP.")

    destino = upload_subdir("nicho_pov_bof") / f"web_{int(time.time())}_{uuid.uuid4().hex[:6]}"
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
        raise _bad_request("ninguno de los ficheros era un ZIP.")

    title = f"🌐 Importar {guardados} ZIP(s) de la web"
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_WEB_IMPORT,
        title=title,
        params={"temp_folder": str(destino), "total": guardados},
    )
    return {"job_id": job.id, "title": title, "zips": guardados}


@router.post("/productos-web/importar")
async def importar_productos_web(
    archivo: Annotated[UploadFile | None, File()] = None,
    # La APP sube por su cuenta y siempre manda el fichero como `file`: en el
    # WebView el selector no le devuelve los ficheros al `<input>`, así que la
    # web no puede mandarlos ella. Se aceptan los dos nombres.
    file: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """Mete un ZIP de la web del curso en la fuente "🌐 Productos Web".

    Es REPETIBLE a propósito: el catálogo se actualiza y hay que poder resubir
    el mismo ZIP. La respuesta dice qué productos son nuevos, cuáles cambiaron
    y cuáles estaban igual — que es lo que dice a cuáles hay que ponerles la
    ficha de TikTok.
    """
    from src.nicho_pov_bof.services import productos_web

    subido = archivo or file
    if subido is None:
        raise _bad_request("no llegó ningún ZIP.")
    datos = await subido.read()
    await subido.close()
    if not datos:
        raise _bad_request("el ZIP llegó vacío.")
    try:
        return productos_web.importar_zip(datos, subido.filename or "")
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except OSError as e:
        raise APIError(f"No se pudo escribir en el Drive: {e}", status_code=500) from e


@router.post("/mis-productos")
async def crear_mi_producto(
    foto_limpia: Annotated[UploadFile, File()],
    foto_ficha: Annotated[UploadFile | None, File()] = None,
    source: Annotated[str, Query()] = "mis_productos",
) -> dict:
    """Alta de un producto PROPIO subiendo sus dos fotos.

    A partir de aquí se comporta igual que uno del curso: las fotos se guardan
    con el mismo convenio de nombres (`3.png` / `3(1).png`), así que el
    emparejado, los textos, la ficha y el montaje funcionan sin nada especial.

    Las carpetas se llenan de diez en diez; al pasar el tope se abre la
    siguiente sola.
    """
    from src.nicho_pov_bof.services import mis_productos

    if not nicho_config.es_catalogo_operador(source):
        raise _bad_request(f"{source!r} no es un catálogo tuyo.")

    async def _leer(archivo: UploadFile, que: str) -> bytes:
        if not archivo:
            return b""
        nombre = (archivo.filename or "").lower()
        if not any(nombre.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")):
            raise _bad_request(
                f"{que} tiene un formato no soportado ({archivo.filename!r}). "
                "Acepta jpg, jpeg, png o webp."
            )
        datos = await archivo.read()
        if not datos:
            raise _bad_request(f"{que} llegó vacía.")
        if len(datos) > 12 * 1024 * 1024:
            raise _bad_request(
                f"{que} pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB."
            )
        return datos

    limpia = await _leer(foto_limpia, "La foto del producto")
    ficha = await _leer(foto_ficha, "La captura de la ficha") if foto_ficha else b""

    try:
        creado = mis_productos.guardar_producto(
            limpia, ficha or None,
            nombre_limpia=foto_limpia.filename or "",
            nombre_ficha=(foto_ficha.filename or "") if foto_ficha else "",
            source=source,
        )
    except OSError as e:
        raise APIError(f"No se pudieron guardar las fotos: {e}", status_code=500) from e

    return {"source": source, **creado}


@router.delete("/mis-productos")
def borrar_mi_producto(
    carpeta: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    source: Annotated[str, Query()] = "mis_productos",
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
) -> dict:
    """Quita las fotos de un producto propio. Solo vale para `mis_productos`.

    Borra SOLO las fotos, que son dos ficheros y va al momento. El hueco de
    numeración lo cierra el botón de reordenar, aparte y cuando el operador
    quiera: renumerar renombra todos los productos siguientes contra el Drive
    montado, y hacerlo en cada borrado significaba esperar eso tres veces
    seguidas al limpiar tres productos. Antes iba dentro de esta petición y
    recargar la página lo dejaba a medias.
    """
    from src.nicho_pov_bof.services import mis_productos

    if not nicho_config.es_catalogo_operador(source):
        raise _bad_request(f"{source!r} no es un catálogo tuyo.")
    if not mis_productos.borrar_producto(
        carpeta, producto, renumerar=False, source=source,
    ):
        raise APIError(
            f"No existe el producto {producto} en {carpeta}.", status_code=404,
        )
    return {"ok": True}


@router.post("/producto/limpiar")
def limpiar_producto(
    body: dict,
    operator: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Deja un producto como recién subido, sin tocar sus textos.

    Fuera el guion, el subliminal, la voz, los clips, el vídeo y las marcas de
    subido/vendido. Hace falta porque el número es la identidad del producto
    dentro de su carpeta y se reutiliza: uno nuevo podía nacer con lo del que
    ocupaba antes ese número. La otra salida era borrarlo y volver a subir las
    dos fotos, que obliga a tenerlas a mano.
    """
    from src.nicho_pov_bof.repos import product_repo

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    producto = str(body.get("producto") or "").strip()
    if not (source and folder and producto):
        raise _bad_request("Faltan source, folder o producto.")
    if source not in nicho_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")

    borrados = product_repo.limpiar_generado(source, folder, producto, operator)
    return {"ok": True, "borrados": borrados}


@router.post("/mis-productos/mover")
def mover_mi_producto(body: dict) -> dict:
    """Pasa un producto de "Muestras productos" a "Tareas Productos" (o al revés).

    Por qué se graba un producto —muestra gratuita o tarea pagada— se sabe a
    veces DESPUÉS de haberlo subido, y sin esto había que borrarlo y volver a
    subir las dos fotos. Se lleva las fotos y lo que guardan los nichos de ese
    producto; la venta apuntada y el escaparate no dependen de la carpeta.
    """
    from src.nicho_pov_bof.services import mis_productos

    carpeta = str(body.get("carpeta") or "").strip()
    producto = str(body.get("producto") or "").strip()
    origen = str(body.get("origen") or "mis_productos").strip()
    destino = str(body.get("destino") or "").strip()
    if not (carpeta and producto and destino):
        raise _bad_request("Faltan carpeta, producto o destino.")
    try:
        movido = mis_productos.mover_producto(
            carpeta, producto, origen=origen, destino=destino,
        )
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except OSError as e:
        raise APIError(f"No se pudieron mover las fotos: {e}", status_code=500) from e
    return {"ok": True, "source": destino, **movido}


@router.get("/mis-productos/plan-recolocar")
def plan_recolocar(source: Annotated[str, Query()] = "mis_productos") -> dict:
    """Qué pasaría al recolocar, SIN tocar nada.

    Mover productos entre carpetas arrastra sus textos, guion, clips y vídeo
    por varios documentos de Redis; enseñar antes el plan es lo que evita
    ejecutarlo a ciegas.
    """
    from src.nicho_pov_bof.services import mis_productos

    plan = mis_productos.plan_compactar(source)
    antes = {
        c: len(mis_productos._numeros(c, source))
        for c in mis_productos.carpetas(source)
    }
    total = sum(antes.values())
    despues: dict[str, int] = {}
    for i in range(total):
        nombre = mis_productos._nombre_carpeta(i // mis_productos.POR_CARPETA, source)
        despues[nombre] = despues.get(nombre, 0) + 1
    return {
        "movimientos": len(plan),
        "total": total,
        "antes": antes,
        "despues": despues,
        "carpetas_borradas": [c for c in antes if c not in despues],
    }


@router.post("/mis-productos/renumerar")
def renumerar_mis_productos(
    carpeta: Annotated[str, Query()] = "",
    source: Annotated[str, Query()] = "mis_productos",
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
) -> dict:
    """Cierra los huecos de numeración de una carpeta propia (5, 7, 8 → 5, 6, 7).

    Se pulsa cuando toca, después de borrar lo que haya que borrar: así se
    renumera UNA vez y no una por cada producto quitado. Arrastra lo guardado
    de cada producto (textos, guion, clips, vídeo, subidos, ventas) a su
    número nuevo.

    Va por la cola porque son renombrados contra el Drive montado: catorce
    operaciones de red al cerrar el hueco del 3 en una carpeta de diez. Dentro
    de la petición, recargar la página lo dejaba a medias.
    """
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_RENUMERAR,
        title=f"🔢 Renumerar · {carpeta}" if carpeta else "🔢 Recolocar productos propios",
        params={"carpeta": carpeta, "source": source},
    )
    return {"job_id": job.id, "title": job.title}


@router.post("/top-vendidos/reparar")
def reparar_top_vendidos(
    folder: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Rehace fotos y textos de una carpeta de Top vendidos desde el original.

    Existe porque una copia puede quedarse torcida (foto de un producto con el
    texto de otro) y desde la pantalla no había forma de arreglarlo: extraer
    los textos otra vez no toca las fotos, y las fotos no se pueden reemparejar
    a mano. El original es la única fuente fiable.
    """
    from src.nicho_pov_bof.services import top_vendidos as tv

    try:
        return tv.reparar_carpeta(folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e


@router.post("/top-vendidos/sincronizar")
def sincronizar_top_vendidos(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Copia a "Top vendidos" los productos del ranking que aún no estén.

    Solo añade, nunca reordena: el sitio de un producto es fijo porque el
    progreso (subido, clips, guion) se guarda por carpeta y moverlo lo
    perdería. El orden por ventas se hace al pintar.

    No gasta Gemini: los textos se copian de la carpeta de origen, donde ya se
    extrajeron.
    """
    try:
        return top_vendidos.sincronizar(usuario=usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    except Exception as e:
        raise APIError(f"No se pudo sincronizar: {e}", status_code=500) from e


@router.post("/producto/guion-plazos", response_model=ProductoInfo)
def sortear_guion_plazos(
    body: GuionPlazosRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoInfo:
    """Asigna a un producto de plazos uno de los guiones del curso.

    No gasta ninguna llamada a ninguna API: son cinco textos fijos y aquí solo
    se sortea cuál toca. Existe para que el operador LEA lo que va a decir la
    voz antes de montar (y pueda pedir otro si no le convence), en vez de
    enterarse con el vídeo ya hecho.
    """
    import random

    from src.nicho_pov_bof.repos import product_repo

    prod = product_repo.get_product(body.source, body.folder, body.producto, usuario)
    if not _precio_y_modo(prod)[1]:
        raise _bad_request(
            "Este producto no es de plazos: su precio no llega al umbral, así "
            "que lleva el audio de siempre."
        )
    guiones = nicho_config.guiones_plazos()
    if not guiones:
        raise APIError("No hay guiones de plazos cargados.", status_code=500)

    actual = str(prod.get("guion_plazos") or "").strip()
    if actual and not body.rehacer:
        return _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)
    # Al pedir otro se descarta el que ya tenía: con cinco textos, repetir el
    # mismo es lo más probable que puede pasar y parecería que no ha hecho nada.
    opciones = [g for g in guiones if g != actual] or guiones
    nuevo = random.choice(opciones)
    try:
        prod = product_repo.update_product(
            body.source, body.folder, body.producto, usuario=usuario,
            guion_plazos=nuevo,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _producto_info(body.producto, prod, body.source, body.folder, queue, usuario)


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

    # Los textos se leen APARTE y no del `update_product` de abajo: los tres
    # campos que toca este endpoint son privados, así que a un usuario que no
    # sea `ness` la respuesta le vuelve solo con lo suyo, SIN título ni tienda —
    # y sin ellos no hay clave de escaparate y la marca se perdía en silencio.
    textos = product_repo.get_product(body.source, body.folder, body.producto, usuario)
    if body.en_escaparate is not None and not textos.get("titulo"):
        raise _bad_request(
            "Este producto no tiene textos todavía: sin el nombre y la tienda no "
            "se puede saber si ya está en el escaparate. Pásale 'Textos' antes."
        )

    # El precio va al documento COMPARTIDO (es un dato del producto, no del
    # operador) y decide si el vídeo lleva guion de plazos. Se escribe a mano
    # cuando la captura de la ficha falta o no se deja leer: sin él, un
    # producto de 150 € se montaría como uno de 15.
    if body.precio is not None:
        nuevo = 0.0 if body.precio < 0 else float(body.precio)
        product_repo.save_extracted_texts(
            body.source, body.folder, {body.producto: {"precio": nuevo}},
        )

    # "Sin stock" también va al documento COMPARTIDO: que un producto se haya
    # retirado del catálogo no depende de quién lo mire. Y el mismo producto
    # sale repetido en varias carpetas, así que marcarlo aquí ahorra que el
    # siguiente vuelva a abrir el enlace para descubrir lo mismo.
    if body.sin_stock is not None:
        product_repo.save_extracted_texts(
            body.source, body.folder,
            {body.producto: {"sin_stock": bool(body.sin_stock)}},
        )

    try:
        if body.clip_s is not None and body.clip_s not in (8, 10):
            raise _bad_request(f"clip_s debe ser 8 o 10, recibido: {body.clip_s}")
        prod = product_repo.update_product(
            body.source, body.folder, body.producto, usuario=usuario,
            en_escaparate=body.en_escaparate,
            uploaded=body.uploaded, sold=body.sold,
            clip_s=body.clip_s,
        )
        # Y en el índice ÚNICO por (tienda|nombre): el mismo producto sale en
        # varias carpetas y se graba con varios nichos, pero al Marketplace se
        # sube una sola vez. Así queda marcado en todos los sitios a la vez.
        if body.en_escaparate is not None:
            product_repo.marcar_escaparate_producto(
                textos, body.en_escaparate, usuario,
            )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # "Subido" lo marca el operador cuando publica en TikTok, y es lo que
    # alimenta el tope diario de la cuenta. Se guarda la hora para poder
    # comprobar de un vistazo que un producto repetido quedó bien marcado.
    if body.uploaded is not None:
        _contar_subida(
            "videos", f"pov_bof|{body.source}|{body.folder}|{body.producto}",
            body.uploaded, usuario,
        )

    # SIN `source`/`folder`: rellenarlos hace que se emparejen las fotos de la
    # carpeta (leerlas del Drive montado y desempatar por contenido), y eso son
    # 10-15 segundos por toque en la acción que más se repite del día. Marcar
    # un booleano no necesita mirar ninguna foto; la pantalla ya conserva las
    # suyas porque solo copia los campos de estado de esta respuesta.
    info = _producto_info(body.producto, prod, queue=queue, usuario=usuario)

    # El ranking de vendidos lleva su propio índice con una copia de lo que
    # hace falta para pintarlo (foto incluida). Se escribe AQUÍ, en el único
    # sitio donde se marca la venta, y no recorriendo las 31 carpetas después.
    if body.sold is not None:
        # En "Top vendidos" la venta se le apunta al producto de ORIGEN, no a
        # la copia. Eso lo resuelve ya el repo (`_ref_vendido`) para todos los
        # nichos por igual — aquí se manda tal cual llegó.
        destino = (body.source, body.folder, body.producto)
        try:
            if body.sold:
                product_repo.marcar_vendido(
                    *destino,
                    titulo=info.titulo or "", tienda=info.tienda or "",
                    clean_photo_id=info.clean_photo_id or "",
                    product_url=info.product_url or "",
                    nicho=(body.nicho or "").strip(),
                    usuario=usuario,
                )
            else:
                product_repo.desmarcar_vendido(*destino, usuario=usuario)
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


def _a_precio(valor) -> float:
    """El precio como número (0 si no se pudo leer de la ficha)."""
    try:
        return float(str(valor).replace(",", ".").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _productos_de_la_carpeta(source: str, folder: str) -> set[str] | None:
    """Ids de producto que salen hoy de emparejar las fotos. `None` si falla.

    No se miden las fotos: agrupar va por el NOMBRE, y medir obligaría a
    descargarlas todas para pintar una lista.
    """
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        fotos = drive_client.list_photos(source, folder)
    except Exception:  # noqa: BLE001
        return None
    if not fotos:
        return None
    return {str(x["producto"]) for x in photo_pairing.pair_folder(fotos)}


@router.post("/titulos-drive/reconstruir")
def reconstruir_titulos_drive() -> dict:
    """Rehace el índice de "qué hay en el Drive del curso".

    Se mantiene solo al extraer textos, así que esto es para lo que YA estaba
    extraído antes de que el índice existiera — cientos de productos. Un
    listado de carpetas por fuente y un `mget`: lento pero de una vez.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client

    carpetas: dict[str, list[str]] = {}
    fallos: list[str] = []
    for fuente in product_repo.FUENTES_DRIVE:
        if fuente not in pov_config.SOURCES:
            continue
        try:
            carpetas[fuente] = [
                c.get("name", "") for c in drive_client.list_product_folders(fuente)
            ]
        except Exception as e:  # noqa: BLE001
            # Una fuente caída no puede dejar el índice a medias en silencio:
            # se avisa y se reconstruye con las que sí contestan.
            fallos.append(f"{fuente}: {e}")

    try:
        total = product_repo.reconstruir_titulos_drive(carpetas)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {
        "titulos": total,
        "fuentes": sorted(carpetas),
        "carpetas": sum(len(v) for v in carpetas.values()),
        "fallos": fallos,
    }


@router.post("/clip-s/carpeta")
def clip_s_carpeta(body: dict) -> dict:
    """Pone la duración de clip (8 o 10 s) a TODOS los productos de la carpeta.

    Es lo normal: el operador genera la tanda entera con la misma herramienta,
    así que elegirlo diez veces era trabajo tonto. El de cada producto sigue
    existiendo para la excepción.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    clip_s = int(body.get("clip_s") or 0)
    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")
    if not folder:
        raise _bad_request("Falta la carpeta.")
    if clip_s not in (8, 10):
        raise _bad_request(f"clip_s debe ser 8 o 10, recibido: {clip_s}")

    # Un solo load/save del documento: producto a producto serían diez idas y
    # vueltas a Upstash por un campo de un dígito.
    try:
        with product_repo._cerrojo_carpeta(source, folder):
            doc = product_repo.load_folder(source, folder)
            productos = doc.setdefault("productos", {})
            for prod in productos.values():
                prod["clip_s"] = clip_s
            product_repo.save_folder(source, folder, doc)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"clip_s": clip_s, "productos": len(productos)}


@router.post("/ids/resolver")
def resolver_ids(body: dict) -> dict:
    """Saca el ID de producto de los enlaces de una carpeta y lo guarda.

    Es lo que hace rápida la publicación: TikTok Studio busca por ID en
    "Añade enlaces de productos", y sin él hay que ir pasando páginas hasta
    dar con el producto. El ID sale de seguir el redirect del enlace corto, o
    sea una petición HTTP por producto: ni API, ni cuota.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import product_url

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")
    if not folder:
        raise _bad_request("Falta la carpeta.")

    doc = product_repo.load_folder(source, folder)
    productos = doc.get("productos") or {}
    indice = product_repo.urls_index()
    urls = {
        pid: product_repo.url_de(prod, indice) for pid, prod in productos.items()
    }
    hallados = product_url.ids_de_carpeta(productos, urls)
    for pid, pid_tiktok in hallados.items():
        try:
            product_repo.update_product(source, folder, pid, product_id=pid_tiktok)
        except RuntimeError:
            pass
    con_url = sum(1 for u in urls.values() if u)
    return {
        "resueltos": len(hallados),
        "con_url": con_url,
        "sin_resolver": con_url - len(hallados) - sum(
            1 for pid, prod in productos.items()
            if prod.get("product_id") and urls.get(pid)
        ),
    }


@router.post("/guiones/lote", status_code=201)
def guiones_lote(
    body: dict,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    operator: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola los guiones de 10s de TODA una carpeta.

    Son diez llamadas a Gemini, o sea diez esperas seguidas si se pulsa
    producto a producto con el operador delante. Por la cola se lanza y se
    sigue trabajando, igual que los textos y que los guiones del Largo.
    """
    from src.nicho_pov_bof import config as pov_config

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")
    if not folder:
        raise _bad_request("Falta la carpeta.")

    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_GUIONES,
        title=f"✍️ Guiones POV BOF · {folder}",
        params={
            "source": source,
            "folder": folder,
            "rehacer": bool(body.get("rehacer")),
            "productos": [str(x) for x in (body.get("productos") or []) if str(x)],
        },
        enqueued_by=operator or None,
    )
    pendientes = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    return {
        "job_id": job.id,
        "title": job.title,
        "position_in_queue": next(
            (i for i, j in enumerate(pendientes) if j.id == job.id), 0
        ),
    }


@router.post("/guion")
def escribir_guion(body: dict) -> dict:
    """Escribe el guion de 10s de UN producto y lo guarda.

    Es lo que sustituye a la frase del banco de audios: nombra el producto y
    lo que hace. Se guarda COMPARTIDO (no por usuario) a propósito — el guion
    habla del producto, no de quién lo graba, así que Mauro y Ana reaprovechan
    el mismo y no se gastan tres llamadas a Gemini por producto.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof_largo.services import guionista

    source = str(body.get("source") or "").strip()
    folder = str(body.get("folder") or "").strip()
    producto = str(body.get("producto") or "").strip()
    if not (source and folder and producto):
        raise _bad_request("Faltan source, folder o producto.")

    prod = product_repo.get_product(source, folder, producto) or {}
    if not prod.get("titulo"):
        raise _bad_request(
            "Este producto no tiene textos extraídos todavía: pulsa antes "
            "'Obtener textos'. Sin título, el guion saldría genérico."
        )
    # Qué cierre le toca a ESTE producto: lo que su ficha dice que cumple.
    from src.nicho_pov_bof_largo import config as largo_config

    plazos = pov_config.hay_plazos(prod)
    envio = largo_config.hay_envio_gratis(prod)
    guardado = str(prod.get("guion_producto") or "")
    # El guion guardado se reaprovecha SIEMPRE (salvo "rehacer"): si lo que
    # promete no cuadra con la ficha, se le cambia el cierre —que es un literal
    # fijo del curso— sin gastar una llamada a Gemini.
    if guardado and not body.get("rehacer"):
        ajustado = pov_config.ajustar_cta(guardado, plazos=plazos, envio=envio)
        if ajustado and ajustado != guardado:
            try:
                product_repo.update_product(
                    source, folder, producto, guion_producto=ajustado,
                    guion_producto_plazos=plazos, guion_producto_envio=envio,
                )
            except RuntimeError:
                pass
        return {
            "guion": ajustado or guardado,
            "subliminal": prod.get("subliminal_producto", ""),
            "caracteres": len(ajustado or guardado),
            "reusado": True,
        }

    foto = None
    try:
        from src.nicho_pov_bof.services import drive_client, photo_pairing

        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
        par = next(
            (x for x in photo_pairing.pair_folder(fotos)
             if str(x.get("producto")) == producto), None,
        )
        limpia = (par or {}).get("clean") or {}
        if limpia.get("id"):
            foto = drive_client.fetch_photo(limpia["id"], suffix=".jpg")
    except Exception:  # noqa: BLE001 — sin foto el guion sale más genérico
        foto = None

    try:
        escrito = guionista.escribir(
            titulo=prod.get("titulo", ""),
            tienda=prod.get("tienda", ""),
            caption=prod.get("caption", ""),
            foto=foto,
            # La frase del pago a plazos solo si la ficha lo ofrece: en un
            # producto de 11 € es relleno y encima no se sostiene.
            prompt=pov_config.prompt_guion_producto(plazos, envio),
            max_caracteres=pov_config.caracteres_guion(plazos, envio),
            etiqueta="nicho_pov_bof",
        )
    except ValueError as e:
        raise APIError(str(e), status_code=422) from e
    except Exception as e:
        raise APIError(f"Gemini no pudo escribir el guion: {e}", status_code=502) from e

    try:
        product_repo.update_product(
            source, folder, producto,
            guion_producto=escrito["guion"],
            subliminal_producto=escrito["subliminal"],
            guion_producto_plazos=plazos,
            guion_producto_envio=envio,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {
        "guion": escrito["guion"],
        "subliminal": escrito["subliminal"],
        "caracteres": len(escrito["guion"]),
        "reusado": False,
    }


@router.post("/urls/importar")
def importar_urls(body: dict) -> dict:
    """Guarda de golpe las fichas copiadas del DOM de la web del curso.

    Su página lleva el enlace de TikTok de cada producto en un `<a>`, con la
    carpeta y el número al lado. Sacarlos de ahí es gratis; averiguarlos uno a
    uno cuesta una llamada de EchoTik por producto, y el plan son 100 al mes.

    Body: `{source, filas: [{carpeta, producto, url}]}`.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo

    source = str(body.get("source") or "").strip()
    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")

    filas = body.get("filas")
    if not isinstance(filas, list) or not filas:
        raise _bad_request("No llegó ninguna fila. Pega el JSON de la consola.")
    if len(filas) > 5000:
        raise _bad_request(f"Demasiadas filas ({len(filas)}).")

    from src.nicho_pov_bof.services import drive_client

    try:
        reales = [c.get("name", "") for c in drive_client.list_product_folders(source)]
    except Exception:  # noqa: BLE001
        reales = []

    try:
        return product_repo.importar_urls(source, filas, reales)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e


@router.get("/urls-catalogo")
def urls_catalogo(
    source: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Todos los productos de un catálogo, agrupados por TIENDA, con su ficha.

    Es la pantalla desde la que se pegan las URLs de TikTok Shop una detrás de
    otra. Por tienda porque así se trabajan: se abre la tienda en la app y se
    van copiando sus productos seguidos.

    Un producto sale UNA vez aunque esté repetido en cinco carpetas: la ficha
    es del producto, no de la carpeta, y pegarla una vez vale para todas.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client

    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")

    try:
        carpetas = [c.get("name", "") for c in drive_client.list_product_folders(source)]
    except (ValueError, RuntimeError) as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    docs = product_repo.load_folders([(source, c) for c in carpetas])
    indice = product_repo.urls_index()
    por_clave: dict[str, dict] = {}
    for carpeta, doc in zip(carpetas, docs):
        # Solo los que HOY tienen fotos: en Redis se quedan los textos de
        # productos que el curso borró o renumeró, y si uno de esos acaba
        # siendo el representante, su miniatura da 404.
        reales = _productos_de_la_carpeta(source, carpeta)
        for pid, prod in ((doc or {}).get("productos") or {}).items():
            if not str(prod.get("titulo") or "").strip():
                continue
            if reales is not None and pid not in reales:
                continue
            claves = product_repo.claves_escaparate(prod)
            if not claves:
                continue
            item = por_clave.setdefault(claves[0], {
                "clave": claves[0],
                "source": source,
                "folder": carpeta,
                "producto": pid,
                "titulo": prod.get("titulo") or "",
                "titulo_tiktok_completo": prod.get("titulo_tiktok_completo") or "",
                "tienda": prod.get("tienda") or "sin tienda",
                "precio": _a_precio(prod.get("precio")),
                # El de antes del descuento: se enseña tachado, como en las
                # fichas de los nichos.
                "precio_lista": _a_precio(prod.get("precio_lista")),
                "url": product_repo.url_de(prod, indice),
                "carpetas": [],
            })
            item["carpetas"].append(carpeta)

    tiendas: dict[str, list[dict]] = {}
    for item in por_clave.values():
        tiendas.setdefault(item["tienda"], []).append(item)
    # De más caro a más barato: el producto caro es el que deja comisión, así
    # que es por el que se empieza a pegar fichas. Los que no tienen precio
    # leído se van al final, que si no se colarían arriba como si fueran 0 €.
    for lista in tiendas.values():
        lista.sort(key=lambda x: (-(x["precio"] or 0), x["titulo"].lower()))

    return {
        "source": source,
        "tiendas": [
            {
                "tienda": tienda,
                "items": lista,
                "con_url": sum(1 for x in lista if x["url"]),
                "total": len(lista),
            }
            for tienda, lista in sorted(
                tiendas.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())
            )
        ],
        "con_url": sum(1 for x in por_clave.values() if x["url"]),
        "total": len(por_clave),
    }


@router.post("/url-producto")
def guardar_url_producto(
    body: GuardarUrlRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Guarda a mano la ficha de TikTok Shop de un producto (vacía = quitarla).

    Se guarda por producto (tienda + título literal), así que vale para todas
    sus carpetas y para todos los usuarios: la ficha de TikTok es la misma,
    cada uno la añade a SU escaparate.
    """
    from src.nicho_pov_bof.repos import product_repo

    prod = product_repo.get_product(body.source, body.folder, body.producto, usuario)
    if not prod:
        raise _bad_request(f"Producto {body.producto!r} no encontrado en {body.folder!r}.")
    try:
        url = product_repo.guardar_url(prod, body.url)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # El ID, al vuelo: es una petición al redirect del enlace y evita que haya
    # que acordarse de un segundo paso para poder enlazar en TikTok Studio.
    from src.nicho_pov_bof.services import product_url as url_svc

    pid_tiktok = url_svc.id_desde_url(url) if url else ""
    try:
        product_repo.update_product(
            body.source, body.folder, body.producto, product_id=pid_tiktok,
        )
    except RuntimeError:
        pass
    return {"url": url, "product_id": pid_tiktok}


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
    (el mount). Cada montaje escribe un fichero nuevo (el nombre lleva la hora)
    y `video_path` apunta al último, así que esto devuelve SIEMPRE la última
    versión; el frontend añade `video_listo_at` a la URL para que el navegador
    no sirva la anterior de su caché.
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
        filename=(Path(ruta).name or p.name) if descargar else None,
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

    escaparate = product_repo.escaparate_index(usuario)
    items: list[ProductoBuscado] = []
    for d in encontrados:
        # Cuatro valores: al añadir la fecha de subida se quedó aquí un
        # desempaquetado de tres y la búsqueda entera devolvía un 500.
        clean, _titled, _aviso, _subida = _fotos_del_producto(
            d["source"], d["folder"], d["producto"],
        )
        items.append(
            ProductoBuscado(
                source=d["source"], folder=d["folder"], producto=d["producto"],
                titulo=d.get("titulo") or "",
                titulo_tiktok_completo=d.get("titulo_tiktok_completo") or "",
                tienda=d.get("tienda") or "",
                clean_photo_id=clean or "",
                product_url=product_repo.url_de(d),
                en_escaparate=product_repo.marcado_en_escaparate(d, escaparate),
                uploaded=bool(d.get("uploaded")),
                sold=bool(d.get("sold")),
                unidades=int(d.get("unidades") or 0),
            )
        )
    return BuscarProductosResponse(items=items, total=total)


@router.get("/recuperados", response_model=RecuperadosResponse)
def list_recuperados(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> RecuperadosResponse:
    """Productos que aparecieron después de haber trabajado ya su carpeta.

    Recorre las 35 carpetas emparejando fotos, así que tarda unos segundos: se
    abre a mano desde un botón, no al cargar la página. Es una herramienta
    TEMPORAL para repescar lo que se perdió; cuando no queden, la lista sale
    vacía y se puede quitar.
    """
    from src.nicho_pov_bof.repos import product_repo

    from src.nicho_pov_bof.repos import product_repo as _pr

    items: list[ProductoRecuperado] = []
    carpetas: list[str] = []
    for d in product_repo.productos_recuperados(usuario):
        prod = _pr.get_product(d["source"], d["folder"], d["producto"], usuario)
        items.append(
            ProductoRecuperado(
                source=d["source"],
                folder=d["folder"],
                producto=_producto_info(
                    d["producto"], prod, d["source"], d["folder"], queue, usuario,
                ),
            )
        )
        etiqueta = f'{d["source"]}|{d["folder"]}'
        if etiqueta not in carpetas:
            carpetas.append(etiqueta)
    return RecuperadosResponse(items=items, carpetas=carpetas)


@router.get("/vendidos/nichos")
def list_nichos_venta() -> dict:
    """Nichos a los que se puede atribuir una venta.

    Se sirven desde el backend y no se hardcodean en la pantalla para que
    añadir un nicho sea tocar UN sitio.
    """
    from src.nicho_pov_bof.repos.product_repo import NICHOS_VENTA

    return {"items": [{"key": k, "label": v} for k, v in NICHOS_VENTA.items()]}


@router.get("/vendidos", response_model=SoldProductsResponse)
def list_sold(
    source: Annotated[str | None, Query()] = None,
    nicho: Annotated[str | None, Query()] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> SoldProductsResponse:
    """Ranking de vendidos, del que más unidades al que menos.

    Sale del índice propio (dos llamadas a Redis). Antes se recorrían las 31
    carpetas de cada fuente producto a producto: ocho segundos para encontrar
    dos ventas, y sin foto.
    """
    from src.nicho_pov_bof.repos import product_repo

    # Sin `nicho` salen TODOS mezclados, que es la vista por defecto.
    items = product_repo.ranking_vendidos(nicho or "", usuario)
    if source:
        items = [i for i in items if i.get("source") == source]
    return SoldProductsResponse(items=items)


@router.post("/vendidos/unidades", response_model=SoldProductsResponse)
def sumar_unidades_vendidas(
    body: UnidadesRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> SoldProductsResponse:
    """Suma (o resta) unidades a un producto ya vendido.

    Un producto que REPITE venta es la señal más valiosa que hay aquí, y no
    había forma de anotarla: vendiera una vez o cinco, se veía igual.
    """
    from src.nicho_pov_bof.repos import product_repo

    try:
        product_repo.sumar_unidades(
            body.source, body.folder, body.producto, body.delta, usuario,
        )
    except ValueError as e:
        raise APIError(str(e), status_code=404) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return SoldProductsResponse(items=product_repo.ranking_vendidos(usuario=usuario))
