"""Transcripción por palabra para las herramientas del Editor Auto.

Con `EDITOR_ASR_PROVIDER=deepgram` (+ `DEEPGRAM_API_KEY`) transcribe con
Deepgram: ~0,02 $/vídeo, sin cargar Whisper large en RAM (~3 GB por proceso)
y con mejores tiempos por palabra. Si Deepgram falla o el audio no es voz
hablada, cae a Whisper local como siempre.

Mismo formato que `src.subtitles_only.transcribe_with_reference`:
lista de {word, start, end} ya limpia (`_clean_whisper_tokens`).
"""
from __future__ import annotations

import os


def usa_deepgram() -> bool:
    return (
        os.getenv("EDITOR_ASR_PROVIDER", "whisper").strip().lower() == "deepgram"
        and bool(os.getenv("DEEPGRAM_API_KEY", "").strip())
    )


def transcribe_words(
    audio_path: str,
    *,
    model_size: str = "large-v3",
    language: str | None = "es",
    audio_type: str = "speech",
    reference_script: str | None = None,
    progress_callback=None,
    on_log=None,
) -> list[dict]:
    if usa_deepgram() and audio_type == "speech":
        try:
            from src.subtitles import _clean_whisper_tokens
            from src.editor_auto.tools.silence_cutter import _transcribe_deepgram

            if progress_callback:
                progress_callback(0.1, "🎙️ Transcribiendo (Deepgram)…")
            words = _clean_whisper_tokens(_transcribe_deepgram(audio_path, language=language))
            if words:
                if progress_callback:
                    progress_callback(1.0, "🎙️ Transcripción completa")
                return words
        except Exception as e:  # noqa: BLE001 — cualquier fallo → Whisper
            if on_log:
                on_log(f"⚠️ Deepgram falló ({e}) — uso Whisper {model_size}")

    from src.subtitles_only import transcribe_with_reference

    return transcribe_with_reference(
        audio_path,
        reference_script=reference_script,
        model_size=model_size,
        language=language,
        audio_type=audio_type,
        progress_callback=progress_callback,
    )
