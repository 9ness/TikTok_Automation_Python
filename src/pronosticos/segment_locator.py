"""Detección de las ventanas temporales del guion en los word_timings de Whisper.

El guion del agente bet-ai-master incluye literalmente transiciones obligatorias
que separan intro / picks / outro. Este módulo busca esas transiciones para
poder cambiar la carpeta de stock cada vez que cambia el pick.

Transiciones reconocidas (en orden temporal de aparición = pick 1, 2, 3, ...):
  - "Empezamos con"  / "Arrancamos con"   → entrada Pick 1
  - "Seguimos con"                         → entrada Pick siguiente
  - "Vamos con"                            → entrada Pick siguiente
  - "Por último"                           → entrada Pick final

El CTA midroll ("linkcito de mi perfil") va ENTRE picks (no dentro). Se localiza
con `cta_locator.find_cta_window()`.
"""

from __future__ import annotations

from .cta_locator import find_cta_window

# Bigrams literales que marcan inicio de pick. (token1, token2) en lowercase, sin acentos eliminados.
# Palabras-número en español neutro. La cifra del bote en el hook ("cuatro mil
# quinientos", "diez mil") arranca con una de éstas — sirve como anchor para
# disparar un SFX de dinero sincronizado con la voz.
_NUMBER_WORDS: set[str] = {
    "un", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
    "dieciséis", "dieciseis", "diecisiete", "dieciocho", "diecinueve",
    "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta",
    "ochenta", "noventa",
    "cien", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
    "seiscientos", "setecientos", "ochocientos", "novecientos",
    "mil", "millón", "millon", "millones",
}


_TRANSITION_BIGRAMS: set[tuple[str, str]] = {
    ("empezamos", "con"),
    ("arrancamos", "con"),
    ("seguimos", "con"),
    ("vamos", "con"),
    ("por", "último"),
    ("por", "ultimo"),  # whisper a veces se come la tilde
}


def _norm(token: str) -> str:
    return (token or "").lower().strip(".,;:!?¡¿\"'() ")


# Palabras que abren el pick textual tras la transición + nombre del equipo.
# Comparación insensible a tildes (Whisper a veces se las come).
# Ej: "Seguimos con City *más* de seis...", "Vamos con Atlético *doble* oportunidad",
# "Empezamos con Bournemouth *ambos* anotan".
import unicodedata as _ud

_PICK_KEYWORDS_RAW = {
    # cantidades / over-under
    "mas", "menos",
    # both teams to score
    "ambos", "anotan", "marcan", "marca",
    # 1X2 / victorias
    "victoria", "gana", "ganador", "vence", "vencer", "se", "lleva",
    # doble oportunidad
    "doble", "oportunidad",
    # hándicap
    "handicap", "hándicap",
    # empates
    "empate", "empatan",
    # mercados específicos
    "remate", "remates", "tiro", "tiros", "disparo", "disparos",
    "tarjeta", "tarjetas",
    "corner", "corners", "córner", "córners",
    "punto", "puntos",
    "gol", "goles",
    # números (a veces el pick empieza con la cifra: "más de 6 córners" → cifra es el ancla)
    "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "doce", "quince",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")


# Pre-normalizar todas las keywords sin tildes para comparación rápida
_PICK_KEYWORDS = {_strip_accents(w) for w in _PICK_KEYWORDS_RAW}


