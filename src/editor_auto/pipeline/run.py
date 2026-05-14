"""Pipeline de Editor Auto — entry point del runner de cola.

Recibe el job (user_id + input_path) y:
  1. Carga el usuario y su flujo configurado.
  2. Resuelve la carpeta de salida en `TIKTOK_EDITOR/Usuarios/<user>/salida/`.
  3. Ejecuta el flow_orchestrator.
  4. Copia el resultado a la carpeta Drive sincronizada con nombre versionado.

Devuelve la ruta absoluta del MP4 final.
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.editor_auto.config import ensure_user_folders
from src.editor_auto.repos import UserRepo
from src.editor_auto.services import run_flow


LogFn = Callable[[str], None]
ProgressFn = Callable[[float, str], None]


def run_editor_auto_pipeline(
    *,
    user_id: str,
    input_video_path: str,
    job_id: str,
    temp_folder: str,
    on_log: LogFn,
    on_progress: ProgressFn,
    script: str | None = None,
    source_filename: str | None = None,
) -> str:
    """Pipeline completo. Devuelve la ruta absoluta del MP4 final en Drive.

    `source_filename`: si está presente (caso workflow entrada→cola), el
    output toma el mismo nombre base con sufijo `_editado`. Ej:
    `1.mp4` → `1_editado.mp4`. Para uploads directos sin source_filename,
    se cae al esquema timestamped legacy (`<fecha>_editor_<jobid>.mp4`).
    """
    repo = UserRepo()
    user = repo.get(user_id)
    if user is None:
        raise RuntimeError(f"Usuario Editor Auto no encontrado: {user_id}")
    if user.deleted:
        raise RuntimeError(f"Usuario marcado como eliminado: {user.name}")

    enabled_steps = [s for s in user.tool_flow if s.enabled]
    if not enabled_steps:
        raise RuntimeError(
            f"El usuario '{user.name}' no tiene herramientas habilitadas en "
            f"su flujo. Configura al menos una antes de generar."
        )

    if not os.path.exists(input_video_path):
        raise RuntimeError(f"Vídeo input no encontrado: {input_video_path}")

    on_log(f"[editor_auto] Job {job_id} · usuario '{user.name}' · "
           f"{len(enabled_steps)} herramienta(s)")

    # Carpetas del usuario en Drive — 4 carpetas: entrada/cola/recuperacion/salida
    _, _, _, _, out_folder = ensure_user_folders(user.name)
    on_log(f"[editor_auto] Output folder: {out_folder}")

    # Naming del MP4 final:
    #   - source_filename presente → `<stem>_editado.mp4` (siempre .mp4,
    #     aunque el input sea .mov/.webm — el encoder estabiliza a H264).
    #   - sin source_filename (upload directo) → timestamped legacy.
    # Si ya existe un editado del mismo día con ese nombre, dedup `_2`/`_3`.
    if source_filename:
        stem = os.path.splitext(os.path.basename(source_filename))[0]
        base_name = f"{stem}_editado.mp4"
        # Dedup si ya hay un editado con ese nombre
        n = 2
        candidate = base_name
        while os.path.exists(os.path.join(out_folder, candidate)):
            candidate = f"{stem}_editado_{n}.mp4"
            n += 1
        base_name = candidate
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        base_name = f"{ts}_editor_{job_id}.mp4"
    final_output_path = os.path.join(out_folder, base_name)
    on_log(f"[editor_auto] Output filename: {base_name}")

    # Output intermedio en temp_folder (lo movemos a Drive al terminar
    # para que un fallo a mitad de render no contamine Drive).
    temp_final = os.path.join(
        temp_folder,
        f"editor_auto_final_{job_id}_{int(time.time())}.mp4",
    )
    Path(temp_folder).mkdir(parents=True, exist_ok=True)

    on_log("[editor_auto] Ejecutando flow_orchestrator…")
    run_flow(
        user=user,
        job_id=job_id,
        input_video_path=input_video_path,
        final_output_path=temp_final,
        temp_folder=temp_folder,
        on_log=on_log,
        on_progress=on_progress,
        script=script,
    )

    # Mover a Drive sincronizado (copy + cleanup, NO move para que un fallo
    # de I/O en Drive no deje el archivo a medias).
    on_log(f"[editor_auto] Copiando a Drive: {final_output_path}")
    shutil.copyfile(temp_final, final_output_path)
    try:
        os.remove(temp_final)
    except OSError:
        pass

    return final_output_path
