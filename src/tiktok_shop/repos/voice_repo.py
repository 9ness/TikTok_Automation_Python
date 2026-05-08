"""CRUD de VoiceClone (catálogo de voces disponibles)."""

from __future__ import annotations

from src.tiktok_shop.config import DEFAULT_VOICE_PRESETS_ES
from src.tiktok_shop.models import VoiceClone
from .redis_base import ShopRedis, get_shop_redis


class VoiceRepo:
    INDEX_KEY = "voice:index"

    def __init__(self, redis: ShopRedis | None = None):
        self.r = redis or get_shop_redis()

    @staticmethod
    def _key(vid: str) -> str:
        return f"voice:{vid}"

    def save(self, voice: VoiceClone) -> VoiceClone:
        self.r.set_json(self._key(voice.id), voice.model_dump())
        self.r.sadd(self.INDEX_KEY, voice.id)
        return voice

    def get(self, voice_id: str) -> VoiceClone | None:
        data = self.r.get_json(self._key(voice_id))
        if not data:
            return None
        try:
            return VoiceClone.model_validate(data)
        except Exception as e:
            print(f"[VoiceRepo] decode error {voice_id}: {e}")
            return None

    def list_all(self, include_presets: bool = True) -> list[VoiceClone]:
        ids = self.r.smembers(self.INDEX_KEY)
        clones = [self.get(i) for i in ids]
        clones = [v for v in clones if v is not None]
        if include_presets:
            preset_objs = [
                VoiceClone(
                    id=f"preset_{p['id']}",
                    name=p["label"],
                    minimax_voice_id=p["id"],
                    language="es",
                    is_preset=True,
                    tags=["preset", "es"],
                )
                for p in DEFAULT_VOICE_PRESETS_ES
            ]
            return preset_objs + sorted(clones, key=lambda v: v.created_at, reverse=True)
        return sorted(clones, key=lambda v: v.created_at, reverse=True)

    def delete(self, voice_id: str) -> bool:
        if voice_id.startswith("preset_"):
            return False  # presets no se borran
        self.r.delete(self._key(voice_id))
        self.r.srem(self.INDEX_KEY, voice_id)
        return True
