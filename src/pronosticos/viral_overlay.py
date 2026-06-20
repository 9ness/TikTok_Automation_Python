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
    "australia": "au", "arabia saudita": "sa", "arabia saudi": "sa", "saudi arabia": "sa",
    "catar": "qa", "qatar": "qa",
    "iran": "ir", "irak": "iq", "iraq": "iq", "jordania": "jo", "jordan": "jo",
    "emiratos arabes unidos": "ae", "uae": "ae", "nueva zelanda": "nz", "new zealand": "nz",
}

_DIAS_ABBR = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("&", "and").split())


# Nombre de selección → ESPAÑOL para mostrar en los overlays (las picks vienen
# en inglés: 'Germany', 'Ivory Coast'). Clave normalizada con _norm().
TEAM_ES: dict[str, str] = {
    "germany": "Alemania", "spain": "España", "france": "Francia",
    "italy": "Italia", "netherlands": "Países Bajos", "holland": "Países Bajos",
    "england": "Inglaterra", "portugal": "Portugal", "belgium": "Bélgica",
    "croatia": "Croacia", "switzerland": "Suiza", "denmark": "Dinamarca",
    "sweden": "Suecia", "norway": "Noruega", "poland": "Polonia",
    "czech republic": "Chequia", "czechia": "Chequia", "austria": "Austria",
    "serbia": "Serbia", "ukraine": "Ucrania", "wales": "Gales",
    "scotland": "Escocia", "turkey": "Turquía", "turkiye": "Turquía",
    "greece": "Grecia", "romania": "Rumanía", "hungary": "Hungría",
    "slovenia": "Eslovenia", "slovakia": "Eslovaquia", "iceland": "Islandia",
    "bosnia and herzegovina": "Bosnia", "uzbekistan": "Uzbekistán",
    "russia": "Rusia", "ireland": "Irlanda", "finland": "Finlandia",
    "argentina": "Argentina", "brazil": "Brasil", "uruguay": "Uruguay",
    "colombia": "Colombia", "chile": "Chile", "peru": "Perú",
    "ecuador": "Ecuador", "paraguay": "Paraguay", "venezuela": "Venezuela",
    "bolivia": "Bolivia", "united states": "Estados Unidos", "usa": "Estados Unidos",
    "mexico": "México", "canada": "Canadá", "costa rica": "Costa Rica",
    "panama": "Panamá", "honduras": "Honduras", "jamaica": "Jamaica",
    "el salvador": "El Salvador", "guatemala": "Guatemala", "curacao": "Curazao",
    "haiti": "Haití", "cuba": "Cuba", "dominican republic": "República Dominicana",
    "morocco": "Marruecos", "senegal": "Senegal", "tunisia": "Túnez",
    "algeria": "Argelia", "egypt": "Egipto", "ghana": "Ghana",
    "nigeria": "Nigeria", "cameroon": "Camerún", "ivory coast": "Costa de Marfil",
    "south africa": "Sudáfrica", "dr congo": "RD Congo", "congo dr": "RD Congo",
    "mali": "Malí", "cape verde": "Cabo Verde",
    "japan": "Japón", "south korea": "Corea del Sur", "korea republic": "Corea del Sur",
    "australia": "Australia", "saudi arabia": "Arabia Saudí", "qatar": "Catar",
    "iran": "Irán", "iraq": "Irak", "jordan": "Jordania",
    "united arab emirates": "Emiratos Árabes", "uae": "Emiratos Árabes",
    "new zealand": "Nueva Zelanda",
}


