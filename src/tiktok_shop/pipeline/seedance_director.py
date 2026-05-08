"""Seedance director — convierte estrategia en prompts para los 3 tiers.

- `standard` y `advanced` cargan `seedance_image_to_video_director.md` y
  devuelven una **lista de clips** (multi_clip_anchor).
- `pro` carga `seedance_pro_director.md` y devuelve un **dict único**
  (single_shot_multishot, multi-ref).

El renderer (seedance_renderer.py) consume el output según el tier.
"""

from __future__ import annotations

import json

from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt


def generate_seedance_prompts(
    strategy: dict,
    *,
    tier: str = "standard",
    style: str = "asmr_macro",
    photos_count: int = 3,
    clip_photo_overrides: list[int] | None = None,
    pro_ref_photo_overrides: list[int] | None = None,
    camera_style: str = "varied_contained",
) -> list[dict] | dict:
    """Genera los prompts Seedance.

    Args:
        clip_photo_overrides: para tiers `standard`/`advanced`, lista de índices
            de foto a usar por clip (sobrescribe la auto-asignación del director).
            Ejemplo: `[0, 2, 1]` → clip 0 usa foto 0, clip 1 usa foto 2, clip 2 usa foto 1.
            Longitud debe coincidir con el número de clips del director (si difiere,
            se aplica solo a los que coincidan; el resto mantiene la decisión IA).
        pro_ref_photo_overrides: para tier `pro`, lista de índices de fotos a usar
            como referencia (max 9). Sobrescribe `ref_photos_indices` del director.

    Returns:
        - Si tier ∈ {standard, advanced}: `list[dict]`, uno por clip, shape:
            {clip_idx, duration, ref_photo_index, use_first_frame_anchor,
             anchor_to_previous_clip_end, prompt}
        - Si tier == pro: `dict`, shape:
            {duration, ref_photos_indices, ref_videos, ref_audios, prompt}
    """
    if tier == "pro":
        result = _generate_pro(
            strategy, style=style, photos_count=photos_count,
            camera_style=camera_style,
        )
        if pro_ref_photo_overrides is not None and isinstance(result, dict):
            # Filtra a índices válidos (<photos_count) y respeta el max 9 de Pro
            valid = [i for i in pro_ref_photo_overrides if 0 <= i < photos_count]
            if valid:
                result["ref_photos_indices"] = valid[:9]
        return result

    result = _generate_image_to_video(
        strategy, tier=tier, style=style, photos_count=photos_count,
        camera_style=camera_style,
    )
    if clip_photo_overrides is not None and isinstance(result, list):
        for i, override_idx in enumerate(clip_photo_overrides):
            if i >= len(result):
                break
            if 0 <= override_idx < photos_count:
                result[i]["ref_photo_index"] = override_idx
                # Si el clip era anclado, mantenemos el flag pero el anchor
                # podría haber sido a otro clip distinto — el renderer ya
                # hace su propia lógica de last_image entre clips consecutivos
                # usando los `ref_photo_index` actualizados.
    return result


def _generate_image_to_video(
    strategy: dict, *, tier: str, style: str, photos_count: int,
    camera_style: str = "varied_contained",
) -> list[dict]:
    if not is_configured():
        return _mock_image_to_video(strategy)

    system = load_system_prompt("seedance_image_to_video_director.md")
    user_msg = (
        f"Tier: {tier}\n"
        f"Style preference: {style}\n"
        f"Camera style (FUNC 5 strategy): {camera_style}\n"
        f"  - 'continuous_slow': cámara muy lenta, planos largos cinematográficos, "
        f"transiciones suaves entre clips (estrategia Cinematográfico).\n"
        f"  - 'varied_contained': cámara variada por clip (push-in, orbit, pan) "
        f"pero sin movimientos bruscos. Cambios de plano más perceptibles "
        f"(estrategia Dinámico TikTok — DEFAULT).\n"
        f"Available reference photos: {photos_count}\n"
        f"Strategy (JSON):\n{json.dumps(strategy, ensure_ascii=False)}\n\n"
        f"Return strict JSON array only."
    )
    result = generate_json(system, user_msg, temperature=0.7)
    if isinstance(result, dict):
        # Algunos modelos envuelven en {"prompts": [...]} o {"clips": [...]}
        for v in result.values():
            if isinstance(v, list):
                return v
    if not isinstance(result, list):
        raise ValueError(f"Seedance i2v director devolvió shape inesperado: {type(result)}")
    return result


def _generate_pro(
    strategy: dict, *, style: str, photos_count: int,
    camera_style: str = "varied_contained",
) -> dict:
    if not is_configured():
        return _mock_pro(strategy, photos_count=photos_count)

    system = load_system_prompt("seedance_pro_director.md")
    user_msg = (
        f"Tier: pro (reference-to-video)\n"
        f"Style preference: {style}\n"
        f"Camera style (FUNC 5 strategy): {camera_style}\n"
        f"Available reference photos: {photos_count} (use up to 9)\n"
        f"Strategy (JSON):\n{json.dumps(strategy, ensure_ascii=False)}\n\n"
        f"Return strict JSON object only (NOT array)."
    )
    result = generate_json(system, user_msg, temperature=0.7)
    if isinstance(result, list) and result:
        # tolerancia: algunos modelos devuelven array de 1 elemento
        result = result[0]
    if not isinstance(result, dict):
        raise ValueError(f"Seedance pro director devolvió shape inesperado: {type(result)}")
    return result


def _mock_image_to_video(strategy: dict) -> list[dict]:
    structure = strategy.get("video_structure", [])
    return [
        {
            "clip_idx": i,
            "duration": clip.get("duration_seconds", 5),
            "ref_photo_index": i,
            "use_first_frame_anchor": i > 0,
            "anchor_to_previous_clip_end": i - 1 if i > 0 else None,
            "prompt": (
                f"[CAMERA]: slow push-in. [SUBJECT]: product from ref photo. "
                f"[STYLE]: cinematic commercial. [NEGATIVE]: text artifacts, faces, fast cuts."
                f" -- (mock para clip {i+1})"
            ),
        }
        for i, clip in enumerate(structure)
    ]


def _mock_pro(strategy: dict, *, photos_count: int) -> dict:
    structure = strategy.get("video_structure", [])
    duration = sum(c.get("duration_seconds", 5) for c in structure) or 15
    n_photos = min(photos_count, 4)
    return {
        "duration": duration,
        "ref_photos_indices": list(range(n_photos)),
        "ref_videos": [],
        "ref_audios": [],
        "prompt": (
            "Shot 1 (0-5s): slow push-in on product, soft studio lighting, cinematic. "
            "Shot 2 (5-10s): orbit close-up, same lighting. "
            "Shot 3 (10-15s): macro detail, ASMR feel. "
            "Smooth transitions between shots. Consistent product appearance and lighting. "
            "-- (mock — Gemini no configurado)"
        ),
    }
