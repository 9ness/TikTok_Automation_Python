"""Publica el batch generado en Drive, una subcarpeta por ponente:
`NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/VIRALIZACION/<cuenta>_<fecha>/<ponente>/`.

Dos vías, en este orden:

1. **Mount FUSE** (`/mnt/drive` en el container, `~/gdrive` en el host). Es la
   vía por defecto: el container de la API **NO tiene el binario `rclone`**
   (solo está instalado en el host por `deploy/setup.sh`), así que shelear a
   rclone desde el runner fallaba siempre con `[Errno 2] No such file or
   directory: 'rclone'`. rclone sube el fichero a Drive en background gracias
   a `--vfs-cache-mode full`.
2. **`rclone copy`** como fallback, para entornos sin el mount.

Los errores se PROPAGAN: una subida fallida no puede acabar en un job verde.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from src.viralizacion import config

OnLog = Callable[[str], None]

# Nombre de subcarpeta ya resuelto por tanda, para no recalcular el sufijo en
# cada vídeo (ver `_mount_dir_for`).
_SUBDIR_CACHE: dict[tuple, str] = {}


def batch_subdir(ponente: str, fecha: str, n_videos: int) -> str:
    """Subcarpeta de una tanda: `32_pablo_2026-07-28`.

    Cada ponente va en su propia subcarpeta dentro de la carpeta elegida por
    el operador, con la cantidad delante para saber de un vistazo qué hay.
    """
    return f"{int(n_videos)}_{ponente}_{fecha}"


def _unique_subdir(base_dir: Path, nombre: str) -> str:
    """Añade sufijo `_2`, `_3`… si esa subcarpeta ya tiene vídeos.

    Generar dos tandas del mismo ponente, el mismo día y con la misma cantidad
    daba EXACTAMENTE el mismo nombre (`28_pablo_2026-07-28`), así que la
    segunda se mezclaba con la primera y los ficheros se pisaban entre sí.
    """
    destino = base_dir / nombre
    if not destino.is_dir() or not any(destino.glob("*.mp4")):
        return nombre
    n = 2
    while (base_dir / f"{nombre}_{n}").is_dir() and any(
        (base_dir / f"{nombre}_{n}").glob("*.mp4")
    ):
        n += 1
    return f"{nombre}_{n}"


def remote_dir_for(nombre_cuenta: str, fecha: str, ponente: str, n_videos: int = 0) -> str:
    carpeta = config.sanitize_account_name(nombre_cuenta)
    return (
        f"{config.DRIVE_REMOTE}{config.DRIVE_UPLOAD_ROOT}/"
        f"{carpeta}/{batch_subdir(ponente, fecha, n_videos)}/"
    )


def _mount_root() -> Path | None:
    """Raíz local del Drive montado por rclone, si está disponible."""
    candidates = [
        os.getenv("DRIVE_MOUNT_ROOT"),
        "/mnt/drive",
        str(Path.home() / "gdrive"),
    ]
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c)
    return None


def _mount_dir_for(
    nombre_cuenta: str, fecha: str, ponente: str, n_videos: int = 0
) -> Path | None:
    root = _mount_root()
    if root is None:
        return None
    carpeta = config.sanitize_account_name(nombre_cuenta)
    base = root / config.DRIVE_UPLOAD_ROOT / carpeta
    # Resuelto una sola vez por tanda y cacheado: si se recalculara en cada
    # `upload_file` el sufijo iría subiendo con cada vídeo y la tanda quedaría
    # repartida entre `_2`, `_3`, `_4`…
    clave = (str(base), ponente, fecha, int(n_videos))
    nombre = _SUBDIR_CACHE.get(clave)
    if nombre is None:
        nombre = _unique_subdir(base, batch_subdir(ponente, fecha, n_videos))
        _SUBDIR_CACHE[clave] = nombre
    return base / nombre


def list_carpetas() -> list[str]:
    """Carpetas ya creadas bajo VIRALIZACION, para ofrecerlas en la UI."""
    root = _mount_root()
    if root is None:
        return []
    base = root / config.DRIVE_UPLOAD_ROOT
    if not base.is_dir():
        return []
    try:
        return sorted(
            (d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=str.lower,
        )
    except OSError:
        return []


def _copy_into_mount(src: Path, dest_dir: Path, on_log: OnLog | None = None) -> None:
    """Copia atómica dentro del mount (`.part` + replace).

    Sin el temporal, rclone puede empezar a subir un MP4 a medio escribir.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    tmp = dest.with_name(dest.name + ".part")
    if on_log:
        on_log(f"[drive] {src.name} → {dest_dir}")
    shutil.copy2(src, tmp)
    tmp.replace(dest)


