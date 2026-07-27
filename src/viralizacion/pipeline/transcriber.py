"""Transcripción Whisper de un audio de voz, cacheada en disco.

El texto no cambia entre rondas del mismo audio (solo cambia el estilo
visual de los subtítulos) — cachear evita re-transcribir con Whisper en
cada ronda, que es el paso más lento del pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from src.viralizacion import config

OnLog = Callable[[str], None]

# Correcciones manuales de nombres propios que Whisper suele transcribir mal
# (mantiene los timings originales, solo cambia el texto mostrado). Vacío
# por defecto — el operador puede añadir entradas si detecta errores
# recurrentes (mismo patrón que el prototipo `WORD_FIXES`).
WORD_FIXES: dict[str, str] = {}


def _to_wav_16k_mono(audio_path: Path, out_wav: Path, on_log: OnLog | None = None) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000",
           str(out_wav), "-loglevel", "error"]
    if on_log:
        on_log("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def transcribe_words(
    ponente: str, audio_path: Path, *, tmp_dir: Path, on_log: OnLog | None = None,
) -> list[dict]:
    """Devuelve `[{word, start, end}, ...]` para `audio_path`, cacheado en
    `config.transcript_cache_path(ponente, audio_path)`."""
    cache_path = config.transcript_cache_path(ponente, audio_path)
    if cache_path.exists():
        if on_log:
            on_log(f"[transcriber] caché encontrada: {cache_path.name}")
        return json.loads(cache_path.read_text())

    from src.subtitles import transcribe

    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = tmp_dir / f"{audio_path.stem}_16k.wav"
    _to_wav_16k_mono(audio_path, wav_path, on_log=on_log)

    if on_log:
        on_log(f"[transcriber] transcribiendo {audio_path.name} (Whisper {config.WHISPER_MODEL_SIZE})…")
    words = transcribe(str(wav_path), model_size=config.WHISPER_MODEL_SIZE, language=config.WHISPER_LANGUAGE)

    cache_path.write_text(json.dumps(words, ensure_ascii=False, indent=2))
    return words


def group_into_phrases(words: list[dict]) -> list[dict]:
    """Agrupa palabras en líneas de ~4-7 palabras / máx ~2.5s, cortando en
    pausas >=0.45s. Cada línea conserva `words` (con timings individuales)
    además del `text` concatenado — necesario para los estilos Reveal
    (letra a letra) y Cinemático (karaoke por palabra)."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        if not current:
            current = [w]
            continue
        would_span = w["end"] - current[0]["start"]
        fits_limits = (
            (len(current) + 1 <= config.SUB_MAX_WORDS)
            and (would_span <= config.SUB_MAX_DURATION)
        )
        gap = w["start"] - current[-1]["end"]
        natural_break = (
            gap >= config.SUB_PAUSE_BREAK
            and len(current) >= config.SUB_MIN_WORDS_BEFORE_PAUSE_BREAK
        )
        if not fits_limits or natural_break:
            groups.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        groups.append(current)

    lines = []
    for g in groups:
        words_out = [
            {"word": WORD_FIXES.get(w["word"], w["word"]).lower(), "start": w["start"], "end": w["end"]}
            for w in g
        ]
        text = " ".join(w["word"] for w in words_out)
        lines.append({"start": g[0]["start"], "end": g[-1]["end"], "text": text, "words": words_out})
    return lines
