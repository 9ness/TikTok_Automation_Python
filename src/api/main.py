"""Punto de entrada FastAPI.

Arrancar en local con:
    uvicorn src.api.main:app --reload --port 8000
"""

from __future__ import annotations

# ============================================================
# Windows stdout encoding fix: por defecto cp1252 no soporta emojis →
# cualquier `print("🎙️ ...")` en runners (locutor.py, etc.) crashea la
# tarea con `UnicodeEncodeError`. Lo arreglamos forzando UTF-8 en stdout
# / stderr lo antes posible. `errors="replace"` por si algún byte sigue
# fuera de tabla (no rompe el job).
# ============================================================
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass  # No-op en plataformas/entornos donde reconfigure no aplica

# ============================================================
# Compat patch: moviepy 1.0.3 usa `Image.ANTIALIAS` que Pillow 10+ eliminó.
# El equivalente moderno es `Image.LANCZOS`. Hay que parchearlo ANTES de
# importar moviepy (que se carga indirectamente por los runners). El mismo
# parche existe en main.py (Streamlit). Sin esto, render de Presidentes
# falla con `module 'PIL.Image' has no attribute 'ANTIALIAS'` y los vídeos
# salen de 4-8s solo con la intro.
# ============================================================
import PIL.Image  # noqa: E402
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS  # type: ignore[attr-defined]

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.config import get_settings
from src.api.exceptions import register_exception_handlers
from src.api.routers import (
    auth_router,
    cuotas_router,
    construccion_pov_router,
    deploy_router,
    copyright_router,
    dashboard_router,
    diagnostics_router,
    editor_auto_enqueue_router,
    editor_auto_folders_router,
    editor_auto_plans_router,
    editor_auto_referrals_router,
    editor_auto_web_upload_router,
    editor_auto_sharing_router,
    editor_auto_stickers_router,
    editor_auto_subscriptions_router,
    editor_auto_tools_router,
    editor_auto_users_router,
    fonts_file_router,
    fonts_router,
    generations_router,
    generations_video_router,
    match_photos_file_router,
    match_photos_router,
    presidents_router,
    product_photo_file_router,
    products_router,
    pronosticos_router,
    queue_router,
    queue_video_router,
    stats_router,
    subs_auto_frame_router,
    subs_auto_router,
    tiktok_shop_discovery_router,
    tiktok_shop_radar_router,
    tiktok_shop_calendar_router,
    tiktok_shop_hooks_router,
    tiktok_shop_performance_router,
    tiktok_shop_presets_router,
    tiktok_shop_replicate_viral_router,
    tiktok_shop_shortcuts_router,
    tiktok_shop_watermark_remover_router,
    users_router,
    viralizacion_enqueue_router,
    nicho_pov_bof_folders_router,
    nicho_pov_bof_productos_router,
    nicho_ropa_prendas_router,
    nicho_ropa_personas_chicas_router,
    nicho_ropa_personas_prendas_router,
    nicho_bof_cine_router,
    nicho_gorras_router,
    cuenta_piloto_router,
    nicho_pov_bof_largo_router,
    nicho_creativos_router,
    nicho_carruseles_router,
    voices_router,
    voices_sample_router,
)
from src.api.websockets import queue_ws_router
from src.api.session import usuario_de_request
from src.api import users as _users


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks. Aquí solo logueamos — Redis es lazy
    (cliente HTTP REST de Upstash, sin pool persistente)."""
    settings = get_settings()
    logger.info("API starting | host=%s port=%d", settings.host, settings.port)
    from src.tiktok_shop.repos.redis_base import get_shop_redis

    redis = get_shop_redis()
    if redis.is_available():
        logger.info("Upstash Redis: configured (REST)")
    else:
        logger.warning("Upstash Redis: NOT configured — degraded mode")

    # Cleanup de uploads expirados (TTL 24h por defecto)
    try:
        from src.api.temp_storage import cleanup_expired
        removed, freed = cleanup_expired()
        if removed > 0:
            logger.info(
                "temp_work cleanup: %d archivos / %.1f MB liberados",
                removed, freed / 1024 / 1024,
            )
    except Exception as e:
        logger.warning("temp_work cleanup falló: %s", e)

    # Editor Auto · seed de planes base (idempotente). Si el admin ya
    # tiene planes creados en Redis, no toca nada. Se ejecuta antes del
    # watcher para que la primera quota check tenga los planes listos.
    try:
        from src.editor_auto.services.plan_seeder import seed_base_plans
        created = seed_base_plans()
        if created > 0:
            logger.info("plan_seeder: %d planes base creados", created)
    except Exception as e:
        logger.warning("plan_seeder falló (no crítico): %s", e)

    # Editor Auto · watcher de auto-enqueue. Background task que cada
    # 30s escanea entrada/ de los usuarios con `auto_enqueue=True` y
    # encola los vídeos nuevos sin intervención humana. Pensado para el
    # VPS 24/7. Se gestiona con un stop_event para cierre limpio.
    import asyncio
    from src.editor_auto.services.auto_enqueue_watcher import watcher_loop
    from src.editor_auto.services.draft_sweeper import sweeper_loop

    watcher_stop = asyncio.Event()
    watcher_task = asyncio.create_task(watcher_loop(watcher_stop))

    # Editor Auto · sweeper de borradores sin enviar (arrastra al próximo día
    # con hueco / recuerda antes del cierre / borra tras la gracia).
    sweeper_stop = asyncio.Event()
    sweeper_task = asyncio.create_task(sweeper_loop(sweeper_stop))

    # Nicho POV BOF · "Mis productos" vive en el Drive MONTADO, y tocar en frío
    # una ruta honda del mount cuesta 20-37s. Se precalienta al arrancar y cada
    # 10 min para que el operador no se coma esa espera al abrir la pantalla
    # justo después de un deploy (que es cuando siempre está fría).
    from src.nicho_pov_bof.services.mis_productos import bucle_precalentado

    calentador_stop = asyncio.Event()
    calentador_task = asyncio.create_task(bucle_precalentado(calentador_stop))

    # Nicho POV BOF · copia diaria del Drive del curso. El admin de aquel Drive
    # borra carpetas sin avisar y hasta ahora la copia dependía de que alguien
    # pulsara el botón: se perdieron ocho productos de "10 Agosto 2026" por dos
    # días de diferencia. Encola un job al día (la marca vive en Redis, así que
    # los reinicios del deploy no la disparan de más).
    from src.nicho_pov_bof.services.backup_diario import bucle as backup_diario_bucle

    backup_stop = asyncio.Event()
    backup_task = asyncio.create_task(backup_diario_bucle(backup_stop))

    try:
        yield
    finally:
        backup_stop.set()
        try:
            await asyncio.wait_for(backup_task, timeout=5)
        except asyncio.TimeoutError:
            backup_task.cancel()
        calentador_stop.set()
        try:
            await asyncio.wait_for(calentador_task, timeout=5)
        except asyncio.TimeoutError:
            calentador_task.cancel()
        sweeper_stop.set()
        try:
            await asyncio.wait_for(sweeper_task, timeout=5)
        except asyncio.TimeoutError:
            sweeper_task.cancel()
        # Graceful shutdown — el SIGTERM handler en api/queue/queue_init
        # ya inició el drain de la cola. Aquí solo paramos el watcher de
        # editor-auto. La JobQueue ya está esperando a que sus workers
        # terminen el job actual; uvicorn no cierra el proceso hasta que
        # este `lifespan` retorna, así que el await join de la queue es
        # quien dicta el tiempo total de shutdown.
        logger.info("API shutting down — parando watcher auto-enqueue…")
        watcher_stop.set()
        try:
            await asyncio.wait_for(watcher_task, timeout=5)
        except asyncio.TimeoutError:
            logger.warning("watcher no paró en 5s, cancelando")
            watcher_task.cancel()

        # Bloqueamos hasta que TODOS los workers de la JobQueue terminen
        # su job actual. Sin timeout aquí: docker-compose tiene su propio
        # `stop_grace_period: 1800s` que actúa como hard limit. Si nuestro
        # proceso termina antes (queue ya vacía), docker arranca el nuevo
        # container inmediatamente.
        try:
            from src.api.dependencies import get_queue
            q = get_queue()
            n_run = q.n_running_jobs()
            if n_run > 0:
                logger.info(
                    "JobQueue: %d job(s) en ejecución — esperando a que "
                    "terminen antes de cerrar (graceful shutdown)…",
                    n_run,
                )
            q.start_draining()
            q.wait_for_drain()
            logger.info("JobQueue: todos los workers cerrados limpiamente.")
        except Exception as e:
            logger.warning("Graceful drain falló (no crítico): %s", e)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.title,
        version=settings.version,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        from src.tiktok_shop.repos.redis_base import get_shop_redis

        return {
            "status": "ok",
            "version": settings.version,
            "redis_configured": get_shop_redis().is_available(),
        }

    app.include_router(products_router)
    app.include_router(product_photo_file_router)
    app.include_router(users_router)
    app.include_router(voices_router)
    app.include_router(voices_sample_router)
    app.include_router(generations_router)
    app.include_router(generations_video_router)
    app.include_router(queue_router)
    app.include_router(queue_video_router)
    app.include_router(presidents_router)
    app.include_router(pronosticos_router)
    app.include_router(match_photos_router)
    app.include_router(match_photos_file_router)
    app.include_router(copyright_router)
    app.include_router(construccion_pov_router)
    app.include_router(subs_auto_router)
    app.include_router(subs_auto_frame_router)
    app.include_router(editor_auto_tools_router)
    app.include_router(editor_auto_users_router)
    app.include_router(editor_auto_enqueue_router)
    app.include_router(editor_auto_stickers_router)
    app.include_router(editor_auto_folders_router)
    app.include_router(editor_auto_sharing_router)
    app.include_router(editor_auto_plans_router)
    app.include_router(editor_auto_subscriptions_router)
    app.include_router(editor_auto_referrals_router)
    app.include_router(editor_auto_web_upload_router)
    app.include_router(tiktok_shop_discovery_router)
    app.include_router(tiktok_shop_radar_router)
    app.include_router(tiktok_shop_calendar_router)
    app.include_router(tiktok_shop_hooks_router)
    app.include_router(tiktok_shop_performance_router)
    app.include_router(tiktok_shop_presets_router)
    app.include_router(tiktok_shop_replicate_viral_router)
    app.include_router(tiktok_shop_shortcuts_router)
    app.include_router(tiktok_shop_watermark_remover_router)
    app.include_router(viralizacion_enqueue_router)
    app.include_router(nicho_pov_bof_folders_router)
    app.include_router(nicho_pov_bof_productos_router)
    app.include_router(nicho_ropa_prendas_router)
    app.include_router(nicho_ropa_personas_chicas_router)
    app.include_router(nicho_ropa_personas_prendas_router)
    app.include_router(nicho_bof_cine_router)
    app.include_router(nicho_gorras_router)
    app.include_router(cuenta_piloto_router)
    app.include_router(nicho_pov_bof_largo_router)
    app.include_router(nicho_creativos_router)
    app.include_router(nicho_carruseles_router)
    app.include_router(stats_router)
    app.include_router(dashboard_router)
    app.include_router(fonts_router)
    app.include_router(fonts_file_router)
    app.include_router(cuotas_router)
    app.include_router(auth_router)
    app.include_router(deploy_router)
    app.include_router(diagnostics_router)
    app.include_router(queue_ws_router)
    return app


app = create_app()


# ---------------------------------------------------------------------------
# Permisos por rol
# ---------------------------------------------------------------------------
# Los usuarios `pro` (Ana, Mauro) solo usan Tiktok Shop AI Pro. Esconder el
# menú en el frontend no basta: la URL se escribe a mano, así que se corta
# aquí. Se listan los prefijos PERMITIDOS, no los prohibidos — si mañana se
# añade un programa nuevo, queda fuera por defecto en vez de quedar abierto
# por olvido.
_PREFIJOS_PRO = (
    "/api/v1/viralizacion",
    "/api/v1/nicho-pov-bof",
    "/api/v1/nicho-ropa",
    "/api/v1/nicho-bof-cine",
    "/api/v1/nicho-gorras",
    "/api/v1/cuenta-piloto",
    "/api/v1/nicho-pov-bof-largo",
    "/api/v1/nicho-creativos",
    "/api/v1/queue",
    "/api/v1/auth",
    "/api/v1/health",
    "/ws/queue",
)


@app.middleware("http")
async def _programa_de_la_peticion(request, call_next):
    """Marca a qué programa cargarle lo que gaste esta petición.

    Las llamadas a las IA que se hacen desde la web (obtener textos, escribir
    guiones, emparejar los vídeos de una tanda) no pasan por la cola, así que
    no tienen `job` del que sacar el programa. Sin esto, su coste acababa en un
    cajón común y el panel no podía decir qué nicho lo gastó.
    """
    from src import cost_tracking

    testigo = cost_tracking.programa_web.set(
        cost_tracking.programa_de_ruta(request.url.path)
    )
    try:
        return await call_next(request)
    finally:
        cost_tracking.programa_web.reset(testigo)


@app.middleware("http")
async def _sin_cache_en_json(request, call_next):
    """Que ninguna respuesta de datos se quede pegada en la caché del cliente.

    Ninguna respuesta JSON llevaba `Cache-Control`, y sin cabecera el WebView de
    la APK puede reutilizar la anterior por su cuenta: el operador añadía un
    producto, la app volvía a pedir el listado y le devolvían el de antes, así
    que parecía que no se había guardado (estaba guardado).

    Solo se pone cuando NADIE la ha puesto ya: las fotos y los vídeos fijan la
    suya a propósito (un file ID de Drive es inmutable y se cachea un día) y no
    hay que pisarla.
    """
    respuesta = await call_next(request)
    if (
        request.url.path.startswith("/api/")
        and "cache-control" not in respuesta.headers
    ):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.middleware("http")
async def _permisos_por_rol(request, call_next):
    ruta = request.url.path
    if ruta.startswith("/api/") or ruta.startswith("/ws/"):
        quien = usuario_de_request(request) or ""
        if quien and not _users.es_admin(quien):
            if not any(ruta.startswith(p) for p in _PREFIJOS_PRO):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"error": "Tu usuario no tiene acceso a esta sección.",
                     "code": "forbidden", "details": {}},
                    status_code=403,
                )
    return await call_next(request)
