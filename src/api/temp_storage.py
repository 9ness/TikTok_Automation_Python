"""Helpers para guardar/leer archivos temporales subidos por la API.

Reglas:
- Todo lo que el cliente sube vive bajo `<temp_root>/api_uploads/<subdir>/`.
- El cliente nunca ve paths absolutos — se le devuelve un path RELATIVO
  a `<temp_root>` (ej. `api_uploads/copyright/clean_in_<ts>.mp4`).
- Cuando el cliente reenvía ese path en `/enqueue`, validamos que tras
  resolverlo NO escapa de `<temp_root>` (anti path-traversal).
- Cleanup: archivos en `api_uploads/` con mtime > TTL se borran al
  startup de la API (lifespan handler).

`<temp_root>` se determina en este orden:
  1. `API_TEMP_ROOT` env var (override explícito).
  2. CFG["paths"]["temp_folder"] del config Streamlit (`./temp_work` por
     defecto). Compartir con Streamlit es deseable: los runners ya leen
     de ahí.
  3. `./temp_work` (fallback).
"""

from __future__ import annotations

import os
import time
from pathlib import Path


DEFAULT_TTL_SECONDS = 24 * 3600  # 24h
API_UPLOADS_SUBDIR = "api_uploads"


def temp_root() -> Path:
    """Devuelve la raíz absoluta del directorio temporal de la API.

    Crea la carpeta y `api_uploads/` si no existen. Idempotente.
    """
    explicit = os.getenv("API_TEMP_ROOT")
    if explicit:
        root = Path(explicit).resolve()
    else:
        try:
            from src.utils import load_config

            cfg = load_config()
            root = Path(cfg["paths"]["temp_folder"]).resolve()
        except Exception:
            root = Path("./temp_work").resolve()

    root.mkdir(parents=True, exist_ok=True)
    (root / API_UPLOADS_SUBDIR).mkdir(parents=True, exist_ok=True)
    return root


def upload_subdir(name: str) -> Path:
    """Crea (si hace falta) y devuelve `<temp_root>/api_uploads/<name>/`."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"Subdir inválido: '{name}'")
    sub = temp_root() / API_UPLOADS_SUBDIR / name
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def to_relative(path: Path) -> str:
    """Convierte un path absoluto a path relativo a `temp_root` con
    separadores POSIX. Lanza ValueError si el path no está dentro."""
    rel = path.resolve().relative_to(temp_root())
    return rel.as_posix()


def resolve_relative(rel_path: str) -> Path:
    """Convierte un path RELATIVO a temp_root en absoluto, validando
    que no escapa del directorio (anti path-traversal).

    Acepta separadores POSIX (`/`) o Windows (`\\`).
    Lanza `ValueError` si:
      - El path es absoluto
      - Tras resolverlo cae fuera de `<temp_root>`
      - El path es vacío
    """
    if not rel_path:
        raise ValueError("path relativo vacío")
    candidate = Path(rel_path)
    if candidate.is_absolute():
        raise ValueError(f"path relativo no puede ser absoluto: '{rel_path}'")

    root = temp_root()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"path '{rel_path}' escapa del directorio temporal."
        )
    return resolved


def cleanup_expired(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> tuple[int, int]:
    """Borra archivos bajo `<temp_root>/api_uploads/**` cuyo mtime esté
    fuera del TTL. Devuelve `(num_files_borrados, bytes_liberados)`.

    Solo afecta a `api_uploads/` — NO toca otros archivos en `temp_root`
    (los que pone el pipeline durante la generación).
    """
    cutoff = time.time() - ttl_seconds
    uploads = temp_root() / API_UPLOADS_SUBDIR
    if not uploads.exists():
        return 0, 0

    removed = 0
    bytes_freed = 0
    for path in uploads.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            try:
                bytes_freed += stat.st_size
                path.unlink()
                removed += 1
            except OSError:
                pass

    # Limpiar directorios vacíos (sin descender más de 2 niveles)
    for sub in uploads.iterdir():
        if sub.is_dir():
            try:
                next(sub.iterdir())
            except StopIteration:
                try:
                    sub.rmdir()
                except OSError:
                    pass

    return removed, bytes_freed
