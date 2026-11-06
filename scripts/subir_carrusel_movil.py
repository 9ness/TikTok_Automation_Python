"""Sube un carrusel de Mis tandas (fotos) a TikTok desde un móvil por ADB y se para antes de Publicar.

Probado el 26/10/2026 en el OPPO de Néstor (1440x3168, TikTok ES). Los puntos de cada móvil están en
PERFILES y se eligen por `wm size` (MOVIL_PERFIL=oppo|mi8 manda); en el Mi 8 falta calibrar enlace, producto y
swipes. Fases:

    python scripts/subir_carrusel_movil.py preparar <id>   # baja ZIP, copia fotos, guarda el sonido en Favoritos
    python scripts/subir_carrusel_movil.py editor <id>     # fotos → sonido → caption → producto por ID
    python scripts/subir_carrusel_movil.py publicar <id>   # pulsa Publicar y marca subido en la app
    python scripts/subir_carrusel_movil.py limpiar         # borra las fotos copiadas del móvil

Entre fases, mira la captura (`/tmp/carr/sh/s.jpg`). Casuísticas de la UI de TikTok:
- Al elegir fotos TikTok pone un sonido recomendado: hay que cambiarlo.
- Los «sonidos originales» NO salen en el buscador: se abre su enlace, se pulsa
  «Guardar» y en el editor se elige desde la pestaña Favoritos.
- ADB no escribe tildes/ñ/emojis y ADBKeyboard no se puede instalar: el caption se
  comparte a Keep (sin guardar la nota), se copia con Ctrl+A/Ctrl+C y se pega con Ctrl+V.
- `input text` con Gboard se come letras: se escribe carácter a carácter.
- El sonido va ANTES que el producto: con producto puesto el selector solo enseña
  «Sonidos comerciales». Si con el del viral no deja el producto, uno comercial parecido.
- El dump de uiautomator no ve las listas de sonidos ni de productos: van por coordenadas
  y se revisan las capturas.
- El buscador de productos del escaparate acepta el ID del producto → un solo resultado,
  el exacto. El nombre del enlace tiene 30 caracteres como máximo.
- Si el producto NO está en el escaparate, el buscador dice «No se han encontrado
  productos»: `preparar` abre su ficha y pulsa «Añadir al escaparate» antes (captura 6_ficha).
  Los enlaces cortos (vm.tiktok.com) se siguen hasta sacar el ID.
"""

from __future__ import annotations

import html
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

SERIAL = os.environ.get("MOVIL_ADB", "100.123.211.22:40281")
PAQUETE = "com.zhiliaoapp.musically"
TMP = Path(os.environ.get("CARR_TMP", "/tmp/carr"))   # uno por móvil si van dos a la vez
CARPETA_MOVIL = "/sdcard/Pictures/carr_tmp"
MCP_URLS = Path(__file__).resolve().parent.parent / "MCP_URLS.local.md"
USUARIO = os.environ.get("MCP_USUARIO", "ness")
SONIDO_ID = os.environ.get("SONIDO_ID", "")   # sonido comercial fijo (Ama Shop), por enlace y con `rapido`: sin lista ni lupa

# Puntos de la UI de TikTok por móvil. Un perfil por pantalla: escalar no basta (densidades distintas).
PERFILES = {
    "oppo": {   # 1440x3168, densidad 560: probado
        "tamano": (1440, 3168),
        "swipe_ficha": (720, 2600, 720, 1200), "swipe_sonido": (720, 900, 720, 2800),
        "mas": (720, 3024), "galeria": (141, 2991), "album": (688, 243), "y_max_album": 400,
        "rejilla": (417, 552, 477, 483),   # x, y, paso x, paso y
        "pildora_sonido": (660, 372), "fila_favorito": (600, 1845), "cerrar_panel_sonido": (720, 750),
        "y_max_sonido": 500, "caption": (700, 980), "atras": (96, 237),
        "enlace_x": 720, "enlace_y_defecto": 2116, "cerrar_enlace": (1341, 2226), "x_pildora_x": 906,
        "anadir_x": 1188, "anadir_ys": (840, 1044), "confirmar_producto": (720, 1698),
        "anadir_abajo": (720, 2970), "sugerencia": (723, 578), "vaciar": (1188, 405),
        "historial": (340, 759), "zona_comerciales": (450, 1500), "buscar_comercial": (1296, 402),
        "check_comercial": (1278, 640),
    },
    "mi8": {   # 1080x2248, densidad 440: hasta «atras» medido el 6/11; enlace, producto y swipes PROVISIONALES
        "tamano": (1080, 2248), "sin_combos": True, "lista_en_dump": True, "ficha_en_caliente": True,   # Android 10: no hay `input keycombination`
        "swipe_ficha": (540, 1845, 540, 852), "swipe_sonido": (540, 640, 540, 1990),
        "mas": (540, 2040), "galeria": (106, 2020), "album": (540, 153), "y_max_album": 278,
        "rejilla": (306, 399, 360, 360),
        "pildora_sonido": (480, 190), "fila_favorito": (450, 1365), "cerrar_panel_sonido": (540, 450),
        "y_max_sonido": 300, "caption": (540, 800), "atras": (78, 150),
        "enlace_x": 540, "enlace_y_defecto": 1625, "cerrar_enlace": (1006, 1712), "x_pildora_x": 680,
        "anadir_x": 891, "anadir_ys": (626, 786), "confirmar_producto": (540, 1298),
        "anadir_abajo": (540, 2000), "sugerencia": (542, 418), "vaciar": (891, 303),
        "historial": (255, 560), "zona_comerciales": (331, 1183), "buscar_comercial": (972, 301),
        "check_comercial": (958, 466),
    },
}
_perfil: dict | None = None


