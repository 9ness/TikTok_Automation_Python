from .copyright import router as copyright_router
from .presidents import router as presidents_router
from .pronosticos import router as pronosticos_router
from .subs_auto import frame_router as subs_auto_frame_router
from .subs_auto import router as subs_auto_router

__all__ = [
    "copyright_router",
    "presidents_router",
    "pronosticos_router",
    "subs_auto_router",
    "subs_auto_frame_router",
]
