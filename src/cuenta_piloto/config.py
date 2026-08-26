"""Cuenta Piloto (Programa 4 — Tiktok Shop AI Pro).

Vídeos ORGÁNICOS: la imagen no la genera ninguna IA, la graba el operador o
viene del propio vendedor. Lo único de IA es la voz. La edición, en cambio, es
la MISMA del Nicho POV BOF (gancho + título + CTA + flecha + voz), así que el
montaje se reutiliza tal cual.

Tres cosas lo separan de todos los demás nichos del programa:

1. **El producto nace de una subida, no de Drive.** Es el primer nicho en el
   que las dos fotos —la limpia y la de la ficha— las sube el operador. No hay
   `drive_client`, ni carpetas que recorrer, ni emparejado que adivinar: el
   operador dice cuál es cuál.
2. **Es por usuario.** Cada uno tiene su propia lista; los productos de uno no
   le aparecen a otro. La cuenta piloto es de quien la lleva.
3. **VARIOS vídeos por producto.** En el resto de nichos un producto tiene un
   `video_path` y punto. Aquí se prueban varios ángulos del mismo producto,
   así que el estado guarda una LISTA y subir otro vídeo nunca pisa el
   anterior.

Las fotos NO pueden vivir en `api_uploads/`: ese árbol se purga cada 24h al
arrancar la API (`temp_storage.cleanup_expired`) y el producto se quedaría sin
foto a la mañana siguiente. Van al Drive montado, como los vídeos.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("CUENTA_PILOTO_REDIS_PREFIX", "cuenta_piloto:")

# Ruta COMPLETA desde la raíz del mount (el mount empieza en "Mi unidad", no
# dentro de NEBULABS), igual que `DRIVE_UPLOAD_ROOT` del resto del programa.
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Cuenta_Piloto"

# Formatos aceptados en la subida.
FOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}

# Una captura de móvil no llega ni de lejos; el tope evita que un vídeo colado
# por error acabe subiéndose entero a Gemini.
MAX_FOTO_BYTES = 12 * 1024 * 1024

SEXOS = ("hombre", "mujer")


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def prompt_live() -> str:
    """El prompt del LIVE, tal cual se copia (ver `prompts/live.md`)."""
    from src.nicho_pov_bof.config import limpiar_prompt

    return limpiar_prompt((prompts_dir() / "live.md").read_text(encoding="utf-8"))


def _raiz_usuario(usuario: str) -> Path:
    """Carpeta persistente del usuario. Al Drive montado; si no hay mount
    (dev local), a `API_TEMP_ROOT` —pero FUERA de `api_uploads/`, que se
    purga sola."""
    from src.nicho_pov_bof.services.audio_bank import mount_root

    quien = _slug_usuario(usuario)
    raiz = mount_root()
    if raiz:
        return raiz / DRIVE_UPLOAD_ROOT / quien
    return Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "cuenta_piloto" / quien


def _slug_usuario(usuario: str) -> str:
    """Nombre de carpeta seguro. Vacío = `ness`, el usuario histórico."""
    import re

    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", (usuario or "").strip())
    return limpio or "ness"


def fotos_dir(usuario: str, producto: str = "") -> Path:
    destino = _raiz_usuario(usuario) / "fotos"
    if producto:
        destino = destino / _slug_usuario(producto)
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def videos_dir(usuario: str, producto: str = "") -> Path:
    destino = _raiz_usuario(usuario) / "videos"
    if producto:
        destino = destino / _slug_usuario(producto)
    destino.mkdir(parents=True, exist_ok=True)
    return destino
