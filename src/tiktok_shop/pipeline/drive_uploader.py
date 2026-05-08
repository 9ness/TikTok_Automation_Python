"""Persistencia de vídeo + metadata en la carpeta TIKTOK_SHOP local.

Mismo patrón que Creator Reward: el "Drive uploader" en realidad solo copia
al path local sincronizado con Drive Desktop / rclone mount. Drive sube por
su cuenta al cabo de unos segundos.

La estructura final es:
    TIKTOK_SHOP/_users/@cuenta/products/<slug>/videos/
        <YYYY-MM-DD>_<hook_category>_v<n>.mp4
        <YYYY-MM-DD>_<hook_category>_v<n>.json
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from typing import Any

from src.tiktok_shop.config import user_videos_folder


def _next_version(folder: str, base_name: str) -> int:
    if not os.path.isdir(folder):
        return 1
    existing = [f for f in os.listdir(folder) if f.startswith(base_name) and f.endswith(".mp4")]
    return len(existing) + 1


def upload_video(
    *,
    src_video_path: str,
    username: str,
    product_slug: str,
    hook_category: str = "general",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Copia el vídeo + escribe metadata.json adyacente.

    Returns:
        (final_video_path, metadata_path)
    """
    if not os.path.exists(src_video_path):
        raise FileNotFoundError(src_video_path)

    target_dir = user_videos_folder(username, product_slug)
    os.makedirs(target_dir, exist_ok=True)

    today = date.today().isoformat()
    base = f"{today}_{hook_category}"
    n = _next_version(target_dir, base)
    final_name = f"{base}_v{n}.mp4"
    final_path = os.path.join(target_dir, final_name)
    shutil.copy2(src_video_path, final_path)

    meta_path = os.path.join(target_dir, f"{base}_v{n}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata or {}, f, ensure_ascii=False, indent=2)

    return final_path, meta_path
