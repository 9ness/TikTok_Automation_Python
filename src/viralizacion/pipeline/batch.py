"""Orquestador de un batch de generación: N vídeos por ponente, repartidos
entre sus audios disponibles, con estilo/filtro rotando por ronda y música
solo en las primeras `music_rounds` rondas de cada audio.

Ver VIRALIZACION_MODULE.md para el diseño completo (numeración, reparto de
rondas, orden de procesamiento)."""

from __future__ import annotations

import math
import uuid
from datetime import date
from pathlib import Path
from typing import Callable

from src.viralizacion import config
from src.viralizacion.pipeline import styles, transcriber
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration
from src.viralizacion.pipeline.renderer import build_paisaje_segments, render_video
from src.viralizacion.services import allocator
from src.viralizacion.services.allocator import PoolExhaustedError
from src.viralizacion.services.drive_uploader import upload_batch

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]


def _rounds_per_audio(total: int, n_audios: int) -> list[int]:
    """Reparte `total` rondas entre `n_audios` lo más uniforme posible:
    `R = ceil(total/n_audios)` rondas por audio, rellenando SECUENCIALMENTE
    (audio 1 hasta R, luego audio 2 hasta R, …) — el último audio que
    recibe rondas se queda con el resto exacto. Coincide con el ejemplo
    del operador: total=23, n_audios=5 → R=5 → [5,5,5,5,3] (23=5+5+5+5+3).

    Nota: si `total <= n_audios`, R=1 y el reparto queda a 1 ronda por
    audio (usa tantos audios como `total`, el resto a 0) — es el caso
    "uniforme" correcto para lotes grandes, pero para lotes de prueba
    pequeños (p.ej. validar los 3 estilos con `total=3` y 5 audios) esto
    reparte 1 ronda por audio en vez de concentrar 3 rondas en 1 audio.
    Si se quiere forzar concentración en pocos audios para un lote
    pequeño, pide un `total` mayor (p.ej. múltiplo de `n_audios`) o usa
    un solo ponente con menos audios."""
    if n_audios <= 0:
        return []
    r = math.ceil(total / n_audios)
    out: list[int] = []
    remaining = total
    for _ in range(n_audios):
        take = min(r, remaining)
        out.append(take)
        remaining -= take
    return out


def preflight_check(ponentes: list[str], cantidad: dict[str, int]) -> list[str]:
    """Valida ANTES de encolar que hay audios y candidatos suficientes.
    Devuelve lista de errores (vacía = todo OK). No consume nada del pool
    (solo cuenta disponibles)."""
    errors: list[str] = []
    for ponente in ponentes:
        if not config.is_known_ponente(ponente):
            errors.append(f"Ponente desconocido: '{ponente}'.")
            continue
        total = cantidad.get(ponente, 0)
        if total <= 0:
            continue
        audios = config.ponente_audio_files(ponente)
        if not audios:
            errors.append(f"'{ponente}': no hay audios disponibles.")
            continue
        if config.ponente_gancho_video(ponente) is None:
            errors.append(f"'{ponente}': no hay vídeo de gancho disponible.")
        # cache_only: no disparar escaneo de cara (minutos) en el enqueue.
        # Si no hay caché aún pero existe gancho, el job lo escaneará al arrancar.
        avail_hooks, total_hooks = allocator.count_available_hooks(
            ponente, cache_only=True
        )
        if total_hooks > 0 and avail_hooks < total:
            errors.append(
                f"'{ponente}': pool de gancho insuficiente — pedidos {total}, "
                f"disponibles {avail_hooks} de {total_hooks} candidatos totales."
            )
        # Paisajes: estimar con el reparto REAL de rondas por audio
        # (no max(duración)×total — eso sobreestima brutalmente si hay un
        # audio largo y varios cortos). 15 vídeos / 5 audios → 3 rondas c/u.
        rounds = _rounds_per_audio(total, len(audios))
        needed_paisajes = 0
        for audio_path, n_rounds in zip(audios, rounds):
            if n_rounds <= 0:
                continue
            fill = max(0.0, ffprobe_duration(audio_path) - config.HOOK_DUR)
            needed_paisajes += build_paisaje_segments(fill) * n_rounds
        avail_paisajes, total_paisajes = allocator.count_available_paisajes(
            ponente, cache_only=True
        )
        if avail_paisajes < needed_paisajes:
            errors.append(
                f"'{ponente}': pool de paisaje insuficiente (estimado) — "
                f"pedidos ~{needed_paisajes} tramos, disponibles {avail_paisajes} "
                f"de {total_paisajes} candidatos totales."
            )
    if not any(cantidad.get(p, 0) > 0 for p in ponentes):
        errors.append("No se pidió ningún vídeo (cantidad total = 0).")
    return errors


