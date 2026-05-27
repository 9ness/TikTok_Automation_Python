"""Render de los clips Seedance vía Atlas Cloud.

Branch por tier:
  - `standard` / `advanced`:
      multi_clip_anchor → asyncio.gather de N jobs `submit_image_to_video()`,
      con anchoring `last_image` apuntando al frame inicial del clip siguiente.
  - `pro`:
      single_shot_multishot → 1 sola petición `submit_reference_to_video()`
      pasando hasta 9 fotos como referencia (multi-shot interno).

NO hay fallback Ken Burns. Si Atlas falla, el job falla con mensaje claro.

Las imágenes se envían según el tier:
  - Pro: base64 inline (per doc).
  - Standard/Advanced: URL pública vía `image_url_provider` (R2/S3 — TODO si
    no está configurado, error indicando cómo activarlo).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Callable

from src.tiktok_shop.api.atlas_cloud import (
    AtlasCloudClient, AtlasCloudError, AtlasCloudTransient,
)
from src.tiktok_shop.config import ATLAS_TIERS, VIDEO_MODELS
from src.tiktok_shop.utils.image_url_provider import (
    get_atlas_image_ref, get_atlas_image_refs,
)


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_seedance_clips(
    *,
    tier: str,
    clip_specs: list[dict] | dict,
    photo_paths: list[str],
    resolution: str = "720p",
    output_dir: str | None = None,
    log_callback: LogCallback = _noop,
    kind: str = "scripted",
) -> list[str]:
    """Devuelve lista de paths a los MP4 generados.

    Args:
        tier: 'standard' | 'advanced' | 'pro'
        clip_specs:
            - Para standard/advanced: lista de dicts con shape:
                {clip_idx, duration, ref_photo_index, anchor_to_previous_clip_end, prompt}
            - Para pro: dict único:
                {duration, ref_photos_indices, prompt}
        photo_paths: lista de paths LOCALES a las fotos del producto.
        resolution: '480p' / '720p' / '1080p-SR' / '1440p-SR' (según tier).
        kind: 'scripted' (default — usa Seedance) | 'music' (usa Hailuo 02 Std
              vía fal.ai, ignorando `tier`). El user lo elige al crear el
              preset; el dispatcher rutea al modelo apropiado.
    """
    # Música → chain Hailuo 02 → Kling 2.1 → Wan 2.2-5b vía fal.ai.
    # El tier del preset se ignora (todos los music usan los mismos
    # modelos optimizados para vídeo de producto sin persona).
    # Devuelve solo paths (los renderers usados se ignoran aquí — el
    # caller que quiera trackearlos debe llamar `render_music_clips`).
    if kind == "music":
        paths, _renderers = render_music_clips(
            clip_specs=clip_specs, photo_paths=photo_paths,
            resolution=resolution, output_dir=output_dir,
            log_callback=log_callback,
        )
        return paths

    if tier not in ATLAS_TIERS:
        raise ValueError(f"Tier no soportado por Atlas: {tier}")

    client = AtlasCloudClient()
    if not client.is_available():
        raise AtlasCloudError(
            "Atlas Cloud no está configurado. Define ATLASCLOUD_API_KEY en .env "
            "para habilitar Seedance. Alternativas prompt-only: Veo3 / Nano Banana 2.",
            kind="auth",
        )

    model_def = VIDEO_MODELS[tier]
    model_id = model_def["model_id"]

    out_dir = output_dir or tempfile.mkdtemp(prefix=f"seedance_{tier}_")
    os.makedirs(out_dir, exist_ok=True)

    if tier == "pro":
        if not isinstance(clip_specs, dict):
            raise ValueError("Pro requiere clip_specs como dict (no lista).")
        return [_render_pro(
            client=client, model_id=model_id, spec=clip_specs,
            photo_paths=photo_paths, resolution=resolution,
            out_dir=out_dir, log_callback=log_callback,
        )]

    if not isinstance(clip_specs, list):
        raise ValueError(f"Tier {tier} requiere clip_specs como lista.")
    return asyncio.run(_render_image_to_video(
        client=client, model_id=model_id, clip_specs=clip_specs,
        photo_paths=photo_paths, resolution=resolution,
        tier=tier, out_dir=out_dir, log_callback=log_callback,
    ))


# ---------------------------------------------------------------------------
# Image-to-Video (Standard / Advanced) con anchoring
# ---------------------------------------------------------------------------
async def _render_image_to_video(
    *,
    client: AtlasCloudClient,
    model_id: str,
    clip_specs: list[dict],
    photo_paths: list[str],
    resolution: str,
    tier: str,
    out_dir: str,
    log_callback: LogCallback,
) -> list[str]:
    n = len(clip_specs)
    log_callback(f"🎬 Encolando {n} clips i2v ({tier}) en Atlas Cloud…")

    # Pre-resolver todas las refs (URLs públicas o base64) una sola vez por foto.
    # NOTA: en Standard/Advanced esto fallará con NotImplementedError si no hay
    # R2 configurado. La excepción burbujea limpia al runner.
    photo_refs = get_atlas_image_refs(photo_paths, tier=tier)

    tasks = []
    for spec in clip_specs:
        idx = spec["clip_idx"]
        ref_idx = spec.get("ref_photo_index")
        if ref_idx is None or not (0 <= ref_idx < len(photo_refs)):
            ref_idx = idx % len(photo_refs)

        # Anchoring: para clip K, last_image = foto del clip K+1 (continuidad).
        next_idx = idx + 1
        next_ref_idx = None
        if next_idx < n:
            next_ref_idx = clip_specs[next_idx].get("ref_photo_index")
            if next_ref_idx is None or not (0 <= next_ref_idx < len(photo_refs)):
                next_ref_idx = next_idx % len(photo_refs)
        last_image_ref = photo_refs[next_ref_idx] if next_ref_idx is not None else None

        tasks.append(_run_single_i2v(
            client=client, model_id=model_id, tier=tier, idx=idx, spec=spec,
            image_ref=photo_refs[ref_idx], last_image_ref=last_image_ref,
            resolution=resolution, out_dir=out_dir, log_callback=log_callback,
        ))

    paths = await asyncio.gather(*tasks)
    return list(paths)


def render_music_clips(
    *,
    clip_specs: list[dict],
    photo_paths: list[str],
    resolution: str = "720p",
    output_dir: str | None = None,
    log_callback: LogCallback = _noop,
) -> tuple[list[str], list[str]]:
    """Wrapper público para renderizar clips musicales con tracking del
    modelo usado. Devuelve `(paths, renderers_per_clip)` para que el
    runner pueda persistir qué modelo generó qué clip (visible en la UI
    de la cola). Si hay mezcla por failover, devuelve uno distinto por
    índice — ej. `["Hailuo 02", "Kling 2.1"]` si el clip 1 falló a Kling.
    """
    from src.tiktok_shop.api.fal_cloud import fal_is_configured
    if not fal_is_configured():
        raise AtlasCloudError(
            "Presets musicales requieren FAL_API_KEY (Hailuo/Kling/Wan vía fal.ai). "
            "Define FAL_API_KEY en .env o cambia el preset a kind=scripted.",
            kind="auth",
        )
    # Kill-switch para pausar la chain musical cuando fal.ai está mal —
    # evita seguir tirando dinero por jobs que probablemente se quedan
    # IN_QUEUE. Activar con `MUSIC_CHAIN_DISABLED=1` en .env del VPS.
    if (os.environ.get("MUSIC_CHAIN_DISABLED") or "").strip() in ("1", "true", "yes"):
        raise AtlasCloudError(
            "Chain musical pausada (MUSIC_CHAIN_DISABLED=1). "
            "Usa Veo 3 Flow manual mientras tanto, o desactiva el flag.",
            kind="disabled",
        )
    if not isinstance(clip_specs, list):
        raise ValueError("kind=music requiere clip_specs como lista (multi-shot).")
    out_dir = output_dir or tempfile.mkdtemp(prefix="music_clips_")
    os.makedirs(out_dir, exist_ok=True)
    return asyncio.run(_render_hailuo_clips(
        clip_specs=clip_specs, photo_paths=photo_paths,
        resolution=resolution, out_dir=out_dir,
        log_callback=log_callback,
    ))


async def _render_hailuo_clips(
    *,
    clip_specs: list[dict],
    photo_paths: list[str],
    resolution: str,
    out_dir: str,
    log_callback: LogCallback,
) -> tuple[list[str], list[str]]:
    """Multi-shot music vía Hailuo 02 (con fallback a Kling 2.1 y Wan
    2.2-5b por clip si Hailuo falla). Devuelve `(paths, renderers)` donde
    `renderers[i]` = nombre legible del modelo que generó el clip i.
    Por ejemplo ["Hailuo 02", "Kling 2.1"] si el clip 1 hizo failover.
    """
    n = len(clip_specs)
    log_callback(
        f"🎵 Encolando {n} clips music (Hailuo 02 → Kling 2.1 → Wan 2.2-5b "
        f"chain) en fal.ai…"
    )

    photo_refs = get_atlas_image_refs(photo_paths, tier="standard")
    hailuo_res = "768P"  # 512P queda muy bajo; 768P = TikTok ready y mismo coste

    tasks = []
    for spec in clip_specs:
        idx = spec["clip_idx"]
        ref_idx = spec.get("ref_photo_index")
        if ref_idx is None or not (0 <= ref_idx < len(photo_refs)):
            ref_idx = idx % len(photo_refs)
        # Hailuo soporta solo durations 6 y 10. Si el preset pide otra,
        # forzamos a 6 (lo más común y barato). Avisamos en log si redondea.
        raw_dur = int(spec.get("duration", 6))
        clamped_dur = 6 if raw_dur <= 7 else 10
        if clamped_dur != raw_dur:
            log_callback(
                f"⚠️ Clip {idx+1}: duración {raw_dur}s redondeada a {clamped_dur}s "
                f"(Hailuo 02 solo acepta 6 o 10)."
            )
        tasks.append(_run_via_hailuo(
            idx=idx, spec={**spec, "duration": clamped_dur},
            image_ref=photo_refs[ref_idx],
            hailuo_res=hailuo_res, out_dir=out_dir,
            log_callback=log_callback,
        ))

    results = await asyncio.gather(*tasks)
    paths = [r[0] for r in results]
    renderers = [r[1] for r in results]
    return paths, renderers


async def _run_via_hailuo(
    *,
    idx: int,
    spec: dict,
    image_ref: str,
    hailuo_res: str,
    out_dir: str,
    log_callback: LogCallback,
) -> tuple[str, str]:
    """Chain de fallback para clip music:
       Runware Hailuo 02 → fal Hailuo 02 → fal Kling 2.1 → fal Wan 2.2-5b.

    Runware tiene infraestructura independiente y solo cobra al completar,
    así que es el primario. Si falla, caemos a la familia fal (3 modelos).

    Devuelve (out_path, renderer_label) para tracking en la UI."""
    from src.tiktok_shop.api.fal_cloud import (
        FalCloudClient, FalCloudError, FalCloudTransient,
        HAILUO_STANDARD_MODEL_ID, KLING_V21_STANDARD_MODEL_ID,
        WAN_V22_5B_MODEL_ID, MUSIC_RENDERER_LABELS,
    )
    loop = asyncio.get_event_loop()
    duration = int(spec.get("duration", 6))
    out_path = os.path.join(out_dir, f"clip_{idx}.mp4")

    # NOTA: Runware Hailuo 02 SOLO soporta 16:9 horizontal (1366x768
    # o 1920x1080). Para TikTok necesitamos 9:16 portrait → no sirve.
    # Investigar Runware Kling 2.1 / Wan 2.5 que sí permiten 9:16
    # (model AIRs pendientes de verificar). Mientras tanto, chain
    # fal-only: Hailuo → Kling → Wan, los 3 ya soportan vertical.
    fal = FalCloudClient()
    # ---- 1) Hailuo 02 Standard ----
    try:
        return await _run_one_fal_job(
            fal=fal, loop=loop,
            submit_fn=lambda: fal.submit_hailuo_i2v(
                image_url=image_ref, prompt=spec["prompt"],
                duration=duration, resolution=hailuo_res,
            ),
            cost_fn=lambda req_id: _record_music_cost(
                model_id=HAILUO_STANDARD_MODEL_ID, duration_s=duration,
                resolution=hailuo_res, idx=idx, req_id=req_id,
            ),
            renderer_label=MUSIC_RENDERER_LABELS[HAILUO_STANDARD_MODEL_ID],
            idx=idx, out_path=out_path, log_callback=log_callback,
        )
    except (FalCloudError, FalCloudTransient) as e_hailuo:
        log_callback(
            f"🔁 Clip {idx+1}: Hailuo falló ({str(e_hailuo)[:100]}). "
            f"Intentando Kling 2.1…"
        )

    # ---- 2) Kling 2.1 Standard ----
    # Kling solo permite 5 o 10s. Si Hailuo era 6s, Kling lo redondea a 5.
    kling_dur = 5 if duration <= 7 else 10
    try:
        return await _run_one_fal_job(
            fal=fal, loop=loop,
            submit_fn=lambda: fal.submit_kling_i2v(
                image_url=image_ref, prompt=spec["prompt"], duration=kling_dur,
            ),
            cost_fn=lambda req_id: _record_music_cost(
                model_id=KLING_V21_STANDARD_MODEL_ID, duration_s=kling_dur,
                resolution=hailuo_res, idx=idx, req_id=req_id,
            ),
            renderer_label=MUSIC_RENDERER_LABELS[KLING_V21_STANDARD_MODEL_ID],
            idx=idx, out_path=out_path, log_callback=log_callback,
        )
    except (FalCloudError, FalCloudTransient) as e_kling:
        log_callback(
            f"🔁 Clip {idx+1}: Kling también falló ({str(e_kling)[:100]}). "
            f"Último intento: Wan 2.2-5b…"
        )

    # ---- 3) Wan 2.2-5b (último recurso) ----
    # Wan máx ~6.7s a 24fps. Si pidieron 10s, le pedimos su máximo.
    wan_dur = min(duration, 6)
    try:
        return await _run_one_fal_job(
            fal=fal, loop=loop,
            submit_fn=lambda: fal.submit_wan_i2v(
                image_url=image_ref, prompt=spec["prompt"],
                duration_s=wan_dur, resolution="720p", aspect_ratio="9:16",
            ),
            cost_fn=lambda req_id: _record_music_cost(
                model_id=WAN_V22_5B_MODEL_ID, duration_s=wan_dur,
                resolution=hailuo_res, idx=idx, req_id=req_id,
            ),
            renderer_label=MUSIC_RENDERER_LABELS[WAN_V22_5B_MODEL_ID],
            idx=idx, out_path=out_path, log_callback=log_callback,
        )
    except (FalCloudError, FalCloudTransient) as e_wan:
        log_callback(
            f"❌ Clip {idx+1}: Hailuo, Kling Y Wan fallaron. fal.ai globalmente "
            f"saturada — reintenta en unas horas o usa Veo 3 Flow."
        )
        raise RuntimeError(
            f"Los 3 providers musicales fallaron en clip {idx+1}. "
            f"Último error (Wan): {e_wan}"
        ) from e_wan


async def _run_via_runware_hailuo(
    *,
    idx: int,
    spec: dict,
    image_ref: str,
    out_path: str,
    log_callback: LogCallback,
) -> tuple[str, str]:
    """Genera 1 clip con Runware Hailuo 02 Standard. Sin internal fallback —
    si falla, el caller (chain) probará otros providers (fal.ai)."""
    from src.tiktok_shop.api.runware_cloud import (
        RunwareClient, HAILUO_02_STD_MODEL_ID,
    )

    loop = asyncio.get_event_loop()
    rw = RunwareClient()
    duration = int(spec.get("duration", 5))
    # Runware Hailuo acepta 5 o 10 (no 6 como fal). Mapeamos 6→5.
    if duration not in (5, 10):
        duration = 5 if duration <= 7 else 10

    job = await loop.run_in_executor(
        None,
        lambda: rw.submit_i2v(
            model_id=HAILUO_02_STD_MODEL_ID,
            image_ref=image_ref,
            prompt=spec["prompt"],
            duration_s=duration,
            width=1080, height=1920,
        ),
    )
    log_callback(
        f"⏳ Clip {idx+1} Runware Hailuo task {job.task_uuid[:8]} encolado ({duration}s)…"
    )
    # Runware cobra al completar — registramos coste TRAS éxito.

    def _hb(elapsed: int, status: str) -> None:
        log_callback(
            f"⏳ Clip {idx+1} Runware: {elapsed//60}m{elapsed%60:02d}s "
            f"(status={status})…"
        )

    await loop.run_in_executor(
        None, lambda: rw.wait(job, on_heartbeat=_hb),
    )
    await loop.run_in_executor(
        None, lambda: rw.download(job.output_url or "", out_path),
    )
    # Coste tras descarga exitosa (Runware solo cobra completados).
    try:
        from src.cost_tracking import record_runware_cloud
        record_runware_cloud(
            model_id=HAILUO_02_STD_MODEL_ID,
            duration_s=duration,
            detail=f"clip {idx+1} · task {job.task_uuid[:8]}",
        )
    except Exception:
        pass
    log_callback(f"✅ Clip {idx+1} entregado por Runware Hailuo 02")
    return out_path, "Hailuo 02 (Runware)"


async def _run_one_fal_job(
    *,
    fal,
    loop,
    submit_fn,
    cost_fn,
    renderer_label: str,
    idx: int,
    out_path: str,
    log_callback: LogCallback,
) -> tuple[str, str]:
    """Submit + wait + download genérico para cualquier modelo fal.
    Devuelve (out_path, renderer_label) en éxito. Levanta FalCloud* en fallo.

    REALIDAD DE FACTURACIÓN (confirmada empíricamente 2026-05-26):
    fal.ai COBRA AL ENCOLAR, no solo al completar. Si el job se queda
    IN_QUEUE forever y nuestro timeout salta, el cargo ya se hizo —
    intentamos cancel best-effort para liberar GPU. Registramos coste
    AL SUBMIT para que el panel /costs refleje el gasto real.
    """
    job = await loop.run_in_executor(None, submit_fn)
    log_callback(
        f"⏳ Clip {idx+1} {renderer_label} req {job.request_id} encolado…"
    )
    # Coste registrado al submit — fal ya cobró el slot.
    try:
        cost_fn(job.request_id)
    except Exception:
        pass

    def _hb(elapsed: int, status: str) -> None:
        log_callback(
            f"⏳ Clip {idx+1} {renderer_label}: {elapsed//60}m{elapsed%60:02d}s "
            f"(status={status})…"
        )

    try:
        await loop.run_in_executor(
            None, lambda: fal.wait(job, on_heartbeat=_hb),
        )
    except Exception:
        # Timeout o fallo del wait — best-effort cancel para liberar la
        # GPU (a veces fal devuelve crédito si el job nunca empezó).
        try:
            await loop.run_in_executor(
                None, lambda: fal.cancel_request(job.model_id, job.request_id),
            )
            log_callback(
                f"🛑 Clip {idx+1} {renderer_label}: cancel enviado a fal.ai "
                f"(req {job.request_id[:8]})."
            )
        except Exception:
            pass
        raise

    await loop.run_in_executor(
        None, lambda: fal.download(job.output_url or "", out_path),
    )
    log_callback(f"✅ Clip {idx+1} entregado por {renderer_label}")
    return out_path, renderer_label


def _record_music_cost(
    *,
    model_id: str,
    duration_s: int,
    resolution: str,
    idx: int,
    req_id: str,
) -> None:
    """Dispatcher de cost tracking según modelo. Cada uno tiene su
    helper específico con su tarifa propia → línea separada en /costs."""
    from src.tiktok_shop.api.fal_cloud import (
        HAILUO_STANDARD_MODEL_ID, KLING_V21_STANDARD_MODEL_ID, WAN_V22_5B_MODEL_ID,
    )
    detail = f"clip {idx+1} · req {req_id[:8]}"
    if model_id == HAILUO_STANDARD_MODEL_ID:
        from src.cost_tracking import record_hailuo_cloud
        record_hailuo_cloud(duration_s=duration_s, resolution=resolution, detail=detail)
    elif model_id == KLING_V21_STANDARD_MODEL_ID:
        from src.cost_tracking import record_kling_cloud
        record_kling_cloud(duration_s=duration_s, detail=detail)
    elif model_id == WAN_V22_5B_MODEL_ID:
        from src.cost_tracking import record_wan_cloud
        record_wan_cloud(duration_s=duration_s, resolution=resolution, detail=detail)


async def _run_via_atlas(
    *,
    client: AtlasCloudClient,
    model_id: str,
    tier: str,
    idx: int,
    spec: dict,
    image_ref: str,
    last_image_ref: str | None,
    resolution: str,
    out_path: str,
    log_callback: LogCallback,
) -> str:
    """Submit + wait + download en Atlas Cloud. Levanta AtlasCloudTransient
    si la cola se atasca/timeout. El caller decide si reintenta en fal.ai."""
    loop = asyncio.get_event_loop()

    def _submit():
        return client.submit_image_to_video(
            model_id=model_id,
            image_url=image_ref,
            last_image_url=last_image_ref,
            prompt=spec["prompt"],
            duration=int(spec.get("duration", 5)),
            resolution=resolution,
            aspect_ratio="9:16",
        )

    job = await loop.run_in_executor(None, _submit)
    log_callback(f"⏳ Clip {idx+1}: Atlas job {job.job_id} encolado, esperando…")

    # Atlas factura al encolar — registramos coste aquí.
    try:
        from src.cost_tracking import record_atlas_cloud
        record_atlas_cloud(
            seconds=int(spec.get("duration", 5)),
            tier=tier,
            resolution=resolution,
            detail=f"clip {idx+1} · job {job.job_id[:8]}",
        )
    except Exception:
        pass

    def _hb(elapsed: int, status: str) -> None:
        log_callback(
            f"⏳ Clip {idx+1} Atlas: {elapsed//60}m{elapsed%60:02d}s "
            f"(status={status})…"
        )

    final_job = await loop.run_in_executor(
        None, lambda: client.wait(job.job_id, on_heartbeat=_hb)
    )
    await loop.run_in_executor(
        None, lambda: client.download(final_job.output_url or "", out_path),
    )
    log_callback(f"✅ Clip {idx+1} entregado por Atlas Cloud")
    return out_path


async def _run_via_fal(
    *,
    tier: str,
    idx: int,
    spec: dict,
    image_ref: str,
    last_image_ref: str | None,
    resolution: str,
    out_path: str,
    log_callback: LogCallback,
    fallback_label: str = "",
) -> str:
    """Submit + wait + download en fal.ai. Levanta excepciones FalCloud*
    si falla. `fallback_label` se añade al detail del coste para distinguir
    'primario' vs 'fallback de Atlas' en /costs."""
    from src.tiktok_shop.api.fal_cloud import FalCloudClient

    loop = asyncio.get_event_loop()
    fal = FalCloudClient()
    fal_job = await loop.run_in_executor(
        None,
        lambda: fal.submit_image_to_video(
            tier=tier,
            image_url=image_ref,
            prompt=spec["prompt"],
            duration=int(spec.get("duration", 5)),
            resolution=resolution,
            aspect_ratio="9:16",
            last_image_url=last_image_ref,
        ),
    )
    log_callback(f"⏳ Clip {idx+1} fal.ai req {fal_job.request_id} encolado…")
    # Coste al encolar — fal cobra ahí (no al completar como pensaba).
    try:
        from src.cost_tracking import record_fal_cloud
        detail = f"clip {idx+1} · req {fal_job.request_id[:8]}"
        if fallback_label:
            detail += f" ({fallback_label})"
        record_fal_cloud(
            seconds=int(spec.get("duration", 5)),
            tier=tier,
            resolution=resolution,
            detail=detail,
        )
    except Exception:
        pass

    def _hb(elapsed: int, status: str) -> None:
        log_callback(
            f"⏳ Clip {idx+1} fal.ai: {elapsed//60}m{elapsed%60:02d}s "
            f"(status={status})…"
        )

    try:
        await loop.run_in_executor(
            None, lambda: fal.wait(fal_job, tier=tier, on_heartbeat=_hb),
        )
    except Exception:
        # Best-effort cancel para liberar GPU si nuestro timeout saltó.
        try:
            await loop.run_in_executor(
                None, lambda: fal.cancel_request(fal_job.model_id, fal_job.request_id),
            )
        except Exception:
            pass
        raise
    await loop.run_in_executor(
        None, lambda: fal.download(fal_job.output_url or "", out_path),
    )
    log_callback(f"✅ Clip {idx+1} entregado por fal.ai")
    return out_path


async def _run_single_i2v(
    *,
    client: AtlasCloudClient,
    model_id: str,
    tier: str,
    idx: int,
    spec: dict,
    image_ref: str,
    last_image_ref: str | None,
    resolution: str,
    out_dir: str,
    log_callback: LogCallback,
) -> str:
    """Dispatcher con preferencia de provider por tier:

      - 🟢 standard / 🟡 advanced  → fal.ai PRIMARIO (cola más estable
        para Seedance Lite); Atlas como fallback si fal cae.
      - 🔴 pro                     → Atlas Cloud PRIMARIO (donde ha
        funcionado mejor históricamente); fal como fallback.

    Si fal.ai no está configurado (FAL_API_KEY ausente), todo va por
    Atlas sin failover.
    """
    from src.tiktok_shop.api.fal_cloud import (
        fal_is_configured, FalCloudError, FalCloudTransient,
    )

    out_path = os.path.join(out_dir, f"clip_{idx}.mp4")
    fal_ready = fal_is_configured()
    prefer_fal = fal_ready and tier in ("standard", "advanced")

    # PRIMARIO = fal.ai (Standard/Advanced cuando FAL configurado)
    if prefer_fal:
        try:
            return await _run_via_fal(
                tier=tier, idx=idx, spec=spec,
                image_ref=image_ref, last_image_ref=last_image_ref,
                resolution=resolution, out_path=out_path,
                log_callback=log_callback,
            )
        except (FalCloudError, FalCloudTransient) as e_fal:
            log_callback(
                f"🔁 Clip {idx+1}: fal.ai falló ({str(e_fal)[:120]}). "
                f"Reintentando en Atlas Cloud…"
            )
            try:
                return await _run_via_atlas(
                    client=client, model_id=model_id, tier=tier, idx=idx,
                    spec=spec, image_ref=image_ref, last_image_ref=last_image_ref,
                    resolution=resolution, out_path=out_path,
                    log_callback=log_callback,
                )
            except AtlasCloudTransient as e_atlas:
                log_callback(
                    f"❌ Clip {idx+1}: fal.ai Y Atlas fallaron. "
                    f"fal: {str(e_fal)[:80]}. Atlas: {str(e_atlas)[:80]}."
                )
                raise RuntimeError(
                    f"Ambos proveedores fallaron en clip {idx+1}. "
                    f"fal: {e_fal}. Atlas: {e_atlas}"
                ) from e_atlas

    # PRIMARIO = Atlas Cloud (tier Pro, o sin FAL configurado)
    try:
        return await _run_via_atlas(
            client=client, model_id=model_id, tier=tier, idx=idx,
            spec=spec, image_ref=image_ref, last_image_ref=last_image_ref,
            resolution=resolution, out_path=out_path,
            log_callback=log_callback,
        )
    except AtlasCloudTransient as e_atlas:
        if not fal_ready:
            log_callback(
                f"❌ Clip {idx+1} Atlas timeout y fal.ai NO configurado "
                f"(define FAL_API_KEY para failover). Propagando error."
            )
            raise
        log_callback(
            f"🔁 Clip {idx+1}: Atlas falló ({str(e_atlas)[:120]}). "
            f"Reintentando en fal.ai…"
        )
        try:
            return await _run_via_fal(
                tier=tier, idx=idx, spec=spec,
                image_ref=image_ref, last_image_ref=last_image_ref,
                resolution=resolution, out_path=out_path,
                log_callback=log_callback,
                fallback_label="fallback Atlas",
            )
        except (FalCloudError, FalCloudTransient) as e_fal:
            log_callback(
                f"❌ Clip {idx+1}: Atlas Y fal.ai fallaron. "
                f"Atlas: {str(e_atlas)[:80]}. fal: {str(e_fal)[:80]}."
            )
            raise RuntimeError(
                f"Ambos proveedores fallaron en clip {idx+1}. "
                f"Atlas: {e_atlas}. fal: {e_fal}"
            ) from e_fal


# ---------------------------------------------------------------------------
# Reference-to-Video (Pro)
# ---------------------------------------------------------------------------
def _render_pro(
    *,
    client: AtlasCloudClient,
    model_id: str,
    spec: dict,
    photo_paths: list[str],
    resolution: str,
    out_dir: str,
    log_callback: LogCallback,
) -> str:
    log_callback("🎬 Encolando 1 clip ref-to-video Pro en Atlas Cloud…")

    ref_indices = spec.get("ref_photos_indices") or list(range(min(len(photo_paths), 9)))
    selected = [photo_paths[i] for i in ref_indices if 0 <= i < len(photo_paths)]
    if not selected:
        selected = photo_paths[:1]
    if len(selected) > 9:
        selected = selected[:9]

    refs = [get_atlas_image_ref(p, tier="pro") for p in selected]

    job = client.submit_reference_to_video(
        model_id=model_id,
        reference_images=refs,
        prompt=spec["prompt"],
        duration=int(spec.get("duration", 15)),
        resolution=resolution,
        ratio="9:16",
        generate_audio=False,
        watermark=False,
    )
    log_callback(f"⏳ Pro job {job.job_id} encolado, esperando…")
    # Registrar coste Atlas en submit (no en complete) — Atlas factura
    # al encolar.
    try:
        from src.cost_tracking import record_atlas_cloud
        record_atlas_cloud(
            seconds=int(spec.get("duration", 15)),
            tier="pro",
            resolution=resolution,
            detail=f"pro ref2v · job {job.job_id[:8]}",
        )
    except Exception:
        pass

    def _hb_pro(elapsed: int, status: str) -> None:
        log_callback(
            f"⏳ Pro: {elapsed//60}m{elapsed%60:02d}s (status={status})…"
        )

    try:
        final_job = client.wait(job.job_id, on_heartbeat=_hb_pro)
    except AtlasCloudTransient as e:
        # Per doc nota: si "9:16" falla, probar "adaptive" como fallback.
        log_callback(f"⚠️ Pro job timeout/transient ({e}). Reintentando con ratio='adaptive'…")
        job2 = client.submit_reference_to_video(
            model_id=model_id, reference_images=refs, prompt=spec["prompt"],
            duration=int(spec.get("duration", 15)), resolution=resolution,
            ratio="adaptive", generate_audio=False, watermark=False,
        )
        final_job = client.wait(job2.job_id, on_heartbeat=_hb_pro)

    out_path = os.path.join(out_dir, "clip_pro.mp4")
    client.download(final_job.output_url or "", out_path)
    log_callback(f"✅ Clip Pro descargado: {os.path.basename(out_path)}")
    return out_path
