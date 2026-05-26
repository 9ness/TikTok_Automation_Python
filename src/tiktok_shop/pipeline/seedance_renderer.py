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
    """
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

    # fal también factura al encolar (los webhooks devuelven coste al
    # completar pero el cargo es inmediato). Registramos al submit.
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

    await loop.run_in_executor(
        None, lambda: fal.wait(fal_job, tier=tier, on_heartbeat=_hb),
    )
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