# ---------------------------------------------------------------- adb básico
def reconectar() -> bool:
    """El OPPO va por Tailscale y a ratos sale «offline» (2/11): reconecta y comprueba con un echo."""
    for _ in range(6):
        try:
            subprocess.run(["adb", "disconnect", SERIAL], capture_output=True, timeout=10)
            subprocess.run(["adb", "connect", SERIAL], capture_output=True, timeout=20)
            r = subprocess.run(["adb", "-s", SERIAL, "shell", "echo", "ok"], capture_output=True, text=True, timeout=10)
            if r.stdout.strip() == "ok":
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(5)
    return False


def adb_run(args: list, timeout: int = 25, text: bool = True):
    """adb con reintento: si se cuelga o sale offline, reconecta y repite (antes moría a los 60 s)."""
    for intento in range(4):
        try:
            r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=text, timeout=timeout)
            err = r.stderr if text else r.stderr.decode(errors="ignore")
            if not re.search(r"device offline|not found|no devices|closed", err):
                return r
        except subprocess.TimeoutExpired:
            pass
        print(f"  adb caído ({' '.join(args[:3])}): reconecto [{intento + 1}/4]", flush=True)
        reconectar()
    raise SystemExit("ADB: el móvil no responde tras 4 reconexiones")


def adb(*args: str, timeout: int = 25) -> str:
    return adb_run(list(args), timeout).stdout


def screencap() -> bytes:
    """PNG completo o reintento: si el ADB se corta a mitad llega vacío o truncado (2/11)."""
    for _ in range(4):
        png = adb_run(["exec-out", "screencap", "-p"], 30, text=False).stdout
        if png[:8] == b"\x89PNG\r\n\x1a\n" and png.rstrip().endswith(b"IEND\xaeB`\x82"):
            return png
        reconectar()
    return png


def perfil() -> dict:
    """Perfil del móvil conectado, una sola consulta. Tamaño desconocido → para: tocar a ciegas podría publicar mal."""
    global _perfil
    if _perfil is None:
        nombre = os.environ.get("MOVIL_PERFIL")
        if nombre:
            if nombre not in PERFILES:
                raise SystemExit(f"MOVIL_PERFIL desconocido: {nombre}")
            _perfil = PERFILES[nombre]
        else:
            salida = adb("shell", "wm", "size")
            m = re.search(r"Physical size: (\d+)x(\d+)", salida) or re.search(r"(\d+)x(\d+)", salida)
            tamano = tuple(map(int, m.groups())) if m else None
            _perfil = next((p for p in PERFILES.values() if p["tamano"] == tamano), None)
            if _perfil is None:
                raise SystemExit(f"Pantalla sin perfil: {salida.strip()!r} (añádelo a PERFILES o usa MOVIL_PERFIL)")
    return _perfil


def pt(nombre: str):
    return perfil()[nombre]


def deslizar(nombre: str, ms: int) -> None:
    adb("shell", "input", "swipe", *map(str, pt(nombre)), str(ms))


def toque_foto(i: int) -> None:
    """Foto i de la rejilla de 3 columnas; lo más nuevo arriba."""
    x, y, paso_x, paso_y = pt("rejilla")
    fila, col = divmod(i, 3)
    tap(x + paso_x * col, y + paso_y * fila, 1)


def tap(x: int, y: int, espera: float = 1.5) -> None:
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(espera)


def tecla(*codigos: int) -> None:
    if len(codigos) == 1:
        adb("shell", "input", "keyevent", str(codigos[0]))
    else:
        adb("shell", "input", "keycombination", *map(str, codigos))
    time.sleep(0.5)


def sin_combos() -> bool:
    return bool(perfil().get("sin_combos"))


def vaciar_texto(n: int = 45) -> None:
    """Vacía el campo con el foco; sin Ctrl+A, al final y borrando hacia atrás."""
    if sin_combos():
        adb("shell", "input", "keyevent", "123", *["67"] * n)
        time.sleep(0.5)
    else:
        tecla(113, 29)
        tecla(67)


def pegar_caption() -> None:
    tap(*pt("caption"), 2)
    if sin_combos():
        video_movil().pegar()             # chip del portapapeles de Gboard
        tecla(62)                         # espacio: cierra la lista de hashtags sugeridos
    else:
        tecla(113, 50)                    # Ctrl+V
    time.sleep(1)


def al_principio() -> None:
    tecla(122) if sin_combos() else tecla(113, 122)   # Inicio; Ctrl+Inicio en el OPPO


