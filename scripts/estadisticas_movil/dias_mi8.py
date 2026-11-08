# Estadísticas DÍA A DÍA de la cuenta árabe en el Xiaomi Mi 8 (1080x2248).
# uso: python3 -I dias_mi8.py AAAA-MM-DD [AAAA-MM-DD …]   (o «DESDE..HASTA»)
# Sale en $EST_DIR/dias_mi8.json: [{fecha, gmv, ventas, impresiones, clics, comision}] (euros como float).
# Arranca desde cualquier pantalla de TikTok: Perfil › TikTok Studio › TikTok Shop para creadores › «>» › Datos.
# La página Datos es web (el volcado de uiautomator sale vacío): todo se lee por OCR (tesseract spa).
# El OPPO tiene sus propios scripts (mes.py/tend.py, otra resolución); este no los toca.
import datetime, json, os, re, subprocess, sys, time

D = os.environ.get("MOVIL_ADB", "100.115.12.26:5555")
W = os.environ.get("EST_DIR", "/tmp/est_mi8"); os.makedirs(W, exist_ok=True)
PKG = "com.zhiliaoapp.musically"
COLS = [113, 255, 397, 538, 679, 820, 961]          # Lun … Dom en el calendario
FILA0, PASO = 1118, 126                             # 1.ª fila del mes en curso al abrir el selector; alto de fila
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def adb(*a, b=False):
    return subprocess.run(["adb", "-s", D, *a], capture_output=True, text=not b).stdout


def tap(x, y, s=1.5):
    adb("shell", "input", "tap", str(int(x)), str(int(y))); time.sleep(s)


def swipe(y1, y2, x=540, ms=500, s=1.5):
    adb("shell", "input", "swipe", str(x), str(y1), str(x), str(y2), str(ms)); time.sleep(s)


def cap(n="c"):
    p = f"{W}/{n}.png"
    open(p, "wb").write(adb("exec-out", "screencap", "-p", b=True))
    return p


def palabras(png=None):
    """[(x, y, w, h, texto)] de toda la pantalla."""
    png = png or cap()
    tsv = subprocess.run(["tesseract", png, "-", "-l", "spa", "--psm", "11", "tsv"],
                         capture_output=True, text=True).stdout
    out = []
    for l in tsv.splitlines()[1:]:
        c = l.split("\t")
        if len(c) == 12 and c[11].strip() and float(c[10]) > 30:
            out.append((int(c[6]), int(c[7]), int(c[8]), int(c[9]), c[11].strip()))
    return out


def ocr_zona(png, x, y, w, h, psm=7):
    subprocess.run(["convert", png, "-crop", f"{w}x{h}+{x}+{y}", "-colorspace", "gray", "-resize", "300%",
                    "-bordercolor", "white", "-border", "40", f"{W}/z.png"])
    return subprocess.run(["tesseract", f"{W}/z.png", "-", "-l", "spa", "--psm", str(psm)],
                          capture_output=True, text=True).stdout.strip()


def hay(texto, pal):
    return any(texto.lower() in p[4].lower() for p in pal)


def donde(texto, pal):
    return next(((x + w // 2, y + h // 2) for x, y, w, h, t in pal if texto.lower() in t.lower()), None)


def num(s):
    s = s.replace("€", "").replace(" ", "").replace("O", "0").replace("o", "0")
    m = re.search(r"\d[\d.,]*K?", s)
    if not m: return None
    s = m.group(0); k = 1000 if s.endswith("K") else 1; s = s.rstrip("K")
    if k > 1: s = s.replace(",", ".")
    else: s = s.replace(".", "").replace(",", ".")
    try: return round(float(s) * k, 2)
    except ValueError: return None


def volcado():
    """[(x, y, texto)] centro de cada nodo del volcado nativo (vacío en páginas web)."""
    import html as _h
    adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    x = adb("exec-out", "cat", "/sdcard/u.xml")
    return [((int(m[2]) + int(m[4])) // 2, (int(m[3]) + int(m[5])) // 2, _h.unescape(m[1]))
            for m in re.finditer(r'(?:text|content-desc)="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]', x)]


def a_datos():
    """Llega a la página Datos: Perfil › TikTok Studio › «Ver detalles» de TikTok Shop para creadores › «>»."""
    pal = palabras()
    # el OCR no siempre lee los chips grises («Ayer»): «Datos clave» también confirma la página (8/11)
    if hay("Personalizado", pal) and (hay("Ayer", pal) or hay("clave", pal)):
        return
    adb("shell", "am", "force-stop", PKG); time.sleep(1)
    adb("shell", "monkey", "-p", PKG, "1"); time.sleep(9)
    tap(972, 2006, 4)                                   # Perfil
    p = next(((x, y) for x, y, t in volcado() if t == "TikTok Studio"), (228, 843))
    tap(*p, 7)
    for _ in range(3):
        v = volcado()
        ps = sorted((x, y) for x, y, t in v if "Ver detalles" in t)
        if ps: break
        tap(927, 739, 2)                                # aviso «Estado de la cuenta» (no sale en el volcado)
    else:
        sys.exit("no encuentro «Ver detalles» en TikTok Studio")
    tap(*ps[-1], 7)                                     # la tarjeta de la derecha: «para creadores»
    fila = donde("Últimos", palabras()) or donde("días", palabras())   # un banner de campaña lo baja (Black Friday, 6/11)
    tap(1017, fila[1] if fila else 692, 6)              # «>» de Hoy / Últimos 7 días
    if not hay("Personalizado", palabras()): sys.exit("no llego a Datos")


def elegir_dia(f: datetime.date, hoy: datetime.date):
    if f == hoy:                                        # el calendario no deja elegir hoy: chip «Hoy»
        tap(*(donde("Hoy", palabras()) or (113, 297)), 4); return
    pal = palabras()
    ay = donde("Ayer", pal)                             # con avisos arriba los chips bajan; marcado en negro
    p = donde("Personalizado", pal) or ((690, ay[1]) if ay else (690, 297))  # el OCR no lee «Personalizado»
    tap(*p, 2.5)
    pal = palabras()
    se = donde("Semana", pal)
    p = donde("Día", pal) or ((197, se[1] + 112) if se else (197, 1720))
    tap(*p, 2.5)
    col = COLS[f.weekday()]
    if (f.year, f.month) == (hoy.year, hoy.month):
        fila = (f.day - 1 + f.replace(day=1).weekday()) // 7
        y = FILA0 + fila * PASO
    else:
        cab = f"{MESES[f.month - 1].capitalize()} {f.year}"
        siguiente = (f.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        cab_sig = f"{MESES[siguiente.month - 1].capitalize()} {siguiente.year}"
        y = None
        for _ in range(12):
            pal = palabras()
            # la cabecera del mes buscado, con sitio debajo para sus filas
            cs = [(yy + hh // 2) for xx, yy, ww, hh, t in pal if t.lower() == MESES[f.month - 1]
                  and any(t2 == str(f.year) and abs(y2 - yy) < 25 for _, y2, _, _, t2 in pal)]
            cs = [c for c in cs if 1050 < c < 1800]
            fila = (f.day - 1 + f.replace(day=1).weekday()) // 7
            if cs and cs[0] + 95 + fila * PASO < 1780:
                y = cs[0] + 95 + fila * PASO; break
            # la cabecera del mes siguiente: el buscado está justo encima
            sg = [(yy + hh // 2) for xx, yy, ww, hh, t in pal if t.lower() == MESES[siguiente.month - 1]
                  and any(t2 == str(siguiente.year) and abs(y2 - yy) < 25 for _, y2, _, _, t2 in pal)]
            sg = [c for c in sg if 1050 < c < 1800]
            ultima = (calendar_dias(f) - 1 + f.replace(day=1).weekday()) // 7
            if sg and sg[0] - 95 - (ultima - fila) * PASO > 1100:
                y = sg[0] - 95 - (ultima - fila) * PASO; break
            swipe(1250, 1650, ms=600)                  # muestra meses anteriores
        if y is None: sys.exit(f"no encuentro {cab} en el calendario")
    tap(col, y, 1.5)
    pal = palabras()
    if not hay("Listo", pal):                           # Ama Shop (5/11): al tocar el día el selector se cierra solo
        time.sleep(2.5)
        if cabecera(palabras()) and re.search(rf"(^|\s)0?{f.day}\s+{MESES[f.month - 1]}", cabecera(palabras())):
            return
    pie = ocr_zona(cap(), 100, 1820, 880, 110)         # «3 nov 2026» bajo el calendario
    if MESES[f.month - 1] not in pie.lower().replace("0ct", "oct"):
        tap(1000, 602, 1.5)                             # cerrar el selector
        raise RuntimeError(f"día mal elegido: quería {f}, pone «{pie}»")
    p = donde("Listo", palabras()) or (540, 2005)
    tap(*p, 4)


def cabecera(pal):
    """La línea «4 nov 2026 GMT+1» bajo los chips, esté donde esté (los avisos de arriba la bajan)."""
    g = [(y, x) for x, y, w, h, t in pal if t.startswith("GMT") and y < 1100]
    if not g: return ""
    yg = g[0][0]
    return " ".join(t for x, y, w, h, t in sorted(pal) if abs(y - yg) < 25 and x < 700).lower()


def leer(f: datetime.date):
    png = cap(f"d_{f}")
    pal = palabras(png)
    # cabecera «2 nov 2026 GMT+1» bajo los chips: la comprobación de verdad del día elegido
    cab = cabecera(pal) or " ".join(t for x, y, w, h, t in sorted(pal) if 360 < y < 430 and x < 700).lower()
    if not re.search(rf"(^|\s)0?{f.day}\s+{MESES[f.month - 1]}", cab):
        raise RuntimeError(f"la página no es de {f}: «{cab}»")
    out = {"fecha": str(f)}
    def cifra(pal, e):
        lado = (lambda x: x < 540) if e[0] < 540 else (lambda x: x >= 540)
        # la cifra grande (alto ≥ 35 px) que hay debajo de la etiqueta, en su misma columna
        c = sorted((y, t) for x, y, w, h, t in pal if lado(x) and e[1] + 30 < y < e[1] + 220
                   and h >= 35 and re.search(r"\d", t))
        return num(c[0][1]) if c else None
    pestanas = [(x, y) for x, y, w, h, t in pal if t == "Comisiones"
                and any(t2 == "Resumen" and abs(y2 - y) < 20 for _, y2, _, _, t2 in pal)]
    for clave, etiqueta in [("gmv", "GMV"), ("ventas", "Ventas"), ("impresiones", "Impresiones"),
                            ("clics", "Clics"), ("comision", "Comisiones")]:
        e = next(((x, y) for x, y, w, h, t in pal if t.startswith(etiqueta) and (x, y) not in pestanas), None)
        out[clave] = cifra(pal, e) if e else None
    if pestanas:                                        # días pasados: «Resumen | Comisiones»
        tap(pestanas[0][0] + 60, pestanas[0][1] + 20, 2.5)
        pal2 = palabras(cap(f"c_{f}"))
        e = next(((x, y) for x, y, w, h, t in pal2 if t == "estimadas"), None)
        e = e and next(((x, y) for x, y, w, h, t in pal2 if t.startswith("Comisi") and abs(y - e[1]) < 15), e)
        out["comision"] = cifra(pal2, e) if e else None
        r = next(((x, y) for x, y, w, h, t in pal2 if t == "Resumen"), None)
        if r: tap(r[0] + 60, r[1] + 20, 1.5)
    return out


def fechas(args):
    r = []
    for a in args:
        if ".." in a:
            d1, d2 = (datetime.date.fromisoformat(x) for x in a.split(".."))
            while d1 <= d2: r.append(d1); d1 += datetime.timedelta(days=1)
        else: r.append(datetime.date.fromisoformat(a))
    return r


def calendar_dias(f):
    import calendar
    return calendar.monthrange(f.year, f.month)[1]


if __name__ == "__main__":
    hoy = datetime.date.today()
    res = []
    a_datos()
    # del más nuevo al más viejo: el selector se abre en el mes del último día elegido, y así el mes en
    # curso siempre se pide con el selector recién abierto en él (FILA0) y los anteriores se buscan por cabecera
    for f in sorted(set(fechas(sys.argv[1:])), reverse=True):
        for intento in range(2):
            try:
                elegir_dia(f, hoy); r = leer(f); break
            except RuntimeError as e:
                print("reintento:", e, flush=True); r = {"fecha": str(f), "error": str(e)}
        print(json.dumps(r, ensure_ascii=False), flush=True)
        res.append(r)
    json.dump(res, open(f"{W}/dias_mi8.json", "w"), ensure_ascii=False, indent=1)
