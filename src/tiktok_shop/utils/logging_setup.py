"""Logging estructurado para TikTok Shop.

Decisiones:
- Usa el módulo `logging` de stdlib (no loguru — Creator Reward usa print y
  no quiero introducir dependencia nueva). Los handlers se montan una sola
  vez via `get_logger()` (idempotente).
- Salida dual:
    * Consola (INFO+) — ya visible en la cola UI vía log_callback existente.
    * Archivo `logs/tiktok_shop_YYYY-MM-DD.log` (DEBUG+) con rotación diaria.
- Formato estructurado: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [logger.name] msg | ctx={key=value,...}`.
- Helper `log_with_context(level, msg, **ctx)` para inyectar `job_id`, `user`,
  `product`, `tier` etc. en una línea sin verbosidad de `extra={}`.
- NO toca el comportamiento de `log_callback` del runner (UI sigue igual).
  El logger es complementario: registra TAMBIÉN a archivo lo que ya pasa por
  callbacks, para post-mortem cuando la cola haya scrolleado.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


_LOGGERS_CONFIGURED: set[str] = set()
_DEFAULT_LOG_DIR = Path("logs")


def _build_handlers(log_dir: Path) -> list[logging.Handler]:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_path = log_dir / "tiktok_shop.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(file_path),
        when="midnight",
        backupCount=14,
        encoding="utf-8",
        delay=True,         # no abrir archivo hasta primer log
        utc=False,
    )
    file_handler.suffix = "%Y-%m-%d"  # → tiktok_shop.log.2026-05-07
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    return [file_handler, console]


def get_logger(name: str = "tiktok_shop") -> logging.Logger:
    """Devuelve un logger con file rotation + consola. Idempotente.

    Args:
        name: nombre del logger (`tiktok_shop`, `tiktok_shop.runner`, etc.).
    """
    logger = logging.getLogger(name)
    if name in _LOGGERS_CONFIGURED:
        return logger

    log_dir_env = os.getenv("TIKTOK_SHOP_LOG_DIR")
    log_dir = Path(log_dir_env) if log_dir_env else _DEFAULT_LOG_DIR

    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # evita duplicados si el root tiene handlers
    for h in _build_handlers(log_dir):
        logger.addHandler(h)

    _LOGGERS_CONFIGURED.add(name)
    return logger


def _format_context(ctx: dict[str, Any]) -> str:
    if not ctx:
        return ""
    parts = []
    for k, v in ctx.items():
        # Trunca valores largos (ej. prompts) para no llenar el log
        s = str(v)
        if len(s) > 200:
            s = s[:197] + "..."
        parts.append(f"{k}={s}")
    return " | ctx=" + ", ".join(parts)


def log_with_context(
    logger: logging.Logger | str, level: int, msg: str, **ctx: Any,
) -> None:
    """Loguea un mensaje con contexto plano (`key=value`).

    Args:
        logger: instancia o nombre — si es nombre, se obtiene via `get_logger`.
        level: `logging.INFO`, `logging.ERROR`, etc.
        msg: mensaje principal.
        **ctx: pares clave=valor para inyectar (job_id, user, product, tier...).
    """
    if isinstance(logger, str):
        logger = get_logger(logger)
    logger.log(level, f"{msg}{_format_context(ctx)}")


# Atajos comunes
def log_info(logger: logging.Logger | str, msg: str, **ctx: Any) -> None:
    log_with_context(logger, logging.INFO, msg, **ctx)


def log_warning(logger: logging.Logger | str, msg: str, **ctx: Any) -> None:
    log_with_context(logger, logging.WARNING, msg, **ctx)


def log_error(logger: logging.Logger | str, msg: str, **ctx: Any) -> None:
    log_with_context(logger, logging.ERROR, msg, **ctx)


def log_debug(logger: logging.Logger | str, msg: str, **ctx: Any) -> None:
    log_with_context(logger, logging.DEBUG, msg, **ctx)