def run_batch(
    *,
    ponentes: list[str],
    cantidad: dict[str, int],
    nombre_cuenta: str,
    music_rounds: int = config.DEFAULT_MUSIC_ROUNDS,
    on_log: OnLog = lambda _msg: None,
    on_progress: OnProgress = lambda _pct, _label: None,
) -> dict:
    errors = preflight_check(ponentes, cantidad)
    if errors:
        raise RuntimeError("Validación previa falló:\n- " + "\n- ".join(errors))

    fecha = date.today().isoformat()
    account_safe = config.sanitize_account_name(nombre_cuenta)
    batch_id = f"{account_safe}_{fecha}_{uuid.uuid4().hex[:6]}"
    staging_root = config.staging_folder() / batch_id
    tmp_root = staging_root / "_tmp"
    staging_root.mkdir(parents=True, exist_ok=True)

    music_path = config.musica_file()

    total_videos = sum(max(0, cantidad.get(p, 0)) for p in ponentes)
    done = 0
    outputs: dict[str, list[str]] = {}

    on_log(f"[batch] {batch_id} · {total_videos} vídeos pedidos · music_rounds={music_rounds}")

    for ponente in ponentes:
        n_total = cantidad.get(ponente, 0)
        if n_total <= 0:
            continue

        hook_video = config.ponente_gancho_video(ponente)
        paisajes_video = config.paisajes_video()
        audios = config.ponente_audio_files(ponente)
        n_audios = len(audios)
        rounds_per_audio = _rounds_per_audio(n_total, n_audios)

        on_log(
            f"[batch][{ponente}] {n_total} vídeos / {n_audios} audios → "
            f"rondas por audio: {rounds_per_audio}"
        )

        outputs[ponente] = []
        ponente_out_dir = staging_root / ponente
        ponente_tmp_dir = tmp_root / ponente

        for audio_idx0, audio_path in enumerate(audios):
            audio_idx = audio_idx0 + 1  # 1-based, orden de listado
            rounds_needed = rounds_per_audio[audio_idx0]
            if rounds_needed <= 0:
                continue

            on_log(f"[batch][{ponente}] audio {audio_idx}/{n_audios} · {audio_path.name} · {rounds_needed} rondas")
            words = transcriber.transcribe_words(
                ponente, audio_path, tmp_dir=ponente_tmp_dir, on_log=on_log,
            )
            target_duration = ffprobe_duration(audio_path)
            fill_duration = target_duration - config.HOOK_DUR
            n_paisajes = build_paisaje_segments(fill_duration)

            for ronda in range(1, rounds_needed + 1):
                style = styles.get_style_for_round(ronda)
                include_music = ronda <= music_rounds
                filename = f"{ponente}{ronda}_{audio_idx}.mp4"
                out_path = ponente_out_dir / filename

                on_progress(done / total_videos if total_videos else 0.0,
                            f"🎬 Generando {filename} ({style.label})…")

                hook_c = allocator.allocate_hook(ponente)
                try:
                    paisaje_cs = allocator.allocate_paisaje_segments(ponente, n_paisajes)
                except PoolExhaustedError:
                    allocator.release_hook(ponente, hook_c["index"])
                    raise

                try:
                    render_video(
                        ponente=ponente,
                        audio_path=audio_path,
                        words=words,
                        hook_video=hook_video,
                        hook_candidate=hook_c,
                        paisajes_video=paisajes_video,
                        paisaje_candidates=paisaje_cs,
                        style=style,
                        include_music=include_music,
                        music_path=music_path,
                        output_path=out_path,
                        tmp_dir=ponente_tmp_dir,
                        on_log=on_log,
                    )
                except Exception:
                    allocator.release_hook(ponente, hook_c["index"])
                    allocator.release_paisajes(ponente, [c["index"] for c in paisaje_cs])
                    on_log(f"[batch][{ponente}] ❌ falló {filename} — índices liberados.")
                    raise

                outputs[ponente].append(str(out_path))
                done += 1
                on_progress(
                    done / total_videos if total_videos else 1.0,
                    f"✅ {filename} listo ({done}/{total_videos})",
                )

    on_progress(0.95, "☁️ Subiendo a Drive…")
    on_log(f"[batch] subiendo {done} vídeos a gdrive:VIRALIZACION/{account_safe}_{fecha}/…")
    remote_dirs = upload_batch(
        staging_root, nombre_cuenta, fecha, ponentes=list(outputs.keys()), on_log=on_log,
    )

    on_progress(1.0, "✅ Batch completado")
    return {
        "batch_id": batch_id,
        "fecha": fecha,
        "nombre_cuenta_safe": account_safe,
        "staging_root": str(staging_root),
        "outputs": outputs,
        "remote_dirs": remote_dirs,
        "total_videos": done,
    }
