"""Fixtures compartidas para tests de TikTok Shop.

Centraliza:
- FakeRedis: implementación in-memory de `ShopRedis` para aislar tests
  CRUD sin tocar Upstash real.
- Sample data: usuarios, productos y generaciones de prueba.
- Helpers de filesystem (carpetas tmp con fotos válidas).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# FakeRedis — implementa la interfaz pública de `ShopRedis` sin red
# ---------------------------------------------------------------------------
class FakeRedis:
    """Sustituto in-memory de `ShopRedis`. Cubre los comandos que usan los
    repos del módulo: GET/SET (json + str), DEL, KEYS, SADD/SREM/SMEMBERS,
    LPUSH/LRANGE.
    """

    def __init__(self) -> None:
        self.kv: dict[str, object] = {}
        self.sets: dict[str, set[str]] = defaultdict(set)
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.prefix = "tiktok_shop:"

    def is_available(self) -> bool:
        return True

    def _full_key(self, key: str) -> str:
        if self.prefix and not key.startswith(self.prefix):
            return f"{self.prefix}{key}"
        return key

    # JSON
    def get_json(self, key: str):
        v = self.kv.get(self._full_key(key))
        return v if isinstance(v, (dict, list)) else None

    def set_json(self, key: str, value) -> bool:
        self.kv[self._full_key(key)] = value
        return True

    # Strings
    def get_str(self, key: str) -> str | None:
        v = self.kv.get(self._full_key(key))
        return v if isinstance(v, str) else None

    def set_str(self, key: str, value: str) -> bool:
        self.kv[self._full_key(key)] = value
        return True

    def delete(self, key: str) -> bool:
        full = self._full_key(key)
        existed = full in self.kv or full in self.sets or full in self.lists
        self.kv.pop(full, None)
        self.sets.pop(full, None)
        self.lists.pop(full, None)
        return existed

    def keys(self, pattern: str) -> list[str]:
        full_pattern = self._full_key(pattern)
        out = []
        all_keys = list(self.kv.keys()) + list(self.sets.keys()) + list(self.lists.keys())
        for k in all_keys:
            if _glob_match(full_pattern, k):
                # repo strip prefix
                out.append(k[len(self.prefix):] if k.startswith(self.prefix) else k)
        return out

    # Sets
    def sadd(self, key: str, member: str) -> bool:
        self.sets[self._full_key(key)].add(member)
        return True

    def srem(self, key: str, member: str) -> bool:
        self.sets[self._full_key(key)].discard(member)
        return True

    def smembers(self, key: str) -> list[str]:
        return list(self.sets.get(self._full_key(key), set()))

    # Lists (LPUSH inserta al principio; LRANGE sobre lista actual)
    def lpush(self, key: str, value: str) -> int:
        self.lists[self._full_key(key)].insert(0, value)
        return len(self.lists[self._full_key(key)])

    def lrange(self, key: str, start: int = 0, stop: int = -1) -> list[str]:
        lst = self.lists.get(self._full_key(key), [])
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]


def _glob_match(pattern: str, key: str) -> bool:
    """Soporte mínimo de glob (`*`) para `keys()`."""
    if "*" not in pattern:
        return pattern == key
    if pattern == "*":
        return True
    if pattern.endswith("*") and not pattern.startswith("*"):
        return key.startswith(pattern[:-1])
    if pattern.startswith("*") and not pattern.endswith("*"):
        return key.endswith(pattern[1:])
    # Caso prefijo*sufijo
    parts = pattern.split("*")
    if len(parts) == 2:
        prefix, suffix = parts
        return key.startswith(prefix) and key.endswith(suffix)
    return False


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def jpeg_path(tmp_path: Path) -> Path:
    """JPEG 1200×800. Low-res en sentido estricto (MIN=800<1024) — sirve
    para testear que el detector OS detecta uno-de-dos lados pequeño."""
    img = Image.new("RGB", (1200, 800), color=(200, 100, 50))
    p = tmp_path / "photo.jpg"
    img.save(p, "JPEG", quality=85)
    return p


@pytest.fixture
def small_jpeg_path(tmp_path: Path) -> Path:
    """Foto JPEG 800×600 (<1024 → debe disparar low-res flag)."""
    img = Image.new("RGB", (800, 600), color=(50, 100, 200))
    p = tmp_path / "small.jpg"
    img.save(p, "JPEG")
    return p


@pytest.fixture
def png_path(tmp_path: Path) -> Path:
    img = Image.new("RGB", (1080, 1920), color=(0, 200, 100))
    p = tmp_path / "photo.png"
    img.save(p, "PNG")
    return p


@pytest.fixture
def webp_path(tmp_path: Path) -> Path:
    img = Image.new("RGB", (1080, 1920), color=(100, 50, 200))
    p = tmp_path / "photo.webp"
    img.save(p, "WEBP")
    return p


@pytest.fixture
def sample_user():
    """TikTokUser limpio para guardar en repos."""
    from src.tiktok_shop.models import TikTokUser
    return TikTokUser(
        username="@test_user",
        display_name="Test User",
        niche="fitness",
    )


@pytest.fixture
def sample_product():
    """Product limpio."""
    from src.tiktok_shop.models import Product
    return Product(
        slug="test_product",
        name="Test Product",
        brand="TestBrand",
        category="fitness",
    )


@pytest.fixture
def sample_generation():
    """VideoGeneration completada."""
    from src.tiktok_shop.models import VideoGeneration, VideoCost, GenerationStatus
    return VideoGeneration(
        user_id="u1",
        product_id="p1",
        tier_used="standard",
        duration_seconds=15,
        resolution="720p",
        cost=VideoCost(
            video_generation=0.27, voice_tts=0.005, total=0.275,
            estimated_at_creation=0.28, actual_after_completion=0.275,
        ),
        generation_status=GenerationStatus.COMPLETED,
    )
