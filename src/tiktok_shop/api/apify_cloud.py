"""Cliente Apify — scraping TikTok pay-per-use.

Apify hostea "actors" (scrapers) que devuelven JSON con metadata de
vídeos TikTok (URL del MP4, views, likes, comments, music, etc).

Pricing (verificado 2026-05 en apify.com):
  - Actor `apidojo/tiktok-scraper`: $0.30 / 1000 posts
  - Actor `apidojo/tiktok-scraper-api`: $0.006 query + $0.0003/post,
    primeros 10-20 GRATIS
  - $5 de crédito gratis al registrarse (cubre ~500-2000 productos)

Nuestra estrategia:
  1. Búsqueda por hashtag/keyword del producto → top N vídeos por views
  2. Para cada vídeo: opcional fetch de comentarios → objeciones reales
  3. Descargar MP4 → analizar con Gemini (visual + audio)

Doc oficial: https://docs.apify.com/api/v2
  Auth: Authorization: Bearer {APIFY_API_TOKEN}
  Endpoint Run-sync: POST /v2/acts/{actor_id}/run-sync-get-dataset-items
    (corre el actor y espera el resultado en una sola llamada)
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

import requests


APIFY_API_URL = "https://api.apify.com/v2"
SUBMIT_TIMEOUT_S = 180  # Apify "run-sync" puede tardar 30-60s
POLL_INTERVAL_S = 5.0
MAX_RETRIES_TRANSIENT = 2


# Actor IDs — verificados en apify.com/store. Permite override via env.
TIKTOK_SCRAPER_ACTOR = os.environ.get(
    "APIFY_TIKTOK_SEARCH_ACTOR", "clockworks/tiktok-scraper",
)
# Actor de comentarios — separado del scraper de búsqueda. Recibe URLs
# de vídeos y devuelve sus comentarios (texto + likes). Lo usamos para
# extraer objeciones/preguntas REALES del público (más afiladas que las
# reviews de Amazon porque vienen del propio canal TikTok).
TIKTOK_COMMENTS_ACTOR = os.environ.get(
    "APIFY_TIKTOK_COMMENTS_ACTOR", "clockworks/tiktok-comments-scraper",
)


class ApifyError(RuntimeError):
    """Error NO retryable (401, 402, payload inválido)."""
    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class ApifyTransient(RuntimeError):
    """Error transitorio (timeout/5xx/cola atascada)."""


def apify_is_configured() -> bool:
    return bool(os.environ.get("APIFY_API_TOKEN", "").strip())


def _api_token() -> str:
    return os.environ.get("APIFY_API_TOKEN", "").strip()


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_token()}",
        "Content-Type": "application/json",
    }


def _run_actor_sync(
    actor_id: str,
    input_data: dict[str, Any],
    *,
    timeout_s: int = SUBMIT_TIMEOUT_S,
) -> list[dict[str, Any]]:
    """Corre un actor de Apify síncronamente y devuelve los items del
    dataset. Usa el endpoint `run-sync-get-dataset-items` que combina
    submit + wait + fetch en 1 sola llamada.

    Replicate Actor IDs llevan "/" pero la API requiere "~": "apidojo/x"
    → "apidojo~x".
    """
    actor_path = actor_id.replace("/", "~")
    url = f"{APIFY_API_URL}/acts/{actor_path}/run-sync-get-dataset-items"
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES_TRANSIENT + 1):
        try:
            r = requests.post(
                url, headers=_headers(), json=input_data,
                timeout=timeout_s,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = ApifyTransient(f"network: {e}")
            if attempt < MAX_RETRIES_TRANSIENT:
                time.sleep(2 ** attempt)
                continue
            raise last_exc
        if r.status_code in (401, 403):
            raise ApifyError(
                f"Apify auth inválida ({r.status_code}). Verifica APIFY_API_TOKEN.",
                status_code=r.status_code, kind="auth",
            )
        if r.status_code == 402:
            raise ApifyError(
                "Apify sin créditos. Recarga en apify.com/settings/billing.",
                status_code=402, kind="credits",
            )
        if r.status_code == 404:
            raise ApifyError(
                f"Apify actor '{actor_id}' no existe o no tienes acceso.",
                status_code=404, kind="actor_not_found",
            )
        if r.status_code >= 500 or r.status_code == 429:
            last_exc = ApifyTransient(f"HTTP {r.status_code}: {r.text[:200]}")
            if attempt < MAX_RETRIES_TRANSIENT:
                time.sleep(2 ** attempt)
                continue
            raise last_exc
        if r.status_code >= 400:
            raise ApifyError(
                f"Apify bad request {r.status_code}: {r.text[:400]}",
                status_code=r.status_code, kind="invalid_request",
            )
        try:
            return r.json()
        except ValueError as e:
            raise ApifyError(f"Apify respuesta no-JSON: {e}", kind="invalid_response")
    raise ApifyTransient(f"Apify falló tras {MAX_RETRIES_TRANSIENT+1} intentos: {last_exc}")


# ═════════════════════════════════════════════════════════════════════
# TikTok search
# ═════════════════════════════════════════════════════════════════════
def search_tiktok_videos(
    query: str,
    *,
    limit: int = 10,
    sort_by: str = "popular",
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Busca vídeos TikTok por keyword y devuelve los top `limit` ordenados
    por popularidad (views/likes).

    Returns:
        Lista de dicts con campos clave (compatible con apidojo/tiktok-scraper):
          - id, webVideoUrl, videoUrl (MP4 download), text (caption),
          - playCount, diggCount (likes), commentCount, shareCount,
          - videoMeta {duration, height, width}, music {meta, ...},
          - authorMeta {name, fans, ...}

    Args:
        query: keyword del producto (ej. "cinta correr plegable")
        limit: máx vídeos a devolver
        sort_by: "popular" | "recent" — orden de los resultados
        log_callback: opcional, recibe mensajes de progreso
    """
    if log_callback:
        log_callback(f"🔎 Apify: buscando '{query}' en TikTok (limit={limit})…")

    # Input schema clockworks/tiktok-scraper (verificado live 2026-05):
    #   - searchQueries: array de keywords
    #   - resultsPerPage: int
    #   - shouldDownloadVideos/Covers/Subtitles/SlideshowImages: bool
    #     (false porque solo queremos metadata; el MP4 lo bajamos aparte)
    #   - proxyCountryCode: ES/US/...
    # NOTA: apidojo/tiktok-scraper devuelve {noResults: true} para
    # cualquier query (broken upstream), por eso usamos clockworks.
    # NOTA: shouldDownloadVideos=True → Apify proxy descarga el MP4 a
    # su key-value store y devuelve URLs en `mediaUrls`. Más fiable que
    # videoMeta.downloadAddr (TikTok CDN rechaza descargas externas sin
    # User-Agent/Referer correctos). Coste extra negligible.
    input_data = {
        "searchQueries": [query],
        "resultsPerPage": min(limit, 30),
        "shouldDownloadVideos": True,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
        "proxyCountryCode": "ES",
    }
    items = _run_actor_sync(TIKTOK_SCRAPER_ACTOR, input_data)
    if not isinstance(items, list):
        if log_callback:
            log_callback(f"⚠️ Apify devolvió shape inesperado: {type(items)}")
        return []

    # Sort: si pedimos popular, ordena por playCount desc.
    if sort_by == "popular":
        items.sort(key=lambda x: int(x.get("playCount") or 0), reverse=True)
    elif sort_by == "recent":
        items.sort(key=lambda x: x.get("createTimeISO") or "", reverse=True)

    # Trim a limit
    items = items[:limit]
    if log_callback:
        log_callback(
            f"✅ Apify: {len(items)} vídeos encontrados. "
            f"Top views: {max((int(x.get('playCount') or 0) for x in items), default=0):,}"
        )
    return items


