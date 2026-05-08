"""Mock de MiniMax TTS — escribe un MP3 placeholder local sin red.

`fake_generate_single_audio()` reemplaza a `src.locutor.generate_single_audio`
en tests. Escribe `MOCK_VOICE_MP3_BYTES` (header MP3 mínimo) en `output_mp3_path`
y devuelve el path. NO llama a la API de MiniMax.

Para tests que requieren un MP3 reproducible (compose con MoviePy real),
considera usar un fixture con un MP3 real corto desde `tests/fixtures/`.
"""

from __future__ import annotations

import os


# Header MP3 mínimo (frame ID3v2 + 1 frame MPEG). Suficiente para que MoviePy
# lea el archivo como audio sin reventar; la duración detectada será ≈0.
MOCK_VOICE_MP3_BYTES = (
    b"ID3\x04\x00\x00\x00\x00\x00\x00"  # ID3v2 header vacío
    b"\xff\xfb\x90\x00"                   # MPEG-1 Layer 3 frame sync
    + b"\x00" * 100                       # padding
)


def fake_generate_single_audio(text: str, output_mp3_path: str, voice_id_override=None) -> str:
    """Drop-in replacement para `src.locutor.generate_single_audio`.

    Escribe un MP3 placeholder y devuelve el path. Ignora `text` y
    `voice_id_override` (los tests pueden inspeccionar via monkeypatch si
    necesitan capturar las llamadas).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_mp3_path)) or ".", exist_ok=True)
    with open(output_mp3_path, "wb") as f:
        f.write(MOCK_VOICE_MP3_BYTES)
    return output_mp3_path
