"""Orquestador de un batch de generación: N vídeos por ponente, repartidos
entre sus audios disponibles, con estilo/filtro rotando por ronda y música
solo en las primeras `music_rounds` rondas de cada audio.

Resiliencia:
- Salta MP4 ya válidos (reanudar batch).
- Si un vídeo falla, libera pool, registra error y SIGUE con el siguiente.
- Sube a Drive cada MP4 al terminar (no espera al final del lote).
"""

from __future__ import annotations

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


def _audios_de(ponente: str, elegidos: dict[str, list[str]] | None) -> list:
    """Audios a usar: los elegidos por el operador, o todos.

    Si lo que llega no casa con ningún fichero del banco se usan todos, en vez
    de quedarse a cero: es preferible generar de más que no generar nada por
    un nombre mal escrito.
    """
    todos = config.ponente_audio_files(ponente)
    quiere = {n.strip() for n in (elegidos or {}).get(ponente, []) if n.strip()}
    if not quiere:
        return todos
    filtrados = [a for a in todos if a.name in quiere]
    return filtrados or todos


def _rounds_per_audio(total: int, duraciones: list[float]) -> list[int]:
    """Cuántos vídeos salen de cada audio. Los LARGOS se llevan los de más.

    Dos cosas que costaron descubrirse:

    1. Antes se calculaba `ceil(total/n)` y se daba ese tope a cada uno hasta
       agotar: con 10 vídeos y 8 audios salía [2,2,2,2,2,0,0,0] y los tres
       ÚLTIMOS no se usaban NUNCA. Ahí estaban justo los dos que mejor
       funcionaban.
    2. Los audios largos retienen más y son los que viralizan: de los vídeos
       del operador, los dos más vistos salieron del único audio que pasaba
       del minuto.

    Así que: reparto entero para que todos entren, y las vueltas SOBRANTES
    para los más largos. Si se piden menos vídeos que audios (base 0), se
    quedan los `total` más largos.
    """
    n = len(duraciones)
    if n <= 0:
        return []
    base, resto = divmod(max(0, total), n)
    out = [base] * n
    por_duracion = sorted(range(n), key=lambda i: duraciones[i], reverse=True)
    for i in por_duracion[:resto]:
        out[i] += 1
    return out


