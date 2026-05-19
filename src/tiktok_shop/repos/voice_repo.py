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
        if not include_presets:
            return sorted(clones, key=lambda v: v.created_at, reverse=True)

        # Preferimos el catálogo system live de MiniMax (cacheado 24h en
        # Redis bajo `voice:minimax_system_catalog`). Garantiza que los
        # voice_id sean válidos cuando el usuario los seleccione (evita el
        # error 2054 "voice id not exist" causado por presets inventados).
        # Fallback a las listas hardcoded `DEFAULT_VOICE_PRESETS_*` si:
        #   - El cache aún no existe (primera carga sin sync)
        #   - MiniMax no está configurada
        # En ese caso usamos solo Spanish (los confirmados originales).
        preset_objs: list[VoiceClone] = []
        try:
            from src.tiktok_shop.api.minimax_catalog import get_system_voices
            live = get_system_voices(force_refresh=False)
        except Exception:
            live = []

        if live:
            for v in live:
                preset_objs.append(VoiceClone(
                    id=f"preset_{v['id']}",
                    name=v["name"],
                    minimax_voice_id=v["id"],
                    language=v["language"],
                    is_preset=True,
                    tags=["preset", v["language"]] + (
                        [v["gender"]] if v.get("gender") else []
                    ),
                ))
        else:
            # Fallback solo a Spanish (validados manualmente). NO incluimos
            # DEFAULT_VOICE_PRESETS_EN aquí porque algunos IDs son inventados
            # y romperían el TTS. El usuario debe llamar a /voices/sync para
            # poblar el catálogo real desde MiniMax.
            for p in DEFAULT_VOICE_PRESETS_ES:
                preset_objs.append(VoiceClone(
                    id=f"preset_{p['id']}",
                    name=p["label"],
                    minimax_voice_id=p["id"],
                    language="es",
                    is_preset=True,
                    tags=["preset", "es"],
                ))

        return (
            preset_objs
            + sorted(clones, key=lambda v: v.created_at, reverse=True)
        )

    def delete(self, voice_id: str) -> bool:
        if voice_id.startswith("preset_"):
            return False  # presets no se borran
        self.r.delete(self._key(voice_id))
        self.r.srem(self.INDEX_KEY, voice_id)
        return True
