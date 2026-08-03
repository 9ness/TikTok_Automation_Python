"""Nicho Ropa Sin Personas (Programa 4 — módulo 8 del curso).

Qué lo diferencia del Nicho POV BOF, que es el que más se le parece:

- El Drive de fotos se comparte **por enlace**, no aparece en "Compartido
  conmigo". Se lee con `--drive-root-folder-id`, que convierte esa carpeta en
  la raíz del remote.
- Es UNA sola carpeta con todos los productos dentro, no una fuente con
  carpetas de producto. De momento solo hay camisetas.
- El vídeo final **no lleva texto quemado** — ni gancho, ni título, ni CTA, ni
  flecha. El producto se enseña y ya. Y va **mudo por defecto**: el operador
  le pone la música al publicar.

Lo que SÍ se reutiliza del Nicho POV BOF, porque es idéntico y funciona:
`photo_pairing` (emparejar foto limpia + captura con título, incluidos los
nombres duplicados) y la descarga de fotos por file ID.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Drive de origen (SOLO LECTURA)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"

# La carpeta compartida por enlace. Con `--drive-root-folder-id` rclone la trata
# como la raíz, así que los paths van vacíos ("gdrive:").
#
# https://drive.google.com/drive/folders/10jSRauIlUVFXo3Dr6RCi8iO1gIY2TDIL
CARPETA_DEFECTO = "10jSRauIlUVFXo3Dr6RCi8iO1gIY2TDIL"

# Nombre con el que se enseña esa carpeta y con el que se guarda su progreso.
# El identificador real es el ID; esto es solo etiqueta.
CARPETA_LABEL = "Camisetas"


def carpeta_id() -> str:
    """ID de la carpeta de productos. Override por `.env` sin desplegar."""
    return (os.getenv("NICHO_ROPA_FOLDER_ID") or CARPETA_DEFECTO).strip()


def redis_prefix() -> str:
    return os.getenv("NICHO_ROPA_REDIS_PREFIX", "nicho_ropa:")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


# El prompt de vídeo tiene dos versiones y la diferencia es UNA frase: la de la
# mano acariciando la ropa. Se guarda una sola vez y la versión sin manos es
# ese texto menos esa línea, para que no puedan quedar desincronizados.
LINEA_MANOS = "Una mano aparece en escena y acaricia la ropa."


def prompt_video(con_manos: bool) -> str:
    texto = (prompts_dir() / "prompt_video.md").read_text(encoding="utf-8").strip()
    if con_manos:
        return texto
    return " ".join(texto.replace(LINEA_MANOS, "").split())


def prompt_imagen() -> str:
    return (prompts_dir() / "prompt_imagen.md").read_text(encoding="utf-8").strip()