def _to_es(name: str) -> str:
    """Traduce el nombre de la selección a español para mostrar (si lo conoce)."""
    return TEAM_ES.get(_norm(name), name)


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
    side = int(W * 0.06)
    card_x = side
    card_w = W - 2 * side                  # tarjeta con márgenes (NO a todo el ancho)
    block_h = 128                          # por partido: 2 líneas (local / visitante)
    vpad = 26
    card_h = n * block_h + 2 * vpad
    card_y = int(H * 0.13)

    # tarjeta blanca compacta y redondeada
    draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h],
                           radius=34, fill=(255, 255, 255, 240))

    name_font = _font(40)
    time_font = _font(36)
    star_font = _font(46)
    flag_sz = 48
    for i, m in enumerate(rows):
        top = card_y + vpad + i * block_h
        cyl = top + block_h // 2
        y1 = top + int(block_h * 0.30)     # local (línea de arriba)
        y2 = top + int(block_h * 0.70)     # visitante (línea de abajo)
        # estrella a la izquierda
        draw.text((card_x + 40, cyl), "★", font=star_font, fill=GOLD, anchor="mm")
        flag_x = card_x + 78
        name_x = flag_x + flag_sz + 16
        # LOCAL: bandera + nombre
        fa = round_flag(m.get("home", ""), flag_sz)
        if fa is not None:
            img.alpha_composite(fa, (flag_x, y1 - flag_sz // 2))
        draw.text((name_x, y1), _to_es(m.get("home", "")), font=name_font, fill=DARK_TEXT, anchor="lm")
        # VISITANTE: bandera + nombre (debajo)
        fb = round_flag(m.get("away", ""), flag_sz)
        if fb is not None:
            img.alpha_composite(fb, (flag_x, y2 - flag_sz // 2))
        draw.text((name_x, y2), _to_es(m.get("away", "")), font=name_font, fill=DARK_TEXT, anchor="lm")
        # ── Grupo derecho estilo "app": auriculares + pastilla PREVIEW + hora ──
        time_txt = m.get("time_peru") or madrid_to_peru(m.get("time", ""))
        gray = (150, 156, 166)
        time_x = card_x + card_w - 30
        draw.text((time_x, cyl), time_txt, font=time_font, fill=(90, 95, 105), anchor="rm")
        tw = draw.textlength(time_txt, font=time_font)
        gx = int(time_x - tw - 26)              # borde derecho del bloque auriculares/PREVIEW
        # pastilla PREVIEW (debajo del centro)
        pv_font = _font(20)
        pvw = draw.textlength("PREVIEW", font=pv_font)
        pill_w = int(pvw + 22)
        px1 = gx - pill_w
        py0 = cyl + 4
        draw.rounded_rectangle([px1, py0, gx, py0 + 32], radius=9, outline=gray, width=2)
        draw.text(((px1 + gx) // 2, py0 + 16), "PREVIEW", font=pv_font, fill=gray, anchor="mm")
        # auriculares encima de la pastilla
        hcx = (px1 + gx) // 2
        hs = 30
        hy = cyl - hs - 6
        draw.arc([hcx - hs // 2, hy, hcx + hs // 2, hy + hs], start=180, end=360, fill=gray, width=3)
        draw.rectangle([hcx - hs // 2, int(hy + hs * 0.42), hcx - hs // 2 + 7, int(hy + hs * 0.82)], fill=gray)
        draw.rectangle([hcx + hs // 2 - 7, int(hy + hs * 0.42), hcx + hs // 2, int(hy + hs * 0.82)], fill=gray)
        # separador entre partidos
        if i < n - 1:
            sy = top + block_h
            draw.line([(card_x + 30, sy), (card_x + card_w - 30, sy)], fill=(0, 0, 0, 28), width=2)

    img.save(output_path, "PNG")
    return output_path


def _relative_day(s: str) -> str:
    """Día relativo en español (Hoy/Mañana/Ayer/día de la semana) según la fecha
    del partido EN PERÚ vs hoy en Perú. Acepta 'YYYY-MM-DD HH:MM' (Madrid, se
    convierte a Perú −7h) o 'YYYY-MM-DD'."""
    import re
    from datetime import date as _date, datetime, timedelta, timezone
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", s or "")
    peru_dt = None
    if m:
        peru_dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])) - timedelta(hours=7)
        d = peru_dt.date()
    else:
        md = re.search(r"(\d{4})-(\d{2})-(\d{2})", s or "")
        if not md:
            return ""
        d = _date(int(md[1]), int(md[2]), int(md[3]))
    peru_today = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)).date()
    diff = (d - peru_today).days
    if diff == 0:
        return "Hoy"
    if diff == 1:
        return "Mañana"
    if diff == -1:
        return "Ayer"
    return dias[(peru_dt or datetime(d.year, d.month, d.day)).weekday()]


def build_viral_match_bar(home: str, away: str, date_str: str, time_raw_or_peru: str,
                          output_path: str, video_size: tuple[int, int] = (1080, 1920)) -> str:
    """Barra oscura del partido (por pick): ★ · bandera+equipo · fecha+hora · bandera+equipo · ★.
    Overlay transparente, barra centrada verticalmente (~y 40%)."""
    W, H = video_size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bar_h = 300
    bar_y = int(H * 0.26)   # arriba para no solaparse con el muñeco (mitad inferior)
    draw.rounded_rectangle([0, bar_y, W, bar_y + bar_h], radius=0, fill=BAR_BG)

    time_txt = time_raw_or_peru if "m." in (time_raw_or_peru or "") else madrid_to_peru(time_raw_or_peru)
    day_lbl = _relative_day(time_raw_or_peru) or _relative_day(date_str)
    cy = bar_y + bar_h // 2
    cx = W // 2

    # estrellas
    star_font = _font(64)
    draw.text((40, cy), "★", font=star_font, fill=GOLD, anchor="lm")
    draw.text((W - 40, cy), "★", font=star_font, fill=GOLD, anchor="rm")

    # hora (Perú) grande + día relativo debajo (centro)
    draw.text((cx, cy - 22), time_txt, font=_font(60), fill=WHITE, anchor="mm")
    if day_lbl:
        draw.text((cx, cy + 44), day_lbl, font=_font(44), fill=(207, 214, 221), anchor="mm")

    # local (izquierda) y visitante (derecha): bandera redonda + nombre debajo
    flag_sz = 96
    name_font = _font(38)
    for team, anchor_x in ((home, int(W * 0.20)), (away, int(W * 0.80))):
        fl = round_flag(team, flag_sz)
        if fl is not None:
            img.alpha_composite(fl, (anchor_x - flag_sz // 2, cy - 60 - flag_sz // 2))
        draw.text((anchor_x, cy + 70), _to_es(team), font=name_font, fill=WHITE, anchor="mm")

    img.save(output_path, "PNG")
    return output_path