def video_movil():
    """El pegado por Keep + Gboard del Mi 8 ya está en subir_video_movil."""
    import subir_video_movil as sv
    sv.SERIAL, sv.TMP = SERIAL, TMP
    return sv


def escribir(texto: str) -> None:
    """Carácter a carácter: con Gboard, `input text` de golpe se come letras."""
    for c in texto:
        if c == " ":
            adb("shell", "input", "keyevent", "62")
        else:
            adb("shell", "input", "text", c if c.isalnum() else f"'{c}'")


def nodos() -> list[dict]:
    xml = adb("exec-out", "uiautomator", "dump", "/dev/tty", timeout=30)   # 1 llamada en vez de 3
    if "<node" not in xml:
        adb("shell", "uiautomator", "dump", "/sdcard/u.xml", timeout=30)
        xml = adb("shell", "cat", "/sdcard/u.xml")
    out = []
    for m in re.finditer(r"<node [^>]*>", xml):
        n = m.group(0)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        out.append({
            "text": (re.search(r' text="([^"]*)"', n) or re.match("()", "")).group(1),
            "desc": (re.search(r'content-desc="([^"]*)"', n) or re.match("()", "")).group(1),
            "clase": (re.search(r'class="([^"]*)"', n) or re.match("()", "")).group(1),
            "x": (x1 + x2) // 2, "y": (y1 + y2) // 2,
        })
    return out


def buscar(patron: str, intentos: int = 4) -> dict | None:
    for _ in range(intentos):
        for n in nodos():
            if re.search(patron, n["text"], re.I) or re.search(patron, n["desc"], re.I):
                return n
        time.sleep(1.5)
    return None


def pulsar(patron: str, espera: float = 2.0) -> bool:
    n = buscar(patron)
    if n:
        tap(n["x"], n["y"], espera)
    return bool(n)


