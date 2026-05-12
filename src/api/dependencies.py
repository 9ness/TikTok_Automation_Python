"""Dependencias FastAPI — DI para repos + auth.

Las funciones `get_*_repo` son simples: cada request crea un repo nuevo
apuntando al mismo `ShopRedis` singleton subyacente. Esto permite a los
tests inyectar `FakeRedis` con `app.dependency_overrides`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header

from src.api.config import APISettings, get_settings
from src.api.exceptions import UnauthorizedError
from src.queue.manager import JobQueue
from src.tiktok_shop.repos import (
    GenerationRepo,
    ProductRepo,
    UserRepo,
    VoiceRepo,
)
from src.tiktok_shop.repos.redis_base import ShopRedis, get_shop_redis


def get_redis() -> ShopRedis:
    return get_shop_redis()


# ---------------------------------------------------------------------------
# Queue singleton (compartido entre requests)
# ---------------------------------------------------------------------------
_API_QUEUE: JobQueue | None = None


def get_queue() -> JobQueue:
    """Devuelve un JobQueue singleton para la API (separado del de Streamlit
    para no entrar en conflicto con `@st.cache_resource`).

    Persistencia en `<cwd>/temp_work/queue_state.json` (mismo path que
    Streamlit — comparten estado), pero el dispatcher se registra una vez
    por proceso. En tests inyectamos un `FakeJobQueue` con
    `app.dependency_overrides`, así que esta función no se ejecuta.
    """
    global _API_QUEUE
    if _API_QUEUE is None:
        persist_dir = os.path.abspath(
            os.getenv("API_QUEUE_PERSIST_DIR") or os.path.join(os.getcwd(), "temp_work")
        )
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _API_QUEUE = JobQueue(persist_dir)
        from src.queue.runners import dispatch_job
        _API_QUEUE.set_dispatcher(dispatch_job)
    return _API_QUEUE


def get_product_repo(redis: Annotated[ShopRedis, Depends(get_redis)]) -> ProductRepo:
    return ProductRepo(redis)


def get_user_repo(redis: Annotated[ShopRedis, Depends(get_redis)]) -> UserRepo:
    return UserRepo(redis)


def get_voice_repo(redis: Annotated[ShopRedis, Depends(get_redis)]) -> VoiceRepo:
    return VoiceRepo(redis)


def get_generation_repo(redis: Annotated[ShopRedis, Depends(get_redis)]) -> GenerationRepo:
    return GenerationRepo(redis)


def get_current_user(
    settings: Annotated[APISettings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Auth simple por header `X-API-Key`.

    - Si `API_KEY` no está definida en el entorno → no se exige (modo dev).
    - Si está definida → header obligatorio y debe coincidir.

    Devuelve un identificador de "usuario" trivial (`api-key-user`). Cuando
    haya multi-tenant lo cambiamos por algo real.
    """
    if not settings.api_key:
        return "anonymous"
    if not x_api_key or x_api_key != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")
    return "api-key-user"
