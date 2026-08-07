"""Nicho Creativos Pro (Programa 4 — módulo 13 del curso).

No monta vídeo: produce un CREATIVO publicitario (una imagen) por producto. Por
eso su pantalla es la del Nicho POV BOF sin la mitad de abajo — ni subir vídeo,
ni voz, ni marcar "Subido".

Lo que sí comparte, y a propósito, es TODO el catálogo: las mismas fuentes de
Drive (los dos de aleatorios y "Mis productos"), las mismas fotos, los mismos
textos extraídos y los MISMOS hashtags. Un producto es un producto: haberle
sacado el título en POV BOF vale aquí, y añadir un hashtag en un nicho lo añade
en todos (lo pidió el operador explícitamente).

Lo único propio es:
  - el prompt de imagen (`prompts/prompt_imagen.md`, del doc del curso
    "Nicho Carruseles/Creativos/Pront Creativos"),
  - el formato 3:4, que hay que recordar al copiarlo porque el generador no lo
    sabe y sale cuadrado,
  - y el progreso por carpeta, que es SUYO: haber hecho una carpeta en POV BOF
    no la deja hecha aquí.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_CREATIVOS_REDIS_PREFIX", "nicho_creativos:")

# Las MISMAS fuentes del Nicho POV BOF: mismo Drive, mismas carpetas, mismas
# fotos, incluida "Mis productos". Se importan para que añadir una fuente allí
# valga aquí sin tocar nada.
from src.nicho_pov_bof.config import SOURCES, es_fuente_propia, source_path  # noqa: E402,F401

# El creativo va en vertical 3:4 (no 9:16 como el vídeo, ni 1:1). El generador
# de imágenes no lo deduce del prompt, así que se enseña al lado del botón:
# copiarlo y olvidarse del formato es el error fácil de este nicho.
FORMATO = "3:4"


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def prompt_imagen() -> str:
    return (prompts_dir() / "prompt_imagen.md").read_text(encoding="utf-8").strip()
