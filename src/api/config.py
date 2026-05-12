"""Settings de la API FastAPI.

Lee de variables de entorno con defaults sensatos para desarrollo local.
"""

from __future__ import annotations

import os
from functools import lru_cache


class APISettings:
    """Configuración mínima de la API.

    NO usa pydantic-settings para no añadir otra dependencia. Variables:
        API_HOST            (default 0.0.0.0)
        API_PORT            (default 8000)
        API_KEY             (opcional — si está set, se requiere en header)
        API_CORS_ORIGINS    (csv — default localhost:3000,localhost:8501)
    """

    def __init__(self) -> None:
        self.host: str = os.getenv("API_HOST", "0.0.0.0")
        self.port: int = int(os.getenv("API_PORT", "8000"))
        self.api_key: str | None = os.getenv("API_KEY") or None
        raw = os.getenv(
            "API_CORS_ORIGINS",
            "http://localhost:3000,http://localhost:8501",
        )
        self.cors_origins: list[str] = [
            o.strip() for o in raw.split(",") if o.strip()
        ]
        self.title: str = "TikTok Automation API"
        self.version: str = "0.1.0"
        self.docs_url: str = "/api/docs"
        self.redoc_url: str = "/api/redoc"
        self.openapi_url: str = "/api/openapi.json"


@lru_cache(maxsize=1)
def get_settings() -> APISettings:
    return APISettings()