def preflight_check(
    ponentes: list[str],
    cantidad: dict[str, int],
    audios_elegidos: dict[str, list[str]] | None = None,
) -> list[str]:
    errors: list[str] = []
    for ponente in ponentes:
        if not config.is_known_ponente(ponente):
            errors.append(f"Ponente desconocido: '{ponente}'.")
            continue
        total = cantidad.get(ponente, 0)
        if total <= 0:
            continue
        audios = _audios_de(ponente, audios_elegidos)
        if not audios:
            errors.append(f"'{ponente}': no hay audios disponibles.")
            continue
        # Vale el vídeo fuente O los ganchos ya pre-cortados. Lo normal es lo
        # segundo: el fuente pesa 300 MB-1,1 GB por ponente y se borra del VPS
        # tras pre-cortar (sigue en Drive), así que exigirlo dejaba a TODOS los
        # ponentes sin poder generar.
        ganchos_dir = config.ponente_ganchos_dir(ponente)
        hay_precortados = ganchos_dir.is_dir() and any(ganchos_dir.glob("hook_*.mp4"))
        if config.ponente_gancho_video(ponente) is None and not hay_precortados:
            errors.append(
                f"'{ponente}': no hay ni vídeo de gancho ni ganchos pre-cortados."
            )
        avail_hooks, total_hooks = allocator.count_available_hooks(
            ponente, cache_only=True
        )
        # El gancho SE RECICLA: al agotarse la vuelta se abre un ciclo nuevo
        # con otro zoom, otro audio y otro estilo. Solo es error no tener
        # ningún candidato en absoluto.
        if total_hooks == 0 and avail_hooks == 0:
            errors.append(
                f"'{ponente}': no hay ningún candidato de gancho detectado."
            )
        duraciones = [ffprobe_duration(a) for a in audios]
        rounds = _rounds_per_audio(total, duraciones)
        needed_paisajes = 0
        for audio_path, n_rounds, full_dur in zip(audios, rounds, duraciones):
            if n_rounds <= 0:
                continue
            # Estimar con la ventana más larga posible por ronda (tope MAX).
            for ronda in range(1, n_rounds + 1):
                _start, win_dur = config.audio_window_for_round(full_dur, ronda)
                fill = max(0.0, win_dur - config.HOOK_DUR)
                needed_paisajes += build_paisaje_segments(fill)
        if clip_library.is_available(config.pais_de(ponente)):
            # Con biblioteca no hay déficit posible salvo que un solo vídeo
            # pida más clips que los que existen: al agotarse la vuelta se
            # abre un ciclo nuevo con ventanas y zooms distintos.
            total_clips = clip_library.clip_count(config.pais_de(ponente))
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
    # Estilos elegidos por el operador. Los vídeos se reparten entre ellos a
    # partes iguales, independientemente de cuántas rondas salgan del reparto
    # de audios. Vacío = los 6.
    styles_pool: list[str] | None = None,
    # Audios elegidos por el operador, por ponente. Vacío = todos los del
    # banco. Permite tirar solo de los largos, que son los que retienen.
    audios_elegidos: dict[str, list[str]] | None = None,
    on_log: OnLog = lambda _msg: None,
    on_progress: OnProgress = lambda _pct, _label: None,
) -> dict:
    errors = preflight_check(ponentes, cantidad, audios_elegidos)
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
        paisajes_video = config.paisajes_video(config.pais_de(ponente))
        audios = _audios_de(ponente, audios_elegidos)
        n_audios = len(audios)
        duraciones_audio = [ffprobe_duration(a) for a in audios]
        rounds_per_audio = _rounds_per_audio(n_total, duraciones_audio)

        on_log(
            f"[batch][{ponente}] {n_total} vídeos / {n_audios} audios → "
            + " · ".join(
                f"{a.name} {d:.0f}s ×{n}"
                for a, d, n in zip(audios, duraciones_audio, rounds_per_audio)
            )
        )

        # Un estilo por vídeo, repartido a partes iguales entre los elegidos.
        #
        # Sin selección explícita se reparten TODOS, que es lo que promete la
        # UI ("Sin marcar ninguna se usan todas"). Antes se caía en la
        # rotación por ronda y, como el nº de rondas sale del reparto de
        # audios, una tanda de 15 vídeos con 8 audios da 2 rondas y salían
        # solo 2 de los 8 estilos — los cuadrados no aparecían nunca.
        pool = [k for k in (styles_pool or styles.STYLE_ORDER) if k in styles.STYLE_PRESETS]
        plan_estilos = styles.distribute_styles(n_total, pool)
        idx_video = 0

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
                key = plan_estilos[idx_video] if idx_video < len(plan_estilos) else None
                style = styles.STYLE_PRESETS.get(key) or styles.resolve_style(ronda, round_styles)
                idx_video += 1
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
                            out_path, nombre_cuenta, fecha, ponente,
                            n_videos=n_total, on_log=on_log,
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
                        if clip_library.is_available(config.pais_de(ponente)):
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
                            out_path, nombre_cuenta, fecha, ponente,
                            n_videos=n_total, on_log=on_log,
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
            ponentes=list(outputs.keys()), cantidad=cantidad, on_log=on_log,
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
    # Limpieza del VPS: el staging acumulaba cientos de MB por tanda (el disco
    # llegó al 88%). Pero antes se COMPRUEBA fichero a fichero que el MP4 está
    # de verdad en el destino: rclone llegó a reportar "upload succeeded" para
    # 4 vídeos que NUNCA aparecieron en Drive (coincidió con una saturación de
    # la cuota de la API). Fiarse del "no hubo errores" habría borrado los
    # únicos originales que quedaban.
    if done > 0 and not upload_failed and not failed and remote_dirs:
        pendientes: list[str] = []
        for ponente, destino in remote_dirs.items():
            dest_dir = Path(destino)
            for local in sorted((staging_root / ponente).glob("*.mp4")):
                remoto = dest_dir / local.name
                if not remoto.is_file() or remoto.stat().st_size != local.stat().st_size:
                    pendientes.append(local.name)
        if pendientes:
            on_log(
                f"[batch] NO se borra el staging: {len(pendientes)} vídeo(s) no "
                f"están confirmados en destino ({pendientes[:4]})"
            )
        else:
            try:
                import shutil as _shutil
                _shutil.rmtree(staging_root, ignore_errors=True)
                on_log(
                    f"[batch] staging local borrado ({staging_root.name}) — "
                    f"{done} vídeo(s) verificados en Drive"
                )
            except OSError as e:
                on_log(f"[batch] no se pudo borrar el staging: {e}")

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
