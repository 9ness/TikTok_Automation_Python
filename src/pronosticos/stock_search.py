"""Búsqueda y caché local de clips de stock para los segmentos del vídeo.

API primaria: Pexels (vertical, comercial-libre).
Fallback: Pixabay (si está configurada la key).

Política de caché:
- Carpeta por liga slugificada: `cache/pronosticos_clips/<league>/`.
- Si hay >=3 clips cacheados, escoge uno al azar (sin tocar API).
- Nunca busca por nombre de jugador/equipo (gasta cuota inútilmente).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def _resolve_cache_base() -> Path:
    """Resuelve la carpeta raíz para clips de stock.

    Preferencia (mismo patrón que el nicho Presidentes):
      1. {TIKTOK_ROOT_PATH}/{folder_structure.pronosticos_clips_folder}
         → carpeta sincronizada con Drive, igual que BIBLIOTECA_PRESIDENTES.
      2. cache/pronosticos_clips/  → fallback local si no hay TIKTOK_ROOT_PATH.
    """
    root = os.environ.get("TIKTOK_ROOT_PATH")
    if root and Path(root).exists():
        folder_name = "BIBLIOTECA_PRONOSTICOS_CLIPS"
        cfg_path = Path("config/config.json")
        if cfg_path.exists():
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                folder_name = cfg.get("folder_structure", {}).get(
                    "pronosticos_clips_folder", folder_name
                )
            except Exception:
                pass
        base = Path(root) / folder_name
    else:
        base = Path("cache/pronosticos_clips")
    base.mkdir(parents=True, exist_ok=True)
    return base


CACHE_BASE = _resolve_cache_base()
PEXELS_VIDEOS_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS_URL = "https://pixabay.com/api/videos/"

GENERIC_FALLBACK_QUERIES = [
    "soccer stadium night",
    "football fans cheering",
    "soccer ball field",
    "stadium lights",
]


# Tokens que se ignoran al hacer matching fuzzy de carpetas (solo conectores
# y prefijos de tipo de club). NUNCA quitar nombres distintivos como 'Real',
# 'Atletico', 'City', 'United' — son los que diferencian equipos de la misma
# ciudad ('Real Madrid' vs 'Atlético Madrid' vs 'Manchester City' vs 'Manchester United').
_STOPWORDS = {
    "de", "del", "el", "la", "los", "las", "of", "the", "and", "y",
    "fc", "cf", "ac", "afc", "cd", "sc", "uc", "fk", "as", "rc",
    "club",
}


# Aliases de tokens individuales: variantes idiomáticas/ortográficas mapeadas
# a un canon común. El canon es arbitrario (lo importante es que ambos lados
# converjan al MISMO canon tras normalizar).
# Cubre los nombres de ciudad europeos en el guion (TTS español) vs carpeta
# del usuario (suele estar en inglés/español sin acentos).
_TOKEN_CANONICAL: dict[str, str] = {
    # Múnich ↔ Munich ↔ München ↔ Muenchen
    "munchen": "munich", "muenchen": "munich",
    # Roma / Rome — el guion suele decir "Roma"
    "roma": "rome",
    # Milan / Milano
    "milano": "milan",
    # Turín / Torino
    "torino": "turin",
    # Nápoles / Napoli / Naples
    "napoli": "naples", "napoles": "naples",
    # Florencia / Firenze / Florence
    "firenze": "florence", "florencia": "florence",
    # Génova / Genova / Genoa
    "genova": "genoa",
    # Venecia / Venezia / Venice
    "venezia": "venice", "venecia": "venice",
    # Sevilla / Seville
    "seville": "sevilla",
    # Lisboa / Lisbon
    "lisbon": "lisboa",
    # Atenas / Athens
    "athens": "atenas",
    # Praga / Praha / Prague
    "praha": "prague", "praga": "prague",
    # Varsovia / Warszawa / Warsaw
    "warszawa": "warsaw", "varsovia": "warsaw",
    # Moscú / Moskva / Moscow
    "moskva": "moscow", "moscu": "moscow",
    # Colonia / Köln / Cologne
    "koln": "cologne", "colonia": "cologne",
    # Estambul / İstanbul
    "estambul": "istanbul",
}


# Acrónimos populares de clubes ↔ tokens del nombre largo. Cuando una set de
# tokens contiene el acrónimo, se añade su expansión (y al revés). Permite que
# una carpeta llamada simplemente "Psg" matchee con "Paris Saint Germain" del
# guion, o "BVB" con "Borussia Dortmund".
_ACRONYM_EXPANSIONS: dict[str, frozenset[str]] = {
    "psg":  frozenset({"paris", "saint", "germain"}),
    "bvb":  frozenset({"borussia", "dortmund"}),
    "manu": frozenset({"manchester", "united"}),
    "manc": frozenset({"manchester", "city"}),
    "mufc": frozenset({"manchester", "united"}),
    "mcfc": frozenset({"manchester", "city"}),
    "psv":  frozenset({"psv", "eindhoven"}),  # PSV ya está en el nombre largo
    "rbl":  frozenset({"rb", "leipzig"}),
}


def _normalize_token(t: str) -> str:
    """Mapea variantes idiomáticas a su token canónico (munchen→munich, etc.)."""
    return _TOKEN_CANONICAL.get(t, t)


def _expand_acronyms(tokens: set[str]) -> set[str]:
    """Si la set contiene un acrónimo conocido, añade su expansión.
    Si contiene la expansión completa, añade el acrónimo. Bidireccional.
    """
    out = set(tokens)
    for tok in list(tokens):
        if tok in _ACRONYM_EXPANSIONS:
            out.update(_ACRONYM_EXPANSIONS[tok])
    for acro, expansion in _ACRONYM_EXPANSIONS.items():
        if expansion.issubset(tokens):
            out.add(acro)
    return out

def _strip_accents(s: str) -> str:
    """'Atlético' → 'Atletico'. Necesario para que slugs de equipos con tilde
    se comparen correctamente con carpetas escritas sin tilde."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _slug(text: str) -> str:
    """Slug canónico: minúsculas, sin acentos, no-alfanum → '_'."""
    s = _strip_accents(text or "general").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or "general"


