# Estadísticas DÍA A DÍA de la cuenta árabe en el Xiaomi Mi 8 (1080x2248).
# uso: python3 -I dias_mi8.py AAAA-MM-DD [AAAA-MM-DD …]   (o «DESDE..HASTA»)
# Sale en $EST_DIR/dias_mi8.json: [{fecha, gmv, ventas, impresiones, clics, comision}] (euros como float).
# Una sola pasada, sin force-stop (salvo --reiniciar), PAUSA_DIAS s entre días; puzle: X una vez y si vuelve, sale.
# Arranca desde cualquier pantalla de TikTok: Perfil › TikTok Studio › TikTok Shop para creadores › «>» › Datos.
# La página Datos es web (el volcado de uiautomator sale vacío): todo se lee por OCR (tesseract spa).
# El OPPO tiene sus propios scripts (mes.py/tend.py, otra resolución); este no los toca.
import datetime, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # con -I no entra la carpeta del script
import studio_ocr as so
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "movil"))
from puzle import boton_cerrar, detectar_puzle  # noqa: E402
from studio_ocr import MESES, cabecera, donde, hay, num  # noqa: F401  (los usa elegir_dia)

D = os.environ.get("MOVIL_ADB", "100.115.12.26:5555")
W = os.environ.get("EST_DIR", "/tmp/est_mi8"); os.makedirs(W, exist_ok=True)
PKG = "com.zhiliaoapp.musically"
COLS = [113, 255, 397, 538, 679, 820, 961]          # Lun … Dom en el calendario
FILA0, PASO = 1118, 126                             # 1.ª fila del mes en curso al abrir el selector; alto de fila


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
    return so.parse_tsv(tsv)


def ocr_zona(png, x, y, w, h, psm=7):
    subprocess.run(["convert", png, "-crop", f"{w}x{h}+{x}+{y}", "-colorspace", "gray", "-resize", "300%",
                    "-bordercolor", "white", "-border", "40", f"{W}/z.png"])
    return subprocess.run(["tesseract", f"{W}/z.png", "-", "-l", "spa", "--psm", str(psm)],
                          capture_output=True, text=True).stdout.strip()


def ocr_cifra(png, zona, escala):
    x, y, w, h = zona
    subprocess.run(["convert", png, "-crop", f"{w}x{h}+{x}+{y}", "-colorspace", "gray", "-resize", escala,
                    "-bordercolor", "white", "-border", "30", f"{W}/z.png"])
    return subprocess.run(["tesseract", f"{W}/z.png", "-", "-l", "spa", "--psm", "7"],
                          capture_output=True, text=True).stdout.strip()


def volcado():
    """[(x, y, texto)] centro de cada nodo del volcado nativo (vacío en páginas web)."""
    adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    x = adb("exec-out", "cat", "/sdcard/u.xml")
    try: open(f"{W}/u.xml", "w").write(x)          # para diagnosticar si la pantalla cambia
    except OSError: pass
    return so.parse_volcado(x)


X_PUESTA = False


def vigilar_puzle(pal=None):
    """Puzle: X UNA vez (regla de Néstor); si sigue o vuelve, se para (código 3) sin resolver ni reintentar."""
    global X_PUESTA
    xml = adb("exec-out", "sh", "-c", "uiautomator dump /sdcard/u.xml >/dev/null && cat /sdcard/u.xml")
    pal = pal if pal is not None else palabras()
    if not (detectar_puzle(xml) or so.hay_puzle_ocr(pal)):
        return
    cap("puzle")
    if X_PUESTA:
        guardar(); sys.exit(f"PUZLE otra vez: paro sin reintentar (captura {W}/puzle.png)")
    p = boton_cerrar(xml)
    if not p:
        guardar(); sys.exit(f"PUZLE sin X visible: paro (captura {W}/puzle.png)")
    X_PUESTA = True
    tap(*p, 4)
    if detectar_puzle(adb("exec-out", "sh", "-c", "uiautomator dump /sdcard/u.xml >/dev/null && cat /sdcard/u.xml")) \
            or so.hay_puzle_ocr(palabras()):
        guardar(); sys.exit(f"PUZLE sigue tras la X: paro (captura {W}/puzle.png)")


RES = []


def guardar():
    json.dump(RES, open(f"{W}/dias_mi8.json", "w"), ensure_ascii=False, indent=1)


