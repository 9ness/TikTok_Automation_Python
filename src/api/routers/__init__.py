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
    match_photos_file_router,
    match_photos_router,
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
    web_upload_router as editor_auto_web_upload_router,
)
from .tiktok_shop import (
    discovery_router as tiktok_shop_discovery_router,
    radar_router as tiktok_shop_radar_router,
    calendar_router as tiktok_shop_calendar_router,
    hooks_router as tiktok_shop_hooks_router,
    performance_router as tiktok_shop_performance_router,
    presets_router as tiktok_shop_presets_router,
    replicate_viral_router as tiktok_shop_replicate_viral_router,
    shortcuts_router as tiktok_shop_shortcuts_router,
    watermark_remover_router as tiktok_shop_watermark_remover_router,
)
from .viralizacion import enqueue_router as viralizacion_enqueue_router
from .nicho_ropa import prendas_router as nicho_ropa_prendas_router
from .nicho_ropa_personas import (
    chicas_router as nicho_ropa_personas_chicas_router,
    prendas_router as nicho_ropa_personas_prendas_router,
)
from .nicho_bof_cine import productos_router as nicho_bof_cine_router
from .cuenta_piloto import productos_router as cuenta_piloto_router
from .nicho_pov_bof_largo import productos_router as nicho_pov_bof_largo_router
from .nicho_creativos import productos_router as nicho_creativos_router
from .nicho_gorras import gorras_router as nicho_gorras_router
from .nicho_pov_bof import (
    folders_router as nicho_pov_bof_folders_router,
    productos_router as nicho_pov_bof_productos_router,
)
from .stats import router as stats_router
from .dashboard import router as dashboard_router
from .auth import router as auth_router
from .deploy import router as deploy_router
from .cuotas import cuotas_router
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
    "match_photos_router",
    "match_photos_file_router",
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
    "cuotas_router",
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
    "editor_auto_web_upload_router",
    "tiktok_shop_discovery_router",
    "tiktok_shop_radar_router",
    "tiktok_shop_calendar_router",
    "tiktok_shop_hooks_router",
    "tiktok_shop_performance_router",
    "tiktok_shop_presets_router",
    "tiktok_shop_replicate_viral_router",
    "tiktok_shop_shortcuts_router",
    "tiktok_shop_watermark_remover_router",
    "viralizacion_enqueue_router",
    "nicho_pov_bof_folders_router",
    "nicho_pov_bof_productos_router",
    "nicho_ropa_prendas_router",
    "nicho_ropa_personas_chicas_router",
    "nicho_ropa_personas_prendas_router",
    "nicho_bof_cine_router",
    "nicho_gorras_router",
    "cuenta_piloto_router",
    "nicho_pov_bof_largo_router",
    "nicho_creativos_router",
]