def _slug_tokens(text: str) -> set[str]:
    """Tokens significativos de un slug (sin stopwords), normalizados y con
    expansión de acrónimos para tolerar variantes (Múnich/Munchen, PSG/Paris
    Saint Germain, etc.)."""
    raw = {t for t in _slug(text).split("_") if t and t not in _STOPWORDS}
    normalized = {_normalize_token(t) for t in raw}
    return _expand_acronyms(normalized)


def _find_existing_folder(label: str) -> Path | None:
    """Busca una subcarpeta ya existente que matchee el label (fuzzy).

    Estrategia (de más estricta a más laxa):
      1. Match exacto del slug.
      2. Comparten ≥2 tokens distintivos (cubre 'Atlético de Madrid' ↔ 'atletico_madrid':
         ambos contienen {atletico, madrid}).
      3. Comparten 1 token Y ambos sets son de un solo token (caso 'Barcelona' ↔ 'barcelona').

    NO matchea por una sola palabra de ciudad común ('Real Madrid' NO matchea
    'Atletico_madrid' aunque ambos compartan 'madrid').
    """
    if not label or not CACHE_BASE.exists():
        return None
    target_slug = _slug(label)
    if not target_slug:
        return None

    existing = [d for d in CACHE_BASE.iterdir() if d.is_dir()]
    if not existing:
        return None

    # 1. Match exacto
    for d in existing:
        if _slug(d.name) == target_slug:
            return d

    # 2/3. Match por tokens distintivos
    target_tokens = _slug_tokens(label)
    if not target_tokens:
        return None

    best: Path | None = None
    best_common = 0
    for d in existing:
        d_tokens = _slug_tokens(d.name)
        if not d_tokens:
            continue
        common = target_tokens & d_tokens
        n = len(common)
        if n == 0:
            continue
        is_match = (
            n >= 2
            or (n == 1 and len(target_tokens) == 1 and len(d_tokens) == 1)
        )
        if is_match and n > best_common:
            best = d
            best_common = n
    return best


def get_clips_pool(home_team: str | None = None, away_team: str | None = None,
                   league: str | None = None,
                   prefer_labels: list[str] | None = None) -> list[str]:
    """Devuelve TODOS los clips disponibles para un pick (en orden de prioridad).

    Estrategia:
      1. Si hay `prefer_labels` (ej: ['intro']), gana la primera de esas carpetas
         que tenga clips. (Caso especial: la intro NO se mezcla con equipos.)
      2. Pool de equipos: si home Y away tienen carpeta con clips, devuelve la
         UNIÓN de ambos pools (así un Atlético-Arsenal alterna stock de ambos).
         Si solo uno tiene, devuelve ese. Si ninguno → fallback.
      3. Fallback: league.
      4. Fallback final: general.

    Si ningún nivel tiene clips → lista vacía. Caller decide si descargar desde
    Pexels o usar fondo sólido.
    """
    if prefer_labels:
        for label in prefer_labels:
            match = _find_existing_folder(label)
            if match:
                cached = sorted(match.glob("*.mp4"))
                if cached:
                    return [str(p) for p in cached]
        # prefer_labels es exclusivo: si ninguna lo tiene, NO caemos al pool de
        # equipos (la llamada de intro espera lista vacía si no hay intro).
        return []

    # Pool de equipos: union home+away cuando ambos tengan clips
    team_pool: list[str] = []
    seen_dirs: set[Path] = set()
    for team in (home_team, away_team):
        if not team:
            continue
        match = _find_existing_folder(team)
        if match and match not in seen_dirs:
            cached = sorted(match.glob("*.mp4"))
            if cached:
                team_pool.extend(str(p) for p in cached)
                seen_dirs.add(match)
    if team_pool:
        return team_pool

    # Fallback: league → general
    for label in (league, "general"):
        if not label:
            continue
        match = _find_existing_folder(label)
        if match:
            cached = sorted(match.glob("*.mp4"))
            if cached:
                return [str(p) for p in cached]
    return []


def parse_match(match: str) -> tuple[str | None, str | None]:
    """'Real Madrid vs Barcelona' → ('Real Madrid', 'Barcelona'). Soporta ' vs ', ' - ', ' x '."""
    if not match:
        return None, None
    for sep in (" vs ", " VS ", " - ", " – ", " x ", " X "):
        if sep in match:
            parts = match.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return match.strip(), None


def search_clip(league: str | None = None, country: str | None = None,
                sport: str | None = None, home_team: str | None = None,
                away_team: str | None = None) -> str | None:
    """Devuelve la ruta local de un clip MP4 listo para usar (o None).

    Estrategia de caché jerárquica:
      1. cache/pronosticos_clips/<home_team>/  ← preferido (más específico)
      2. cache/pronosticos_clips/<away_team>/
      3. cache/pronosticos_clips/<league>/
      4. cache/pronosticos_clips/general/

    Si una capa tiene >=3 clips cacheados, escoge uno al azar de ahí (sin pegarle
    a la API). Esto cubre el caso de que el usuario meta clips manuales por equipo.
    """
    # Lectura: matching fuzzy para encontrar carpetas existentes aunque el
    # nombre no sea idéntico al slug canónico ('Atletico_madrid' ↔ 'Atlético de Madrid').
    candidates_dirs: list[Path] = []
    seen: set[Path] = set()
    for label in (home_team, away_team, league, "general"):
        if not label:
            continue
        match = _find_existing_folder(label)
        if match and match not in seen:
            candidates_dirs.append(match)
            seen.add(match)

    # 1. Cache hit: si CUALQUIER carpeta encontrada tiene 3+ clips, úsala
    for d in candidates_dirs:
        cached = sorted(d.glob("*.mp4"))
        if len(cached) >= 3:
            return str(random.choice(cached))

    # 2. No hay caché suficiente → pegar a APIs, descargando a la carpeta CANÓNICA del local
    canonical_label = home_team or away_team or league or "general"
    target_dir = CACHE_BASE / _slug(canonical_label)
    target_dir.mkdir(parents=True, exist_ok=True)

    queries = _build_queries(league=league, country=country, sport=sport,
                             home_team=home_team)

    for q in queries:
        url = _try_pexels(q, target_dir)
        if url:
            return url
        url = _try_pixabay(q, target_dir)
        if url:
            return url

    # 3. Fallback final: cualquier clip ya cacheado en alguna carpeta encontrada
    for d in candidates_dirs:
        cached = sorted(d.glob("*.mp4"))
        if cached:
            return str(random.choice(cached))
    return None


def _build_queries(league=None, country=None, sport=None,
                   home_team=None) -> list[str]:
    """Queries de más específico (estadio del local) a más genérico.

    OJO: nombres de equipo en queries de Pexels suelen no devolver clips reales
    del equipo (todo lo de ese tipo es copyright). Pero a veces devuelve fans /
    estadios identificables. La caché manual del usuario es la vía buena.
    """
    out: list[str] = []
    if home_team:
        out.append(f"{home_team} stadium")
    if league:
        out.append(f"{league} stadium")
    if country:
        out.append(f"{country} football crowd")
    if sport and sport.lower() != "football":
        out.append(f"{sport} arena")
    out.extend(GENERIC_FALLBACK_QUERIES)
    seen: set[str] = set()
    deduped: list[str] = []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            deduped.append(q)
    return deduped


def _try_pexels(query: str, cache_dir: Path) -> str | None:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    try:
        r = requests.get(
            PEXELS_VIDEOS_URL,
            headers={"Authorization": api_key},
            params={"query": query, "orientation": "portrait", "per_page": 8, "size": "medium"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        videos = r.json().get("videos", [])
        for v in videos:
            files = v.get("video_files") or []
            mp4s = [f for f in files
                    if f.get("file_type") == "video/mp4" and f.get("link")]
            mp4s.sort(key=lambda f: abs((f.get("height") or 1080) - 1920))
            for f in mp4s:
                local = _download(f["link"], cache_dir)
                if local:
                    return local
    except Exception:
        pass
    return None


def _try_pixabay(query: str, cache_dir: Path) -> str | None:
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        return None
    try:
        r = requests.get(
            PIXABAY_VIDEOS_URL,
            params={"key": api_key, "q": query, "video_type": "film",
                    "orientation": "vertical", "per_page": 8, "safesearch": "true"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        for v in r.json().get("hits", []):
            for q_key in ("large", "medium", "small"):
                f = (v.get("videos") or {}).get(q_key) or {}
                if f.get("url"):
                    local = _download(f["url"], cache_dir)
                    if local:
                        return local
    except Exception:
        pass
    return None


def _download(url: str, cache_dir: Path) -> str | None:
    name = hashlib.md5(url.encode("utf-8")).hexdigest()[:12] + ".mp4"
    target = cache_dir / name
    if target.exists() and target.stat().st_size > 50_000:
        return str(target)
    try:
        r = requests.get(url, timeout=60, stream=True)
        if r.status_code != 200:
            return None
        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 15):
                if chunk:
                    f.write(chunk)
        if target.stat().st_size < 50_000:
            target.unlink(missing_ok=True)
            return None
        return str(target)
    except Exception:
        return None
