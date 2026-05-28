from .products import photo_file_router as product_photo_file_router
from .products import router as products_router
from .users import router as users_router
from .voices import router as voices_router
from .voices import sample_router as voices_sample_router
from .generations import router as generations_router
from .generations import video_router as generations_video_router
from .queue import router as queue_router
from .queue import video_router as queue_video_router
from .creator_reward import (
    construccion_pov_router,
    copyright_router,
    presidents_router,
    pronosticos_router,
    subs_auto_frame_router,
    subs_auto_router,
)
from .editor_auto import (
    enqueue_router as editor_auto_enqueue_router,
    folders_router as editor_auto_folders_router,
    plans_router as editor_auto_plans_router,
    referrals_router as editor_auto_referrals_router,
    sharing_router as editor_auto_sharing_router,
    stickers_router as editor_auto_stickers_router,
    subscriptions_router as editor_auto_subscriptions_router,
    tools_router as editor_auto_tools_router,
    users_router as editor_auto_users_router,
)
from .tiktok_shop import (
    presets_router as tiktok_shop_presets_router,
    replicate_viral_router as tiktok_shop_replicate_viral_router,
    watermark_remover_router as tiktok_shop_watermark_remover_router,
)
from .stats import router as stats_router
from .dashboard import router as dashboard_router
from .auth import router as auth_router
from .deploy import router as deploy_router
from .diagnostics import router as diagnostics_router
from .fonts import file_router as fonts_file_router, router as fonts_router

__all__ = [
    "products_router",
    "product_photo_file_router",
    "users_router",
    "voices_router",
    "voices_sample_router",
    "generations_router",
    "generations_video_router",
    "queue_router",
    "queue_video_router",
    "construccion_pov_router",
    "copyright_router",
    "presidents_router",
    "pronosticos_router",
    "subs_auto_router",
    "subs_auto_frame_router",
    "stats_router",
    "dashboard_router",
    "fonts_router",
    "fonts_file_router",
    "auth_router",
    "deploy_router",
    "diagnostics_router",
    "editor_auto_enqueue_router",
    "editor_auto_folders_router",
    "editor_auto_sharing_router",
    "editor_auto_stickers_router",
    "editor_auto_tools_router",
    "editor_auto_users_router",
    "editor_auto_plans_router",
    "editor_auto_subscriptions_router",
    "editor_auto_referrals_router",
    "tiktok_shop_presets_router",
    "tiktok_shop_replicate_viral_router",
    "tiktok_shop_watermark_remover_router",
]
