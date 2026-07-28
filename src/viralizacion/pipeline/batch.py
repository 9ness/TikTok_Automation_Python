"""Orquestador de un batch de generación: N vídeos por ponente, repartidos
entre sus audios disponibles, con estilo/filtro rotando por ronda y música
solo en las primeras `music_rounds` rondas de cada audio.

Resiliencia:
- Salta MP4 ya válidos (reanudar batch).
- Si un vídeo falla, libera pool, registra error y SIGUE con el siguiente.
- Sube a Drive cada MP4 al terminar (no espera al final del lote).
"""

from __future__ import annotations

import math
import traceback
import uuid
from datetime import date
from pathlib import Path
from typing import Callable

from src.viralizacion import config
from src.viralizacion.pipeline import styles, transcriber
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration, is_valid_mp4
from src.viralizacion.pipeline.renderer import build_paisaje_segments, render_video
from src.viralizacion.services import allocator, clip_library
from src.viralizacion.services.allocator import PoolExhaustedError
from src.viralizacion.services.drive_uploader import upload_batch, upload_file

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]


def _rounds_per_audio(total: int, n_audios: int) -> list[int]:
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
        avail_hooks, total_hooks = allocator.count_available_hooks(
            ponente, cache_only=True
        )
        if total_hooks > 0 and avail_hooks < total:
            errors.append(
                f"'{ponente}': pool de gancho insuficiente — pedidos {total}, "
                f"disponibles {avail_hooks} de {total_hooks} candidatos totales."
            )
        rounds = _rounds_per_audio(total, len(audios))
        needed_paisajes = 0
        for audio_path, n_rounds in zip(audios, rounds):
            if n_rounds <= 0:
                continue
            full_dur = ffprobe_duration(audio_path)
            # Estimar con la ventana más larga posible por ronda (tope MAX).
            for ronda in range(1, n_rounds + 1):
                _start, win_dur = config.audio_window_for_round(full_dur, ronda)
                fill = max(0.0, win_dur - config.HOOK_DUR)
                needed_paisajes += build_paisaje_segments(fill)
        if clip_library.is_available():
            # Con biblioteca no hay déficit posible salvo que un solo vídeo
            # pida más clips que los que existen: al agotarse la vuelta se
            # abre un ciclo nuevo con ventanas y zooms distintos.
            total_clips = clip_library.clip_count()
            max_por_video = max(
                (build_paisaje_segments(
                    max(0.0, config.audio_window_for_round(
                        ffprobe_duration(a), r)[1] - config.HOOK_DUR))
                 for a, nr in zip(audios, rounds) if nr > 0
                 for r in range(1, nr + 1)),
                default=0,
            )
            if max_por_video > total_clips:
                errors.append(
                    f"'{ponente}': un vídeo necesita {max_por_video} clips de "
                    f"paisaje y la biblioteca solo tiene {total_clips}."
                )
            continue

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
    # Estilo elegido por el operador para cada ronda: `round_styles[i]` es la
    # ronda i+1. Lo que no se especifique cae en la rotación automática.
    round_styles: list[str] | None = None,
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
    skipped = 0
    failed: list[dict] = []
    # Vídeos que se renderizaron OK pero no llegaron a Drive.
    upload_failed: list[dict] = []
    sync_error: str = ""
    outputs: dict[str, list[str]] = {}
    remote_dirs: dict[str, str] = {}

    on_log(
        f"[batch] {batch_id} · {total_videos} vídeos pedidos · "
        f"music_rounds={music_rounds} · max_dur={config.MAX_VIDEO_DURATION_S}s · "
        f"preset={config.FFMPEG_PRESET}/crf{config.FFMPEG_CRF}"
    )

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
            audio_idx = audio_idx0 + 1
            rounds_needed = rounds_per_audio[audio_idx0]
            if rounds_needed <= 0:
                continue

            on_log(
                f"[batch][{ponente}] audio {audio_idx}/{n_audios} · "
                f"{audio_path.name} · {rounds_needed} rondas"
            )
            words = transcriber.transcribe_words(
                ponente, audio_path, tmp_dir=ponente_tmp_dir, on_log=on_log,
            )
            full_audio_dur = ffprobe_duration(audio_path)

            for ronda in range(1, rounds_needed + 1):
                style = styles.resolve_style(ronda, round_styles)
                include_music = ronda <= music_rounds
                filename = f"{ponente}{ronda}_{audio_idx}.mp4"
                out_path = ponente_out_dir / filename

                audio_start, win_dur = config.audio_window_for_round(full_audio_dur, ronda)
                fill_duration = max(0.0, win_dur - config.HOOK_DUR)
                n_paisajes = build_paisaje_segments(fill_duration)

                progress_base = done / total_videos if total_videos else 0.0
                on_progress(
                    progress_base,
                    f"🎬 Generando {filename} ({style.label}, {win_dur:.0f}s)…",
                )

                if is_valid_mp4(out_path, min_duration=config.MIN_VIDEO_DURATION_S * 0.8):
                    on_log(f"[batch][{ponente}] ⏭️  skip {filename} (ya válido)")
                    outputs[ponente].append(str(out_path))
                    done += 1
                    skipped += 1
                    try:
                        remote = upload_file(
                            out_path, nombre_cuenta, fecha, ponente, on_log=on_log,
                        )
                        remote_dirs[ponente] = remote
                    except Exception as e:
                        on_log(f"[batch][{ponente}] ⚠️ upload skip {filename}: {e}")
                        upload_failed.append(
                            {"file": filename, "ponente": ponente, "error": str(e)}
                        )
                    on_progress(
                        done / total_videos if total_videos else 1.0,
                        f"✅ {filename} (skip) ({done}/{total_videos})",
                    )
                    continue

                hook_c = None
                paisaje_cs = None
                try:
                    hook_c = allocator.allocate_hook(ponente)
                    try:
                        # Biblioteca de clips si está disponible: cada clip es
                        # un plano real (un solo lugar) y sin texto. Si no,
                        # se trocea el vídeo largo como antes.
                        if clip_library.is_available():
                            paisaje_cs = allocator.allocate_paisaje_clips(
                                ponente, n_paisajes, min_total_dur=fill_duration,
                            )
                        else:
                            paisaje_cs = allocator.allocate_paisaje_segments(
                                ponente, n_paisajes
                            )
                    except PoolExhaustedError:
                        allocator.release_hook(ponente, hook_c["index"])
                        raise

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
                        audio_start=audio_start,
                        target_duration=win_dur,
                    )

                    if not is_valid_mp4(out_path, min_duration=config.MIN_VIDEO_DURATION_S * 0.8):
                        raise RuntimeError(f"MP4 inválido tras render: {out_path}")

                    outputs[ponente].append(str(out_path))
                    done += 1
                    on_log(
                        f"[batch][{ponente}] ✅ {filename} listo "
                        f"(ronda {ronda} · estilo {style.label})"
                    )
                    try:
                        remote = upload_file(
                            out_path, nombre_cuenta, fecha, ponente, on_log=on_log,
                        )
                        remote_dirs[ponente] = remote
                    except Exception as e:
                        # No se traga el fallo: si nadie lo registra, el job
                        # acaba en verde con CERO vídeos en Drive.
                        on_log(f"[batch][{ponente}] ⚠️ upload {filename}: {e}")
                        upload_failed.append(
                            {"file": filename, "ponente": ponente, "error": str(e)}
                        )

                    on_progress(
                        done / total_videos if total_videos else 1.0,
                        f"✅ {filename} listo ({done}/{total_videos})",
                    )
                except PoolExhaustedError as e:
                    # El pool agotado NO es transitorio: seguir iterando solo
                    # repite el mismo fallo en cada vídeo restante y entierra
                    # el motivo. Aborta el lote con el error claro.
                    if out_path.exists():
                        out_path.unlink(missing_ok=True)
                    on_log(f"[batch][{ponente}] ⛔ pool agotado: {e}")
                    raise
                except Exception as e:
                    if hook_c is not None:
                        try:
                            allocator.release_hook(ponente, hook_c["index"])
                        except Exception:
                            pass
                    if paisaje_cs is not None:
                        try:
                            allocator.release_paisajes(
                                ponente, [c["index"] for c in paisaje_cs]
                            )
                        except Exception:
                            pass
                    if out_path.exists():
                        try:
                            out_path.unlink()
                        except OSError:
                            pass
                    err_msg = f"{type(e).__name__}: {e}"
                    on_log(f"[batch][{ponente}] ❌ falló {filename}: {err_msg}")
                    on_log(traceback.format_exc()[-800:])
                    failed.append({"file": filename, "ponente": ponente, "error": err_msg})
                    # Continúa con el siguiente vídeo (no aborta el lote).
                    continue

    # Sync final por si algún upload puntual falló.
    on_progress(0.97, "☁️ Sync final a Drive…")
    try:
        final_remotes = upload_batch(
            staging_root, nombre_cuenta, fecha,
            ponentes=list(outputs.keys()), on_log=on_log,
        )
        remote_dirs.update(final_remotes)
    except Exception as e:
        on_log(f"[batch] ⚠️ sync final: {e}")
        sync_error = str(e)

    # Si NADA llegó a Drive, el batch no sirve por muchos MP4 locales que haya.
    if done > 0 and not remote_dirs:
        raise RuntimeError(
            "Ningún vídeo llegó a Drive. "
            + (f"Último error de sync: {sync_error}. " if sync_error else "")
            + (f"Fallos de subida: {upload_failed[:3]}" if upload_failed else "")
        )

    ok = done > 0 and not failed and not upload_failed
    status = "ok" if ok else ("partial" if done > 0 else "failed")
    on_progress(
        1.0,
        f"{'✅' if ok else '⚠️'} Batch {status}: {done}/{total_videos} ok"
        + (f", {len(failed)} fallos" if failed else "")
        + (f", {skipped} skip" if skipped else ""),
    )
    if done == 0:
        raise RuntimeError(
            f"Batch sin ningún vídeo generado. Fallos: {failed[:5]}"
        )

    return {
        "batch_id": batch_id,
        "fecha": fecha,
        "nombre_cuenta_safe": account_safe,
        "staging_root": str(staging_root),
        "outputs": outputs,
        "remote_dirs": remote_dirs,
        "total_videos": done,
        "failed": failed,
        "upload_failed": upload_failed,
        "skipped": skipped,
        "status": status,
    }
