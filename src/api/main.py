"""Punto de entrada FastAPI.

Arrancar en local con:
    uvicorn src.api.main:app --reload --port 8000
"""

from __future__ import annotations

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
    construccion_pov_router,
    deploy_router,
    copyright_router,
    dashboard_router,
    diagnostics_router,
    editor_auto_enqueue_router,
    editor_auto_folders_router,
    editor_auto_sharing_router,
    editor_auto_stickers_router,
    editor_auto_tools_router,
    editor_auto_users_router,
    fonts_file_router,
    fonts_router,
    generations_router,
    generations_video_router,
    presidents_router,
    product_photo_file_router,
    products_router,
    pronosticos_router,
    queue_router,
    queue_video_router,
    stats_router,
    subs_auto_frame_router,
    subs_auto_router,
    users_router,
    voices_router,
    voices_sample_router,
)
from src.api.websockets import queue_ws_router


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

    yield
    logger.info("API shutting down")


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
    app.include_router(stats_router)
    app.include_router(dashboard_router)
    app.include_router(fonts_router)
    app.include_router(fonts_file_router)
    app.include_router(auth_router)
    app.include_router(deploy_router)
    app.include_router(diagnostics_router)
    app.include_router(queue_ws_router)
    return app


app = create_app()