def _first_music_url(music: dict[str, Any]) -> str:
    """Devuelve la primera URL de preview del audio. clockworks puede dar
    `playUrl` (str) o `playUrlList` (list). Tolerante a ambos."""
    pu = music.get("playUrl")
    if isinstance(pu, str) and pu:
        return pu
    lst = music.get("playUrlList")
    if isinstance(lst, list) and lst:
        return str(lst[0])
    return ""


def extract_video_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Normaliza el dict del actor a un shape interno simple para
    consumir desde el research_service. Tolerante a campos faltantes."""
    video_meta = item.get("videoMeta") or {}
    # clockworks expone el audio en `musicMeta`; otros actores en `music`.
    music = item.get("musicMeta") or item.get("music") or {}
    author = item.get("authorMeta") or {}
    # clockworks con shouldDownloadVideos=True expone `mediaUrls[0]` →
    # URL proxied de Apify (estable). Fallbacks por compat.
    media_urls = item.get("mediaUrls") or []
    mp4_url = (
        (media_urls[0] if media_urls else "")
        or item.get("videoUrl")
        or video_meta.get("downloadAddr")
        or ""
    )
    return {
        "tiktok_id": str(item.get("id") or ""),
        "url": item.get("webVideoUrl") or "",
        "mp4_url": mp4_url,
        "caption": item.get("text") or "",
        "hashtags": [h.get("name", "") for h in (item.get("hashtags") or []) if isinstance(h, dict)],
        "view_count": int(item.get("playCount") or 0),
        "like_count": int(item.get("diggCount") or 0),
        "comment_count": int(item.get("commentCount") or 0),
        "share_count": int(item.get("shareCount") or 0),
        "duration_s": float(video_meta.get("duration") or 0),
        "width": int(video_meta.get("width") or 0),
        "height": int(video_meta.get("height") or 0),
        # Audio/sonido — clave para viralidad TikTok. clockworks musicMeta:
        # {musicName, musicAuthor, musicId, musicOriginal, playUrl}.
        "music_id": str(music.get("musicId") or music.get("id") or ""),
        "music_name": music.get("musicName") or music.get("name") or "",
        "music_author": music.get("musicAuthor") or music.get("authorName") or "",
        "music_is_original": bool(music.get("musicOriginal") or music.get("original") or False),
        "music_url": _first_music_url(music),
        "author_name": author.get("name") or "",
        "author_followers": int(author.get("fans") or 0),
        "created_at": item.get("createTimeISO") or "",
    }


def scrape_tiktok_comments(
    video_urls: list[str],
    *,
    max_comments_per_video: int = 30,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Scrape los comentarios de N vídeos TikTok via Apify.

    Devuelve lista de dicts normalizados: {text, like_count, video_url,
    reply_count}. Los comentarios con más likes son los que mejor
    representan las dudas/objeciones del público.

    Args:
        video_urls: URLs de vídeos TikTok (https://www.tiktok.com/@x/video/123)
        max_comments_per_video: tope por vídeo (más = más coste Apify)
        log_callback: opcional, mensajes de progreso
    """
    urls = [u for u in (video_urls or []) if u]
    if not urls:
        return []
    if log_callback:
        log_callback(
            f"💬 Apify: scraping comentarios de {len(urls)} vídeos "
            f"(máx {max_comments_per_video}/vídeo)…"
        )
    # Input schema clockworks/tiktok-comments-scraper:
    #   postURLs: array de URLs de vídeo
    #   commentsPerPost: int
    #   maxRepliesPerComment: int (0 = sin replies, más barato)
    input_data = {
        "postURLs": urls,
        "commentsPerPost": max_comments_per_video,
        "maxRepliesPerComment": 0,
    }
    try:
        items = _run_actor_sync(TIKTOK_COMMENTS_ACTOR, input_data)
    except (ApifyError, ApifyTransient) as e:
        if log_callback:
            log_callback(f"  ⚠️ Apify comments falló ({e}) — sigo sin comentarios")
        return []
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or it.get("comment") or "").strip()
        if not text:
            continue
        out.append({
            "text": text,
            "like_count": int(it.get("diggCount") or it.get("likesCount") or 0),
            "reply_count": int(it.get("replyCommentTotal") or it.get("repliesCount") or 0),
            "video_url": it.get("videoWebUrl") or it.get("postUrl") or "",
        })
    # Orden por likes desc — los comentarios con más likes resumen las
    # dudas/objeciones que más comparte el público.
    out.sort(key=lambda c: c["like_count"], reverse=True)
    if log_callback:
        log_callback(f"  ✓ {len(out)} comentarios recogidos")
    return out


