"""Tests de los overrides manuales de fotos por clip (FUNC 3)."""

from __future__ import annotations

import src.tiktok_shop.pipeline.seedance_director as director_mod
from src.tiktok_shop.pipeline.seedance_director import generate_seedance_prompts


def _fake_strategy(n_clips: int = 3) -> dict:
    """Estrategia mock con N clips de 5s cada uno."""
    return {
        "video_structure": [
            {"clip_number": i + 1, "duration_seconds": 5,
             "purpose": f"clip_{i}", "visual_description": "...",
             "voiceover_segment": "..."}
            for i in range(n_clips)
        ],
    }


# ---------------------------------------------------------------------------
# Standard / Advanced — clip_photo_overrides
# ---------------------------------------------------------------------------
class TestImageToVideoOverrides:
    def test_no_override_uses_auto_assignment(self, monkeypatch):
        # Sin override: el director auto-asigna ref_photo_index = clip_idx
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="standard", photos_count=3,
        )
        assert isinstance(result, list)
        # Mock: ref_photo_index = i (auto)
        assert [c["ref_photo_index"] for c in result] == [0, 1, 2]

    def test_override_replaces_ref_photo_index(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="standard", photos_count=4,
            clip_photo_overrides=[2, 0, 3],
        )
        assert isinstance(result, list)
        assert [c["ref_photo_index"] for c in result] == [2, 0, 3]

    def test_override_with_invalid_index_keeps_auto(self, monkeypatch):
        # Override con índice fuera de rango (5 con solo 3 fotos) → ignora ese y
        # mantiene el auto del director para esa posición.
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="standard", photos_count=3,
            clip_photo_overrides=[1, 5, 0],  # 5 es inválido
        )
        # Clip 0 → 1 (override), Clip 1 → mantiene auto = 1, Clip 2 → 0 (override)
        assert result[0]["ref_photo_index"] == 1
        assert result[1]["ref_photo_index"] == 1  # auto del mock
        assert result[2]["ref_photo_index"] == 0

    def test_override_shorter_than_clips_partial(self, monkeypatch):
        """Si override tiene menos elementos que clips, los restantes mantienen auto."""
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="standard", photos_count=3,
            clip_photo_overrides=[2],  # solo overridea clip 0
        )
        assert result[0]["ref_photo_index"] == 2
        assert result[1]["ref_photo_index"] == 1  # auto
        assert result[2]["ref_photo_index"] == 2  # auto

    def test_override_longer_than_clips_truncates(self, monkeypatch):
        """Si override tiene más elementos que clips, los extras se ignoran."""
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(2), tier="standard", photos_count=5,
            clip_photo_overrides=[3, 4, 1, 0],  # 4 overrides para 2 clips
        )
        assert len(result) == 2
        assert result[0]["ref_photo_index"] == 3
        assert result[1]["ref_photo_index"] == 4

    def test_override_works_for_advanced_tier(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(2), tier="advanced", photos_count=3,
            clip_photo_overrides=[2, 0],
        )
        assert [c["ref_photo_index"] for c in result] == [2, 0]


# ---------------------------------------------------------------------------
# Pro — pro_ref_photo_overrides
# ---------------------------------------------------------------------------
class TestProOverrides:
    def test_no_override_pro_uses_auto(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=4,
        )
        assert isinstance(result, dict)
        # Mock pro: ref_photos_indices = list(range(min(photos_count, 4)))
        assert result["ref_photos_indices"] == [0, 1, 2, 3]

    def test_pro_override_replaces_indices(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=5,
            pro_ref_photo_overrides=[4, 2, 0],
        )
        assert result["ref_photos_indices"] == [4, 2, 0]

    def test_pro_override_filters_invalid_indices(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=3,
            pro_ref_photo_overrides=[0, 99, 1, -1, 2],  # 99 y -1 inválidos
        )
        assert result["ref_photos_indices"] == [0, 1, 2]

    def test_pro_override_caps_at_9(self, monkeypatch):
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=15,
            pro_ref_photo_overrides=list(range(15)),  # 15 índices
        )
        assert len(result["ref_photos_indices"]) == 9
        assert result["ref_photos_indices"] == list(range(9))

    def test_pro_empty_override_falls_back_to_auto(self, monkeypatch):
        """Si el override está vacío (lista filtrada queda vacía), mantiene auto."""
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=3,
            pro_ref_photo_overrides=[10, 20, 30],  # todos inválidos → vacío
        )
        # Cuando todos los índices son inválidos, mantiene el auto del director
        assert result["ref_photos_indices"] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Cross-tier: el override no aplicable se ignora silenciosamente
# ---------------------------------------------------------------------------
class TestCrossTier:
    def test_clip_override_ignored_in_pro(self, monkeypatch):
        """`clip_photo_overrides` solo aplica a i2v, en pro se ignora."""
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(3), tier="pro", photos_count=3,
            clip_photo_overrides=[2, 1, 0],  # ignorado en pro
        )
        assert isinstance(result, dict)
        # Pro mantiene su auto-asignación
        assert result["ref_photos_indices"] == [0, 1, 2]

    def test_pro_override_ignored_in_i2v(self, monkeypatch):
        """`pro_ref_photo_overrides` solo aplica a pro, en i2v se ignora."""
        monkeypatch.setattr(director_mod, "is_configured", lambda: False)
        result = generate_seedance_prompts(
            _fake_strategy(2), tier="standard", photos_count=3,
            pro_ref_photo_overrides=[2, 1],  # ignorado en standard
        )
        # Standard mantiene su auto del mock
        assert [c["ref_photo_index"] for c in result] == [0, 1]
