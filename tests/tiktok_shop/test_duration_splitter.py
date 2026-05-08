"""Tests del duration_splitter: división de duraciones por tier."""

import pytest

from src.tiktok_shop.utils.duration_splitter import describe_split, split_duration


class TestStandardAdvanced:
    """Standard y Advanced comparten reglas (max 12, min 4 por clip).

    NOTA: el splitter ahora acepta `strategy` (default `dynamic` per FUNC 5).
    Estos tests verifican que sin pasar strategy se aplica DYNAMIC y los
    splits coinciden con la tabla del brief de la estrategia dinámica.
    Tests específicos por estrategia están en
    `test_duration_splitter_strategies.py`.
    """

    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    @pytest.mark.parametrize("total,expected", [
        # Tabla DYNAMIC (default) con margen para compensar shrinkage del editor
        # (mayo 2026): la suma pedida a Atlas es ~target+1s, NO target exacto.
        (5,  [6]),
        (10, [6, 5]),
        (12, [5, 4, 4]),
        (15, [6, 5, 5]),
        (20, [6, 6, 5, 5]),
        (24, [6, 5, 5, 5, 5]),
        (25, [6, 6, 5, 5, 5]),
        (30, [6, 6, 6, 5, 5, 5]),
    ])
    def test_uniform_splits(self, tier: str, total: int, expected: list[int]):
        assert split_duration(total, tier) == expected
        # Suma pedida a Atlas ≥ total (con margen) — NO == total.
        assert sum(split_duration(total, tier)) >= total

    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_non_uniform_falls_to_general(self, tier: str):
        # 13 segundos: ni divisible 5/10/12 → reparto manual (fallback)
        clips = split_duration(13, tier)
        assert sum(clips) == 13
        assert all(4 <= c <= 12 for c in clips)
        assert len(clips) >= 2  # no cabe en uno solo (>12)

    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_clips_within_tier_limits(self, tier: str):
        # Cualquier duración entre 4-100s: cada clip ∈ [4, 12]
        for total in range(4, 100):
            clips = split_duration(total, tier)
            for c in clips:
                assert 4 <= c <= 12, f"Clip {c} fuera de limites para total={total}"
            # Tablas preset añaden margen (~1s); fallback automático mantiene
            # suma = total. Aceptamos cualquiera de los dos.
            assert sum(clips) >= total or sum(clips) == max(4, total)

    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_min_clip_floor(self, tier: str):
        # Pedir 1s → al menos 1 clip de 4s (mínimo del tier)
        assert split_duration(1, tier) == [4]
        assert split_duration(3, tier) == [4]


class TestPro:
    """Pro tier permite hasta 15s nativos en un solo clip multi-shot."""

    @pytest.mark.parametrize("total,expected", [
        (5,  [5]),
        (10, [10]),
        (12, [12]),
        (15, [15]),                    # 15s en 1 clip — clave de Pro
    ])
    def test_pro_single_clip_up_to_15s(self, total: int, expected: list[int]):
        assert split_duration(total, "pro") == expected

    def test_pro_above_15s_splits(self):
        # 30s en pro: 2 clips de 15s
        clips = split_duration(30, "pro")
        assert sum(clips) == 30
        assert all(c <= 15 for c in clips)

    def test_pro_min_floor(self):
        assert split_duration(1, "pro") == [4]


class TestEdgeCases:
    def test_zero_returns_empty(self):
        assert split_duration(0, "standard") == []
        assert split_duration(0, "pro") == []

    def test_negative_returns_empty(self):
        assert split_duration(-5, "standard") == []

    def test_unknown_tier_raises(self):
        with pytest.raises(ValueError, match="Tier desconocido"):
            split_duration(15, "ultraplus")


class TestDescribeSplit:
    def test_single_clip(self):
        assert describe_split([5]) == "1 clip de 5s"

    def test_uniform_clips(self):
        assert describe_split([5, 5, 5]) == "3 clips de 5s"
        assert describe_split([10, 10]) == "2 clips de 10s"

    def test_mixed_clips(self):
        assert describe_split([10, 5]) == "2 clips: 10s + 5s"
        assert describe_split([12, 12, 6]) == "3 clips: 12s + 12s + 6s"

    def test_empty(self):
        assert describe_split([]) == "0 clips"
