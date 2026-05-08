"""Smoke tests de los mocks de API y un E2E del pipeline con todo mockeado.

Este E2E NO toca red. NO gasta. Verifica que:
  - `MockAtlasCloudClient` tiene la misma firma que el real.
  - Los fakes de Gemini devuelven shapes válidos para los modelos Pydantic.
  - El runner `run_tiktok_shop` corre completo en modo `veo3_prompt_only`
    (el camino más simple para validar el wiring).
"""

from __future__ import annotations

import os


from tests.tiktok_shop.mocks import (
    MOCK_ATLAS_OUTPUT_URL,
    MOCK_VIDEO_BYTES,
    MockAtlasCloudClient,
    fake_analyzer_json,
    fake_generate_single_audio,
    fake_nano_banana_text,
    fake_pro_director_dict,
    fake_seedance_director_list,
    fake_strategist_json,
    fake_veo3_prompt_text,
)


# ---------------------------------------------------------------------------
# Atlas mock client
# ---------------------------------------------------------------------------
class TestMockAtlasClient:
    def test_is_available(self):
        c = MockAtlasCloudClient()
        assert c.is_available() is True

    def test_submit_image_to_video_records_call(self):
        c = MockAtlasCloudClient()
        job = c.submit_image_to_video(
            model_id="standard-id", image_url="data:image/jpeg;base64,xxx",
            prompt="test", duration=5, resolution="720p",
            last_image_url="data:image/jpeg;base64,yyy",
        )
        assert job.job_id
        assert len(c.calls) == 1
        assert c.calls[0]["endpoint"] == "image_to_video"
        assert c.calls[0]["has_last_image"] is True
        assert c.calls[0]["duration"] == 5

    def test_submit_reference_to_video_records_n_refs(self):
        c = MockAtlasCloudClient()
        job = c.submit_reference_to_video(
            reference_images=["a", "b", "c"], prompt="test", duration=15,
        )
        assert job.job_id
        assert c.calls[0]["endpoint"] == "reference_to_video"
        assert c.calls[0]["n_refs"] == 3

    def test_wait_returns_completed(self):
        c = MockAtlasCloudClient()
        result = c.wait("any_id")
        assert result.status == "completed"
        assert result.output_url == MOCK_ATLAS_OUTPUT_URL

    def test_download_writes_bytes(self, tmp_path):
        c = MockAtlasCloudClient()
        dest = tmp_path / "out.mp4"
        c.download(MOCK_ATLAS_OUTPUT_URL, str(dest))
        assert dest.exists()
        assert dest.read_bytes() == MOCK_VIDEO_BYTES

    def test_drop_in_compatibility(self):
        """Las firmas públicas deben coincidir con el cliente real."""
        from src.tiktok_shop.api.atlas_cloud import AtlasCloudClient
        import inspect
        for method in ("submit_image_to_video", "submit_reference_to_video", "poll", "wait", "download"):
            real_sig = inspect.signature(getattr(AtlasCloudClient, method))
            mock_sig = inspect.signature(getattr(MockAtlasCloudClient, method))
            assert set(real_sig.parameters.keys()) == set(mock_sig.parameters.keys()), \
                f"Firma divergente en {method}: real={real_sig}, mock={mock_sig}"


# ---------------------------------------------------------------------------
# Gemini fakes — shapes válidos
# ---------------------------------------------------------------------------
class TestGeminiFakes:
    def test_analyzer_shape(self):
        out = fake_analyzer_json()
        assert "product_type" in out
        assert "key_features" in out
        assert "needs_nano_banana_regeneration" in out
        assert isinstance(out["suggested_audiences"], list)
        assert len(out["suggested_audiences"]) == 5

    def test_strategist_shape(self):
        out = fake_strategist_json()
        assert "hook_text" in out
        assert "voiceover_script" in out
        assert "video_structure" in out
        assert len(out["video_structure"]) == 3

    def test_seedance_director_list(self):
        out = fake_seedance_director_list()
        assert isinstance(out, list)
        assert len(out) == 3
        for clip in out:
            assert "clip_idx" in clip
            assert "duration" in clip
            assert "prompt" in clip
            assert "ref_photo_index" in clip
        # Anchoring: clip 1 ancla a clip 0, clip 2 ancla a clip 1
        assert out[0]["anchor_to_previous_clip_end"] is None
        assert out[1]["anchor_to_previous_clip_end"] == 0
        assert out[2]["anchor_to_previous_clip_end"] == 1

    def test_pro_director_dict(self):
        out = fake_pro_director_dict()
        assert isinstance(out, dict)
        assert "duration" in out
        assert "ref_photos_indices" in out
        assert "prompt" in out
        assert "Shot 1" in out["prompt"]  # multi-shot syntax

    def test_veo3_prompt_string(self):
        out = fake_veo3_prompt_text()
        assert isinstance(out, str)
        assert "9:16" in out
        assert "8 seconds" in out

    def test_nano_banana_prompt_string(self):
        out = fake_nano_banana_text()
        assert isinstance(out, str)
        assert "EXACT product appearance" in out
        assert "9:16" in out


