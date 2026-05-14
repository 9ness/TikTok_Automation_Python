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


def _preflight_check(enabled_steps) -> list[str]:
    """Comprueba que cada tool del flow pueda arrancar SIN error de
    dependencias antes de empezar a llamar a APIs de pago.

    Devuelve lista de errores (vacía = todo OK). Cada error es un string
    legible para el operador. El runner aborta el job si hay >0 errores
    — el cliente reencola tras arreglar la causa, sin doble cobro.

    Validaciones:
      - FFmpeg presente y al menos UN encoder H264 funcional (libx264
        o h264_nvenc — uno de los dos debe abrir).
      - Por cada tool habilitada:
          silence_cutter / silence_cutter_scripted:
            · faster-whisper importable
            · OPENAI_API_KEY si la tool usa OpenAI (pass 1 o pass 2)
            · Gemini config si gemini pass2 habilitado
            · silero-vad importable si vad_enabled
          sticker_arrow:
            · faster-whisper si transcribe_for_detection
          subs_auto:
            · nada externo, solo ffmpeg
    """
    errors: list[str] = []

    # 1. FFmpeg present
    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        errors.append("ffmpeg no está en PATH")
        return errors  # sin ffmpeg el resto no tiene sentido

    # 2. Al menos UN encoder H264 funcional. Probamos NVENC primero
    # (cache global vía _has_nvenc); si falla, probamos libx264.
    try:
        from src.editor_auto.tools.silence_cutter import _has_nvenc
        nvenc_ok = _has_nvenc()
    except Exception:
        nvenc_ok = False
    if not nvenc_ok:
        # Probar libx264 con un encode de 1 frame
        import subprocess as _sp
        try:
            rc = _sp.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.05:r=10",
                 "-c:v", "libx264", "-frames:v", "1", "-f", "null", "-"],
                capture_output=True, timeout=15,
            ).returncode
            if rc != 0:
                errors.append(
                    "Ningún encoder H264 funcional (ni h264_nvenc ni libx264)"
                )
        except Exception as e:
            errors.append(f"FFmpeg falla al probar libx264: {e}")

    # 3. Por tool habilitada
    for step in enabled_steps:
        tool_id = step.tool_id
        cfg = step.config or {}

        if tool_id in ("silence_cutter", "silence_cutter_scripted"):
            # faster-whisper local — no necesita API key
            try:
                import faster_whisper  # noqa: F401
            except ImportError as e:
                errors.append(
                    f"{tool_id}: faster-whisper no instalado ({e})"
                )

            # Silero si vad_enabled
            if bool(cfg.get("vad_enabled", True)):
                try:
                    import silero_vad  # noqa: F401
                except ImportError as e:
                    errors.append(
                        f"{tool_id}: silero-vad no instalado ({e}) — "
                        f"desactiva 'vad_enabled' o instala la dep"
                    )

            # OpenAI (pass 1 si ai_clean_enabled, pass 2 si openai pass2,
            # o scripted_llm_arbitration en scripted)
            uses_openai = (
                bool(cfg.get("ai_clean_enabled", True))
                or bool(cfg.get("ai_pass2_openai_enabled", False))
                or bool(cfg.get("scripted_llm_arbitration", False))
            )
            if uses_openai:
                try:
                    from src.editor_auto.api.openai_client import is_configured
                    if not is_configured():
                        errors.append(
                            f"{tool_id}: usa OpenAI pero OPENAI_API_KEY no "
                            f"está en el .env del server"
                        )
                except ImportError as e:
                    errors.append(f"{tool_id}: openai SDK no importable ({e})")

            # Gemini (solo silence_cutter — scripted no usa Gemini)
            if tool_id == "silence_cutter" and bool(
                cfg.get("ai_pass2_gemini_enabled", True)
            ):
                try:
                    from src.editor_auto.api.gemini_client import is_configured
                    if not is_configured():
                        errors.append(
                            f"{tool_id}: usa Gemini pass2 pero "
                            f"GOOGLE_GEMINI_KEY no configurada"
                        )
                except ImportError as e:
                    errors.append(f"{tool_id}: gemini SDK no importable ({e})")

            # silence_cutter_scripted: avisar si .txt resultará vacío.
            # (El validation real lo hace el router antes de encolar; aquí
            # solo recordatorio si por algún motivo llega sin script).
            if tool_id == "silence_cutter_scripted":
                if not (cfg.get("script") or "").strip():
                    # No es error duro — el runner inyecta el script desde
                    # job.params si es source=entrada con companion. Pero
                    # si llega aquí sin script, fallará la tool en run().
                    # Lo dejamos pasar; la tool lo gestiona.
                    pass

        elif tool_id == "sticker_arrow":
            if bool(cfg.get("transcribe_for_detection", True)):
                try:
                    import faster_whisper  # noqa: F401
                except ImportError as e:
                    errors.append(
                        f"sticker_arrow: faster-whisper no instalado ({e})"
                    )
            # Validar que el sticker_file elegido existe en Assets/flechas/
            sticker = (cfg.get("sticker_file") or "").strip()
            if not sticker:
                errors.append(
                    "sticker_arrow: 'sticker_file' vacío en la config"
                )
            else:
                try:
                    from src.editor_auto.tools.sticker_arrow import (
                        _resolve_sticker_path,
                    )
                    if not _resolve_sticker_path(sticker):
                        errors.append(
                            f"sticker_arrow: no encuentro '{sticker}' en "
                            f"Assets/flechas/. ¿Sync rclone pendiente?"
                        )
                except Exception as e:
                    errors.append(f"sticker_arrow: error resolviendo asset ({e})")

        elif tool_id == "subs_auto":
            # Solo requiere ffmpeg (ya chequeado arriba) + fuentes (las
            # fuentes son archivos bundle, sin deps externas).
            pass

        else:
            errors.append(
                f"Tool '{tool_id}' desconocida (no registrada en REGISTRY)"
            )

    return errors


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

    # ===== PREFLIGHT CHECKS =====
    # Validamos que TODO lo que el flow necesita esté operativo ANTES de
    # gastar dinero en Whisper/OpenAI/Gemini. Si algo falla, abortamos
    # SIN cobrar — el input queda intacto para re-intentar.
    on_log("[editor_auto] 🔎 Preflight: comprobando deps de cada tool…")
    errors = _preflight_check(enabled_steps)
    if errors:
        msg = "Preflight FAILED — abortando antes de cobrar:\n" + "\n".join(
            f"  • {e}" for e in errors
        )
        on_log(msg)
        raise RuntimeError(msg)
    on_log("[editor_auto] ✅ Preflight OK — arrancando pipeline")

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
