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
import re
import shutil
from pathlib import Path
from typing import Any

from src.editor_auto.config import (
    USER_FOLDERS,
    user_subfolder,
)


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
# Extensión del archivo de guión que acompaña a un vídeo. El cliente
# deposita `1.mp4` + `1.txt` en `entrada/`; el listado asocia ambos
# automáticamente y al encolar leemos el contenido del .txt como script
# si el flow del usuario usa `silence_cutter_scripted`.
SCRIPT_EXT = ".txt"
SCRIPT_MAX_BYTES = 200_000  # cap defensivo (~200KB) — un guion normal son <10KB


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


def _script_companion(dir_path: str, video_name: str) -> dict[str, Any] | None:
    """Si junto al vídeo existe `<stem>.txt`, devuelve `{filename, size_bytes,
    modified_at}` del .txt. Si no, `None`. La asociación es por stem
    insensible a mayúsculas para tolerar `Video.MP4` + `video.txt`."""
    stem = os.path.splitext(video_name)[0]
    candidate = stem + SCRIPT_EXT
    path = os.path.join(dir_path, candidate)
    if os.path.isfile(path):
        return {"filename": candidate, **_stat(path)}
    # Fallback case-insensitive: itera el dir si la primera ruta no existe.
    # Útil en filesystems case-sensitive (Linux) cuando el cliente sube con
    # otra capitalización.
    lower = (stem + SCRIPT_EXT).lower()
    try:
        for n in os.listdir(dir_path):
            if n.lower() == lower:
                p = os.path.join(dir_path, n)
                if os.path.isfile(p):
                    return {"filename": n, **_stat(p)}
    except OSError:
        pass
    return None


_DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def list_files(username: str, folder: str) -> list[dict[str, Any]]:
    """Lista los vídeos de una carpeta del usuario, ordenados por
    `modified_at` descendente. Cada vídeo lleva `script` (dict con
    `filename`+`size_bytes`+`modified_at`) si existe `<stem>.txt` al
    lado, o `None` en caso contrario. Los `.txt` NO aparecen como
    items separados — son metadatos del vídeo.

    Incluye también los vídeos dentro de SUBCARPETAS DE DÍA (el flujo
    web organiza entrada/salida por `YYYY-MM-DD/`): esos entran con
    `filename = "YYYY-MM-DD/archivo.mp4"` y campo `day`, para que el
    panel admin los VEA (antes los días salían a 0)."""
    dir_path = user_subfolder(username, folder)
    if not os.path.isdir(dir_path):
        return []
    files: list[dict[str, Any]] = []

    def _scan(scan_dir: str, prefix: str, day: str | None) -> None:
        for name in os.listdir(scan_dir):
            full = os.path.join(scan_dir, name)
            if day is None and os.path.isdir(full) and _DAY_DIR_RE.match(name):
                _scan(full, f"{name}/", name)  # un solo nivel de día
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in VIDEO_EXTS or not os.path.isfile(full):
                continue
            meta = _stat(full)
            files.append({
                "filename": f"{prefix}{name}",
                "folder": folder,
                "ext": ext,
                "day": day,
                "script": _script_companion(scan_dir, name),
                **meta,
            })

    try:
        _scan(dir_path, "", None)
    except OSError:
        pass
    files.sort(key=lambda f: f["modified_at"], reverse=True)
    return files


