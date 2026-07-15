from .discovery import router as discovery_router
from .radar import router as radar_router
from .calendar import router as calendar_router
from .hooks import router as hooks_router
from .performance import router as performance_router
from .presets import router as presets_router
from .replicate_viral import router as replicate_viral_router
from .shortcuts import router as shortcuts_router
from .watermark_remover import router as watermark_remover_router

__all__ = [
    "discovery_router",
    "radar_router",
    "calendar_router",
    "hooks_router",
    "performance_router",
    "presets_router",
    "replicate_viral_router",
    "shortcuts_router",
    "watermark_remover_router",
]
