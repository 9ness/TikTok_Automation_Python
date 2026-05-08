"""Wrapper sobre el endpoint de voice cloning de MiniMax.

El TTS normal vive en `src/locutor.py` (reusado para la generación de voz
en los vídeos). Aquí solo cubrimos la creación de voces personalizadas.

Endpoint MiniMax: POST /v1/voice_clone
  - Sube un sample de 10-30s
  - Devuelve un voice_id usable como cualquier voz preset.

⚠️ La spec exacta del endpoint puede variar entre versiones del API. Si falla
la subida, la UI debe permitir guardar manualmente el voice_id devuelto por
otro canal (algunos planes lo proporcionan vía dashboard).
"""

from __future__ import annotations

import os

import requests


CLONE_URL = "https://api.minimax.io/v1/voice_clone"


def is_available() -> bool:
    return bool(os.getenv("MINIMAX_API_KEY"))


def clone_voice(
    sample_path: str,
    *,
    name: str,
    language: str = "es",
    timeout: int = 120,
) -> str:
    """Sube un MP3 sample a MiniMax y devuelve el voice_id resultante.

    Args:
        sample_path: ruta a un MP3 de 10-30s con voz limpia.
        name: nombre descriptivo (no se usa al sintetizar, solo metadata).
        language: código ISO de idioma (es/en/...).

    Returns:
        voice_id (string) que se puede pasar a `locutor.generate_single_audio`
        como `voice_id_override`.
    """
    api_key = os.getenv("MINIMAX_API_KEY")
    group_id = os.getenv("MINIMAX_GROUP_ID")
    if not api_key:
        raise EnvironmentError("Falta MINIMAX_API_KEY en .env")
    if not os.path.exists(sample_path):
        raise FileNotFoundError(sample_path)

    headers = {"Authorization": f"Bearer {api_key}"}
    with open(sample_path, "rb") as f:
        files = {"file": (os.path.basename(sample_path), f, "audio/mpeg")}
        data = {
            "name": name,
            "language": language,
        }
        if group_id:
            data["group_id"] = group_id
        r = requests.post(CLONE_URL, headers=headers, data=data, files=files, timeout=timeout)
        r.raise_for_status()
        payload = r.json()

    voice_id = payload.get("voice_id") or payload.get("data", {}).get("voice_id")
    if not voice_id:
        raise RuntimeError(f"MiniMax voice_clone respuesta sin voice_id: {payload}")
    return voice_id
