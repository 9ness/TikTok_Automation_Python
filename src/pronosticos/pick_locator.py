"""Localización del texto exacto de cada pick dentro de los word_timings.

El proyecto bet-ai-master (`PronosticosAuto.md` §199-249) envuelve cada pick
del script entre paréntesis mediante un post-proceso DETERMINISTA. Eso nos da
el texto LITERAL del pick tal como se narra, lo que permite:

  1. Anclar el SFX clink al inicio EXACTO del pick (más fiable que detectar
     keywords sueltas tipo "más"/"ambos"/"victoria").
  2. Pintar de verde-victoria las palabras del pick en los subtítulos para que
     el espectador visualice de un vistazo el pronóstico.

Antes del TTS hay que quitar los paréntesis para que la voz no los pronuncie.
"""

from __future__ import annotations

import re
import unicodedata as _ud


_PICK_RE = re.compile(r"\(([^()]+)\)")


def extract_pick_texts(script: str) -> list[str]:
    """Devuelve los textos de cada pick (interior de los paréntesis), en orden."""
    return [m.strip() for m in _PICK_RE.findall(script or "") if m.strip()]


def strip_pick_parens(script: str) -> str:
    """Quita SOLO los paréntesis de pick (mantiene el texto interno).

    Sirve para alimentar al TTS sin que los paréntesis afecten la prosodia.
    """
    return _PICK_RE.sub(lambda m: m.group(1), script or "")


def _strip_accents(s: str) -> str:
    return "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")


def _norm(token: str) -> str:
    return _strip_accents((token or "").lower().strip(".,;:!?¡¿\"'() "))


def find_pick_windows(words: list[dict], pick_texts: list[str],
                      log_callback=None) -> list[tuple[int, int] | None]:
    """Devuelve, para cada `pick_texts[i]`, su ventana `(start_idx, end_idx)`
    en `words` (índices inclusivos de los word_timings de Whisper).

    Devuelve lista del mismo largo que `pick_texts` con `None` donde no hay match.
    Búsqueda secuencial (avanza el cursor tras cada match) con tolerancia a ruido
    de Whisper: 1 mismatch interno o 1 token extra/faltante.
    """
    if not words or not pick_texts:
        return [None] * len(pick_texts)

    norm_words = [_norm(w.get("word", "")) for w in words]
    out: list[tuple[int, int] | None] = []
    cursor = 0

    for pt in pick_texts:
        tokens = [t for t in (_norm(x) for x in pt.split()) if t]
        if not tokens:
            out.append(None)
            continue

        win = _find_subseq(norm_words, tokens, cursor)
        if win is None:
            # Reintento desde cero por si Whisper barajó orden (raro)
            win = _find_subseq(norm_words, tokens, 0)

        if win is not None:
            cursor = win[1] + 1
            if log_callback:
                log_callback(
                    f"  🟢 pick '{pt[:50]}' → words[{win[0]}..{win[1]}] "
                    f"@ {words[win[0]]['start']:.2f}s"
                )
        else:
            if log_callback:
                log_callback(f"  ⚠️ pick '{pt[:50]}' NO localizado en word_timings")
        out.append(win)

    return out


def _find_subseq(haystack: list[str], needle: list[str],
                  start: int) -> tuple[int, int] | None:
    """Busca `needle` en `haystack[start:]`.

    Estrategia escalonada:
      1. Match exacto.
      2. ≤ 1 mismatch interno (Whisper sustituye una palabra).
      3. Hueco extra de ±1 token (Whisper inserta una sílaba como palabra suelta).
    """
    n = len(needle)
    if n == 0 or len(haystack) - start < 1:
        return None

    # 1. Exacto
    for i in range(start, len(haystack) - n + 1):
        if all(haystack[i + j] == needle[j] for j in range(n)):
            return i, i + n - 1

    # 2. ≤1 mismatch interno (la primera y última deben coincidir para anclarlo)
    for i in range(start, len(haystack) - n + 1):
        if haystack[i] != needle[0] or haystack[i + n - 1] != needle[-1]:
            continue
        mism = sum(1 for j in range(n) if haystack[i + j] != needle[j])
        if mism <= 1:
            return i, i + n - 1

    # 3. Hueco extra de 1 token: needle cabe en una ventana de n+1
    if len(haystack) - start >= n + 1:
        for i in range(start, len(haystack) - n):
            if haystack[i] != needle[0]:
                continue
            if haystack[i + n] == needle[-1]:
                return i, i + n
            if haystack[i + n - 1] == needle[-1] and i + n - 1 < len(haystack):
                # Probablemente sea ya match exacto cubierto en (1), pero por si acaso
                return i, i + n - 1

    return None


def _is_digit_token(s: str) -> bool:
    """¿Es un token tipo '4.500' / '10.000' / '7000'? (resultado de collapse)"""
    if not s:
        return False
    cleaned = s.replace(".", "").replace(",", "")
    return cleaned.isdigit() and len(cleaned) >= 1


def annotate_word_colors(sub_words: list[dict],
                          pick_windows: list[tuple[int, int] | None],
                          word_timings: list[dict],
                          pick_color: str,
                          money_color: str | None = None) -> list[dict]:
    """Devuelve nueva lista de `sub_words` con campo `color` añadido donde aplique.

    - Cada palabra cuyo timing cae dentro de una ventana de pick → `pick_color`.
    - La PRIMERA palabra-cifra (token tipo '4.500' tras collapse) → `money_color`.
      Si `money_color` es None, usa `pick_color`.
    No muta la entrada.
    """
    if money_color is None:
        money_color = pick_color

    pick_ranges: list[tuple[float, float]] = []
    for win in pick_windows or []:
        if win is None:
            continue
        a, b = win
        if 0 <= a < len(word_timings) and 0 <= b < len(word_timings):
            pick_ranges.append((float(word_timings[a]["start"]),
                                float(word_timings[b]["end"])))

    out: list[dict] = []
    money_done = False
    for sw in sub_words:
        new = dict(sw)
        word = new.get("word", "")
        t_start = float(new.get("start", 0))
        t_end = float(new.get("end", t_start))

        if not money_done and _is_digit_token(word):
            new["color"] = money_color
            money_done = True
        else:
            for (s_s, e_s) in pick_ranges:
                if t_start >= s_s - 0.05 and t_end <= e_s + 0.05:
                    new["color"] = pick_color
                    break
        out.append(new)
    return out
