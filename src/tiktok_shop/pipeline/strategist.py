"""Content strategist — toma análisis del producto + audiencia + hook category
y devuelve hook_text, voiceover_script, video_structure por clip, hashtags.

⚠️ Bug-fix v3 (BUG 1): el strategist puede generar voiceover_script demasiado
largo para la duración pedida. MiniMax habla a ~3 palabras/segundo en español;
si el guion excede el límite, el audio dura más que el vídeo y el editor tiene
que truncarlo (mejor caso) o se generan loops visuales (peor caso, ya
arreglado en editor.py pero hay que evitarlo en origen).

`generate_strategy()` ahora valida el word-count y reintenta hasta `max_retries`
veces pidiendo a Gemini que acorte. Si tras los reintentos sigue largo, recorta
duro al límite y loguea warning.
"""

from __future__ import annotations

import json
import re

from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt
from src.tiktok_shop.utils.logging_setup import log_info, log_warning


# Palabras por segundo a las que habla MiniMax en español. Bajado de 3.0
# a 2.7 (BUG B mayo 2026) — con 3.0 el guion de 45 palabras producía audio
# de 17-19s para vídeos de 15s, generando overflow que el editor truncaba
# con fade-out perdiendo el CTA final. Con 2.7 wps, 15s × 2.7 = 40 palabras
# máximo → audio cabe en ~14-15s con margen sin truncar.
WORDS_PER_SECOND_ES = 2.7

# Ratio mínimo respecto al máximo. Gemini tiende a errar por defecto y
# generar guiones cortos (20 palabras para 15s, ~7s de audio) — quedaba
# vídeo "vacío" sin contenido en los últimos segundos. Con MIN_WORDS_RATIO
# = 0.75 forzamos un objetivo de 30 palabras (75% de 40) para 15s, lo que
# da ~11s de audio sobre 14s de video → cobertura natural sin overflow.
MIN_WORDS_RATIO = 0.75

_LOGGER = "tiktok_shop.strategist"


def max_words_for_duration(duration_seconds: int) -> int:
    """Devuelve el límite duro de palabras para una duración dada.

    Match exacto con la tabla del system prompt `content_strategist.md`.
    """
    return int(duration_seconds * WORDS_PER_SECOND_ES)


def min_words_for_duration(duration_seconds: int) -> int:
    """Devuelve el OBJETIVO MÍNIMO de palabras para una duración dada.

    Si el strategist devuelve menos de este valor, reintentamos pidiéndole
    que extienda el script (Gemini suele quedarse corto si solo le damos
    un máximo). El mínimo es ~75% del máximo.
    """
    return int(max_words_for_duration(duration_seconds) * MIN_WORDS_RATIO)


def count_words(text: str) -> int:
    """Cuenta palabras separadas por whitespace, ignorando puntuación."""
    if not text:
        return 0
    cleaned = re.sub(r"[^\w\s]", " ", text)
    return len([w for w in cleaned.split() if w])


