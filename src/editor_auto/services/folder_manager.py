"""Gestión de las 4 carpetas del usuario Editor Auto.

Carpetas:
    entrada/       — cliente deposita vídeos crudos aquí
    cola/          — vídeo bloqueado mientras procesa (admin no toca)
    recuperacion/  — originales tras procesado OK (por si re-editar)
    salida/        — MP4 final que el cliente descarga

Operaciones soportadas (todas con validación anti-path-traversal):
    - `list_files(user, folder)` → metadatos de los archivos
    - `count_files(user)` → conteos por carpeta (para badges UI)
    - `move_file(user, from, to, filename)` → renombra entre carpetas
    - `delete_file(user, folder, filename)` → borra (irreversible)
    - `resolve_file(user, folder, filename)` → path absoluto para servir

Reglas:
    - `filename` debe ser un basename limpio (sin `..`, sin separadores).
    - Solo se aceptan extensiones de la whitelist `VIDEO_EXTS`.
    - `move_file` con destino que ya existe → renombra con sufijo `_2`,
      `_3`, … para no machacar trabajo previo.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from src.editor_auto.config import (
    USER_FOLDERS,
    user_subfolder,
)


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class FolderError(Exception):
    """Error de validación / operación de carpetas. Se traduce a HTTP
    400/404 en el router."""


def _validate_filename(filename: str) -> str:
    """Acepta solo basenames limpios. Devuelve el basename validado.

    Rechaza:
      - rutas absolutas o relativas (`..`, `/`, `\\`)
      - nombres vacíos o solo espacios
      - extensiones fuera de `VIDEO_EXTS`
    """
    if not filename or not filename.strip():
        raise FolderError("Filename vacío")
    base = os.path.basename(filename)
    if base != filename or ".." in base or "/" in base or "\\" in base:
        raise FolderError(f"Filename inválido (path traversal): {filename!r}")
    ext = os.path.splitext(base)[1].lower()
    if ext not in VIDEO_EXTS:
        raise FolderError(
            f"Extensión no permitida: {ext!r}. Solo: {sorted(VIDEO_EXTS)}"
        )
    return base


def _stat(path: str) -> dict[str, Any]:
    """Metadatos de un archivo: size, mtime. Tolerante a errores I/O."""
    try:
        st = os.stat(path)
        return {
            "size_bytes": st.st_size,
            "modified_at": int(st.st_mtime),
        }
    except OSError:
        return {"size_bytes": 0, "modified_at": 0}


def list_files(username: str, folder: str) -> list[dict[str, Any]]:
    """Lista los vídeos de una carpeta del usuario, ordenados por
    `modified_at` descendente (más reciente arriba)."""
    dir_path = user_subfolder(username, folder)
    if not os.path.isdir(dir_path):
        return []
    files: list[dict[str, Any]] = []
    for name in os.listdir(dir_path):
        ext = os.path.splitext(name)[1].lower()
        if ext not in VIDEO_EXTS:
            continue
        full = os.path.join(dir_path, name)
        if not os.path.isfile(full):
            continue
        meta = _stat(full)
        files.append({
            "filename": name,
            "folder": folder,
            "ext": ext,
            **meta,
        })
    files.sort(key=lambda f: f["modified_at"], reverse=True)
    return files


def count_files(username: str) -> dict[str, int]:
    """Devuelve `{entrada: N, cola: N, recuperacion: N, salida: N}`. Si
    una carpeta no existe (usuario nuevo) cuenta 0."""
    counts: dict[str, int] = {}
    for folder in USER_FOLDERS:
        try:
            counts[folder] = len(list_files(username, folder))
        except ValueError:
            counts[folder] = 0
    return counts


def resolve_file(username: str, folder: str, filename: str) -> str:
    """Path absoluto al archivo (para servirlo o pasarlo al pipeline).
    Valida y comprueba existencia — lanza `FolderError` si no existe."""
    base = _validate_filename(filename)
    dir_path = user_subfolder(username, folder)
    path = os.path.join(dir_path, base)
    if not os.path.isfile(path):
        raise FolderError(
            f"Archivo no encontrado en {folder}/: {base}"
        )
    return path


def _unique_name_in(folder_path: str, base: str) -> str:
    """Si `base` ya existe en `folder_path`, añade sufijo `_2`, `_3`…
    Devuelve el basename libre. Evita pisar trabajos previos al mover."""
    if not os.path.exists(os.path.join(folder_path, base)):
        return base
    stem, ext = os.path.splitext(base)
    i = 2
    while True:
        candidate = f"{stem}_{i}{ext}"
        if not os.path.exists(os.path.join(folder_path, candidate)):
            return candidate
        i += 1


def move_file(
    username: str,
    src_folder: str,
    dst_folder: str,
    filename: str,
) -> dict[str, Any]:
    """Mueve `filename` de `src_folder` a `dst_folder` (ambos del mismo
    usuario). Si el destino ya tiene un archivo con ese nombre, renombra
    con sufijo `_2`, `_3`, … en lugar de pisar.

    Devuelve `{filename_new, src_folder, dst_folder}` con el nombre
    final tras la deduplicación.

    Mover a la misma carpeta de origen es no-op (devuelve el archivo tal
    cual). Si src y dst son la misma + filename existe → devuelve idem.
    """
    base = _validate_filename(filename)
    src_dir = user_subfolder(username, src_folder)
    dst_dir = user_subfolder(username, dst_folder)
    src_path = os.path.join(src_dir, base)
    if not os.path.isfile(src_path):
        raise FolderError(
            f"Archivo no encontrado en {src_folder}/: {base}"
        )
    if src_folder == dst_folder:
        return {
            "filename_new": base,
            "src_folder": src_folder,
            "dst_folder": dst_folder,
            "moved": False,
        }
    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    final_name = _unique_name_in(dst_dir, base)
    dst_path = os.path.join(dst_dir, final_name)
    # `shutil.move` maneja cross-device (en algunos mounts FUSE de rclone
    # `os.rename` falla con EXDEV — necesitamos copy + delete).
    shutil.move(src_path, dst_path)
    return {
        "filename_new": final_name,
        "src_folder": src_folder,
        "dst_folder": dst_folder,
        "moved": True,
    }


def delete_file(username: str, folder: str, filename: str) -> None:
    """Borra el archivo del filesystem. IRREVERSIBLE — la UI pide
    confirmación antes de llamar."""
    base = _validate_filename(filename)
    dir_path = user_subfolder(username, folder)
    path = os.path.join(dir_path, base)
    if not os.path.isfile(path):
        raise FolderError(
            f"Archivo no encontrado en {folder}/: {base}"
        )
    os.remove(path)