def find_pick_anchors(words: list[dict], pick_starts: list[float],
                      log_callback=None) -> list[float]:
    """Para cada pick (definido por su `pick_starts[i]`), devuelve el timestamp
    de la palabra que abre el pronóstico textual (`más` / `ambos` / `victoria`...).

    Ej (palabra entre asteriscos = anchor):
      "Seguimos con City *más* de seis disparos a puerta"
      "Vamos con Atlético *doble* oportunidad"
      "Por último *ambos* anotan en Leverkusen Bayern"

    Si no se encuentra una palabra-clave dentro del pick, usa `pick_start + 1.5s`
    como fallback (estimación: tras la transición y nombre del equipo).

    `log_callback`: si se pasa, loggea cada anchor con el token que lo disparó
    (útil para diagnosticar por qué un clink no suena).
    """
    anchors: list[float] = []
    for i, ps in enumerate(pick_starts):
        next_ps = pick_starts[i + 1] if i + 1 < len(pick_starts) else float("inf")
        anchor: float | None = None
        anchor_token: str | None = None
        for w in words or []:
            ts = float(w.get("start", 0))
            if ts <= ps + 0.05:
                continue
            if ts >= next_ps:
                break
            tok_norm = _strip_accents(_norm(w.get("word", "")))
            if tok_norm in _PICK_KEYWORDS:
                anchor = ts
                anchor_token = w.get("word", "")
                break
        if anchor is not None:
            anchors.append(anchor)
            if log_callback:
                log_callback(f"  pick {i+1}: anchor 🔔 a los {anchor:.2f}s "
                             f"(token: '{anchor_token}')")
        else:
            fallback = ps + 1.5
            anchors.append(fallback)
            if log_callback:
                log_callback(f"  pick {i+1}: ⚠️ sin keyword detectada — "
                             f"fallback a {fallback:.2f}s (start+1.5s)")
    return anchors


def find_money_anchor(words: list[dict], intro_end: float | None = None) -> float | None:
    """Devuelve el `start` (s) de la primera palabra-número de la intro.

    Sirve para sincronizar un SFX de dinero con la cifra del bote pronunciada
    al inicio del hook ('cuatro mil quinientos', 'diez mil', etc.).

    Acepta tanto palabras-número en español ('cuatro', 'mil', ...) como tokens
    de dígitos ('4500', '4.500') por si Whisper transcribe la cifra en formato
    numérico — caso conocido del modelo `base` con language="es".

    Si `intro_end` se da, solo busca antes de ese timestamp.
    """
    for w in words or []:
        ts = float(w.get("start", 0))
        if intro_end is not None and ts >= intro_end:
            break
        norm = _norm(w.get("word", ""))
        if norm in _NUMBER_WORDS:
            return ts
        cleaned = norm.replace(".", "").replace(",", "")
        if cleaned.isdigit() and len(cleaned) >= 2:
            return ts
    return None


def find_pick_starts(words: list[dict]) -> list[float]:
    """Devuelve los segundos donde arranca cada pick, en orden temporal."""
    if not words:
        return []
    starts: list[float] = []
    for i in range(len(words) - 1):
        bigram = (_norm(words[i]["word"]), _norm(words[i + 1]["word"]))
        if bigram in _TRANSITION_BIGRAMS:
            starts.append(float(words[i]["start"]))
    return starts


def find_segments(words: list[dict], total_duration: float, log_callback=None) -> dict:
    """Devuelve `{intro, picks, cta}` con las ventanas temporales del vídeo.

    - `intro`: tupla (0, primer_pick_start) — narración antes del primer "Empezamos con".
    - `picks`: lista de tuplas (start, end) — UNA por pick detectado, en orden.
              El último termina en `total_duration`.
    - `cta`: tupla (start, end) del bloque CTA midroll, o None si no se detecta.

    Si NO se detectan transiciones (Whisper falló o el guion es atípico), se
    devuelve la duración completa como `intro` y `picks=[]` para que el pipeline
    pueda caer al reparto uniforme.
    """
    starts = find_pick_starts(words)
    cta = find_cta_window(words, log_callback=log_callback)

    if not starts:
        return {
            "intro": (0.0, total_duration),
            "picks": [],
            "cta": cta,
        }

    intro = (0.0, starts[0])
    picks: list[tuple[float, float]] = []
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total_duration
        # NO recortar por CTA: el visual del pick fluye continuo y perfil.png
        # se superpone como overlay encima (con clip de stock visible detrás).
        picks.append((s, end))

    return {"intro": intro, "picks": picks, "cta": cta}
