"""Render del carrusel TikTok (PNG 1080x1920) por pick individual.

Layout actualizado a `PronosticosAuto.md` v2:
- Cada pick es UNA imagen (no 3 picks juntos en un carrusel).
- Para `multi_match` se renderiza una imagen por pick de `selected_picks`.
- Para `single_match` se renderiza una imagen por pick de `focus_selections`.

Estructura visual:
- Fondo: gradiente + escudo del local difuminado (si trae home_logo)
- Header: liga
- Caja blanca grande con título del partido
- Píldora azul con el pick específico
- Badge numérico con índice del pick

No usa emojis — Pillow no los renderiza correctamente sin fuentes color
y esas no están garantizadas en Windows estándar.
"""

from __future__ import annotations

import io

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Etiquetas cortas por tipo de pick (en lugar de emojis para Windows-safety).
PICK_LABELS = [
    (("córner", "corner", "córners", "corners"), "CRN"),
    (("tarjeta", "tarjetas", "card", "cards"), "TJT"),
    (("gol", "goles", "marcan", "anotan"), "GOL"),
    (("remate", "remates", "tiro", "tiros"), "RMT"),
    (("punto", "puntos"), "PTS"),
    (("hándicap", "handicap"), "HND"),
    (("victoria", "gana", "ganador"), "WIN"),
]

DEFAULT_BG = (12, 18, 33)
ACCENT_BLUE = (30, 1, 196)      # #1E01C4 (preset usuario)
ACCENT_GREEN = (16, 185, 129)
DARK_PANEL = (22, 28, 45)
LIGHT_TEXT = (245, 245, 250)
DARK_TEXT = (15, 17, 25)
GOLD = (253, 208, 2)


def _label_for_pick(pick: str) -> str:
    p = pick.lower()
    for keys, lbl in PICK_LABELS:
        if any(k in p for k in keys):
            return lbl
    return "BET"


