"""Detección de la ventana del CTA midroll en los word_timings de Whisper.

El guion del proyecto bet-ai-master incluye literalmente la frase
"el linkcito de mi perfil" como anclaje del CTA midroll. Cuando esa palabra se
pronuncia, el vídeo debe mostrar `perfil.png` (captura del perfil de TikTok).

Este módulo localiza el rango temporal aproximado de ese bloque CTA dentro
de la transcripción palabra a palabra.
"""

from __future__ import annotations

# El overlay perfil.png debe aparecer JUSTO cuando se pronuncia
# "linkcito"/"linksito"/"perfil" — no segundos antes. Por eso la ventana arranca
# en el propio anchor (con un lead-in mínimo) y solo avanza unas pocas palabras
# para cubrir "...de mi perfil".
# Whisper transcribe palabras raras como "linkcito" de varias formas — buscamos
# todas las variantes plausibles + fallback a la palabra "perfil" (más estable).
_CTA_ANCHORS_PRIMARY = ("linkcito", "linksito", "linkito", "linsito", "linkcit",
                        "lincito", "lincsito")
# Bigram fallback: "mi perfil" siempre aparece literal al final del CTA.
_CTA_FALLBACK_BIGRAM = ("mi", "perfil")
_LEAD_IN_S = 0.15       # arranca un pelín antes para que el cambio visual coincida con la sílaba
_FORWARD_WORDS = 5      # cubre "linkcito de mi perfil" + 1 palabra extra
_MIN_DURATION_S = 2.5
_MAX_DURATION_S = 4.0


def _norm(token: str) -> str:
    return (token or "").lower().strip(".,;:!?¡¿\"'() ")


def find_cta_window(words: list[dict], log_callback=None) -> tuple[float, float] | None:
    """Devuelve (start_s, end_s) del bloque CTA, o None si no se halla.

    Estrategia robusta:
      1. Match con cualquier variante del anchor primario ("linkcito" y similares).
      2. Si falla, busca el bigram "mi perfil" (estable, raramente mal-transcrito).
      3. La ventana ARRANCA en el propio anchor (con un lead-in mínimo) y avanza
         ~5 palabras, capada a 2.5-4s — perfil.png aparece cuando se pronuncia
         "linkcito"/"perfil", no antes.

    `log_callback` (opcional): se llama con info de diagnóstico si se halla por fallback
    o si no se halla nada.
    """
    if not words:
        return None

    anchor_idx = _find_primary_anchor(words)
    if anchor_idx is None:
        anchor_idx = _find_fallback_anchor(words)
        if anchor_idx is not None and log_callback:
            tok = _norm(words[anchor_idx]["word"])
            log_callback(f"ℹ️ CTA detectado vía fallback 'mi perfil' (Whisper transcribió: '{tok}')")

    if anchor_idx is None:
        if log_callback:
            # Loggear los tokens cercanos a donde DEBERÍA estar el CTA (a partir del 50%
            # del audio) para que el usuario diagnostique la transcripción
            try:
                last_third_start = words[len(words) // 2]["start"]
                tokens_zone = [
                    _norm(w["word"]) for w in words
                    if last_third_start <= float(w["start"]) <= last_third_start + 15.0
                ]
                log_callback(f"ℹ️ CTA no detectado. Tokens del audio (zona media): {' '.join(tokens_zone)[:300]}")
            except Exception:
                pass
        return None

    end_idx = min(len(words) - 1, anchor_idx + _FORWARD_WORDS)

    start_s = max(0.0, float(words[anchor_idx]["start"]) - _LEAD_IN_S)
    end_s = float(words[end_idx]["end"])

    duration = end_s - start_s
    if duration < _MIN_DURATION_S:
        end_s = start_s + _MIN_DURATION_S
    elif duration > _MAX_DURATION_S:
        end_s = start_s + _MAX_DURATION_S

    return start_s, end_s


def _find_primary_anchor(words: list[dict]) -> int | None:
    for i, w in enumerate(words):
        token = _norm(w.get("word", ""))
        # substring match contra cualquier variante
        if any(anchor in token for anchor in _CTA_ANCHORS_PRIMARY):
            return i
        # también acepta tokens que contengan "link" + tienen ≥7 chars (filtra
        # casualmente "link" suelto de inglés improbable en este corpus)
        if "link" in token and len(token) >= 7:
            return i
    return None


def _find_fallback_anchor(words: list[dict]) -> int | None:
    """Busca el bigram 'mi perfil' que cierra siempre el bloque CTA."""
    for i in range(len(words) - 1):
        t1 = _norm(words[i].get("word", ""))
        t2 = _norm(words[i + 1].get("word", ""))
        if (t1, t2) == _CTA_FALLBACK_BIGRAM:
            # El "linkcito" estaría 1-2 palabras antes de "mi perfil"; usamos el
            # índice de "perfil" - 2 como estimación del anchor.
            return max(0, i - 1)
    return None
