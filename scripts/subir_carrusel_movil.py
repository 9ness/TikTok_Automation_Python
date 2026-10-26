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
"""

from __future__ import annotations

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

SERIAL = os.environ.get("MOVIL_ADB", "100.123.211.22:39195")
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
            "text": re.search(r'text="([^"]*)"', n).group(1),
            "desc": re.search(r'content-desc="([^"]*)"', n).group(1),
            "clase": re.search(r'class="([^"]*)"', n).group(1),
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


def carrusel(cid: str) -> dict:
    datos = mcp("mis_tandas", {"fotos": True})
    for t in datos["tandas"]:
        for c in t.get("items", t.get("carruseles", [])):
            if c.get("id") == cid:
                return c
    raise SystemExit(f"No encuentro el carrusel {cid} en Mis tandas")


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


# ---------------------------------------------------------------- fases
def preparar(cid: str) -> None:
    (TMP / f"inicio_{cid}").write_text(str(time.time()))
    c = carrusel(cid)
    d = TMP / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "datos.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
    zipdata = urllib.request.urlopen(c["zip"], timeout=400).read()
    with zipfile.ZipFile(io.BytesIO(zipdata)) as z:
        fotos = sorted(n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png")))
        for i, n in enumerate(fotos, 1):
            (d / f"{i:02d}{Path(n).suffix.lower()}").write_bytes(z.read(n))
    locales = sorted(p for p in d.iterdir() if p.suffix in (".jpg", ".jpeg", ".png"))
    print(f"{c['titulo']!r}: {len(locales)} fotos · sonido {c['musica']['tiktok']['titulo']}")

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
    # Guardado de antes → quitar y volver a guardar: así queda el PRIMERO de Favoritos
    if pulsar(r"^Guardado$"):
        time.sleep(1)
    if pulsar(r"^Guardar$"):
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
    if not buscar(r"Siguiente", intentos=1):
        pulsar(r"Selección múltiple")     # activa los círculos
    for i in range(n_fotos):              # rejilla 3 columnas; lo más nuevo arriba
        fila, col = divmod(i, 3)
        tap(417 + 477 * col, 552 + 483 * fila, 1)
    captura("1_seleccion")
    if not pulsar(rf"Siguiente \({n_fotos}\)", 5):
        raise SystemExit("No veo «Siguiente (N)»: revisa la selección")

    # Sonido desde Favoritos
    tap(660, 372, 3)                      # píldora del sonido recomendado
    pulsar(r"^Favoritos$", 3)
    tap(600, 1845, 3)                     # primera fila = el último guardado (el dump no ve la lista)
    tap(720, 750, 2)                      # cierra el panel
    captura("2_sonido")
    pulsar(r"^Siguiente$", 4)

    # Caption
    tap(700, 980, 2)
    tecla(113, 50)                        # Ctrl+V
    time.sleep(1)
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
    pid = c["product_url"].rstrip("/").split("/")[-1]
    abrir_enlace()
    if buscar(r"sonido comercial", intentos=2):
        # El sonido del viral no deja producto: se quita, se pone el producto y se
        # buscan comerciales con su título. NO se elige a ciegas: lo decide Néstor.
        tap(1341, 2226, 2)                # cierra «Añadir enlace»
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
    tap(1188, 840, 4)                     # «Añadir» del único resultado (la lista no sale en el dump)
    campo = [n for n in nodos() if n["desc"] == "edit_anchor_name_input"]
    if not campo:
        raise SystemExit("No se abrió «Cambiar nombre»: ¿sin producto con ese ID o el sonido lo impide?")
    if campo:
        tap(campo[0]["x"], campo[0]["y"], 1)
        tecla(113, 29)
        tecla(67)
        escribir(nombre_enlace(c))
        time.sleep(2)
        tecla(111)                        # oculta el teclado
    if not pulsar(r"^Añadir$", 4):
        tap(720, 2970, 4)
    if _comercial:
        al_editor()
        tap(660, 372, 4)                  # con producto solo salen «Sonidos comerciales»
        escribir(consulta_comercial(c))
        tecla(66)
        time.sleep(5)
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
    {"preparar": preparar, "editor": editor, "producto": producto, "publicar": publicar, "limpiar": limpiar}[fase](*resto)
