"""Mocks de clientes API para tests E2E sin coste.

Cada mock implementa la misma interfaz que el cliente real (mismas firmas,
mismo shape de retorno) pero sin red. Permiten correr el pipeline completo
en CI/CD y en iteración local sin gastar.

Uso típico (con `monkeypatch`):

    from tests.tiktok_shop.mocks import MockAtlasCloudClient, mock_gemini, mock_minimax

    def test_runner(monkeypatch, ...):
        monkeypatch.setattr(
            'src.tiktok_shop.api.atlas_cloud.AtlasCloudClient',
            MockAtlasCloudClient,
        )
        monkeypatch.setattr(
            'src.tiktok_shop.api.gemini.generate_json',
            mock_gemini.fake_strategist_json,
        )
        ...
"""

from .mock_atlas import MockAtlasCloudClient, MOCK_ATLAS_OUTPUT_URL, MOCK_VIDEO_BYTES
from .mock_gemini import (
    fake_analyzer_json,
    fake_seedance_director_list,
    fake_strategist_json,
    fake_veo3_prompt_text,
    fake_nano_banana_text,
    fake_pro_director_dict,
)
from .mock_minimax import fake_generate_single_audio, MOCK_VOICE_MP3_BYTES

__all__ = [
    "MockAtlasCloudClient",
    "MOCK_ATLAS_OUTPUT_URL",
    "MOCK_VIDEO_BYTES",
    "fake_analyzer_json",
    "fake_strategist_json",
    "fake_seedance_director_list",
    "fake_pro_director_dict",
    "fake_veo3_prompt_text",
    "fake_nano_banana_text",
    "fake_generate_single_audio",
    "MOCK_VOICE_MP3_BYTES",
]