def _font(size: int, bold: bool = True):
    from src.font_resolver import resolve_font
    candidates = (
        [r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
        if bold else
        [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(resolve_font(path), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _safe_download(url: str, timeout: int = 8) -> Image.Image | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200 or not r.content:
            return None
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None


def _vertical_gradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    W, H = size
    base = Image.new("RGB", (W, H), top)
    px = base.load()
    for y in range(H):
        ratio = y / max(1, H - 1)
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        for x in range(W):
            px[x, y] = (r, g, b)
    return base


def render_carousel(bet: dict, idx: int, output_path: str,
                    video_size: tuple[int, int] = (1080, 1920)) -> str:
    """Genera y guarda el PNG del carrusel para una combinada."""
    W, H = video_size
    selections = bet.get("selections", [])

    # ── Fondo: gradiente vertical
    bg = _vertical_gradient((W, H), (8, 12, 28), (28, 6, 78)).convert("RGBA")

    # ── Logo del local difuminado y centrado como marca de agua
    if selections:
        logo_img = _safe_download(selections[0].get("home_logo"))
        if logo_img is not None:
            target = 760
            logo_resized = logo_img.resize((target, target), Image.Resampling.LANCZOS)
            faded = logo_resized.copy()
            alpha = faded.split()[-1].point(lambda a: int(a * 0.18))
            faded.putalpha(alpha)
            faded = faded.filter(ImageFilter.GaussianBlur(radius=3))
            bg.alpha_composite(faded, ((W - target) // 2, 320))

    draw = ImageDraw.Draw(bg)

    # ── Badge del puesto (esquina sup-izq)
    badge_r = 90
    bcx, bcy = 100 + badge_r, 120 + badge_r
    draw.ellipse([bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r], fill=GOLD)
    draw.text((bcx, bcy), str(idx), font=_font(110), fill=DARK_TEXT, anchor="mm")

    # ── Cabecera con liga / país
    if selections:
        league = selections[0].get("league") or ""
        country = selections[0].get("country") or ""
        meta = f"{league}  ·  {country}".strip(" ·")
        if meta:
            draw.text((W // 2, 110), meta.upper(), font=_font(40), fill=LIGHT_TEXT, anchor="mm")

    # ── Caja blanca con título del partido
    match_label = (bet.get("match") or "Combinada Viral").strip()
    box_w, box_h = int(W * 0.86), 220
    box_x = (W - box_w) // 2
    box_y = 1040
    _rounded(draw, box_x, box_y, box_w, box_h, radius=28, fill=(255, 255, 255))
    _fit_text(draw, match_label, (box_x + 30, box_y, box_x + box_w - 30, box_y + box_h),
              start_size=72, min_size=36, fill=DARK_TEXT, max_lines=2)

    # ── Caja oscura con los 3 picks
    pbox_y = box_y + box_h + 36
    pbox_h = 380
    _rounded(draw, box_x, pbox_y, box_w, pbox_h, radius=28, fill=DARK_PANEL)

    pick_h = pbox_h // 3
    pick_font = _font(46)
    label_font = _font(36)
    for i, sel in enumerate(selections[:3]):
        pick_text = (sel.get("pick") or "").strip() or "Selección"
        label = _label_for_pick(pick_text)
        row_y = pbox_y + i * pick_h
        # tag a la izquierda
        tag_w = 130
        tag_pad = 30
        tag_x0 = box_x + tag_pad
        tag_y0 = row_y + (pick_h - 80) // 2
        _rounded(draw, tag_x0, tag_y0, tag_w, 80, radius=14, fill=ACCENT_BLUE)
        draw.text((tag_x0 + tag_w // 2, tag_y0 + 40), label,
                  font=label_font, fill=LIGHT_TEXT, anchor="mm")
        # texto del pick
        draw.text((tag_x0 + tag_w + 30, row_y + pick_h // 2),
                  pick_text, font=pick_font, fill=LIGHT_TEXT, anchor="lm")
        # separador
        if i < 2:
            sep_y = row_y + pick_h - 2
            draw.line([(box_x + 30, sep_y), (box_x + box_w - 30, sep_y)],
                      fill=(255, 255, 255, 30), width=1)

    # ── Píldora con la cuota total
    odd_value = bet.get("total_odd", 0) or 0
    odd_text = f"+{float(odd_value):.2f}".replace(".", ",")
    pill_w, pill_h = 480, 150
    pill_x = (W - pill_w) // 2
    pill_y = pbox_y + pbox_h + 50
    _rounded(draw, pill_x, pill_y, pill_w, pill_h, radius=pill_h // 2, fill=ACCENT_GREEN)
    draw.text((W // 2, pill_y + pill_h // 2), odd_text,
              font=_font(96), fill=LIGHT_TEXT, anchor="mm")

    # ── Footer hora del partido
    if selections:
        time_str = selections[0].get("time", "")
        if time_str:
            draw.text((W // 2, pill_y + pill_h + 90), f"Hoy · {time_str}",
                      font=_font(44), fill=LIGHT_TEXT, anchor="mm")

    bg.convert("RGB").save(output_path, "PNG")
    return output_path


def render_pick_card(pick: dict, idx: int, output_path: str,
                     video_size: tuple[int, int] = (1080, 1920),
                     competition_focus: str | None = None) -> str:
    """Renderiza UN pick individual (multi_match v2 / focus_selections single_match).

    Diferencias respecto al render_carousel legacy:
      - Sin caja oscura con 3 picks. La píldora azul muestra el pick único.
      - Sin píldora de cuota total (cada pick es una apuesta individual).
      - Soporta competition_focus opcional como subtítulo (Europa League, etc.).
    """
    W, H = video_size

    # Fondo gradiente
    bg = _vertical_gradient((W, H), (8, 12, 28), (28, 6, 78)).convert("RGBA")

    # Escudo del local como marca de agua si está disponible
    home_logo = _safe_download(pick.get("home_logo"))
    if home_logo is not None:
        target = 760
        logo_resized = home_logo.resize((target, target), Image.Resampling.LANCZOS)
        faded = logo_resized.copy()
        alpha = faded.split()[-1].point(lambda a: int(a * 0.18))
        faded.putalpha(alpha)
        faded = faded.filter(ImageFilter.GaussianBlur(radius=3))
        bg.alpha_composite(faded, ((W - target) // 2, 320))

    draw = ImageDraw.Draw(bg)

    # Badge numérico (esquina sup-izq)
    badge_r = 90
    bcx, bcy = 100 + badge_r, 120 + badge_r
    draw.ellipse([bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r], fill=GOLD)
    draw.text((bcx, bcy), str(idx), font=_font(110), fill=DARK_TEXT, anchor="mm")

    # Header con liga (y competition_focus si aplica)
    league = (pick.get("league") or "").upper()
    if competition_focus:
        # Modo competition_focus → la liga es siempre la misma. Mostramos solo eso.
        header = competition_focus.upper()
    else:
        country = (pick.get("country") or "").upper()
        header = f"{league}  ·  {country}".strip(" ·") if country else league
    if header:
        draw.text((W // 2, 110), header, font=_font(40), fill=LIGHT_TEXT, anchor="mm")

    # Caja blanca con título del partido
    match_label = (pick.get("match") or "").strip() or "Pronóstico"
    box_w, box_h = int(W * 0.86), 220
    box_x = (W - box_w) // 2
    box_y = 1040
    _rounded(draw, box_x, box_y, box_w, box_h, radius=28, fill=(255, 255, 255))
    _fit_text(draw, match_label, (box_x + 30, box_y, box_x + box_w - 30, box_y + box_h),
              start_size=72, min_size=36, fill=DARK_TEXT, max_lines=2)

    # Píldora azul con el pick concreto (lo más importante visualmente)
    pick_text = (pick.get("pick") or "").strip() or "Selección"
    pbox_y = box_y + box_h + 50
    pbox_h = 220
    _rounded(draw, box_x, pbox_y, box_w, pbox_h, radius=28, fill=ACCENT_BLUE)
    _fit_text(draw, pick_text, (box_x + 30, pbox_y, box_x + box_w - 30, pbox_y + pbox_h),
              start_size=84, min_size=44, fill=LIGHT_TEXT, max_lines=2)

    # Footer hora del partido (si está)
    time_str = pick.get("time") or ""
    if time_str:
        draw.text((W // 2, pbox_y + pbox_h + 80), f"Hoy · {time_str}",
                  font=_font(44), fill=LIGHT_TEXT, anchor="mm")

    bg.convert("RGB").save(output_path, "PNG")
    return output_path


# ── Helpers de dibujo ─────────────────────────────────────────────────

def _rounded(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
             radius: int, fill) -> None:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, bbox: tuple[int, int, int, int],
              start_size: int, min_size: int, fill, max_lines: int = 2,
              font_path_bold: bool = True) -> None:
    """Encaja `text` dentro del bbox auto-reduciendo la fuente. Centrado."""
    x0, y0, x1, y1 = bbox
    max_w = x1 - x0
    max_h = y1 - y0

    size = start_size
    while size >= min_size:
        font = _font(size, bold=font_path_bold)
        lines = _wrap(text, font, max_w, draw)
        line_h = font.getbbox("Mg")[3] - font.getbbox("Mg")[1]
        total_h = len(lines) * line_h + max(0, len(lines) - 1) * int(line_h * 0.15)
        if len(lines) <= max_lines and total_h <= max_h:
            cy = (y0 + y1) // 2 - total_h // 2
            for line in lines:
                draw.text(((x0 + x1) // 2, cy), line, font=font, fill=fill, anchor="mt")
                cy += line_h + int(line_h * 0.15)
            return
        size -= 4

    font = _font(min_size, bold=font_path_bold)
    draw.text(((x0 + x1) // 2, (y0 + y1) // 2), text[:40], font=font, fill=fill, anchor="mm")


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        candidate = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_w or not current:
            current.append(w)
        else:
            lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines
