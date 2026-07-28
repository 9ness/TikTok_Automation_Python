"""Config del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

FASE 1: solo lectura del Drive compartido "Productos España" + tracking de
carpetas ya completadas. Todavía NO genera vídeos.

Decisiones:
- El Drive de productos está COMPARTIDO CONMIGO (shared-with-me), no vive en
  "Mi unidad" → NO se ve por el mount FUSE de `gdrive-mount.service`. Hay que
  leerlo por CLI con `--drive-shared-with-me` (ver `services/drive_client.py`).
- "Productos España" es SOLO LECTURA. El pipeline nunca escribe ahí.
- El estado "completada" vive en Redis (prefijo `nicho_pov_bof:`), NO en Drive
  — así no ensuciamos un Drive de terceros.
- Las fotos tienen NOMBRES DUPLICADOS reales dentro de una misma carpeta
  (`2.PNG` dos veces, `10.PNG` vs `10.png`). Por eso el identificador canónico
  de una foto es su **file ID de Drive**, nunca su nombre.
- Las salidas futuras (fase 2) irán bajo TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/,
  mismo patrón que VIRALIZACION.
"""

from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# Drive de origen (SOLO LECTURA)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"

# Carpeta raíz compartida. Ojo: lleva tilde, es el nombre real en Drive.
SHARED_ROOT = "Productos España"

# Flag de backend rclone que convierte "Compartido conmigo" en la raíz del
# remote. Sin esto la carpeta no existe para rclone.
SHARED_WITH_ME_FLAG = "--drive-shared-with-me"

# Fuentes de producto (las 2 que pidió el usuario). El `slug` es lo que viaja
# por la API; el `folder` es el nombre literal en Drive.
SOURCES: dict[str, dict[str, str]] = {
    "aleatorios_1": {
        "label": "1 Prod Aleatorios",
        "folder": "1 Prod Aleatorios",
    },
    "aleatorios_2": {
        "label": "2 Prod Aleatorios 2",
        "folder": "2 Prod Aleatorios 2",
    },
}


def source_path(source: str) -> str:
    """Path rclone completo de una fuente. Lanza si el slug no existe."""
    meta = SOURCES.get(source)
    if not meta:
        raise ValueError(
            f"Fuente desconocida: {source!r}. Válidas: {sorted(SOURCES)}"
        )
    return f"{DRIVE_REMOTE}{SHARED_ROOT}/{meta['folder']}"


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def is_image(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in IMAGE_EXTS


def natural_sort_key(name: str) -> tuple:
    """Orden natural: 1, 2, 10 (no 1, 10, 2).

    Las carpetas se llaman "1 Pront Flow", "10 Pront Flow"... y las fotos
    "1.PNG", "10.PNG". Un sort lexicográfico las descoloca.
    """
    parts = re.split(r"(\d+)", name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


# ---------------------------------------------------------------------------
# Caché de listados
# ---------------------------------------------------------------------------
# `rclone lsjson` sobre el Drive compartido tarda segundos. Cacheamos en
# memoria del proceso API para que la UI no se arrastre. Refrescable a mano
# desde el endpoint con `?refresh=true`.
LISTING_TTL_S = float(os.getenv("NICHO_POV_BOF_LISTING_TTL_S") or 300)

# Timeout de cada invocación de rclone.
RCLONE_TIMEOUT_S = float(os.getenv("NICHO_POV_BOF_RCLONE_TIMEOUT_S") or 120)


def rclone_config_path() -> str:
    """Ruta del rclone.conf a usar, o "" para el default de rclone.

    En el container la API corre como uid 999 y el `rclone.conf` canónico del
    host es 600 del uid 1000 → ilegible. El operador deja una copia legible en
    `secrets/rclone.conf`, que el compose monta read-only en `/app/secrets`.
    """
    explicit = os.getenv("NICHO_POV_BOF_RCLONE_CONFIG")
    if explicit:
        return explicit
    if os.path.isfile("/app/secrets/rclone.conf"):
        return "/app/secrets/rclone.conf"
    return ""


def photo_cache_dir() -> str:
    """Dir local donde se cachean las fotos descargadas por file ID.

    Vive bajo API_TEMP_ROOT (volumen persistido del container) para no
    re-descargar la misma foto en cada scroll de la UI.
    """
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "nicho_pov_bof_photos")


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
def redis_prefix() -> str:
    """Prefijo Redis del módulo. Default `nicho_pov_bof:`. Override por env."""
    return os.getenv("NICHO_POV_BOF_REDIS_PREFIX") or "nicho_pov_bof:"


# ---------------------------------------------------------------------------
# Salida (FASE 2 — todavía sin usar)
# ---------------------------------------------------------------------------
# Mismo patrón que VIRALIZACION: todo cuelga de TIKTOK_SHOP_AI_PRO.
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF"