def generate_strategy(
    product_analysis: dict,
    *,
    audience: str,
    hook_category: str,
    duration_seconds: int = 15,
    language: str = "es",
    product_name: str = "",
    extra_directives: str = "",
    max_retries: int = 2,
    video_strategy: str = "dynamic",
) -> dict:
    """Devuelve dict con shape definido en `prompts/content_strategist.md`.

    Tras el primer call, valida word-count del `voiceover_script`. Si excede
    el límite para `duration_seconds`, reintenta hasta `max_retries` veces
    pidiendo a Gemini que acorte. Si tras todos los reintentos sigue largo,
    trunca duro al número de palabras del límite y loguea warning.
    """
    if not is_configured():
        return _mock_strategy(duration_seconds, language)

    # FUNC 5: el strategist debe saber cuál es la estrategia para que el
    # `voiceover_script` y la `video_structure` encajen con el ritmo visual
    # (pocos clips largos vs muchos clips cortos).
    _STRATEGY_DESCRIPTIONS = {
        "cinematic": (
            "🎬 CINEMATOGRÁFICO: pocos clips largos (5-12s cada uno), continuidad "
            "visual máxima, un solo plano evolucionando lentamente. El voiceover "
            "debe ser CALMADO y elegante, frases más largas, ritmo pausado."
        ),
        "dynamic": (
            "⚡ DINÁMICO TIKTOK: muchos clips cortos (4-5s cada uno), cambios de "
            "plano frecuentes para máxima retención. El voiceover debe ser "
            "ENERGÉTICO, frases cortas y directas, ritmo rápido. Cada clip "
            "puede tener su micro-mensaje."
        ),
    }
    strategy_description = _STRATEGY_DESCRIPTIONS.get(
        video_strategy, _STRATEGY_DESCRIPTIONS["dynamic"],
    )

    system = load_system_prompt("content_strategist.md")
    base_user_msg = (
        f"Product name: {product_name or '(unnamed)'}\n"
        f"Product analysis (JSON):\n{json.dumps(product_analysis, ensure_ascii=False)}\n\n"
        f"Selected audience: {audience}\n"
        f"Selected hook category: {hook_category}\n"
        f"Duration target: {duration_seconds} seconds\n"
        f"Output language: {language}\n"
        f"Video strategy: {strategy_description}\n"
        f"Extra directives: {extra_directives or '(none)'}\n\n"
        f"Return strict JSON only."
    )

    max_words = max_words_for_duration(duration_seconds)
    min_words = min_words_for_duration(duration_seconds)

    user_msg = base_user_msg
    last_strategy: dict = {}
    for attempt in range(max_retries + 1):
        last_strategy = generate_json(system, user_msg, temperature=0.85)
        script = last_strategy.get("voiceover_script", "") or ""
        n_words = count_words(script)

        # Caso OK: dentro de [min, max].
        if min_words <= n_words <= max_words:
            log_info(_LOGGER, "Strategy OK",
                     duration=duration_seconds, n_words=n_words,
                     min=min_words, max=max_words, attempt=attempt + 1)
            return last_strategy

        # Excede el límite máximo — reintentar pidiendo recorte explícito.
        if n_words > max_words:
            if attempt < max_retries:
                log_warning(_LOGGER, "Voiceover excede límite, pidiendo recorte",
                            duration=duration_seconds, n_words=n_words,
                            limit=max_words, attempt=attempt + 1)
                user_msg = (
                    f"{base_user_msg}\n\n"
                    f"⚠️ ACORTA: tu intento anterior tenía {n_words} palabras pero el "
                    f"LÍMITE DURO para {duration_seconds}s es {max_words} palabras. "
                    f"Reescribe `voiceover_script` con MÁXIMO {max_words} palabras "
                    f"manteniendo hook + idea principal + CTA. Quita relleno."
                )
                continue
            # Último intento sin éxito — truncar duro.
            log_warning(_LOGGER, "Voiceover sigue excediendo límite tras retries — truncando",
                        n_words=n_words, limit=max_words, attempts=max_retries + 1)
            last_strategy["voiceover_script"] = _truncate_to_words(script, max_words)
            return last_strategy

        # Por debajo del mínimo — reintentar pidiendo extender.
        if attempt < max_retries:
            log_warning(_LOGGER, "Voiceover demasiado corto, pidiendo extender",
                        duration=duration_seconds, n_words=n_words,
                        min_target=min_words, max_limit=max_words,
                        attempt=attempt + 1)
            user_msg = (
                f"{base_user_msg}\n\n"
                f"⚠️ EXTIENDE: tu intento anterior tenía {n_words} palabras, "
                f"DEMASIADO CORTO para {duration_seconds}s. El video se sentirá "
                f"vacío. Reescribe `voiceover_script` con AL MENOS {min_words} "
                f"y MÁXIMO {max_words} palabras. Añade detalles concretos del "
                f"producto (beneficios, números, sensaciones) y mantén hook + "
                f"social proof + CTA. Conversacional, NO relleno corporativo."
            )
        else:
            # Último intento sin éxito — aceptar el guion corto con warning.
            # NO podemos extender mecánicamente sin dañar el contenido.
            log_warning(_LOGGER, "Voiceover sigue corto tras retries — aceptando",
                        n_words=n_words, min_target=min_words,
                        attempts=max_retries + 1)

    return last_strategy


def _truncate_to_words(text: str, max_words: int) -> str:
    """Recorta `text` al primer punto/coma que cierre dentro de `max_words`,
    o duramente al N-ésima palabra si no hay puntuación cercana.

    Mantiene el final natural (preferimos cortar en `.` o `,`).
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    head = " ".join(words[:max_words])
    # Buscar último signo de cierre en los últimos 10 caracteres
    for sep in (". ", "! ", "? ", "; "):
        idx = head.rfind(sep)
        if idx > len(head) - 30 and idx > 0:
            return head[:idx + 1]
    # Sin puntuación cercana → corte duro + punto
    return head.rstrip(",;:") + "."


def _mock_strategy(duration: int, language: str) -> dict:
    n_clips = 1 if duration <= 5 else 2 if duration <= 10 else 3
    clip_dur = duration // n_clips
    structure = [
        {
            "clip_number": i + 1,
            "duration_seconds": clip_dur,
            "purpose": "hook" if i == 0 else "demo" if i == 1 else "cta",
            "visual_description": "(modo mock — Gemini no configurado)",
            "voiceover_segment": "(modo mock)",
        }
        for i in range(n_clips)
    ]
    return {
        "hook_text": "(Gemini no configurado — escribe tu hook manualmente)",
        "voiceover_script": "(Gemini no configurado — escribe tu guion aquí)",
        "captions_emphasis": [],
        "cta_text": "Carrito naranja para que lo pilles tú." if language == "es" else "Tap the basket below.",
        "video_structure": structure,
        "human_presence_required": True,
        "tiktok_hashtags": ["#fyp", "#parati"],
    }