def read_script_companion(
    username: str, folder: str, video_filename: str,
) -> str | None:
    """Lee el contenido del .txt companion del vídeo. Devuelve `None` si
    no existe. Cap `SCRIPT_MAX_BYTES`. UTF-8 con replace para tolerar
    archivos guardados en latin-1."""
    base = _validate_filename(video_filename)
    dir_path = user_subfolder(username, folder)
    companion = _script_companion(dir_path, base)
    if not companion:
        return None
    path = os.path.join(dir_path, companion["filename"])
    try:
        with open(path, "rb") as f:
            data = f.read(SCRIPT_MAX_BYTES + 1)
    except OSError:
        return None
    if len(data) > SCRIPT_MAX_BYTES:
        # Demasiado grande — probablemente no es un guion, no lo usamos.
        # No es un error, simplemente lo ignoramos como "sin script".
        return None
    text = data.decode("utf-8", errors="replace").strip()
    return text or None


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
    Valida y comprueba existencia — lanza `FolderError` si no existe.

    Acepta también `YYYY-MM-DD/archivo.mp4` (subcarpeta de día del flujo
    web) — el prefijo de día se valida estricto contra el patrón de fecha,
    así que no abre path traversal."""
    day: str | None = None
    name = filename or ""
    if "/" in name:
        head, _, tail = name.partition("/")
        if _DAY_DIR_RE.match(head):
            day, name = head, tail
    base = _validate_filename(name)
    dir_path = user_subfolder(username, folder)
    if day:
        dir_path = os.path.join(dir_path, day)
    path = os.path.join(dir_path, base)
    if not os.path.isfile(path):
        raise FolderError(
            f"Archivo no encontrado en {folder}/: {filename}"
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
    *,
    move_companion: bool = True,
) -> dict[str, Any]:
    """Mueve `filename` de `src_folder` a `dst_folder` (ambos del mismo
    usuario). Si el destino ya tiene un archivo con ese nombre, renombra
    con sufijo `_2`, `_3`, … en lugar de pisar.

    Si existe el archivo de guion companion (`<stem>.txt`) Y
    `move_companion=True`, también lo mueve preservando la asociación
    (el companion adopta el nuevo stem si hubo deduplicación).

    Devuelve `{filename_new, src_folder, dst_folder, moved,
    companion_moved}`. `companion_moved` es el nombre nuevo del .txt si
    se movió, o `None`.
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
            "companion_moved": None,
        }
    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    final_name = _unique_name_in(dst_dir, base)
    dst_path = os.path.join(dst_dir, final_name)
    # `shutil.move` maneja cross-device (en algunos mounts FUSE de rclone
    # `os.rename` falla con EXDEV — necesitamos copy + delete).
    shutil.move(src_path, dst_path)

    # Mover companion .txt si existe y el flag lo permite. El companion
    # adopta el nuevo stem para preservar la asociación tras dedup
    # (si `1.mp4` se renombró a `1_2.mp4`, su .txt va como `1_2.txt`).
    companion_moved: str | None = None
    if move_companion:
        companion = _script_companion(src_dir, base)
        if companion:
            try:
                src_txt = os.path.join(src_dir, companion["filename"])
                new_stem = os.path.splitext(final_name)[0]
                new_txt_name = new_stem + SCRIPT_EXT
                # Dedup también el .txt por si por algún motivo ya existe.
                new_txt_name = _unique_name_in(dst_dir, new_txt_name)
                dst_txt = os.path.join(dst_dir, new_txt_name)
                shutil.move(src_txt, dst_txt)
                companion_moved = new_txt_name
            except OSError:
                # Si falla el companion no abortamos el move del vídeo —
                # el .txt quedará huérfano en src pero el video llegó OK.
                pass

    return {
        "filename_new": final_name,
        "src_folder": src_folder,
        "dst_folder": dst_folder,
        "moved": True,
        "companion_moved": companion_moved,
    }


def delete_file(
    username: str,
    folder: str,
    filename: str,
    *,
    delete_companion: bool = True,
) -> None:
    """Borra el archivo del filesystem. IRREVERSIBLE. Si existe el
    companion .txt y `delete_companion=True`, lo borra también."""
    base = _validate_filename(filename)
    dir_path = user_subfolder(username, folder)
    path = os.path.join(dir_path, base)
    if not os.path.isfile(path):
        raise FolderError(
            f"Archivo no encontrado en {folder}/: {base}"
        )
    os.remove(path)
    if delete_companion:
        companion = _script_companion(dir_path, base)
        if companion:
            try:
                os.remove(os.path.join(dir_path, companion["filename"]))
            except OSError:
                pass
