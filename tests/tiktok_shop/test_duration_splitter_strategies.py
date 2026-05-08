"""Tests de las tablas exactas de splits por estrategia (FUNC 5)."""

from __future__ import annotations

import pytest

from src.tiktok_shop.utils.duration_splitter import describe_split, split_duration


# ---------------------------------------------------------------------------
# Cinematográfico — tabla con margen para compensar shrinkage (mayo 2026)
# ---------------------------------------------------------------------------
# shrinkage = N×0.15 trim_head + (N-1)×0.5 crossfade
# Atlas devuelve clips ~target+0.04s. Suma post-shrinkage debe ≥ target.
class TestCinematicTable:
    @pytest.mark.parametrize("total,expected", [
        (5,  [6]),              # 5.89s real ≥ 5
        (10, [11]),             # 10.89s real ≥ 10
        (12, [7, 6]),           # 12.28s real ≥ 12
        (15, [11, 5]),          # 15.28s real ≥ 15
        (20, [12, 9]),          # 20.28s real ≥ 20
        (24, [12, 8, 6]),       # 24.68s real ≥ 24
        (25, [12, 9, 6]),       # 25.68s real ≥ 25
        (30, [12, 12, 8]),      # 30.68s real ≥ 30
    ])
    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_exact_match(self, total: int, expected: list[int], tier: str):
        assert split_duration(total, tier, "cinematic") == expected
        # La SUMA pedida a Atlas es target + margen (~1s), NO target exacto.
        assert sum(split_duration(total, tier, "cinematic")) >= total

    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_all_clips_within_limits(self, tier: str):
        for total in [5, 10, 12, 15, 20, 24, 25, 30]:
            for c in split_duration(total, tier, "cinematic"):
                assert 4 <= c <= 12, f"clip {c}s fuera de [4,12] en total={total}"


# ---------------------------------------------------------------------------
# Dinámico — tabla con margen para compensar shrinkage (mayo 2026)
# ---------------------------------------------------------------------------
# shrinkage = N×0.15 trim_head + (N-1)×0.3 crossfade
class TestDynamicTable:
    @pytest.mark.parametrize("total,expected", [
        (5,  [6]),                          # 5.89s real ≥ 5
        (10, [6, 5]),                       # 10.48s real ≥ 10
        (12, [5, 4, 4]),                    # 12.08s real ≥ 12
        (15, [6, 5, 5]),                    # 15.08s real ≥ 15
        (20, [6, 6, 5, 5]),                 # 20.67s real ≥ 20
        (24, [6, 5, 5, 5, 5]),              # 24.26s real ≥ 24
        (25, [6, 6, 5, 5, 5]),              # 25.26s real ≥ 25
        (30, [6, 6, 6, 5, 5, 5]),           # 30.85s real ≥ 30
    ])
    @pytest.mark.parametrize("tier", ["standard", "advanced"])
    def test_exact_match(self, total: int, expected: list[int], tier: str):
        assert split_duration(total, tier, "dynamic") == expected
        # La SUMA pedida a Atlas es target + margen (~1s), NO target exacto.
        assert sum(split_duration(total, tier, "dynamic")) >= total

    def test_dynamic_more_clips_than_cinematic(self):
        """A misma duración, dinámico produce >=clips que cinematográfico."""
        for total in [10, 15, 20, 24, 30]:
            cine = split_duration(total, "standard", "cinematic")
            dyn = split_duration(total, "standard", "dynamic")
            assert len(dyn) >= len(cine), (
                f"En {total}s, dynamic={len(dyn)} clips < cinematic={len(cine)}"
            )


# ---------------------------------------------------------------------------
# Pro — strategy ignorada (1 clip multi-shot hasta 15s)
# ---------------------------------------------------------------------------
class TestProIgnoresStrategy:
    @pytest.mark.parametrize("total", [5, 10, 12, 15])
    @pytest.mark.parametrize("strategy", ["cinematic", "dynamic"])
    def test_pro_single_clip_ignores_strategy(self, total: int, strategy: str):
        assert split_duration(total, "pro", strategy) == [total]

    @pytest.mark.parametrize("strategy", ["cinematic", "dynamic"])
    def test_pro_above_15s_chunks(self, strategy: str):
        # 30s pro: 2 clips de 15s, ambas estrategias producen lo mismo
        assert split_duration(30, "pro", strategy) == [15, 15]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Estrategia"):
            split_duration(15, "standard", "ultraplus")

    def test_unknown_tier_raises(self):
        with pytest.raises(ValueError, match="Tier"):
            split_duration(15, "ultraplus", "cinematic")

    def test_zero_returns_empty(self):
        assert split_duration(0, "standard", "cinematic") == []
        assert split_duration(0, "pro", "dynamic") == []

    def test_below_min_floor(self):
        assert split_duration(1, "standard", "cinematic") == [4]
        assert split_duration(3, "standard", "dynamic") == [4]

    def test_default_strategy_is_dynamic(self):
        """Si no se pasa strategy, el default es DYNAMIC."""
        assert split_duration(15, "standard") == split_duration(15, "standard", "dynamic")

    def test_off_table_duration_falls_back(self):
        """Una duración fuera de la tabla preset (ej. 18s) cae al fallback
        automático respetando los límites del tier."""
        clips = split_duration(18, "standard", "dynamic")
        assert sum(clips) == 18
        assert all(4 <= c <= 12 for c in clips)


# ---------------------------------------------------------------------------
# describe_split — coherencia con el formato que pide el brief
# ---------------------------------------------------------------------------
class TestDescribeSplit:
    def test_uniform(self):
        assert describe_split([5, 5, 5]) == "3 clips de 5s"

    def test_mixed(self):
        # 12,8,5 → "3 clips: 12s + 8s + 5s"
        assert describe_split([12, 8, 5]) == "3 clips: 12s + 8s + 5s"

    def test_single(self):
        assert describe_split([15]) == "1 clip de 15s"
