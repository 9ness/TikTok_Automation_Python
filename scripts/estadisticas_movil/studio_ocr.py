# Lectura PURA (sin móvil) de las pantallas de TikTok Studio que capturan los scripts del Mi 8.
# Todo lo que depende de adb/tesseract vive en dias_mi8.py; aquí solo se interpreta el texto,
# para poder probarlo con fixtures (tests/estadisticas_movil/).
# pal = [(x, y, w, h, texto)] tal como sale de tesseract --psm 11 tsv (confianza > 30).
import datetime
import html
import re

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
ETIQUETAS = [("gmv", "GMV"), ("ventas", "Ventas"), ("impresiones", "Impresiones"),
             ("clics", "Clics"), ("comision", "Comisiones")]


def parse_tsv(tsv: str, conf_min: float = 30):
    out = []
    for l in tsv.splitlines()[1:]:
        c = l.split("\t")
        if len(c) == 12 and c[11].strip():
            try:
                if float(c[10]) <= conf_min:
                    continue
                out.append((int(c[6]), int(c[7]), int(c[8]), int(c[9]), c[11].strip()))
            except ValueError:
                continue
    return out


def parse_volcado(xml: str):
    """[(x, y, texto)] centro de cada nodo con text/content-desc de un volcado de uiautomator."""
    return [((int(m[2]) + int(m[4])) // 2, (int(m[3]) + int(m[5])) // 2, html.unescape(m[1]))
            for m in re.finditer(r'(?:text|content-desc)="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]', xml)]


def hay(texto, pal):
    return any(texto.lower() in p[4].lower() for p in pal)


def donde(texto, pal):
    return next(((x + w // 2, y + h // 2) for x, y, w, h, t in pal if texto.lower() in t.lower()), None)


def num(s):
    """«37,75 €» → 37.75 · «4,4K» → 4400 · «1.234» → 1234 · sin cifra → None."""
    if s is None:
        return None
    s = s.replace("€", "").replace(" ", "").replace("O", "0").replace("o", "0")
    s = re.sub(r"(?<=\d)/(?=\d)", ",", s)               # «1/1K»: el OCR lee la coma como barra
    m = re.search(r"\d[\d.,]*K?", s)
    if not m:
        return None
    s = m.group(0)
    k = 1000 if s.endswith("K") else 1
    s = s.rstrip("K")
    if k > 1:
        s = s.replace(",", ".")
    else:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s) * k, 2)
    except ValueError:
        return None


def cabecera(pal):
    """La línea «4 nov 2026 GMT+1» bajo los chips, esté donde esté (los avisos de arriba la bajan)."""
    g = [(y, x) for x, y, w, h, t in pal if t.startswith("GMT") and y < 1100]
    if not g:
        return ""
    yg = g[0][0]
    return " ".join(t for x, y, w, h, t in sorted(pal) if abs(y - yg) < 25 and x < 700).lower()


def es_dia(cab: str, f: datetime.date) -> bool:
    cab = cab.lower().replace("0ct", "oct")
    return bool(re.search(rf"(^|\s)0?{f.day}\s+{MESES[f.month - 1]}", cab))


def cabecera_resumen(pal):
    return cabecera(pal) or " ".join(t for x, y, w, h, t in sorted(pal) if 360 < y < 430 and x < 700).lower()


def cifra(pal, e):
    """La cifra grande (alto ≥ 35 px) debajo de la etiqueta e=(x, y), en su misma mitad de pantalla."""
    lado = (lambda x: x < 540) if e[0] < 540 else (lambda x: x >= 540)
    c = sorted((y, t) for x, y, w, h, t in pal if lado(x) and e[1] + 30 < y < e[1] + 220
               and h >= 35 and re.search(r"\d", t))
    return num(c[0][1]) if c else None


def pestanas_comision(pal):
    """Posición de la pestaña «Comisiones» de la barra «Resumen | Comisiones» (días pasados)."""
    return [(x, y) for x, y, w, h, t in pal if t == "Comisiones"
            and any(t2 == "Resumen" and abs(y2 - y) < 20 for _, y2, _, _, t2 in pal)]


def extraer_resumen(pal, f: datetime.date):
    """{fecha, gmv, ventas, impresiones, clics, comision} de la página Datos de un día.
    Lanza ValueError si la página no es de ese día."""
    cab = cabecera_resumen(pal)
    if not es_dia(cab, f):
        raise ValueError(f"la página no es de {f}: «{cab}»")
    out = {"fecha": str(f)}
    pest = pestanas_comision(pal)
    for clave, etiqueta in ETIQUETAS:
        e = next(((x, y) for x, y, w, h, t in pal if t.startswith(etiqueta) and (x, y) not in pest), None)
        out[clave] = cifra(pal, e) if e else None
    return out


def extraer_comision(pal):
    """Comisión de la pestaña Comisiones: cifra bajo «Comisiones estimadas»."""
    e = next(((x, y) for x, y, w, h, t in pal if t == "estimadas"), None)
    e = e and next(((x, y) for x, y, w, h, t in pal if t.startswith("Comisi") and abs(y - e[1]) < 15), e)
    return cifra(pal, e) if e else None


def boton_ver_detalles(nodos, pal=None):
    """Dónde tocar «Ver detalles» de la tarjeta «TikTok Shop para creadores» en TikTok Studio.
    nodos = volcado nativo [(x, y, texto)]; si no está ahí (desde 7/11 a veces no sale), se busca
    en el OCR pal. Con varias tarjetas, la de la derecha (o la de abajo si están en columna)."""
    ps = sorted((x, y) for x, y, t in nodos if "ver detalles" in t.lower())
    if not ps and pal:
        ps = sorted((x + w // 2, y + h // 2) for x, y, w, h, t in pal
                    if t.lower().startswith("detalles")
                    and any(t2.lower() == "ver" and abs(y2 - y) < 20 and 0 < x - x2 < 150
                            for x2, y2, _, _, t2 in pal))
        ps = [(x - 40, y) for x, y in ps]               # centro de «Ver detalles», no de «detalles»
    if not ps:
        return None
    return ps[-1]


def zona_cifra(e):
    """Recorte (x, y, w, h) donde está la cifra grande bajo la etiqueta e=(x, y) (Mi 8, 1080 px)."""
    x0 = 60 if e[0] < 540 else 570
    return (x0, e[1] + 82, 460, 90)


def elegir_lectura(lecturas):
    """Varias lecturas OCR de la misma cifra a distintas escalas → la mejor.
    El OCR se come la coma de «1,1K» y lee «11K»; al revés no pasa nunca, así que gana
    la que trae separador. Si ninguna, la más repetida."""
    vals = [(t, num(t)) for t in lecturas if t and num(t) is not None]
    if not vals:
        return None
    con_sep = [v for t, v in vals if re.search(r"\d[.,/]\d", t)]
    if con_sep:
        return con_sep[0]
    cuenta = {}
    for _, v in vals:
        cuenta[v] = cuenta.get(v, 0) + 1
    return max(cuenta, key=cuenta.get)


PUZLE = re.compile(r"verifica\b|arrastra|desliza el|rompecabezas|puzzle|puzle|captcha|completa la pieza", re.I)


def hay_puzle_ocr(pal) -> bool:
    """El puzle de TikTok es un WebView: uiautomator no lo ve, se mira por OCR (6-9/11: ~22 en el Mi 8)."""
    texto = " ".join(t for *_, t in pal)
    return bool(PUZLE.search(texto))
