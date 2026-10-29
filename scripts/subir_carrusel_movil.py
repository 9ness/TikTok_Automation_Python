"""Sube un carrusel de Mis tandas (fotos) a TikTok desde un móvil por ADB y se para antes de Publicar.

Probado el 26/10/2026 en el OPPO de Néstor (1440x3168, TikTok ES). Fases:

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
TMP = Path("/tmp/carr")
CARPETA_MOVIL = "/sdcard/Pictures/carr_tmp"
MCP_URLS = Path(__file__).resolve().parent.parent / "MCP_URLS.local.md"
USUARIO = os.environ.get("MCP_USUARIO", "ness")


# ---------------------------------------------------------------- adb básico
def adb(*args: str, timeout: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout


def tap(x: int, y: int, espera: float = 1.5) -> None:
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(espera)


def tecla(*codigos: int) -> None:
    if len(codigos) == 1:
        adb("shell", "input", "keyevent", str(codigos[0]))
    else:
        adb("shell", "input", "keycombination", *map(str, codigos))
    time.sleep(0.5)


def escribir(texto: str) -> None:
    """Carácter a carácter: con Gboard, `input text` de golpe se come letras."""
    for c in texto:
        if c == " ":
            adb("shell", "input", "keyevent", "62")
        else:
            adb("shell", "input", "text", c if c.isalnum() else f"'{c}'")


def nodos() -> list[dict]:
    adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    xml = adb("shell", "cat", "/sdcard/u.xml")
    adb("shell", "rm", "-f", "/sdcard/u.xml")
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

    png = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"], capture_output=True).stdout
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.resize((im.width // 3, im.height // 3)).save(TMP / "sh" / f"{nombre}.jpg", quality=80)
    print(f"captura: {TMP / 'sh' / (nombre + '.jpg')}")


# ---------------------------------------------------------------- datos de la app
def mcp(herramienta: str, argumentos: dict) -> dict:
    url = re.search(rf"^- {USUARIO}: (\S+)", MCP_URLS.read_text(), re.M).group(1)
    cuerpo = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": herramienta, "arguments": argumentos}}
    req = urllib.request.Request(url, json.dumps(cuerpo).encode(), {
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    texto = r["result"]["content"][0]["text"]
    if r["result"].get("isError"):
        raise SystemExit(f"MCP {herramienta}: {texto}")
    return json.loads(texto)


CACHE = TMP / "tandas.json"


def carrusel(cid: str) -> dict:
    """De la caché del lote si existe (una sola llamada al MCP para todos)."""
    if CACHE.exists():
        datos = json.loads(CACHE.read_text())
    else:
        datos = mcp("mis_tandas", {"fotos": True})
    for t in datos["tandas"]:
        for c in t.get("items", t.get("carruseles", [])):
            if c.get("id") == cid:
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


def al_escaparate(pid: str) -> bool:
    """Abre la ficha en TikTok y pulsa «Añadir al escaparate». True si lo añadió o ya estaba."""
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", f"https://www.tiktok.com/view/product/{pid}", PAQUETE)
    time.sleep(8)
    captura("6_ficha")
    if buscar(r"(se ha eliminado|Producto no disponible)", intentos=1):
        raise SystemExit(f"{pid}: la ficha dice «eliminado/no disponible» (6_ficha) → sin stock, saltar")
    if buscar(r"(Añadido al escaparate|En el escaparate|Quitar del escaparate)", intentos=1):
        return True
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
        d = TMP / c["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "datos.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
        if not any(d.glob("0*")):
            bajar_fotos(c, d)
        pid = pid_de(c)
        return f"{c['id']} · {len(list(d.glob('0*')))} fotos · {pid} · {c['musica']['tiktok']['titulo']} · {' '.join(c['titulo'].split())}"

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
    # Fuera del escaparate el producto no sale al buscarlo por ID: se añade antes de abrir el editor.
    if not al_escaparate(pid_de(c)):
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
    adb("shell", "input", "swipe", "720", "900", "720", "2800", "300")  # a veces abre a media página
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
    tap(720, 3024, 4)                     # «+»
    tap(141, 2991, 3)                     # galería
    # Solo el álbum carr_tmp: en «Recientes» se cuelan capturas y vídeos más nuevos
    if not any(n["text"] == "carr_tmp" and n["y"] < 400 for n in nodos()):
        tap(688, 243, 2)                  # desplegable de álbumes
        if not pulsar(r"^carr_tmp$", 3):
            raise SystemExit("No encuentro el álbum carr_tmp")
    if not buscar(r"Siguiente", intentos=1):
        pulsar(r"Selección múltiple")     # activa los círculos
    for i in range(n_fotos):              # rejilla 3 columnas; lo más nuevo arriba
        fila, col = divmod(i, 3)
        tap(417 + 477 * col, 552 + 483 * fila, 1)
    captura("1_seleccion")
    if not pulsar(rf"Siguiente \({n_fotos}\)", 5):
        raise SystemExit("No veo «Siguiente (N)»: revisa la selección")

    # Sonido desde Favoritos
    for _ in range(2):                    # a veces la fila no ha cargado y queda «Añadir sonido»
        tap(660, 372, 3)                  # píldora del sonido recomendado
        pulsar(r"^Favoritos$", 4)
        tap(600, 1845, 3)                 # primera fila = el último guardado (el dump no ve la lista)
        tap(720, 750, 2)                  # cierra el panel
        if not any(n["text"] == "Añadir sonido" and n["y"] < 500 for n in nodos()):
            break
    captura("2_sonido")
    pulsar(r"^Siguiente$", 4)

    # Caption
    tap(700, 980, 2)
    tecla(113, 50)                        # Ctrl+V
    time.sleep(1)
    # A veces TikTok antepone un hashtag suyo (p. ej. del sonido): se borra lo que haya delante.
    inicio = c["caption"][:20]
    texto = next((html.unescape(n["text"]) for n in nodos()
                  if n["clase"].endswith("EditText") and inicio in html.unescape(n["text"])), "")
    sobra = texto.find(inicio)
    if sobra > 0:
        print(f"AVISO: TikTok añadió «{texto[:sobra].strip()}» delante del caption → borrado")
        tecla(113, 122)                   # Ctrl+Inicio
        for _ in range(sobra):
            tecla(112)                    # Supr
    pulsar(r"^Listo$", 2)

    producto(cid)


def al_editor() -> None:
    """Atrás desde publicar: a veces pasa por «Vista previa» (con «Editar fotos»)."""
    tap(96, 237, 3)
    if pulsar(r"^Editar fotos$", 3):
        return


def abrir_enlace() -> None:
    """Fila «Añadir enlace»: el nodo con desc es un icono estrecho; se toca la fila entera."""
    n = next((n for n in nodos() if n["text"] == "Añadir enlace"), None)
    tap(720, n["y"] if n else 2116, 3)


def consulta_comercial(c: dict) -> str:
    """Qué buscar en «Sonidos comerciales»: el título si es una canción; si es un
    «original sound», el estilo de la música elegida para Meta (lofi, chill…)."""
    t = c["musica"]["tiktok"]
    if not re.search(r"original|sonido original", t["titulo"], re.I):
        return t["titulo"]
    estilo = (c["musica"].get("meta") or {}).get("estilo", "chill")
    return {"navidad": "christmas"}.get(estilo.split("_")[0], estilo.split("_")[0])


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
            tap(1341, 2226, 2)
        al_editor()
        x = next((n for n in nodos() if n["desc"] == "Cerrar" and n["y"] < 500), None)
        tap(x["x"] if x else 906, 372, 2) # «x» de la píldora del sonido
        pulsar(r"^Siguiente$", 4)
        abrir_enlace()
        _comercial = True
    else:
        _comercial = False
    pulsar(r"^Producto$", 5)
    pulsar(r"Buscar productos", 2)
    escribir(pid)
    tecla(66)
    time.sleep(4)
    captura("3_producto")
    if buscar(r"No se han encontrado", intentos=1):
        raise SystemExit(f"{pid} no sale al buscarlo: no está en el escaparate (mira 6_ficha de preparar)")
    campo = []
    for y in (840, 1044):                 # «Añadir» del único resultado: su altura cambia (la lista no sale en el dump)
        tap(1188, y, 4)
        if buscar(r"Obtener una muestra", intentos=1):
            tecla(4)                      # se pulsó la tarjeta, no «Añadir»
            time.sleep(2)
            continue
        campo = [n for n in nodos() if n["desc"] == "edit_anchor_name_input"]
        if not campo:                     # a veces «¿Añadir producto al vídeo?» (el dump no lo ve)
            tap(720, 1698, 4)
            campo = [n for n in nodos() if n["desc"] == "edit_anchor_name_input"]
        if campo:
            break
    if not campo:
        raise SystemExit("No se abrió «Cambiar nombre»: ¿producto sin stock («No disponible», mira 3_producto), sin ese ID o el sonido lo impide?")
    if campo:
        nombre = nombre_enlace(c)
        for _ in range(3):                # Gboard a veces cambia letras («Fruti»): se comprueba y se reescribe
            tap(campo[0]["x"], campo[0]["y"], 1)
            tecla(113, 29)
            tecla(67)
            escribir(nombre)
            time.sleep(2)
            if any(n["desc"] == "edit_anchor_name_input" and n["text"] == nombre for n in nodos()):
                break
            print("AVISO: el nombre del enlace no salió bien, lo reescribo")
        tecla(111)                        # oculta el teclado
    if not pulsar(r"^Añadir$", 4):
        tap(720, 2970, 4)
    if _comercial:
        al_editor()
        tap(660, 372, 4)                  # con producto solo salen «Sonidos comerciales»
        escribir(consulta_comercial(c))
        time.sleep(3)
        tap(723, 578, 8)                  # primera sugerencia: con Enter a veces no hay resultados
        for _ in range(2):                # a veces sale «No se encontraron resultados»: repetir desde el historial
            if not buscar(r"No se encontraron", intentos=1):
                break
            tap(1188, 405, 2)             # vaciar
            tecla(4)                      # oculta teclado → se ve el historial
            time.sleep(2)
            tap(340, 759, 8)              # primera búsqueda del historial (la misma)
        captura("5_comerciales")
        tap(1278, 640, 4)                 # check del primero: el más parecido
        captura("5_comercial")
        pulsar(r"^Siguiente$", 4)
    captura("4_final")
    print("Listo para revisar antes de Publicar")


def publicar(cid: str) -> None:
    if not pulsar(r"^Publicar$", 10):
        raise SystemExit("No veo el botón Publicar")
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
    {"lote": lote, "preparar": preparar, "editor": editor, "producto": producto, "publicar": publicar, "limpiar": limpiar}[fase](*resto)
