"""Overlays del estilo de vídeo VIRAL para Pronósticos.

Dos overlays transparentes (RGBA 1080x1920) que se componen sobre el clip de fondo:

  1. build_viral_hook_overlay(...)  → tarjeta blanca con la LISTA de partidos del día
     (gancho): cada fila = bandera + selección + hora Perú + bandera + selección.

  2. build_viral_match_bar(...)     → barra oscura del partido (por pick): banderas
     REDONDAS de selección + fecha + hora Perú + estrellas a los lados.

Las banderas de selección se resuelven por nombre de equipo → ISO-3166 alpha-2 →
flagcdn (PNG), recortadas en círculo. El carrusel/escudos existentes usan logos de
club; aquí necesitamos banderas de país.

Sin emojis (Pillow no los pinta bien). Mismo estilo de fuentes que carousel_renderer.
"""

from __future__ import annotations

import io
import unicodedata

import requests
from PIL import Image, ImageDraw, ImageFont

GOLD = (245, 197, 24)
WHITE = (255, 255, 255)
DARK_TEXT = (17, 19, 25)
BAR_BG = (10, 12, 16, 210)

# ── selección → ISO-3166 alpha-2 (para flagcdn) ───────────────────────────────
TEAM_ISO2: dict[str, str] = {
    "espana": "es", "spain": "es", "francia": "fr", "france": "fr",
    "alemania": "de", "germany": "de", "italia": "it", "italy": "it",
    "paises bajos": "nl", "holanda": "nl", "netherlands": "nl", "portugal": "pt",
    "inglaterra": "gb-eng", "england": "gb-eng", "belgica": "be", "belgium": "be",
    "croacia": "hr", "croatia": "hr", "suiza": "ch", "switzerland": "ch",
    "dinamarca": "dk", "denmark": "dk", "suecia": "se", "sweden": "se",
    "noruega": "no", "norway": "no", "polonia": "pl", "poland": "pl",
    "republica checa": "cz", "czech republic": "cz", "czechia": "cz", "austria": "at",
    "serbia": "rs", "ucrania": "ua", "ukraine": "ua", "gales": "gb-wls", "wales": "gb-wls",
    "escocia": "gb-sct", "scotland": "gb-sct", "turquia": "tr", "turkey": "tr", "turkiye": "tr",
    "grecia": "gr", "greece": "gr", "rumania": "ro", "romania": "ro", "hungria": "hu", "hungary": "hu",
    "eslovenia": "si", "slovenia": "si", "eslovaquia": "sk", "slovakia": "sk",
    "bosnia y herzegovina": "ba", "bosnia and herzegovina": "ba", "bosnia": "ba",
    "islandia": "is", "iceland": "is", "uzbekistan": "uz",
    "argentina": "ar", "brasil": "br", "brazil": "br", "uruguay": "uy", "colombia": "co",
    "chile": "cl", "peru": "pe", "ecuador": "ec", "paraguay": "py", "venezuela": "ve", "bolivia": "bo",
    "estados unidos": "us", "usa": "us", "united states": "us", "mexico": "mx", "canada": "ca",
    "costa rica": "cr", "panama": "pa", "honduras": "hn", "jamaica": "jm", "el salvador": "sv",
    "guatemala": "gt", "curazao": "cw", "curacao": "cw", "haiti": "ht", "cuba": "cu",
    "republica dominicana": "do", "dominican republic": "do",
    "marruecos": "ma", "morocco": "ma", "senegal": "sn", "tunez": "tn", "tunisia": "tn",
    "argelia": "dz", "algeria": "dz", "egipto": "eg", "egypt": "eg", "ghana": "gh",
    "nigeria": "ng", "camerun": "cm", "cameroon": "cm", "costa de marfil": "ci", "ivory coast": "ci",
    "sudafrica": "za", "south africa": "za", "rd congo": "cd", "dr congo": "cd", "congo dr": "cd",
    "mali": "ml", "cabo verde": "cv", "cape verde": "cv",
    "japon": "jp", "japan": "jp", "corea del sur": "kr", "south korea": "kr", "korea republic": "kr",
    "australia": "au", "arabia saudita": "sa", "saudi arabia": "sa", "catar": "qa", "qatar": "qa",
    "iran": "ir", "irak": "iq", "iraq": "iq", "jordania": "jo", "jordan": "jo",
    "emiratos arabes unidos": "ae", "uae": "ae", "nueva zelanda": "nz", "new zealand": "nz",
}

_DIAS_ABBR = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("&", "and").split())


