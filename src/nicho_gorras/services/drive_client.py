"""Lectura de la carpeta de productos, compartida POR ENLACE.

La diferencia con el Nicho POV BOF: aquella carpeta está en "Compartido
conmigo" y se lee con `--drive-shared-with-me`; esta solo se comparte por
enlace, así que no aparece ahí. Se lee con `--drive-root-folder-id`, que hace
que rclone trate esa carpeta como la raíz del remote — por eso los paths van
vacíos (`gdrive:`).

La descarga de una foto suelta SÍ se reutiliza del otro nicho: va por file ID,
que es global en Drive y no depende de dónde cuelgue la carpeta.
"""

from __future__ import annotations

import json
import re
import subprocess

from src.nicho_pov_bof import config as pov_config
from src.nicho_gorras import config

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _run_rclone(args: list[str], carpeta: str) -> str:
    cmd = [
        "rclone", *args,
        "--drive-root-folder-id", config.carpeta_id(carpeta),
    ]
    conf = pov_config.rclone_config_path()
    if conf:
        cmd += ["--config", conf]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=pov_config.RCLONE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"rclone tardó más de {pov_config.RCLONE_TIMEOUT_S:.0f}s leyendo la "
            "carpeta de ropa."
        ) from None
    except FileNotFoundError:
        raise RuntimeError(
            "rclone no está instalado en este entorno. La carpeta se comparte "
            "por enlace y solo se puede leer por CLI."
        ) from None
    if proc.returncode != 0:
        raise RuntimeError(f"rclone falló: {proc.stderr[-400:]}")
    return proc.stdout


def list_photos(carpeta: str = "", *, refresh: bool = False) -> list[dict]:
    """Fotos de la carpeta, en orden natural.

    Devuelve `[{"id","name","size","mime"}]`. El `id` es el identificador
    canónico: dentro de la carpeta hay nombres REPETIDOS (`5.PNG` dos veces,
    la foto limpia y la captura), igual que en el Nicho POV BOF.

    Cacheado con la misma máquina que el otro nicho (memoria → Redis sirviendo
    lo viejo mientras refresca por detrás → rclone). La clave lleva su propio
    prefijo aunque el documento viva en el namespace del POV BOF: duplicar
    sesenta líneas de caché para cambiar el prefijo no compensa.
    """
    carpeta = carpeta or config.CARPETA_DEFECTO

    def cargar() -> list[dict]:
        items = json.loads(
            _run_rclone(["lsjson", config.DRIVE_REMOTE, "--files-only"], carpeta) or "[]"
        )
        fotos = [
            {
                "id": it.get("ID", ""),
                "name": it.get("Name", ""),
                "size": int(it.get("Size") or 0),
                "mime": it.get("MimeType", ""),
            }
            for it in items
            if it.get("ID")
            and pov_config.is_image(it.get("Name", ""), it.get("MimeType", ""))
        ]
        fotos.sort(key=lambda f: pov_config.natural_sort_key(f["name"]))
        return fotos

    from src.nicho_pov_bof.services import drive_client as pov_drive

    return pov_drive._listar_cacheado(
        f"nicho_ropa:photos:{carpeta}", cargar, refresh=refresh,
    )


def fetch_photo(file_id: str, *, suffix: str = ".jpg"):
    """Descarga por file ID, cacheada en disco.

    Se delega en el Nicho POV BOF a propósito: el ID es global en Drive, así
    que la misma función vale, y así hay una sola caché de fotos.
    """
    if not _FILE_ID_RE.match(file_id or ""):
        raise ValueError(f"file_id no válido: {file_id!r}")
    from src.nicho_pov_bof.services import drive_client as pov_drive

    return pov_drive.fetch_photo(file_id, suffix=suffix)


def probe_dimensions(photo: dict) -> dict:
    """Añade `width`/`height`, que es lo que distingue la foto limpia
    (cuadrada) de la captura con título (alta). Reutiliza la del otro nicho."""
    from src.nicho_pov_bof.services import drive_client as pov_drive

    return pov_drive.probe_dimensions(photo)
