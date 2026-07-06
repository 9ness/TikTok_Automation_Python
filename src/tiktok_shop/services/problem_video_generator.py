"""Generador de vídeos que atacan el PROBLEMA del cliente (MOFU/TOFU).

A partir del producto (nombre + análisis IA), hace un análisis profundo de
cliente/dolor y devuelve 2-3 conceptos de vídeo GANADORES listos para Veo 3,
cada uno con su prompt + textos en pantalla + ángulo/emoción atacada + caption.

Sube el nivel frente a los hooks BOFU (parte baja del embudo): en vez de
"compra ya + nombre del producto", ataca el problema real y la emoción que
hace que la persona QUIERA comprar. Consejo del operador: los vídeos BOFU no
tiran, hay que atacar el dolor.

Usa `gemini.generate_text` (con fallback a OpenAI si Gemini sin cuota).
"""

from __future__ import annotations

import json
from typing import Any

from src.tiktok_shop.api import gemini
from src.tiktok_shop.api.gemini import load_system_prompt
from src.tiktok_shop.models import Product
from src.tiktok_shop.services.hooks_generator import _product_context_block


def generate_problem_videos(
    product: Product,
    *,
    n: int = 3,
    language: str | None = None,
) -> dict[str, Any]:
    """Genera N (2-3) conceptos de vídeo que atacan el problema del cliente.

    Returns:
        dict con `ideal_customer`, `sale` (análisis) y
        `videos: [{concept, emotion, angle, veo3_prompt, on_screen_text[], caption}]`.
    """
    n = max(1, min(3, int(n)))
    lang = "en" if (language or product.language or "es").lower().startswith("en") else "es"
    lang_name = "English" if lang == "en" else "Spanish (Spain)"
    system = load_system_prompt("problem_video_director.md")

    user_prompt = (
        f"{_product_context_block(product)}\n"
        f"OUTPUT LANGUAGE (para on_screen_text y caption): {lang} ({lang_name}).\n"
        f"El veo3_prompt SIEMPRE en inglés.\n\n"
        f"Analiza el producto y diseña EXACTAMENTE {n} conceptos de vídeo, cada "
        f"uno atacando un ángulo/emoción DISTINTO. Devuelve SOLO el JSON con "
        f"`ideal_customer`, `sale` y `videos`."
    )

    result = gemini.generate_text(
        system_prompt=system,
        user_prompt=user_prompt,
        model="gemini-2.5-flash",
        expect_json=True,
        temperature=0.85,
    )
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    videos: list[dict[str, Any]] = []
    for v in (data.get("videos") or [])[:n]:
        if not isinstance(v, dict):
            continue
        veo = str(v.get("veo3_prompt", "")).strip()
        if not veo:
            continue
        # 1 texto gancho + 1 CTA (nada de secuencias largas). Compat: si el
        # modelo devuelve `on_screen_text` como lista, usa el 1º como hook.
        hook = str(v.get("hook_text", "")).strip()
        if not hook:
            ost = v.get("on_screen_text") or []
            hook = str(ost[0]).strip() if ost else ""
        videos.append({
            "concept": str(v.get("concept", ""))[:80],
            "format": str(v.get("format", ""))[:80],
            "emotion": str(v.get("emotion", ""))[:80],
            "angle": str(v.get("angle", ""))[:240],
            "veo3_prompt": veo[:2000],
            "spoken_line": str(v.get("spoken_line", ""))[:300],
            "hook_text": hook[:120],
            "cta_text": str(v.get("cta_text", ""))[:60],
            "caption": str(v.get("caption", ""))[:300],
        })

    return {
        "ideal_customer": data.get("ideal_customer") if isinstance(data.get("ideal_customer"), dict) else {},
        "sale": data.get("sale") if isinstance(data.get("sale"), dict) else {},
        "videos": videos,
        "language": lang,
    }