# ---------------------------------------------------------------------------
# MiniMax mock
# ---------------------------------------------------------------------------
class TestMockMinimax:
    def test_writes_mp3_file(self, tmp_path):
        out = tmp_path / "voice.mp3"
        result = fake_generate_single_audio("hello world", str(out))
        assert result == str(out)
        assert out.exists()
        # Tiene header ID3 (los primeros 3 bytes son "ID3")
        assert out.read_bytes()[:3] == b"ID3"

    def test_creates_dest_dir(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "voice.mp3"
        fake_generate_single_audio("x", str(nested))
        assert nested.exists()


# ---------------------------------------------------------------------------
# E2E mockeado: runner en modo veo3_prompt_only (sin coste, sin red)
# ---------------------------------------------------------------------------
class TestRunnerWithMocks:
    """Verifica el wiring del runner con todas las APIs mockeadas.

    Camino veo3_prompt_only es el más estable para tests: NO toca Atlas, NO
    toca MiniMax, solo Gemini para strategist + veo3_director.
    """

    def test_veo3_prompt_only_path(
        self, tmp_path, fake_redis, monkeypatch, jpeg_path,
    ):
        # Setup: usuario + producto en FakeRedis
        from src.tiktok_shop.models import (
            Product, ProductPhoto, ProductPhotos, TikTokUser, VideoConfig,
        )
        from src.tiktok_shop.repos import (
            GenerationRepo, ProductRepo, UserRepo,
        )

        ur = UserRepo(redis=fake_redis)
        pr = ProductRepo(redis=fake_redis)
        gr = GenerationRepo(redis=fake_redis)

        u = TikTokUser(username="@mock", display_name="Mock", default_video_tier="standard")
        p = Product(
            slug="mock_p", name="Mock Product",
            video_config=VideoConfig(default_tier="veo3_prompt_only"),
            target_audience=["Generalista"],
            photos=ProductPhotos(source=[ProductPhoto(filename="a.jpg", local_path=str(jpeg_path))]),
        )
        ur.save(u)
        pr.save(p)

        # Monkeypatch repos para que el runner las encuentre
        monkeypatch.setattr("src.tiktok_shop.repos.UserRepo",
                            lambda: ur)
        monkeypatch.setattr("src.tiktok_shop.repos.ProductRepo",
                            lambda: pr)
        monkeypatch.setattr("src.tiktok_shop.repos.GenerationRepo",
                            lambda: gr)

        # Monkeypatch Gemini
        monkeypatch.setattr(
            "src.tiktok_shop.pipeline.analyzer.generate_json",
            fake_analyzer_json,
        )
        monkeypatch.setattr(
            "src.tiktok_shop.pipeline.strategist.generate_json",
            fake_strategist_json,
        )
        monkeypatch.setattr(
            "src.tiktok_shop.pipeline.veo3_director.generate_text",
            fake_veo3_prompt_text,
        )
        # is_configured = True para que no caiga al stub mock interno
        monkeypatch.setattr("src.tiktok_shop.pipeline.analyzer.is_configured",
                            lambda: True)
        monkeypatch.setattr("src.tiktok_shop.pipeline.strategist.is_configured",
                            lambda: True)
        monkeypatch.setattr("src.tiktok_shop.pipeline.veo3_director.is_configured",
                            lambda: True)

        # Job mock
        from src.queue.models import Job, JobMode
        from src.queue.runners import _RUNNERS

        job = Job(mode=JobMode.TIKTOK_SHOP, params={
            "user_id": u.id, "product_id": p.id,
            "tier": "veo3_prompt_only",
            "duration": 8, "resolution": "720p",
            "hook_category": "curiosity", "hook_text": "POV: descubre",
            "audience": "Generalista", "voice_id": "Spanish_EnergeticBoy",
            "language": "es", "is_shoppable": False, "ai_disclosure": True,
            "temp_folder": str(tmp_path),
        })

        runner = _RUNNERS[JobMode.TIKTOK_SHOP]
        logs = []
        progress = []

        result = runner(job, logs.append, lambda pct, lbl: progress.append((pct, lbl)))

        # Veo3 devuelve el path a un .txt con el prompt
        assert result.endswith(".txt")
        assert os.path.exists(result)
        prompt = open(result, encoding="utf-8").read()
        assert "9:16" in prompt
        assert "8 seconds" in prompt

        # El registro VideoGeneration quedó en MANUAL_PENDING
        from src.tiktok_shop.models import GenerationStatus
        gens = gr.list_recent(limit=10)
        assert len(gens) == 1
        assert gens[0].generation_status == GenerationStatus.MANUAL_PENDING
        assert gens[0].tier_used == "veo3_prompt_only"
        assert gens[0].veo3_prompt is not None
        # Coste prompt-only debe ser 0
        assert gens[0].cost.total == 0.0

        # Progreso llegó al 100%
        assert progress[-1][0] == 1.0
