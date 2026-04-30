"""Parser de números en español → enteros, y colapso de word_timings.

El TTS pronuncia las cifras como palabras ("cuatro mil quinientos") porque así
las recibe del payload (Whisper también las transcribe en palabras). Pero los
SUBTÍTULOS quedan mejor con dígitos: "4.500" en vez de tres palabras separadas.

Este módulo:
  - Reconoce secuencias de palabras-número en una lista de word_timings.
  - Las fusiona en un solo token con la cifra formateada (separador de miles `.`).
  - Mantiene el `start` del primer y el `end` del último token de la secuencia.
"""

from __future__ import annotations

import unicodedata


# ── Vocabulario numérico (sin acentos para tolerancia a Whisper) ──

_UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}

_TEENS = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
}

_VEINTI = {
    "veinte": 20,
    "veintiuno": 21, "veintiun": 21, "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}

_TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}

_HUNDREDS = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
    "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}

_SCALES = {
    "mil": 1_000, "miles": 1_000,
    "millon": 1_000_000, "millones": 1_000_000,
}

_CONNECTORS = {"y"}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _norm(token: str) -> str:
    return _strip_accents((token or "").lower().strip(".,;:!?¡¿\"'() "))


def _try_int(tok: str) -> int | None:
    """Devuelve el entero si el token es solo dígitos (acepta '7', '000', '4500')."""
    n = _norm(tok)
    return int(n) if n.isdigit() else None


def _is_number_token(tok: str) -> bool:
    """¿Esta palabra forma parte de una cifra? (palabra-número o dígitos puros)."""
    if _try_int(tok) is not None:
        return True
    n = _norm(tok)
    return (n in _UNITS or n in _TEENS or n in _VEINTI or n in _TENS
            or n in _HUNDREDS or n in _SCALES)


def _word_to_value(tok: str) -> int | None:
    """Devuelve el valor numérico de la palabra/dígito o None si no es número."""
    int_v = _try_int(tok)
    if int_v is not None:
        return int_v
    n = _norm(tok)
    if n in _UNITS: return _UNITS[n]
    if n in _TEENS: return _TEENS[n]
    if n in _VEINTI: return _VEINTI[n]
    if n in _TENS: return _TENS[n]
    if n in _HUNDREDS: return _HUNDREDS[n]
    return None


def _fuse_consecutive_digits(tokens: list[str]) -> list[str]:
    """Pre-fusiona runs de tokens-dígito consecutivos.

    Whisper a veces transcribe 'siete mil' como ['7', '000'] en lugar de palabras.
    Sin fusión, '7' + '000' daría 7+0=7 (mal). Con fusión, queda '7000'.
    """
    out = []
    i = 0
    n = len(tokens)
    while i < n:
        if _try_int(tokens[i]) is not None:
            digits = _norm(tokens[i])
            i += 1
            while i < n and _try_int(tokens[i]) is not None:
                digits += _norm(tokens[i])
                i += 1
            out.append(digits)
        else:
            out.append(tokens[i])
            i += 1
    return out


def _parse_number_sequence(tokens: list[str]) -> int | None:
    """Convierte una secuencia de palabras-número en un entero.

    Algoritmo acumulador:
      - Suma unidades/decenas/centenas en `current`.
      - Al encontrar 'mil' o 'millón': multiplica current por la escala y
        empuja a `total`, reinicia current.

    Pre-fusiona dígitos consecutivos para evitar que '7'+'000' sume 7+0.
    """
    fused = _fuse_consecutive_digits(tokens)
    total = 0
    current = 0
    saw_any = False
    for tok in fused:
        n = _norm(tok)
        if n in _CONNECTORS:
            continue
        v = _word_to_value(tok)
        if v is not None:
            current += v
            saw_any = True
            continue
        if n in _SCALES:
            scale = _SCALES[n]
            current = (current or 1) * scale
            total += current
            current = 0
            saw_any = True
            continue
        break
    if not saw_any:
        return None
    return total + current


def format_int_es(n: int) -> str:
    """Formatea un entero con punto como separador de miles (estilo ES)."""
    return f"{n:,.0f}".replace(",", ".")


def collapse_spanish_numbers(words: list[dict]) -> list[dict]:
    """Devuelve una nueva lista de word_timings donde las secuencias de
    palabras-número están fusionadas en un solo token con dígitos.

    No muta la lista original. Mantiene timings (start del primero, end del último).
    """
    if not words:
        return []

    out: list[dict] = []
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        token = w.get("word", "")
        if not _is_number_token(token):
            out.append(w)
            i += 1
            continue

        # Acumular tokens-número consecutivos (incluyendo conectores 'y')
        seq_tokens: list[str] = []
        seq_start_idx = i
        while i < n:
            cur_tok = words[i].get("word", "")
            cur_norm = _norm(cur_tok)
            if cur_norm in _CONNECTORS:
                # 'y' solo cuenta si lo siguiente es número (filtra "y" suelto que no sea conector)
                if i + 1 < n and _is_number_token(words[i + 1].get("word", "")):
                    seq_tokens.append(cur_tok)
                    i += 1
                    continue
                break
            if _is_number_token(cur_tok):
                seq_tokens.append(cur_tok)
                i += 1
            else:
                break

        value = _parse_number_sequence(seq_tokens)
        if value is None or len(seq_tokens) == 0:
            # No se pudo parsear — emitir tokens originales
            for k in range(seq_start_idx, i):
                out.append(words[k])
            continue

        out.append({
            "word": format_int_es(value),
            "start": float(words[seq_start_idx]["start"]),
            "end": float(words[i - 1]["end"]),
        })

    return out