def a_datos():
    """Llega a la página Datos: Perfil › TikTok Studio › «Ver detalles» de TikTok Shop para creadores › «>»."""
    pal = palabras()
    # el OCR no siempre lee los chips grises («Ayer»): «Datos clave» también confirma la página (8/11)
    if hay("Personalizado", pal) and (hay("Ayer", pal) or hay("clave", pal)):
        return
    # SIN force-stop (Admin 9/11): reabrir TikTok tras cerrarlo a la fuerza es de lo que más saca el puzle.
    # Con «--reiniciar» se fuerza una vez (máx. 1 por sesión) si la app se queda colgada.
    if "--reiniciar" in sys.argv:
        adb("shell", "am", "force-stop", PKG); time.sleep(1)
    adb("shell", "monkey", "-p", PKG, "1"); time.sleep(9)
    vigilar_puzle()
    # 12/11: TikTok se reabre donde se quedó, a menudo DENTRO del centro de creadores (pestañas
    # Inicio/Productos/Vídeos/Crecimiento): ahí (972, 2006) es «Crecimiento», no «Perfil». Se sale con su X.
    for _ in range(3):
        pal = palabras()
        if not (hay("Crecimiento", pal) or hay("Personalizado", pal) or hay("beneficios", pal)):
            break
        tap(75, 160, 3)                                 # X / flecha atrás de arriba a la izquierda
    tap(972, 2006, 4)                                   # Perfil
    swipe(600, 1800, ms=300, s=1); swipe(600, 1800, ms=300, s=2)   # perfil arriba del todo (si no, Studio no se ve)
    p = next(((x, y) for x, y, t in volcado() if t == "TikTok Studio"), (228, 884))
    tap(*p, 7)
    p = None
    for i in range(4):
        # desde 7/11 a veces no sale en el volcado nativo: se busca también por OCR
        p = so.boton_ver_detalles(volcado(), palabras(cap(f"studio_{i}")))
        if p: break
        if i == 1: swipe(1500, 900)                     # la tarjeta puede quedar debajo de un banner
        else: tap(927, 739, 2)                          # aviso «Estado de la cuenta» (no sale en el volcado)
    else:
        sys.exit(f"no encuentro «Ver detalles» en TikTok Studio (capturas {W}/studio_*.png y u.xml)")
    tap(*p, 7)                                          # la tarjeta de la derecha: «para creadores»
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


def leer(f: datetime.date):
    png = cap(f"d_{f}")
    pal = palabras(png)
    # cabecera «2 nov 2026 GMT+1» bajo los chips: la comprobación de verdad del día elegido
    try: out = so.extraer_resumen(pal, f)
    except ValueError as e: raise RuntimeError(str(e))
    pest0 = so.pestanas_comision(pal)
    for clave, etiqueta in so.ETIQUETAS:                # cifra que el OCR de pantalla entera no leyó
        e = next(((x, y) for x, y, w, h, t in pal if t.startswith(etiqueta) and (x, y) not in pest0), None)
        if out.get(clave) is None and e:
            out[clave] = so.elegir_lectura([ocr_cifra(png, so.zona_cifra(e), r) for r in ("50%", "100%", "200%")])
    pestanas = so.pestanas_comision(pal)
    if pestanas:                                        # días pasados: «Resumen | Comisiones»
        tap(pestanas[0][0] + 60, pestanas[0][1] + 20, 2.5)
        pal2 = palabras(cap(f"c_{f}"))
        out["comision"] = so.extraer_comision(pal2)
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
    res = RES
    pausa = float(os.environ.get("PAUSA_DIAS", "45"))   # entre días: las ráfagas de lecturas sacan el puzle
    a_datos()
    # del más nuevo al más viejo: el selector se abre en el mes del último día elegido, y así el mes en
    # curso siempre se pide con el selector recién abierto en él (FILA0) y los anteriores se buscan por cabecera
    for i, f in enumerate(sorted(set(fechas([a for a in sys.argv[1:] if not a.startswith("--")])), reverse=True)):
        if i: time.sleep(pausa)
        vigilar_puzle()
        for intento in range(2):
            try:
                elegir_dia(f, hoy); r = leer(f); break
            except RuntimeError as e:
                print("reintento:", e, flush=True); r = {"fecha": str(f), "error": str(e)}
        print(json.dumps(r, ensure_ascii=False), flush=True)
        res.append(r); guardar()                        # lo leído queda guardado aunque luego pare
    guardar()
