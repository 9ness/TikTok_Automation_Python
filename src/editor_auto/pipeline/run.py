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


def _preflight_check(enabled_steps) -> tuple[list[str], list[str]]:
    """Comprueba que cada tool del flow pueda arrancar antes de gastar
    dinero. Distingue:

    - **errors** (lista 0+): problemas que IMPIDEN el pipeline. El runner
      aborta SIN cobrar. Ej: faster-whisper missing, OPENAI_API_KEY
      ausente cuando la tool usa OpenAI, ningún encoder H264 funcional.
    - **warnings** (lista 0+): features OPCIONALES que degradan (la tool
      las maneja con `try/except` interno). Se loguean al inicio y el
      pipeline sigue. Ej: silero-vad no instalado → cae a amplitude +
      IA; Gemini missing → cae a solo OpenAI o n-gram heuristic.

    Devuelve `(errors, warnings)`. El runner solo aborta si `errors`.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. FFmpeg present
    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        errors.append("ffmpeg no está en PATH")
        return errors, warnings  # sin ffmpeg el resto no tiene sentido

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
            # faster-whisper local — HARD (sin él no hay transcripción
            # ni word_timings, base de todo el cortador).
            try:
                import faster_whisper  # noqa: F401
            except ImportError as e:
                errors.append(
                    f"{tool_id}: faster-whisper no instalado ({e})"
                )

            # Silero — SOFT. El cortador funciona sin él usando amplitude
            # + IA + inter-word-gap. Solo perdemos detección fina de
            # silencios sutiles (respiración, "ejem" boca cerrada).
            if bool(cfg.get("vad_enabled", True)):
                try:
                    import silero_vad  # noqa: F401
                except ImportError as e:
                    warnings.append(
                        f"{tool_id}: silero-vad no disponible ({e}) — "
                        f"el cortador usará amplitude + IA + gaps "
                        f"entre palabras como sustituto"
                    )

            # OpenAI — HARD si la tool requiere OpenAI activamente.
            # Para silence_cutter: ai_clean_enabled (default True) y/o
            # ai_pass2_openai_enabled. Para scripted: scripted_llm_arbitration.
            uses_openai_hard = (
                bool(cfg.get("ai_clean_enabled", True))
                or bool(cfg.get("ai_pass2_openai_enabled", False))
            )
            uses_openai_optional = bool(
                cfg.get("scripted_llm_arbitration", False)
            )
            if uses_openai_hard:
                try:
                    from src.editor_auto.api.openai_client import is_configured
                    if not is_configured():
                        errors.append(
                            f"{tool_id}: usa OpenAI pero OPENAI_API_KEY no "
                            f"está en el .env del server"
                        )
                except ImportError as e:
                    errors.append(f"{tool_id}: openai SDK no importable ({e})")
            elif uses_openai_optional:
                # En scripted, el LLM es opcional (el diff por sí solo
                # ya hace la mayoría del trabajo). Solo warning.
                try:
                    from src.editor_auto.api.openai_client import is_configured
                    if not is_configured():
                        warnings.append(
                            f"{tool_id}: arbitrator LLM activado pero "
                            f"OPENAI_API_KEY ausente — solo se usará el "
                            f"diff transcript-vs-guión"
                        )
                except ImportError:
                    pass

            # Gemini — SOFT. Si no está, queda solo OpenAI pass2 (si
            # habilitado) o solo la heurística n-gram. Tool degrada bien.
            if tool_id == "silence_cutter" and bool(
                cfg.get("ai_pass2_gemini_enabled", True)
            ):
                try:
                    from src.editor_auto.api.gemini_client import is_configured
                    if not is_configured():
                        warnings.append(
                            f"{tool_id}: Gemini pass2 activo pero "
                            f"GOOGLE_GEMINI_KEY ausente — n-gram + OpenAI "
                            f"pass2 (si activo) cubrirán la detección"
                        )
                except ImportError as e:
                    warnings.append(
                        f"{tool_id}: gemini SDK no importable ({e}) — "
                        f"omitiendo pass2 Gemini"
                    )

        elif tool_id == "sticker_arrow":
            # transcribe_for_detection — SOFT. Sin Whisper la tool usa
            # solo el fallback de "últimos N segundos".
            if bool(cfg.get("transcribe_for_detection", True)):
                try:
                    import faster_whisper  # noqa: F401
                except ImportError as e:
                    warnings.append(
                        f"sticker_arrow: faster-whisper no disponible ({e}) "
                        f"— detección de gatillo deshabilitada, se usará "
                        f"fallback de últimos N segundos"
                    )
            # sticker_file — HARD. Sin el asset no hay nada que overlay.
            sticker = (cfg.get("sticker_file") or "").strip()
            if not sticker:
                errors.append(
                    "sticker_arrow: 'sticker_file' vacío en la config"
                )
            else:
                try:
                    from src.editor_auto.config import arrows_folder
                    from src.editor_auto.tools.sticker_arrow import (
                        STICKER_EXTS,
                        _resolve_sticker_path,
                    )
                    if not _resolve_sticker_path(sticker):
                        folder = arrows_folder()
                        if not os.path.isdir(folder):
                            errors.append(
                                f"sticker_arrow: la carpeta '{folder}' no existe "
                                f"en este entorno. Crea la carpeta en Drive y "
                                f"sube tus stickers (.mov/.webm/.gif) ahí."
                            )
                        else:
                            try:
                                available = sorted([
                                    n for n in os.listdir(folder)
                                    if os.path.splitext(n)[1].lower() in STICKER_EXTS
                                ])
                            except OSError:
                                available = []
                            if not available:
                                errors.append(
                                    f"sticker_arrow: la carpeta '{folder}' existe "
                                    f"pero está vacía. Sube '{sticker}' a Drive en "
                                    f"esa carpeta (o fuerza refresh rclone: "
                                    f"`rclone rc vfs/refresh recursive=true`)."
                                )
                            else:
                                preview = ", ".join(available[:8]) + (
                                    f" (+{len(available) - 8} más)" if len(available) > 8 else ""
                                )
                                errors.append(
                                    f"sticker_arrow: '{sticker}' no está en "
                                    f"'{folder}'. Disponibles: {preview}. Si "
                                    f"acabas de subirlo a Drive, ejecuta "
                                    f"`rclone rc vfs/refresh recursive=true`."
                                )
                except Exception as e:
                    errors.append(f"sticker_arrow: error resolviendo asset ({e})")

        elif tool_id == "subs_auto":
            # Solo requiere ffmpeg (ya chequeado arriba) + fuentes (las
            # fuentes son archivos bundle, sin deps externas).
            pass

        elif tool_id == "photo_insert":
            # Todas las deps son BLANDAS — si faltan, la tool hace no-op
            # (no inserta fotos) pero NO rompe el pipeline.
            try:
                import faster_whisper  # noqa: F401
            except ImportError as e:
                warnings.append(
                    f"photo_insert: faster-whisper no disponible ({e}) — "
                    f"no se podrán detectar nombres, no se insertarán fotos"
                )
            try:
                from src.editor_auto.api import gemini_client
                if not gemini_client.is_configured():
                    warnings.append(
                        "photo_insert: Gemini no configurado — no se "
                        "detectarán famosos/marcas (no se insertarán fotos)"
                    )
            except Exception as e:
                warnings.append(f"photo_insert: Gemini no importable ({e})")

        else:
            errors.append(
                f"Tool '{tool_id}' desconocida (no registrada en REGISTRY)"
            )

    return errors, warnings


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
    manual_keep_intervals: list | None = None,
    output_override: str | None = None,
    output_subdir: str | None = None,
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
    # gastar dinero en Whisper/OpenAI/Gemini. Si hay errors (hard) →
    # abortamos SIN cobrar. Si hay warnings (soft) → los logueamos y
    # seguimos (la tool maneja la feature ausente).
    on_log("[editor_auto] 🔎 Preflight: comprobando deps de cada tool…")
    errors, warnings = _preflight_check(enabled_steps)
    for w in warnings:
        on_log(f"[editor_auto] ⚠️  {w}")
    if errors:
        msg = "Preflight FAILED — abortando antes de cobrar:\n" + "\n".join(
            f"  • {e}" for e in errors
        )
        on_log(msg)
        raise RuntimeError(msg)
    on_log(
        f"[editor_auto] ✅ Preflight OK — arrancando pipeline"
        + (f" ({len(warnings)} warning(s) — features degradadas)" if warnings else "")
    )

    # Carpetas del usuario en Drive — 4 carpetas: entrada/cola/recuperacion/salida
    _, _, _, _, out_folder = ensure_user_folders(user.name)
    # Subcarpeta por DÍA (subida web): salida/<YYYY-MM-DD>/ para no amontonar
    # los vídeos de distintos días. Solo cuando el job lo indica; el flujo del
    # admin (sin output_subdir) sigue escribiendo en salida/ plano.
    if output_subdir and not output_override:
        out_folder = os.path.join(out_folder, output_subdir)
        Path(out_folder).mkdir(parents=True, exist_ok=True)
    on_log(f"[editor_auto] Output folder: {out_folder}")

    # Naming del MP4 final:
    #   - source_filename presente → `<stem>_editado.mp4` (siempre .mp4,
    #     aunque el input sea .mov/.webm — el encoder estabiliza a H264).
    #   - sin source_filename (upload directo) → timestamped legacy.
    # Si ya existe un editado del mismo día con ese nombre, dedup `_2`/`_3`.
    if output_override:
        # Retoque MANUAL: REEMPLAZA el vídeo de salida existente con el MISMO
        # nombre (sin dedup). El editor manual pasa la ruta del output a pisar.
        final_output_path = output_override
        base_name = os.path.basename(output_override)
        on_log(f"[editor_auto] Output (reemplazo manual): {base_name}")
    elif source_filename:
        stem = os.path.splitext(os.path.basename(source_filename))[0]
        base_name = f"{stem}_editado.mp4"
        # Dedup si ya hay un editado con ese nombre
        n = 2
        candidate = base_name
        while os.path.exists(os.path.join(out_folder, candidate)):
            candidate = f"{stem}_editado_{n}.mp4"
            n += 1
        base_name = candidate
        final_output_path = os.path.join(out_folder, base_name)
        on_log(f"[editor_auto] Output filename: {base_name}")
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
        manual_keep_intervals=manual_keep_intervals,
    )

    # Mover a Drive sincronizado (copy + cleanup, NO move para que un fallo
    # de I/O en Drive no deje el archivo a medias).
    on_log(f"[editor_auto] Copiando a Drive: {final_output_path}")
    shutil.copyfile(temp_final, final_output_path)
    try:
        os.remove(temp_final)
    except OSError:
        pass

    # Reubicar el "proyecto editable" (si el cutter lo escribió) junto al
    # output, indexado por su nombre, para que el editor manual lo cargue.
    try:
        proj_src = os.path.join(temp_folder, f"editproject_{job_id}.json")
        if os.path.exists(proj_src):
            # `.editproj` a nivel de USUARIO (hermano de salida), NO dentro de
            # salida: así no ensucia la carpeta ni la ve el cliente (solo se
            # comparte `salida`). out_folder == .../<user>/salida.
            proj_dir = os.path.join(os.path.dirname(out_folder), ".editproj")
            os.makedirs(proj_dir, exist_ok=True)
            shutil.copyfile(proj_src, os.path.join(proj_dir, f"{base_name}.json"))
            os.remove(proj_src)
            on_log(f"[editor_auto] 📝 Proyecto editable guardado para {base_name}")
    except OSError:
        pass

    return final_output_path