def _font(size: int, bold: bool = True):
    from src.font_resolver import resolve_font
    candidates = ([r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
                  if bold else [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"])
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


def round_flag(team_name: str, size: int) -> Image.Image | None:
    """Bandera REDONDA de la selección (None si no se conoce el país)."""
    iso = TEAM_ISO2.get(_norm(team_name))
    if not iso:
        return None
    src = _safe_download(f"https://flagcdn.com/w160/{iso}.png")
    if src is None:
        return None
    w, h = src.size
    s = min(w, h)
    sq = src.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(sq, (0, 0), mask)
    # borde blanco
    ImageDraw.Draw(out).ellipse([1, 1, size - 2, size - 2], outline=(255, 255, 255, 230), width=max(2, size // 22))
    return out


def madrid_to_peru(raw: str) -> str:
    """'YYYY-MM-DD HH:MM' (Madrid, verano UTC+2) → hora Perú (UTC-5) en 'h:mm p.m.'."""
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", raw or "")
    if not m:
        return raw or ""
    from datetime import datetime, timedelta
    d = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])) - timedelta(hours=7)
    ampm = "a.m." if d.hour < 12 else "p.m."
    h12 = d.hour % 12 or 12
    return f"{h12}:{d.minute:02d} {ampm}"


def _date_badge(date_str: str) -> tuple[str, str]:
    """date_str 'YYYY-MM-DD' → ('DD/MM/YY', 'mié')."""
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str or "")
    if not m:
        return "", ""
    from datetime import date
    wd = date(int(m[1]), int(m[2]), int(m[3])).weekday()
    return f"{m[3]}/{m[2]}/{m[1][2:]}", _DIAS_ABBR[wd]


def build_viral_hook_overlay(matches: list[dict], output_path: str,
                             video_size: tuple[int, int] = (1080, 1920)) -> str:
    """Tarjeta blanca con la lista de partidos (gancho). `matches`: lista de dicts
    con keys home, away, time_peru (o time crudo). Overlay transparente."""
    W, H = video_size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    rows = matches[:4]
    n = max(1, len(rows))
    pad = int(W * 0.05)
    card_x = int(W * 0.05)
    card_w = W - 2 * card_x
    row_h = 150
    card_h = n * row_h + 2 * pad
    card_y = int(H * 0.20)

    # tarjeta blanca redondeada
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=34, fill=(255, 255, 255, 245))

    fsize = 46
    font = _font(fsize)
    flag_sz = 70
    cx = W // 2
    for i, m in enumerate(rows):
        ry = card_y + pad + i * row_h + row_h // 2
        time_txt = m.get("time_peru") or madrid_to_peru(m.get("time", ""))
        # hora centro
        draw.text((cx, ry), time_txt, font=font, fill=DARK_TEXT, anchor="mm")
        tw = draw.textlength(time_txt, font=font)
        # banderas a los lados de la hora
        fa = round_flag(m.get("home", ""), flag_sz)
        fb = round_flag(m.get("away", ""), flag_sz)
        fa_x = int(cx - tw / 2 - 24 - flag_sz)
        fb_x = int(cx + tw / 2 + 24)
        if fa is not None:
            img.alpha_composite(fa, (fa_x, ry - flag_sz // 2))
        if fb is not None:
            img.alpha_composite(fb, (fb_x, ry - flag_sz // 2))
        # nombres a los extremos
        draw.text((fa_x - 24, ry), str(m.get("home", "")), font=font, fill=DARK_TEXT, anchor="rm")
        draw.text((fb_x + flag_sz + 24, ry), str(m.get("away", "")), font=font, fill=DARK_TEXT, anchor="lm")
        if i < n - 1:
            sy = card_y + pad + (i + 1) * row_h
            draw.line([(card_x + 30, sy), (card_x + card_w - 30, sy)], fill=(0, 0, 0, 30), width=2)

    img.save(output_path, "PNG")
    return output_path


def build_viral_match_bar(home: str, away: str, date_str: str, time_raw_or_peru: str,
                          output_path: str, video_size: tuple[int, int] = (1080, 1920)) -> str:
    """Barra oscura del partido (por pick): ★ · bandera+equipo · fecha+hora · bandera+equipo · ★.
    Overlay transparente, barra centrada verticalmente (~y 40%)."""
    W, H = video_size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bar_h = 300
    bar_y = int(H * 0.38)
    draw.rounded_rectangle([0, bar_y, W, bar_y + bar_h], radius=0, fill=BAR_BG)

    ddmmyy, abbr = _date_badge(date_str)
    time_txt = time_raw_or_peru if "m." in (time_raw_or_peru or "") else madrid_to_peru(time_raw_or_peru)
    cy = bar_y + bar_h // 2
    cx = W // 2

    # estrellas
    star_font = _font(64)
    draw.text((40, cy), "★", font=star_font, fill=GOLD, anchor="lm")
    draw.text((W - 40, cy), "★", font=star_font, fill=GOLD, anchor="rm")

    # fecha + hora (centro)
    draw.text((cx, cy - 24), ddmmyy, font=_font(56), fill=WHITE, anchor="mm")
    draw.text((cx, cy + 40), f"{abbr}, {time_txt}", font=_font(42), fill=(207, 214, 221), anchor="mm")

    # local (izquierda) y visitante (derecha): bandera redonda + nombre debajo
    flag_sz = 96
    name_font = _font(38)
    for team, anchor_x in ((home, int(W * 0.20)), (away, int(W * 0.80))):
        fl = round_flag(team, flag_sz)
        if fl is not None:
            img.alpha_composite(fl, (anchor_x - flag_sz // 2, cy - 60 - flag_sz // 2))
        draw.text((anchor_x, cy + 70), str(team), font=name_font, fill=WHITE, anchor="mm")

    img.save(output_path, "PNG")
    return output_path
