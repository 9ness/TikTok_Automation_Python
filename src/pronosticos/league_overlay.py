"""Overlay de escudos de ligas/copas en la intro del vídeo.

Cuando la narración pronuncia palabras-trigger ('ligas', 'champions',
'europa'...) aparecen los logos de las competiciones implicadas en los picks
del día, en fila horizontal centrada en la zona alta-central del frame.

Layout (replica el ejemplo del usuario):
- Logos al ~30% del alto del vídeo
- Tamaño "considerable": cada logo ~13-16% del alto del frame (≈250-300px en 1920)
- Espaciado horizontal entre logos: ~4% del ancho

Assets esperados en `BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/`:
  liga_española.png, liga_inglesa.png, liga_alemana.png, liga_italiana.png,
  liga_francesa.png, liga_mexicana.png, liga_portugal.png,
  copa_champions.png, copa_europaleague.png, copa_conferenceleague.png.
"""

from __future__ import annotations

from PIL import Image

# Mapping league name (lowercase, sin acentos relevantes) → filename del asset.
# Se compara con `substring in pick_league.lower()`, así que cubrir sinónimos largos
# y cortos para dar margen a variaciones de bet-ai-master.
LEAGUE_FILE_MAP: list[tuple[str, str]] = [
    # España
    ("la liga", "liga_española.png"),
    ("laliga", "liga_española.png"),
    ("primera división", "liga_española.png"),
    ("primera division", "liga_española.png"),
    # Inglaterra
    ("premier league", "liga_inglesa.png"),
    ("premier", "liga_inglesa.png"),
    # Alemania
    ("bundesliga", "liga_alemana.png"),
    # Italia
    ("serie a", "liga_italiana.png"),
    # Francia
    ("ligue 1", "liga_francesa.png"),
    ("ligue1", "liga_francesa.png"),
    # México
    ("liga mx", "liga_mexicana.png"),
    # Portugal
    ("liga portugal", "liga_portugal.png"),
    ("primeira liga", "liga_portugal.png"),
    # UEFA — copas (van primero en preferencia si el league text las contiene)
    ("uefa champions league", "copa_champions.png"),
    ("champions league", "copa_champions.png"),
    ("champions", "copa_champions.png"),
    ("uefa europa league", "copa_europaleague.png"),
    ("europa league", "copa_europaleague.png"),
    ("conference league", "copa_conferenceleague.png"),
]


# Palabras del guion que disparan la aparición del overlay (lowercase, sin tildes).
LEAGUE_OVERLAY_TRIGGERS: set[str] = {
    "ligas", "liga",
    "champions",
    "europa",
    "conference",
    "copa", "copas",
}


def _norm_league(text: str) -> str:
    return (text or "").lower().strip()


def filename_for_league(league_name: str) -> str | None:
    """Devuelve el filename del asset correspondiente a una liga, o None."""
    if not league_name:
        return None
    norm = _norm_league(league_name)
    for needle, filename in LEAGUE_FILE_MAP:
        if needle in norm:
            return filename
    return None


def resolve_league_logos(picks: list[dict], asset_resolver, max_logos: int = 3) -> list[str]:
    """Devuelve hasta `max_logos` paths a logos de ligas únicos, en orden de aparición.

    `asset_resolver(*parts)` debe ser un callable que dado ('fotos', 'archivo.png')
    devuelva el path absoluto si existe, o None.
    """
    seen_paths: list[str] = []
    seen_files: set[str] = set()
    for pick in picks or []:
        league_name = pick.get("league") or ""
        filename = filename_for_league(league_name)
        if not filename or filename in seen_files:
            continue
        path = asset_resolver("fotos", filename)
        if path:
            seen_paths.append(path)
            seen_files.add(filename)
        if len(seen_paths) >= max_logos:
            break
    return seen_paths


def _norm_token(token: str) -> str:
    return (token or "").lower().strip(".,;:!?¡¿\"'() ")


def find_league_overlay_anchor(words: list[dict], intro_end: float | None = None) -> float | None:
    """Devuelve el timestamp de la primera palabra-trigger en la intro (o None)."""
    for w in words or []:
        ts = float(w.get("start", 0))
        if intro_end is not None and ts >= intro_end:
            break
        if _norm_token(w.get("word", "")) in LEAGUE_OVERLAY_TRIGGERS:
            return ts
    return None


def build_league_overlay_image(logo_paths: list[str], video_size: tuple[int, int],
                                logo_height_pct: float = 0.13,
                                spacing_pct: float = 0.04) -> Image.Image | None:
    """Compone los logos en fila horizontal centrada sobre canvas RGBA del tamaño del vídeo.

    Retorna None si no hay logos.
    """
    if not logo_paths:
        return None

    W, H = video_size
    target_h = max(60, int(H * logo_height_pct))
    spacing = int(W * spacing_pct)

    # Cargar y resize manteniendo aspect ratio (los assets son 200x200 según user,
    # pero soportamos cualquier ratio por si añade más después)
    images: list[Image.Image] = []
    for path in logo_paths:
        try:
            im = Image.open(path).convert("RGBA")
        except Exception:
            continue
        ratio = target_h / im.height
        new_w = max(1, int(im.width * ratio))
        im = im.resize((new_w, target_h), Image.Resampling.LANCZOS)
        images.append(im)
    if not images:
        return None

    # Canvas del ancho del vídeo, alto = altura de los logos
    canvas_h = target_h
    canvas = Image.new("RGBA", (W, canvas_h), (0, 0, 0, 0))

    total_w = sum(im.width for im in images) + spacing * (len(images) - 1)
    x = max(0, (W - total_w) // 2)
    for im in images:
        canvas.paste(im, (x, 0), im)
        x += im.width + spacing

    return canvas