def fetch_videos_by_url(
    video_urls: list[str],
    *,
    log_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Recupera metadata actual (views/likes/comments/shares) de vídeos
    TikTok concretos por su URL. Usado por el feedback loop de rendimiento
    para refrescar las métricas de los vídeos que el operador ya publicó.

    Devuelve los items crudos del actor (pásalos por extract_video_metadata)."""
    urls = [u for u in (video_urls or []) if u]
    if not urls:
        return []
    if log_callback:
        log_callback(f"📊 Apify: refrescando métricas de {len(urls)} vídeos…")
    input_data = {
        "postURLs": urls,
        "resultsPerPage": len(urls),
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
    }
    items = _run_actor_sync(TIKTOK_SCRAPER_ACTOR, input_data)
    return items if isinstance(items, list) else []


def download_tiktok_video(
    mp4_url: str, dest_path: str,
    *, timeout_s: int = 120,
) -> str:
    """Descarga el MP4 del TikTok a disk.

    Con shouldDownloadVideos=True, clockworks guarda el MP4 en su
    key-value store de Apify (URL `https://api.apify.com/v2/key-value-
    stores/.../records/...mp4`) que requiere `?token=` para acceder
    (403 sin él). Para esas URLs añadimos el token automáticamente.
    """
    if not mp4_url:
        raise ApifyError("mp4_url vacío — el actor no devolvió downloadAddr")
    # URLs del key-value store de Apify requieren auth con el token.
    if "api.apify.com" in mp4_url and "token=" not in mp4_url:
        sep = "&" if "?" in mp4_url else "?"
        mp4_url = f"{mp4_url}{sep}token={_api_token()}"
    try:
        r = requests.get(mp4_url, timeout=timeout_s, stream=True)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ApifyTransient(f"download TikTok network: {e}")
    if r.status_code >= 400:
        raise ApifyTransient(f"download TikTok HTTP {r.status_code}")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                f.write(chunk)
    return dest_path
