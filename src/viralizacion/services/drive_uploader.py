"""Sube el batch generado a Drive vía rclone, una subcarpeta por ponente:
`gdrive:VIRALIZACION/<cuenta>_<fecha>/<ponente>/`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from src.viralizacion import config

OnLog = Callable[[str], None]


def upload_batch(
    staging_root: Path,
    nombre_cuenta: str,
    fecha: str,
    ponentes: list[str],
    on_log: OnLog | None = None,
) -> dict[str, str]:
    """Copia `staging_root/<ponente>/*.mp4` a
    `gdrive:VIRALIZACION/<cuenta_saneada>_<fecha>/<ponente>/` para cada
    ponente con ficheros. Devuelve `{ponente: remote_dir}`."""
    account_safe = config.sanitize_account_name(nombre_cuenta)
    remote_base = f"{config.DRIVE_REMOTE}{config.DRIVE_UPLOAD_ROOT}/{account_safe}_{fecha}"
    results: dict[str, str] = {}

    for ponente in ponentes:
        local_dir = staging_root / ponente
        if not local_dir.is_dir() or not any(local_dir.glob("*.mp4")):
            continue
        remote_dir = f"{remote_base}/{ponente}/"
        cmd = ["rclone", "copy", str(local_dir), remote_dir, "-v"]
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