def _rclone_copy(src: str, remote_dir: str, on_log: OnLog | None = None) -> None:
    cmd = ["rclone", "copy", src, remote_dir, "-v"]
    if on_log:
        on_log("+ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if on_log:
        for line in (proc.stdout + proc.stderr).splitlines():
            on_log(f"[rclone] {line}")
    if proc.returncode != 0:
        raise RuntimeError(
            f"rclone copy falló para {src!r} → {remote_dir}: {(proc.stderr or '')[-500:]}"
        )


def upload_file(
    local_path: Path,
    nombre_cuenta: str,
    fecha: str,
    ponente: str,
    n_videos: int = 0,
    on_log: OnLog | None = None,
) -> str:
    """Publica un único MP4 en cuanto termina (no espera al batch entero)."""
    if not local_path.is_file():
        raise FileNotFoundError(str(local_path))

    mount_dir = _mount_dir_for(nombre_cuenta, fecha, ponente, n_videos)
    if mount_dir is not None:
        _copy_into_mount(local_path, mount_dir, on_log=on_log)
        return str(mount_dir)

    remote_dir = remote_dir_for(nombre_cuenta, fecha, ponente, n_videos)
    _rclone_copy(str(local_path), remote_dir, on_log=on_log)
    return remote_dir


def upload_batch(
    staging_root: Path,
    nombre_cuenta: str,
    fecha: str,
    ponentes: list[str],
    cantidad: dict[str, int] | None = None,
    on_log: OnLog | None = None,
) -> dict[str, str]:
    """Publica `staging_root/<ponente>/*.mp4` para cada ponente con ficheros.

    Solo sube MP4 — el staging contiene también scratch del renderer que no
    debe acabar en Drive. Devuelve `{ponente: destino}`.
    """
    results: dict[str, str] = {}

    for ponente in ponentes:
        local_dir = staging_root / ponente
        if not local_dir.is_dir():
            continue
        mp4s = sorted(local_dir.glob("*.mp4"))
        if not mp4s:
            continue

        n_videos = (cantidad or {}).get(ponente, len(mp4s))
        mount_dir = _mount_dir_for(nombre_cuenta, fecha, ponente, n_videos)
        if mount_dir is not None:
            for f in mp4s:
                dest = mount_dir / f.name
                # Ya publicado con el mismo tamaño → no reescribir.
                if dest.is_file() and dest.stat().st_size == f.stat().st_size:
                    continue
                _copy_into_mount(f, mount_dir, on_log=on_log)
            results[ponente] = str(mount_dir)
            continue

        remote_dir = remote_dir_for(nombre_cuenta, fecha, ponente, n_videos)
        # `--include *.mp4` para no arrastrar scratch del renderer.
        cmd = ["rclone", "copy", str(local_dir), remote_dir, "--include", "*.mp4", "-v"]
        if on_log:
            on_log("+ " + " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if on_log:
            for line in (proc.stdout + proc.stderr).splitlines():
                on_log(f"[rclone] {line}")
        if proc.returncode != 0:
            raise RuntimeError(
                f"rclone copy falló para '{ponente}' → {remote_dir}: {proc.stderr[-500:]}"
            )
        results[ponente] = remote_dir

    return results
