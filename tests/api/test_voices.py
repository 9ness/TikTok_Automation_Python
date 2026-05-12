"""Tests de los endpoints de la biblioteca de voces."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_voice_clone(name: str, language: str = "es", tags: list[str] | None = None):
    """Construye un VoiceClone para inyectar en el FakeRedis vía VoiceRepo."""
    from src.tiktok_shop.models import VoiceClone

    return VoiceClone(
        name=name,
        minimax_voice_id=f"clone_{name.replace(' ', '_')}",
        language=language,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
class TestListVoices:
    def test_list_includes_default_presets(self, app_client: TestClient):
        """`include_presets=True` (default) — vienen los 3 presets MiniMax ES."""
        r = app_client.get("/api/v1/voices")
        assert r.status_code == 200
        body = r.json()
        # Al menos los 3 presets configurados en DEFAULT_VOICE_PRESETS_ES
        assert body["total"] >= 3
        ids = {v["id"] for v in body["items"]}
        assert "preset_Spanish_EnergeticBoy" in ids
        assert "preset_Spanish_Strong-WilledBoy" in ids
        assert "preset_Spanish_PassionateWarrior" in ids

    def test_list_excludes_presets_when_flag_false(
        self, app_client: TestClient, fake_shop_redis
    ):
        from src.tiktok_shop.repos import VoiceRepo
        repo = VoiceRepo(fake_shop_redis)
        repo.save(_make_voice_clone("Mi clone", language="es", tags=["female"]))

        r = app_client.get("/api/v1/voices?include_presets=false")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Mi clone"
        assert body["items"][0]["is_preset"] is False

    def test_list_filtered_by_language(
        self, app_client: TestClient, fake_shop_redis
    ):
        from src.tiktok_shop.repos import VoiceRepo
        repo = VoiceRepo(fake_shop_redis)
        repo.save(_make_voice_clone("Voz EN", language="en"))
        repo.save(_make_voice_clone("Voz ES", language="es"))

        r = app_client.get("/api/v1/voices?language=en&include_presets=false")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Voz EN"

    def test_list_filtered_by_gender_male(
        self, app_client: TestClient, fake_shop_redis
    ):
        from src.tiktok_shop.repos import VoiceRepo
        repo = VoiceRepo(fake_shop_redis)
        repo.save(_make_voice_clone("Mujer", tags=["female"]))
        repo.save(_make_voice_clone("Hombre", tags=["male"]))

        r = app_client.get("/api/v1/voices?gender=male&include_presets=false")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "Hombre"

    def test_list_gender_matches_preset_by_name_heuristic(
        self, app_client: TestClient
    ):
        """Los presets MiniMax ES son todos boys → gender=male debe traerlos."""
        r = app_client.get("/api/v1/voices?gender=male")
        body = r.json()
        # Los 3 presets contienen 'Boy' o 'Warrior'
        preset_ids = [v["id"] for v in body["items"] if v["is_preset"]]
        assert len(preset_ids) >= 3


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
class TestGetVoice:
    def test_get_preset(self, app_client: TestClient):
        r = app_client.get("/api/v1/voices/preset_Spanish_EnergeticBoy")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "preset_Spanish_EnergeticBoy"
        assert body["is_preset"] is True
        assert body["language"] == "es"

    def test_get_clone(self, app_client: TestClient, fake_shop_redis):
        from src.tiktok_shop.repos import VoiceRepo
        repo = VoiceRepo(fake_shop_redis)
        clone = _make_voice_clone("Mi clone")
        repo.save(clone)

        r = app_client.get(f"/api/v1/voices/{clone.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == clone.id
        assert body["is_preset"] is False

    def test_get_missing_preset_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/voices/preset_nonexistent")
        assert r.status_code == 404
        assert r.json()["code"] == "voice_not_found"

    def test_get_missing_clone_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/voices/abc-def-not-here")
        assert r.status_code == 404
        assert r.json()["code"] == "voice_not_found"