def captura(nombre: str = "s") -> None:
    from PIL import Image

    try:   # la captura es para revisar: si falla no debe tumbar la fase
        im = Image.open(io.BytesIO(screencap())).convert("RGB")
    except Exception as e:
        print(f"captura {nombre}: falló ({e})")
        return
    im.resize((im.width // 3, im.height // 3)).save(TMP / "sh" / f"{nombre}.jpg", quality=80)
    print(f"captura: {TMP / 'sh' / (nombre + '.jpg')}")


def texto_pantalla() -> str:
    """Texto de la mitad de arriba por OCR (la lista de productos no sale en el volcado)."""
    from PIL import Image

    png = screencap()
    im = Image.open(io.BytesIO(png)).convert("L")
    im.crop((0, 0, im.width, im.height // 2)).save(TMP / "sh" / "ocr.png")
    return subprocess.run(["tesseract", str(TMP / "sh" / "ocr.png"), "-", "-l", "spa", "--psm", "6"],
                          capture_output=True, text=True).stdout


def texto_zona(y0: int, y1: int) -> str:
    """OCR de una franja horizontal (coordenadas reales de la pantalla)."""
    from PIL import Image

    png = screencap()
    im = Image.open(io.BytesIO(png)).convert("L")
    im.crop((0, y0, im.width, y1)).save(TMP / "sh" / "ocr.png")
    return subprocess.run(["tesseract", str(TMP / "sh" / "ocr.png"), "-", "-l", "spa", "--psm", "6"],
                          capture_output=True, text=True).stdout


def botones_anadir() -> list[dict]:
    """«Añadir» de la lista de productos, si el volcado la ve (Mi 8 sí; OPPO no)."""
    if not perfil().get("lista_en_dump"):
        return []
    return [n for n in nodos() if n["desc"] == "button_add_product"]


def sin_resultados() -> bool:
    """«No se han encontrado productos» no sale en el volcado: se mira con OCR el centro de la pantalla."""
    from PIL import Image

    if buscar(r"No se han encontrado", intentos=1):
        return True
    if perfil().get("lista_en_dump"):     # Mi 8: sin resultados la lista queda en BLANCO, sin ese texto
        return not botones_anadir()
    png = screencap()
    im = Image.open(io.BytesIO(png)).convert("L")
    im.crop((0, int(im.height * .25), im.width, int(im.height * .5))).save(TMP / "sh" / "ocr.png")
    t = subprocess.run(["tesseract", str(TMP / "sh" / "ocr.png"), "-", "-l", "spa", "--psm", "6"],
                       capture_output=True, text=True).stdout
    return bool(re.search(r"encontrado|otra b", t))


# ---------------------------------------------------------------- datos de la app
def mcp(herramienta: str, argumentos: dict) -> dict:
    url = re.search(rf"^- {USUARIO}\b[^:\n]*: (\S+)", MCP_URLS.read_text(), re.M).group(1)   # admite «- ana (Moda Mujer…): url»
    cuerpo = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": herramienta, "arguments": argumentos}}
    req = urllib.request.Request(url, json.dumps(cuerpo).encode(), {
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    for intento in range(3):   # la factory a veces no contesta (2/11): reintenta en vez de tirar la fase
        try:
            r = json.load(urllib.request.urlopen(req, timeout=420))   # mis_tandas de ness tarda ~5 min (5/11)
            break
        except (TimeoutError, OSError) as e:
            if intento == 2:
                raise SystemExit(f"MCP {herramienta}: sin respuesta ({e})")
            print(f"  MCP {herramienta} sin respuesta: reintento", flush=True)
            time.sleep(10)
    texto = r["result"]["content"][0]["text"]
    if r["result"].get("isError"):
        raise SystemExit(f"MCP {herramienta}: {texto}")
    return json.loads(texto)


CACHE = TMP / "tandas.json"


def carrusel(cid: str) -> dict:
    c = _carrusel(cid)
    if SONIDO_ID:
        c["musica"]["tiktok"] = {"titulo": f"fijo {SONIDO_ID}",
                                 "enlace": f"https://www.tiktok.com/music/sonido-{SONIDO_ID}"}
    return c


def _carrusel(cid: str) -> dict:
    """De la caché del lote si existe (una sola llamada al MCP para todos)."""
    def buscar(datos: dict) -> dict | None:
        for t in datos["tandas"]:
            for c in t.get("items", t.get("carruseles", [])):
                if c.get("id") == cid:
                    return c
        return None

    if CACHE.exists():
        c = buscar(json.loads(CACHE.read_text()))
        if c:
            return c
    # Caché vieja o inexistente (4/11: «No encuentro» → force-stop y reintento): se pide fresca y se guarda
    datos = mcp("mis_tandas", {"fotos": True})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(datos, ensure_ascii=False))
    c = buscar(datos)
    if c:
        return c
    raise SystemExit(f"No encuentro el carrusel {cid} en Mis tandas")


def pid_de(c: dict) -> str:
    """ID del producto; los enlaces cortos (vm.tiktok.com) se siguen hasta la ficha."""
    url = c["product_url"]
    if "/product/" not in url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            url = urllib.request.urlopen(req, timeout=30).geturl()
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"No resuelvo el enlace corto {url}: {e}")
    m = re.search(r"/(?:product|pdp)/(\d+)", url)
    if not m:
        raise SystemExit(f"No saco el ID de producto de {url}")
    return m.group(1)


SIN_STOCK = TMP / "sin_stock_pids.txt"   # productos ya vistos sin existencias: se saltan sin abrir nada


def sin_stock(pid: str, motivo: str) -> None:
    with SIN_STOCK.open("a") as f:
        f.write(pid + "\n")
    raise SystemExit(f"{pid}: {motivo} → sin stock, saltar")


def al_escaparate(pid: str) -> bool:
    """Abre la ficha en TikTok y pulsa «Añadir al escaparate». True si lo añadió o ya estaba."""
    if SIN_STOCK.exists() and pid in SIN_STOCK.read_text().split():
        raise SystemExit(f"{pid}: ya visto sin existencias → sin stock, saltar")
    if perfil().get("ficha_en_caliente"):  # Mi 8: con la app cerrada el enlace cae en el feed, no en la ficha
        adb("shell", "monkey", "-p", PAQUETE, "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(9)
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", f"https://www.tiktok.com/view/product/{pid}", PAQUETE)
    time.sleep(12 if perfil().get("ficha_en_caliente") else 8)
    captura("6_ficha")
    if buscar(r"(se ha eliminado|Producto no disponible)", intentos=1):
        sin_stock(pid, "la ficha dice «eliminado/no disponible» (6_ficha)")
    # el stock sale en el panel «Información de la promoción», que sube al 2.º deslizamiento
    for _ in range(2):
        deslizar("swipe_ficha", 600)
        time.sleep(2)
        if buscar(r"Sin existen", intentos=1):
            captura("6_panel")
            sin_stock(pid, "«Sin existencias» en la ficha (6_panel)")
        if buscar(r"Información de la promoción", intentos=1):
            break
    # ya añadido: el botón del panel pasa a «Descubrir más» (2/11, comprobado en el OPPO)
    if buscar(r"(Añadido al escaparate|En el escaparate|Quitar del escaparate|Descubrir más)", intentos=1):
        return True
    if not pulsar(r"Añadir al escaparate", 4):
        # Al deslizar sube el panel «Información de la promoción»: ahí sale el stock y el botón
        for _ in range(3):
            deslizar("swipe_ficha", 600)
            time.sleep(2)
            if buscar(r"Sin existen", intentos=1):
                captura("6_panel")
                sin_stock(pid, "«Sin existencias» en la ficha (6_panel)")
            if buscar(r"Añadir al escaparate", intentos=1):
                break
        if not pulsar(r"Añadir al escaparate", 4):
            return False
    captura("6_escaparate")
    return True


def nombre_enlace(c: dict) -> str:
    """≤30 caracteres, sin la tienda y sin tildes (ADB no las escribe)."""
    t = " ".join(c["titulo"].split())
    for marca in (c.get("tienda", ""), (c.get("tienda") or " ").split()[0]):
        if marca and t.lower().startswith(marca.lower() + " "):
            t = t[len(marca):].strip()
            break
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 ]", "", t)
    out = ""
    for p in t.split():
        if len(out) + len(p) + (1 if out else 0) > 30:
            break
        out = f"{out} {p}".strip()
    return out


def bajar_fotos(c: dict, d: Path) -> None:
    """El ZIP lo arma la app al vuelo: ~2 min. Por eso el lote los baja todos a la vez."""
    zipdata = urllib.request.urlopen(c["zip"], timeout=400).read()
    with zipfile.ZipFile(io.BytesIO(zipdata)) as z:
        fotos = sorted(n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png")))
        for i, n in enumerate(fotos, 1):
            (d / f"{i:02d}{Path(n).suffix.lower()}").write_bytes(z.read(n))


# ---------------------------------------------------------------- fases
def lote() -> None:
    """Una llamada a Mis tandas + todos los ZIP pendientes en paralelo, antes de tocar el móvil."""
    from concurrent.futures import ThreadPoolExecutor
    datos = mcp("mis_tandas", {"fotos": True})
    CACHE.write_text(json.dumps(datos, ensure_ascii=False))
    pend = [c for t in datos["tandas"] for c in t.get("items", t.get("carruseles", []))
            if not c.get("subido") and not c.get("sin_stock")]

    def uno(c: dict) -> str:
        try:
            return _uno(c)
        except Exception as e:   # uno raro (sin ZIP, sin título…) no debe tumbar el lote
            return f"{c.get('id')} · ERROR {e!r}"

    def _uno(c: dict) -> str:
        d = TMP / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "datos.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
        if not any(d.glob("0*")):
            bajar_fotos(c, d)
        pid = pid_de(c)
        return f"{c['id']} · {len(list(d.glob('0*')))} fotos · {pid} · {((c.get('musica') or {}).get('tiktok') or {}).get('titulo')} · {' '.join((c.get('titulo') or '').split())}"

    with ThreadPoolExecutor(8) as ex:
        for linea in ex.map(uno, pend):
            print(linea)


def preparar(cid: str) -> None:
    (TMP / f"inicio_{cid}").write_text(str(time.time()))
    c = carrusel(cid)
    d = TMP / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "datos.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
    if not any(d.glob("0*")):
        bajar_fotos(c, d)
    locales = sorted(p for p in d.iterdir() if p.suffix in (".jpg", ".jpeg", ".png"))
    print(f"{c['titulo']!r}: {len(locales)} fotos · sonido {c['musica']['tiktok']['titulo']}")
    # La ficha del escaparate solo se abre si el producto ya falló al buscarlo por ID (marca de producto()):
    # el producto se añade en el propio vídeo por su ID (Néstor, 2/11), y abrir la ficha costaba 1-2 min.
    pid = pid_de(c)
    if SIN_STOCK.exists() and pid in SIN_STOCK.read_text().split():
        raise SystemExit(f"{pid}: ya visto sin existencias → sin stock, saltar")
    if (TMP / f"escaparate_{pid}").exists() and not al_escaparate(pid):
        print("AVISO: no vi «Añadir al escaparate» ni que ya estuviera (mira 6_ficha); sigo")
    adb("shell", "am", "force-stop", PAQUETE)

    limpiar()
    adb("shell", "mkdir", "-p", CARPETA_MOVIL)
    for p in locales:
        destino = f"{CARPETA_MOVIL}/{cid}_{p.name}"
        adb("push", str(p), destino)
        adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", f"file://{destino}")
        time.sleep(1)

    # Sonido → Favoritos (los originales no salen en el buscador)
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", c["musica"]["tiktok"]["enlace"], PAQUETE)
    time.sleep(6)
    deslizar("swipe_sonido", 300)  # a veces abre a media página
    time.sleep(2)
    # Guardado de antes → quitar y volver a guardar: así queda el PRIMERO de Favoritos
    if pulsar(r"^Guardado$"):
        time.sleep(1)
    guardado = False
    for _ in range(3):                    # a veces la página tarda en cargar (>10 s)
        if pulsar(r"^Guardar$"):
            guardado = True
            break
        time.sleep(4)
    if guardado:
        print("sonido guardado (primero en Favoritos)")
    else:
        print("AVISO: no encuentro «Guardar» en la página del sonido")
    captura()


def copiar_caption(c: dict) -> None:
    texto = c["caption"] + " " + " ".join(c.get("hashtags", []))
    if sin_combos():
        video_movil().al_portapapeles(texto)
        return
    (TMP / "sh" / "cap.txt").write_text(texto)
    adb("push", str(TMP / "sh" / "cap.txt"), "/data/local/tmp/cap.txt")
    adb("shell", 'am start -a android.intent.action.SEND -t text/plain -p com.google.android.keep '
                 '--es android.intent.extra.TEXT "$(cat /data/local/tmp/cap.txt)"')
    time.sleep(4)
    campo = buscar(re.escape(c["caption"][:20]))
    if not campo:
        raise SystemExit("Keep no ha abierto el texto")
    adb("shell", "input", "swipe", str(campo["x"]), str(campo["y"]), str(campo["x"]), str(campo["y"]), "900")
    time.sleep(1)
    tecla(113, 29)  # Ctrl+A
    tecla(113, 31)  # Ctrl+C
    tecla(113, 29)
    tecla(67)       # vaciar → Keep no guarda la nota
    tecla(4)
    tecla(4)
    adb("shell", "rm", "-f", "/data/local/tmp/cap.txt")


def editor(cid: str) -> None:
    c = json.loads((TMP / cid / "datos.json").read_text())
    n_fotos = len([p for p in (TMP / cid).iterdir() if p.suffix in (".jpg", ".jpeg", ".png")])
    copiar_caption(c)

    adb("shell", "am", "force-stop", PAQUETE)
    adb("shell", "monkey", "-p", PAQUETE, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(7)
    tap(*pt("mas"), 4)                     # «+»
    tap(*pt("galeria"), 3)                     # galería
    # Solo el álbum carr_tmp: en «Recientes» se cuelan capturas y vídeos más nuevos
    if not any(n["text"] == "carr_tmp" and n["y"] < pt("y_max_album") for n in nodos()):
        tap(*pt("album"), 2)                  # desplegable de álbumes
        if not pulsar(r"^carr_tmp$", 3):
            raise SystemExit("No encuentro el álbum carr_tmp")
    if not buscar(r"Siguiente", intentos=1):
        pulsar(r"Selección múltiple")     # activa los círculos
    for i in range(n_fotos):
        toque_foto(i)
    captura("1_seleccion")
    if not pulsar(rf"Siguiente \({n_fotos}\)", 5):
        raise SystemExit("No veo «Siguiente (N)»: revisa la selección")

    # Sonido desde Favoritos
    for _ in range(2):                    # a veces la fila no ha cargado y queda «Añadir sonido»
        tap(*pt("pildora_sonido"), 3)                  # píldora del sonido recomendado
        pulsar(r"^Favoritos$", 4)
        tap(*pt("fila_favorito"), 3)                 # primera fila = el último guardado (el dump no ve la lista)
        tap(*pt("cerrar_panel_sonido"), 2)                  # cierra el panel
        if not any(n["text"] == "Añadir sonido" and n["y"] < pt("y_max_sonido") for n in nodos()):
            break
    captura("2_sonido")
    pulsar(r"^Siguiente$", 4)

    # Caption
    pegar_caption()
    # A veces TikTok antepone un hashtag suyo (p. ej. del sonido): se borra lo que haya delante.
    inicio = c["caption"][:20]
    texto = next((html.unescape(n["text"]) for n in nodos()
                  if n["clase"].endswith("EditText") and inicio in html.unescape(n["text"])), "")
    sobra = texto.find(inicio)
    if sobra > 0:
        print(f"AVISO: TikTok añadió «{texto[:sobra].strip()}» delante del caption → borrado")
        al_principio()
        for _ in range(sobra):
            tecla(112)                    # Supr
    pulsar(r"^Listo$", 2)

    producto(cid)


def rapido(cid: str) -> None:
    """Vía rápida de Néstor (2/11): fotos al móvil → enlace del sonido → «Usar sonido» → galería → caption → producto.
    Sin ficha del escaparate ni Favoritos (~7 min frente a ~11). Si algo no cuadra, sale con error y el
    wrapper repite por la ruta normal (preparar + editor)."""
    (TMP / f"inicio_{cid}").write_text(str(time.time()))
    c = carrusel(cid)
    d = TMP / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "datos.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
    if not any(d.glob("0*")):
        bajar_fotos(c, d)
    pid = pid_de(c)
    if SIN_STOCK.exists() and pid in SIN_STOCK.read_text().split():
        raise SystemExit(f"{pid}: ya visto sin existencias → sin stock, saltar")
    if (TMP / f"escaparate_{pid}").exists() and not al_escaparate(pid):   # ya falló al buscarlo por ID
        print("AVISO: no vi «Añadir al escaparate» ni que ya estuviera (mira 6_ficha); sigo")
    locales = sorted(p for p in d.iterdir() if p.suffix in (".jpg", ".jpeg", ".png"))
    print(f"{c['titulo']!r}: {len(locales)} fotos · sonido {c['musica']['tiktok']['titulo']} (vía rápida)")
    adb("shell", "am", "force-stop", PAQUETE)
    limpiar()
    adb("shell", "mkdir", "-p", CARPETA_MOVIL)
    for p in locales:
        destino = f"{CARPETA_MOVIL}/{cid}_{p.name}"
        adb("push", str(p), destino)
        adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", f"file://{destino}")
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", c["musica"]["tiktok"]["enlace"], PAQUETE)
    time.sleep(7)
    for _ in range(3):                    # «Hubo un problema» al abrir en frío: «Volver a intentar»
        if pulsar(r"^Usar sonido$", 4):
            break
        pulsar(r"^Volver a intentar$", 5)
    else:
        captura("r_sonido")
        raise SystemExit("No veo «Usar sonido» (mira r_sonido)")
    time.sleep(3)
    tap(*pt("galeria"), 3)                     # galería (miniatura abajo a la izquierda)
    if not any(n["text"] == "carr_tmp" and n["y"] < pt("y_max_album") for n in nodos()):
        tap(*pt("album"), 2)
        if not pulsar(r"^carr_tmp$", 3):
            raise SystemExit("No encuentro el álbum carr_tmp")
    if not buscar(r"Siguiente", intentos=1):
        pulsar(r"Selección múltiple")
    for i in range(len(locales)):
        toque_foto(i)
    captura("1_seleccion")
    if not pulsar(rf"Siguiente \({len(locales)}\)", 5):
        raise SystemExit("No veo «Siguiente (N)»: revisa la selección")
    if not any("Sonido original" in n["text"] or n["desc"] == "Música" for n in nodos()):
        print("AVISO: no veo el sonido puesto en el editor")
    captura("2_sonido")
    copiar_caption(c)                     # Keep y vuelta: el editor sigue igual
    pulsar(r"^Siguiente$", 4)
    pegar_caption()
    inicio = c["caption"][:20]
    texto = next((html.unescape(n["text"]) for n in nodos()
                  if n["clase"].endswith("EditText") and inicio in html.unescape(n["text"])), "")
    if not texto:
        raise SystemExit("El caption no se pegó")
    sobra = texto.find(inicio)
    if sobra > 0:
        al_principio()
        for _ in range(sobra):
            tecla(112)
    pulsar(r"^Listo$", 2)
    producto(cid)


def al_editor() -> None:
    """Atrás desde publicar: a veces pasa por «Vista previa» (con «Editar fotos»)."""
    tap(*pt("atras"), 3)
    if pulsar(r"^Editar fotos$", 3):
        return


def abrir_enlace() -> None:
    """Fila «Añadir enlace»: el nodo con desc es un icono estrecho; se toca la fila entera."""
    n = next((n for n in nodos() if n["text"] == "Añadir enlace"), None)
    tap(pt("enlace_x"), n["y"] if n else pt("enlace_y_defecto"), 3)


def consulta_comercial(c: dict) -> str:
    """Qué buscar en «Sonidos comerciales»: el título si es una canción; si es un
    «original sound», el estilo de la música elegida para Meta (lofi, chill…)."""
    t = c["musica"]["tiktok"]
    if not re.search(r"original|sonido original", t["titulo"], re.I):
        return t["titulo"]
    estilo = (c["musica"].get("meta") or {}).get("estilo", "chill")
    return {"navidad": "christmas"}.get(estilo.split("_")[0], estilo.split("_")[0])


AVISO_COMISION = r"^\W*Entendido\W*$"   # «Protección de comisión de 30 días»: tapa la lista, una vez por cuenta y puede salir tarde


def producto(cid: str) -> None:
    """Desde la pantalla de publicar: producto por ID y, si el sonido no lo deja, uno comercial."""
    c = carrusel(cid)
    pid = pid_de(c)
    abrir_enlace()
    time.sleep(2)
    if buscar(r"sonido comercial", intentos=3):
        # El sonido del viral no deja producto: se quita, se pone el producto y se
        # buscan comerciales con su título. NO se elige a ciegas: lo decide Néstor.
        if not pulsar(r"^Cerrar$"):       # cierra «Añadir enlace» (su altura cambia)
            tap(*pt("cerrar_enlace"), 2)
        al_editor()
        x = next((n for n in nodos() if n["desc"] == "Cerrar" and n["y"] < pt("y_max_sonido")), None)
        tap(x["x"] if x else pt("x_pildora_x"), pt("pildora_sonido")[1], 2) # «x» de la píldora del sonido
        pulsar(r"^Siguiente$", 4)
        abrir_enlace()
        _comercial = True
    else:
        _comercial = False
    pulsar(r"^Producto$", 5)
    pulsar(AVISO_COMISION, 2)
    pulsar(r"Buscar productos", 2)
    escribir(pid)
    tecla(66)
    time.sleep(4)
    captura("3_producto")
    for intento in range(4):              # a veces el buscador no lo encuentra a la primera: se repite
        if not sin_resultados():
            break
        print(f"AVISO: «No se han encontrado productos», repito la búsqueda ({intento + 1})", flush=True)
        time.sleep(3 + 3 * intento)
        pulsar(AVISO_COMISION, 2)
        pulsar(r"Buscar productos|^\d{10,}$", 1)
        vaciar_texto()
        escribir(pid)
        tecla(66)
        time.sleep(6)
    captura("3_producto")
    if re.search(r"Sin existencias|Existencias: ?0\b", texto_pantalla()):
        sin_stock(pid, "«Sin existencias» en el escaparate (3_producto)")
    if sin_resultados():
        (TMP / f"escaparate_{pid}").write_text("1")   # el reintento de preparar abrirá la ficha y lo añadirá
        raise SystemExit(f"{pid} no sale al buscarlo: no está en el escaparate (mira 6_ficha de preparar)")
    campo = []
    # «Añadir» del único resultado: en el Mi 8 sale en el volcado; en el OPPO no, y su altura cambia
    puntos = [(b["x"], b["y"]) for b in botones_anadir()[:1]] or [(pt("anadir_x"), y) for y in pt("anadir_ys")]
    for x, y in puntos:
        tap(x, y, 4)
        if buscar(r"Obtener una muestra", intentos=1):
            tecla(4)                      # se pulsó la tarjeta, no «Añadir»
            time.sleep(2)
            continue
        campo = [n for n in nodos() if n["desc"] == "edit_anchor_name_input"]
        if not campo:                     # a veces «¿Añadir producto al vídeo?» (el dump no lo ve)
            tap(*pt("confirmar_producto"), 4)
            campo = [n for n in nodos() if n["desc"] == "edit_anchor_name_input"]
        if campo:
            break
    if not campo:
        captura("3_sin_campo")            # 6/11: este texto NO puede decir «sin stock»: subir_prebf lo tomaba por agotado y saltaba sin probar la ruta normal
        raise SystemExit("No se abrió «Cambiar nombre»: ¿«No disponible» (mira 3_sin_campo), sin ese ID o el sonido lo impide?")
    if campo:
        nombre = nombre_enlace(c)
        for _ in range(3):                # Gboard a veces cambia letras («Fruti»): se comprueba y se reescribe
            tap(campo[0]["x"], campo[0]["y"], 1)
            vaciar_texto()
            escribir(nombre)
            time.sleep(2)
            if any(n["desc"] == "edit_anchor_name_input" and n["text"] == nombre for n in nodos()):
                break
            print("AVISO: el nombre del enlace no salió bien, lo reescribo")
        tecla(4 if perfil().get("lista_en_dump") else 111)   # oculta el teclado (en el Mi 8 ESC no lo cierra)
    if not pulsar(r"^\W*Añadir\W*$", 4):
        tap(*pt("anadir_abajo"), 4)
    if _comercial:
        al_editor()
        tap(*pt("pildora_sonido"), 4)                  # con producto solo salen «Sonidos comerciales»
        escribir(consulta_comercial(c))
        time.sleep(3)
        tap(*pt("sugerencia"), 8)                  # primera sugerencia: con Enter a veces no hay resultados
        for _ in range(2):                # a veces sale «No se encontraron resultados»: repetir desde el historial
            if not buscar(r"No se encontraron", intentos=1):
                break
            tap(*pt("vaciar"), 2)             # vaciar
            tecla(4)                      # oculta teclado → se ve el historial
            time.sleep(2)
            tap(*pt("historial"), 8)              # primera búsqueda del historial (la misma)
        # lista vacía sin aviso (no sale en el volcado): «Buscar» y, si nada, otras consultas del estilo
        hay = lambda: re.search(r"[A-Za-z]{3,}", texto_zona(*pt("zona_comerciales")))  # noqa: E731
        for q in [None, "slowed", "trending", "pop"]:
            if hay():
                break
            print(f"AVISO: sin sonidos comerciales; pruebo {q or '«Buscar»'}", flush=True)
            if q:
                tap(*pt("vaciar"), 2)         # vaciar
                escribir(q)
            tap(*pt("buscar_comercial"), 8)             # «Buscar» (la lista queda por encima del teclado)
        captura("5_comerciales")
        tap(*pt("check_comercial"), 4)                 # check del primero: el más parecido
        captura("5_comercial")
        pulsar(r"^Siguiente$", 4)
    captura("4_final")
    print("Listo para revisar antes de Publicar")


def publicar(cid: str) -> None:
    # Publicar se pulsa UNA sola vez (repetir = duplicado). Si no se ve (ADB caído a mitad), reconecta y mira otra vez.
    n = buscar(r"^Publicar$")
    if not n:
        reconectar(); time.sleep(3)
        n = buscar(r"^Publicar$")
    if not n:
        captura()
        raise SystemExit("No veo el botón Publicar")
    try:   # sin reintento: si este toque se repitiera, publicaría dos veces
        subprocess.run(["adb", "-s", SERIAL, "shell", "input", "tap", str(n["x"]), str(n["y"])], capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        print("AVISO: el toque de Publicar se colgó; NO se repite (mira la cuenta)")
    time.sleep(10)
    r = mcp("marcar_tanda", {"id": cid, "subido": True, "fotos": True})
    print("subido en la app:", r.get("subido"))
    ini = TMP / f"inicio_{cid}"
    if ini.exists():
        mins = (time.time() - float(ini.read_text())) / 60
        print(f"tiempo total: {mins:.1f} min")
        with open(TMP / "tiempos.txt", "a") as f:
            f.write(f"{cid} {mins:.1f}\n")
    captura()


def limpiar() -> None:
    lista = adb("shell", "ls", CARPETA_MOVIL).split()
    for f in lista:
        ruta = f"{CARPETA_MOVIL}/{f}"
        adb("shell", "rm", "-f", ruta)
        adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{ruta}")


if __name__ == "__main__":
    (TMP / "sh").mkdir(parents=True, exist_ok=True)
    fase, *resto = sys.argv[1:]
    {"lote": lote, "rapido": rapido, "preparar": preparar, "editor": editor, "producto": producto, "publicar": publicar, "limpiar": limpiar}[fase](*resto)
