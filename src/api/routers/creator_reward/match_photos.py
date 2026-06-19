"""Fotos de partido para el estilo de vídeo VIRAL (V2).

Reutiliza la búsqueda de imágenes que existía en Master Picks (scrape de Bing
Images, sin API key) y la trae al VPS para guardar fotos a disco en formato
vertical 9:16 (1080×1920) dentro de la estructura de carpetas de la v1:

    {TIKTOK_ROOT_PATH}/BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/<Equipo>/<slug>-N.jpg

Endpoints (auth por X-API-Key heredada del router):
- POST   /search        → busca imágenes en Bing (devuelve URLs + dimensiones).
- GET    /folders       → lista las carpetas de equipo bajo fotos/ con conteo.
- GET    /list          → lista las fotos guardadas de un equipo.
- POST   /save          → descarga una URL, recorta a 9:16 y la guarda.
- DELETE /photo         → borra una foto guardada.

Y un router SIN auth para servir los ficheros a <img> (igual que el sample de
voces / las fotos de producto):
- GET    /file          → devuelve el JPG guardado.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, ValidationError

_PREFIX = "/api/v1/creator-reward/match-photos"

router = APIRouter(
    prefix=_PREFIX,
    tags=["creator-reward · match-photos"],
    dependencies=[Depends(get_current_user)],
)

# Router de ficheros SIN auth (para que <img src> cargue sin headers).
file_router = APIRouter(prefix=_PREFIX, tags=["creator-reward · match-photos"])

_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.bing.com/",
}


# ── Schemas ───────────────────────────────────────────────────────────────────
class ImageResult(BaseModel):
    url: str
    thumbnail: str
    title: str
    width: int = 0
    height: int = 0


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=120)
    limit: int = Field(default=40, ge=1, le=60)


class SearchResponse(BaseModel):
    images: list[ImageResult]


class FolderItem(BaseModel):
    name: str
    count: int


class FoldersResponse(BaseModel):
    folders: list[FolderItem]


class PhotoItem(BaseModel):
    filename: str
    url: str
    width: int
    height: int
    size_kb: int


class PhotoListResponse(BaseModel):
    team: str
    photos: list[PhotoItem]


class SaveRequest(BaseModel):
    image_url: str = Field(..., min_length=8)
    team: str = Field(..., min_length=1, max_length=80)


class SaveResponse(BaseModel):
    team: str
    filename: str
    url: str


class TeamStatus(BaseModel):
    name: str
    has_photos: bool
    count: int


class TeamsForDateResponse(BaseModel):
    date: str
    teams: list[TeamStatus]


class AutoFetchRequest(BaseModel):
    team: str = Field(..., min_length=1, max_length=80)
    mode: Literal["missing", "all"] = "missing"
    query: str | None = None


class AutoFetchResponse(BaseModel):
    team: str
    status: Literal["created", "exists", "no_good", "failed"]
    filename: str | None = None
    url: str | None = None
    source: str | None = None
    query: str | None = None
    count: int = 0
    reason: str | None = None


# ── Helpers de disco ──────────────────────────────────────────────────────────
def _clips_root() -> Path:
    """{TIKTOK_ROOT_PATH}/BIBLIOTECA_PRONOSTICOS_CLIPS (respeta config.json)."""
    root = os.environ.get("TIKTOK_ROOT_PATH")
    if not root:
        raise APIError("TIKTOK_ROOT_PATH no está configurado en el servidor.")
    folder = "BIBLIOTECA_PRONOSTICOS_CLIPS"
    cfg_path = os.path.join("config", "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            folder = cfg.get("folder_structure", {}).get(
                "pronosticos_clips_folder", folder
            )
        except Exception:
            pass
    return Path(root) / folder


def _fotos_root() -> Path:
    return _clips_root() / "fotos"


def _safe_team(team: str) -> str:
    """Normaliza el nombre del equipo a una carpeta segura (sin path traversal)."""
    t = (team or "").strip()
    t = t.replace("/", " ").replace("\\", " ")
    t = re.sub(r"[^\w\s\-]", "", t, flags=re.UNICODE).strip()
    t = re.sub(r"\s+", " ", t)
    if not t or t in {".", ".."}:
        raise ValidationError("Nombre de equipo inválido.")
    return t


def _slug(team: str) -> str:
    s = _safe_team(team).lower().replace(" ", "-")
    return re.sub(r"-+", "-", s) or "foto"


def _team_dir(team: str, create: bool = False) -> Path:
    d = _fotos_root() / _safe_team(team)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(filename: str) -> str:
    name = os.path.basename((filename or "").strip())
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValidationError("Nombre de archivo inválido.")
    return name


# ── Búsqueda Bing (portada de Master Picks) ─────────────────────────────────────
def _bing_image_search(query: str, limit: int) -> list[ImageResult]:
    qft = "+filterui:imagesize-large+filterui:photo-photo"
    url = (
        "https://www.bing.com/images/search?"
        f"q={quote(query)}&qft={quote(qft)}&form=IRFLTR&first=1"
    )
    try:
        resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=12)
    except Exception as e:  # pragma: no cover - red
        raise APIError(f"No se pudo contactar con el buscador: {e}")
    if resp.status_code != 200:
        raise APIError(f"El buscador devolvió {resp.status_code}.")
    html = resp.text

    results: list[ImageResult] = []
    seen: set[str] = set()
    for m in re.finditer(r'<a\s+[^>]*class="iusc"[^>]*>', html, re.IGNORECASE):
        anchor = m.group(0)
        mm = re.search(r'\bm="([^"]+)"', anchor) or re.search(r"\bm='([^']+)'", anchor)
        if not mm:
            continue
        href_m = re.search(r'href="([^"]+)"', anchor) or re.search(
            r"href='([^']+)'", anchor
        )
        href = href_m.group(1).replace("&amp;", "&") if href_m else ""
        wm = re.search(r"[?&]expw=(\d+)", href)
        hm = re.search(r"[?&]exph=(\d+)", href)
        width = int(wm.group(1)) if wm else 0
        height = int(hm.group(1)) if hm else 0
        decoded = (
            mm.group(1)
            .replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&#x27;", "'")
            .replace("&#39;", "'")
        )
        try:
            data = json.loads(decoded)
        except Exception:
            continue
        murl = (data.get("murl") or "").strip()
        turl = (data.get("turl") or "").strip()
        title = re.sub(r"<[^>]+>", "", data.get("t") or "").strip()
        if not murl or not re.match(r"^https?://", murl, re.IGNORECASE) or murl in seen:
            continue
        if width and height and (width < 800 or height < 600):
            continue
        seen.add(murl)
        results.append(
            ImageResult(
                url=murl,
                thumbnail=turl or murl,
                title=title or "Resultado",
                width=width,
                height=height,
            )
        )

    # Fallback genérico si Bing varió el marcado (solo si el parser principal = 0).
    if not results:
        for gm in re.finditer(
            r"https?://[^\s\"'<>\\]+?\.(?:jpg|jpeg|png|webp)", html, re.IGNORECASE
        ):
            u = gm.group(0)
            if any(
                bad in u
                for bad in ("bing.com", "bing.net", "gstatic.com", "encrypted-tbn")
            ) or len(u) >= 1000 or u in seen:
                continue
            seen.add(u)
            results.append(
                ImageResult(url=u, thumbnail=u, title="Resultado", width=0, height=0)
            )

    results.sort(key=lambda r: -(r.width * r.height))
    return results[:limit]


def _cover_9x16(img: Image.Image, tw: int = 1080, th: int = 1920) -> Image.Image:
    """Escala 'cover' a 9:16 y recorta centrado (sin deformar)."""
    img = img.convert("RGB")
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    rw, rh = max(1, round(sw * scale)), max(1, round(sh * scale))
    img = img.resize((rw, rh), Image.Resampling.LANCZOS)
    left = (rw - tw) // 2
    top = (rh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _next_index(dest: Path, slug: str) -> int:
    if not dest.exists():
        return 1
    nums = [0]
    for p in dest.iterdir():
        m = re.match(rf"^{re.escape(slug)}-(\d+)\.jpe?g$", p.name, re.IGNORECASE)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1


def _file_url(team: str, filename: str) -> str:
    return f"{_PREFIX}/file?team={quote(team)}&filename={quote(filename)}"


def _persist_image(img: Image.Image, team: str) -> tuple[str, str]:
    """Recorta a 9:16 y guarda en fotos/<team>/. Devuelve (filename, url)."""
    out = _cover_9x16(img)
    dest = _team_dir(team, create=True)
    slug = _slug(team)
    filename = f"{slug}-{_next_index(dest, slug)}.jpg"
    out.save(dest / filename, "JPEG", quality=88)
    return filename, _file_url(team, filename)


def _count_photos(team: str) -> int:
    d = _team_dir(team)
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.suffix.lower() in _IMG_EXTS and p.is_file())


def _split_teams(match: str) -> list[str]:
    """'Barcelona vs Real Madrid' → ['Barcelona', 'Real Madrid']."""
    parts = re.split(r"\s+(?:vs\.?|v\.?|-|–|x)\s+", str(match or ""), flags=re.IGNORECASE)
    return [p.strip() for p in parts if p and p.strip()]


# ── Auto-fetch: una foto de JUGADOR por equipo (filtro Gemini Vision) ──────────
def _download_valid(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_BROWSER_HEADERS, timeout=12)
        if r.status_code != 200 or len(r.content) < 8000:
            return None
        im = Image.open(io.BytesIO(r.content))
        if im.width < 500 or im.height < 500:
            return None
        im.convert("RGB")  # fuerza decodificar (descarta corruptas/SVG)
        return r.content
    except Exception:
        return None


def _pick_best_player(images: list[bytes], team: str) -> int:
    """Gemini Vision elige la mejor foto que muestre un JUGADOR real (cara+cuerpo).
    Devuelve el índice 0-based, o -1 si NINGUNA vale. Si la IA falla → 0."""
    if not images:
        return -1
    try:
        thumbs: list[bytes] = []
        for b in images:
            im = Image.open(io.BytesIO(b)).convert("RGB")
            buf = io.BytesIO()
            _cover_9x16(im, 320, 420).save(buf, "JPEG", quality=65)
            thumbs.append(buf.getvalue())
        prompt = (
            f"Te paso {len(images)} imágenes CANDIDATAS (índice 0..{len(images) - 1}) "
            f"como FONDO vertical 9:16 de un vídeo de TikTok sobre el equipo de fútbol "
            f'"{team}".\n\n'
            "REQUISITO: la imagen DEBE mostrar a UNA PERSONA — un JUGADOR real, con "
            "CARA y CUERPO visibles, jugando o posando.\n"
            "RECHAZA (devuelve -1 si TODAS son así): camiseta sola sin persona, "
            "trofeos/copas/medallas/balones, escudos/logos/banderas/gráficos/texto, "
            "estadios vacíos o gradas, foto de equipo completo (varios en fila), "
            "collages, fotos antiguas o borrosas.\n\n"
            "De las que SÍ muestran un jugador con cara visible, elige la MEJOR: primer "
            "plano o plano medio, nítida, actual, que funcione recortada a 9:16 vertical.\n\n"
            'Devuelve SOLO JSON: {"best_index": <índice 0-based o -1>, "reason": "<breve>"}.'
        )
        from src.tiktok_shop.api.gemini import generate_text

        txt = generate_text(
            "Eres un editor visual estricto que selecciona fotos de jugadores.",
            prompt,
            expect_json=True,
            images=thumbs,
            temperature=0.1,
            max_output_tokens=200,
        )
        m = re.search(r"\{[\s\S]*\}", txt or "")
        data = json.loads(m.group(0) if m else (txt or "{}"))
        idx = int(data.get("best_index", -1))
        if idx == -1:
            return -1
        if 0 <= idx < len(images):
            return idx
        return 0
    except Exception:
        return 0  # si Vision falla, aceptamos la mejor del ranking


def _auto_fetch_one(team_raw: str, mode: str, query: str | None) -> AutoFetchResponse:
    team = _safe_team(team_raw)
    existing = _count_photos(team)
    if mode == "missing" and existing > 0:
        return AutoFetchResponse(team=team, status="exists", count=existing)

    year = datetime.now().year
    if query and query.strip():
        queries = [query.strip()]
    else:
        queries = [
            f"{team} jugador estrella futbol {year}",
            f"{team} futbolista {year} primer plano cara",
            f"{team} jugador celebrando {year}",
        ]

    last = ""
    for q in queries:
        try:
            cands = _bing_image_search(q, 8)
        except Exception as e:
            last = f"búsqueda: {e}"
            continue
        if not cands:
            last = "sin resultados"
            continue
        valid: list[tuple[bytes, str]] = []
        for c in cands[:6]:
            if len(valid) >= 3:
                break
            b = _download_valid(c.url)
            if b:
                valid.append((b, c.url))
        if not valid:
            last = "ninguna candidata se pudo descargar"
            continue
        best = _pick_best_player([b for b, _ in valid], team)
        if best == -1:
            last = "sin foto de jugador (solo camisetas/trofeos/escudos)"
            continue
        content, source = valid[best]
        try:
            img = Image.open(io.BytesIO(content))
            filename, url = _persist_image(img, team)
        except Exception as e:
            last = f"no se pudo guardar: {e}"
            continue
        return AutoFetchResponse(
            team=team,
            status="created",
            filename=filename,
            url=url,
            source=source,
            query=q,
            count=existing + 1,
        )

    return AutoFetchResponse(
        team=team, status="no_good", count=existing, reason=last or "sin foto válida"
    )


# ── Endpoints ───────────────────────────────────────────────────────────────────
@router.post("/search", response_model=SearchResponse)
def search_images(payload: SearchRequest) -> SearchResponse:
    return SearchResponse(images=_bing_image_search(payload.query.strip(), payload.limit))


@router.get("/folders", response_model=FoldersResponse)
def list_folders() -> FoldersResponse:
    root = _fotos_root()
    out: list[FolderItem] = []
    if root.exists():
        for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not d.is_dir():
                continue
            count = sum(
                1 for p in d.iterdir() if p.suffix.lower() in _IMG_EXTS and p.is_file()
            )
            out.append(FolderItem(name=d.name, count=count))
    return FoldersResponse(folders=out)


@router.get("/list", response_model=PhotoListResponse)
def list_photos(team: Annotated[str, Query(..., min_length=1)]) -> PhotoListResponse:
    team = _safe_team(team)
    d = _team_dir(team)
    photos: list[PhotoItem] = []
    if d.exists():
        for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
            if p.suffix.lower() not in _IMG_EXTS or not p.is_file():
                continue
            w = h = 0
            try:
                with Image.open(p) as im:
                    w, h = im.size
            except Exception:
                pass
            photos.append(
                PhotoItem(
                    filename=p.name,
                    url=_file_url(team, p.name),
                    width=w,
                    height=h,
                    size_kb=round(p.stat().st_size / 1024),
                )
            )
    return PhotoListResponse(team=team, photos=photos)


@router.post("/save", response_model=SaveResponse, status_code=status.HTTP_201_CREATED)
def save_photo(payload: SaveRequest) -> SaveResponse:
    team = _safe_team(payload.team)
    try:
        resp = requests.get(payload.image_url, headers=_BROWSER_HEADERS, timeout=15)
    except Exception as e:
        raise APIError(f"No se pudo descargar la imagen: {e}")
    if resp.status_code != 200 or not resp.content:
        raise APIError(f"La imagen devolvió {resp.status_code}.")
    try:
        img = Image.open(io.BytesIO(resp.content))
        filename, url = _persist_image(img, team)
    except Exception as e:
        raise ValidationError(f"El archivo no es una imagen válida: {e}")
    return SaveResponse(team=team, filename=filename, url=url)


@router.get("/teams", response_model=TeamsForDateResponse)
def teams_for_date(date: Annotated[str, Query(..., min_length=8)]) -> TeamsForDateResponse:
    """Equipos que aparecen en los picks de esa fecha (Redis) + estado de fotos."""
    from src.pronosticos.data_loader import get_picks, list_versions, load_raw_payload

    payload = load_raw_payload(date)
    if payload is None:
        return TeamsForDateResponse(date=date, teams=[])
    names: dict[str, None] = {}
    for v in list_versions(payload) or []:
        for p in get_picks(v) or []:
            for t in _split_teams(p.get("match", "")):
                names.setdefault(t, None)
    teams = [
        TeamStatus(name=n, has_photos=_count_photos(n) > 0, count=_count_photos(n))
        for n in sorted(names, key=str.lower)
    ]
    return TeamsForDateResponse(date=date, teams=teams)


@router.post("/auto-fetch", response_model=AutoFetchResponse)
def auto_fetch(payload: AutoFetchRequest) -> AutoFetchResponse:
    """Busca y guarda UNA foto de jugador para un equipo (1 por llamada;
    el frontend itera mostrando progreso). mode='missing' salta los que ya
    tienen foto; mode='all' añade una más."""
    return _auto_fetch_one(payload.team, payload.mode, payload.query)


@router.delete("/photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    team: Annotated[str, Query(..., min_length=1)],
    filename: Annotated[str, Query(..., min_length=1)],
) -> None:
    team = _safe_team(team)
    name = _safe_filename(filename)
    path = _team_dir(team) / name
    if path.exists() and path.is_file():
        path.unlink()


@file_router.get("/file")
def get_photo_file(
    team: Annotated[str, Query(..., min_length=1)],
    filename: Annotated[str, Query(..., min_length=1)],
) -> FileResponse:
    team = _safe_team(team)
    name = _safe_filename(filename)
    path = _team_dir(team) / name
    if not path.exists() or not path.is_file():
        raise ValidationError("Foto no encontrada.")
    # Cache corto: las fotos pueden reemplazarse; evita servir versiones viejas.
    return FileResponse(
        path=str(path),
        media_type="image/jpeg",
        filename=name,
        headers={"Cache-Control": "public, max-age=60"},
    )
