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
import shutil

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


_SECRETS_RCLONE_CONF = "/app/secrets/rclone.conf"


def _copia_escribible(origen: str) -> str:
    """Copia de `origen` en un sitio donde rclone PUEDA escribir.

    El token de Google caduca cada hora y rclone lo renueva y lo reescribe en
    el config. Con el config montado read-only no puede: reintenta el guardado
    DIEZ veces con backoff antes de rendirse, y eso son ~5s tirados en CADA
    invocación (una lista de carpetas pasaba de 1,4s en el host a 6-9s aquí).
    Peor aún, al no persistirlo vuelve a pedir un token nuevo la próxima vez.

    Se copia a un sitio escribible y se re-siembra si el operador actualiza el
    original. rclone se encarga solo de mantener el token al día ahí.
    """
    destino_dir = os.getenv("API_TEMP_ROOT") or "temp_work"
    destino = os.path.join(destino_dir, "rclone_nicho.conf")
    try:
        if (
            not os.path.isfile(destino)
            or os.path.getmtime(origen) > os.path.getmtime(destino)
        ):
            os.makedirs(destino_dir, exist_ok=True)
            shutil.copyfile(origen, destino)
            os.chmod(destino, 0o600)
        return destino
    except OSError:
        # Sin sitio escribible se sigue con el original: lento, pero funciona.
        return origen


def rclone_config_path() -> str:
    """Ruta del rclone.conf a usar, o "" para el default de rclone.

    En el container la API corre como uid 999 y el `rclone.conf` canónico del
    host es 600 del uid 1000 → ilegible. El operador deja una copia legible en
    `secrets/rclone.conf`, que el compose monta read-only en `/app/secrets`.
    """
    explicit = os.getenv("NICHO_POV_BOF_RCLONE_CONFIG")
    if explicit:
        return explicit
    if os.path.isfile(_SECRETS_RCLONE_CONF):
        return _copia_escribible(_SECRETS_RCLONE_CONF)
    return ""


# Cuántos días se conserva la copia local de un vídeo ya publicado.
VIDEO_CACHE_DIAS = 10


def video_cache_dir() -> str:
    """Dir local con una copia de los vídeos ya montados.

    El vídeo bueno vive en Drive, pero servir la descarga DESDE el mount es
    lentísimo la primera vez: si el fichero no está en la caché de rclone,
    hay que bajarlo entero de Google antes del primer byte — medido, 36
    segundos para 17 MB. El operador lo notaba al descargar varios seguidos.

    Con una copia local la descarga es instantánea. Se limpia sola pasados
    `VIDEO_CACHE_DIAS` para que no engorde el disco del VPS.
    """
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "nicho_pov_bof_videos")


def video_cache_path(folder: str, producto: str, usuario: str = "") -> str:
    """Ruta de la copia local de un vídeo. Nombre plano y saneado.

    Lleva el usuario porque cada uno monta SU vídeo del mismo producto: sin
    esto, Ana se descargaría el de ness.
    """
    quien = usuario or "ness"
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{quien}__{producto}__{folder}")
    return os.path.join(video_cache_dir(), f"{seguro}.mp4")


def limpiar_video_cache(dias: int = VIDEO_CACHE_DIAS) -> int:
    """Borra copias locales viejas. Devuelve cuántas."""
    import time

    carpeta = video_cache_dir()
    if not os.path.isdir(carpeta):
        return 0
    limite = time.time() - dias * 86400
    borrados = 0
    for nombre in os.listdir(carpeta):
        ruta = os.path.join(carpeta, nombre)
        try:
            if os.path.isfile(ruta) and os.path.getmtime(ruta) < limite:
                os.unlink(ruta)
                borrados += 1
        except OSError:
            continue
    return borrados


def photo_cache_dir() -> str:
    """Dir local donde se cachean las fotos descargadas por file ID.

    Vive bajo API_TEMP_ROOT (volumen persistido del container) para no
    re-descargar la misma foto en cada scroll de la UI.
    """
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "nicho_pov_bof_photos")


# ---------------------------------------------------------------------------
# Vídeo (fase 2)
# ---------------------------------------------------------------------------
TARGET_W, TARGET_H, TARGET_FPS = 1080, 1920, 30

# Zonas seguras de TikTok — mismas que el resto del proyecto
# (`src/subtitles.py`): fuera de aquí la UI de TikTok tapa el texto.
SAFE_X = (0.05, 0.78)
SAFE_Y = (0.15, 0.75)

# Bloque de texto: gancho arriba, título del producto en medio, CTA debajo.
TEXT_BLOCK_Y = 0.17          # centro del bloque, dentro de la zona segura
# Jerarquía clara: el gancho manda, el CTA le sigue y el nombre del producto
# va notablemente más pequeño. Antes los tres rondaban 60px y el bloque salía
# plano ("parece muy básico", dixit el operador).
HOOK_FONT_SIZE = 72
CTA_FONT_SIZE = 60
TITLE_FONT_SIZE = 46

# Flecha .mov: abajo a la izquierda, justo encima de la etiqueta naranja de la
# tienda que pinta TikTok. Mismos valores que `ready_video.py`.
ARROW_CX, ARROW_CY = 0.22, 0.82
ARROW_SCALE_W = 0.16
# La flecha entra este margen ANTES de que se diga la palabra clave.
ARROW_LEAD_S = 1.0
ARROW_DURATION_S = 3.5

# Palabra que dispara la flecha. Las 5 frases locutadas dicen todas
# "carrito naranja", así que basta con "carrito"; el resto son variantes por
# si en el futuro se graban frases nuevas.
ARROW_KEYWORDS = ("carrito", "naranja", "cupones", "cupón", "enlace", "tienda")

# Duración objetivo del vídeo. Los audios rondan 12-14s, así que lo normal es
# que el audio sea MÁS LARGO y haya que alargar el vídeo.
VIDEO_TARGET_S = 10.0
# Si el audio es más largo, el vídeo se alarga rebobinando su tramo final
# (ida y vuelta). No se ralentiza: deformaría el gesto de la mano.
REVERSE_TAIL_MAX_S = 4.0


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
