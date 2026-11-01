"""Sube un vídeo de Hmizat (cuenta árabe, Mi 8) a TikTok por ADB, con producto enlazado.

Lee el SUBIDA.json de la ronda (lista de {numero, archivo, product_id, nombre_enlace,
caption, sonido, voz}) que deja la producción en /mnt/.../trabajo/hmizat_rondaN/.

    python scripts/subir_video_movil.py todo <ronda_dir> <N> [--sin-publicar]
    python scripts/subir_video_movil.py preparar <ronda_dir> <N>    # copia el vídeo a la galería
    python scripts/subir_video_movil.py editor <ronda_dir> <N>      # vídeo → sonido → caption → producto
    python scripts/subir_video_movil.py publicar <ronda_dir> <N>    # «Comprobar contenido» → Publicar
    python scripts/subir_video_movil.py limpiar
    python scripts/subir_video_movil.py programar <ronda_dir> <AAAA-MM-DD> HH:MM [HH:MM ...]
        # una tarea `at` por vídeo (en orden); cada una lanza `todo` y apunta en SUBIDAS.log

Casuística del Mi 8 (1080x2248, Android 10, TikTok ES, @hmizat.spain):
- Sin `input keycombination`: el árabe (caption y nombre del enlace) se comparte a Keep,
  se copia con pulsación larga → «Seleccionar todo» → «Copiar», y se pega con el chip del
  portapapeles de Gboard (la barra de sugerencias sigue activa por eso).
- Sonido «Suns» (Official Sound Studio) ANTES del producto: con producto puesto el
  selector solo enseña «Sonidos comerciales». Los vídeos con voz (`voz.si`) van con su audio.
- Sin la etiqueta «Contenido generado por IA» (Néstor, 29/10).
- «Comprobar contenido» antes de publicar (hasta 10 al día; evita infracciones).
- Prohibido «Crear ahora» y «Retirar».
- Al acabar: rm /sdcard/u.xml, HOME y bloquear (lo hace `todo` también si falla).
Coordenadas marcadas con CAL: las listas de TikTok no salen en el dump; se calibraron a mano.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

SERIAL = os.environ.get("MOVIL_ADB", "100.115.12.26:5555")
PAQUETE = "com.zhiliaoapp.musically"
KEEP = "com.google.android.keep"
TMP = Path("/tmp/subir_video")
CARPETA_MOVIL = "/sdcard/DCIM/Hmizat"
SONIDO = "https://www.tiktok.com/music/Suns-6696371042123778818"
BUSCAR_SONIDO = (968, 280)  # CAL: «Buscar» a la derecha de la caja de búsqueda de sonidos
MADRID = ZoneInfo("Europe/Madrid")


# ---------------------------------------------------------------- adb básico
def adb(*args: str, timeout: int = 120) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True,
                       timeout=timeout, stdin=subprocess.DEVNULL)
    return r.stdout


def tap(x: int, y: int, espera: float = 1.5) -> None:
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(espera)


def tecla(codigo: int | str, espera: float = 0.6) -> None:
    adb("shell", "input", "keyevent", str(codigo))
    time.sleep(espera)


def escribir(texto: str) -> None:
    """Solo ASCII (los IDs). Carácter a carácter: con Gboard, de golpe se come letras."""
    for c in texto:
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
        g = lambda k: (re.search(rf' {k}="([^"]*)"', n) or re.match("()", "")).group(1)  # noqa: E731
        out.append({"text": g("text"), "desc": g("content-desc"), "clase": g("class"),
                    "id": g("resource-id"), "checked": g("checked") == "true", "x": (x1 + x2) // 2, "y": (y1 + y2) // 2,
                    "y1": y1, "y2": y2, "x1": x1, "x2": x2})
    return out


def buscar(patron: str, intentos: int = 4, pausa: float = 1.5) -> dict | None:
    for _ in range(intentos):
        for n in nodos():
            if re.search(patron, n["text"], re.I) or re.search(patron, n["desc"], re.I):
                return n
        time.sleep(pausa)
    return None


def pulsar(patron: str, espera: float = 2.0, intentos: int = 4) -> bool:
    n = buscar(patron, intentos)
    if n:
        tap(n["x"], n["y"], espera)
    return bool(n)


def captura(nombre: str = "s") -> None:
    from PIL import Image

    png = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                         capture_output=True, stdin=subprocess.DEVNULL).stdout
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.resize((im.width // 2, im.height // 2)).save(TMP / "sh" / f"{nombre}.jpg", quality=80)
    print(f"captura: {TMP / 'sh' / (nombre + '.jpg')}")


def ocr(patron: str, zona: tuple[int, int, int, int] | None = None) -> tuple[int, int] | None:
    """Busca un texto en pantalla con tesseract (menús flotantes y listas que no salen en el
    volcado). Devuelve el centro en coordenadas reales del Mi 8, o None."""
    png = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                         capture_output=True, stdin=subprocess.DEVNULL).stdout
    f = TMP / "sh" / "ocr.png"
    f.write_bytes(png)
    tsv = subprocess.run(["tesseract", str(f), "-", "-l", "spa", "--psm", "11", "tsv"],
                         capture_output=True, text=True).stdout
    filas = [r.split("\t") for r in tsv.splitlines()[1:]]
    pal = [(r[11], int(r[6]), int(r[7]), int(r[8]), int(r[9])) for r in filas if len(r) == 12 and r[11].strip()]
    # une palabras vecinas de la misma línea para buscar frases («Seleccionar todo»)
    for i, (t, x, y, w, h) in enumerate(pal):
        frase, x2 = t, x + w
        for t2, xx, yy, ww, hh in pal[i + 1:i + 4]:
            if abs(yy - y) > 15:
                break
            frase, x2 = f"{frase} {t2}", xx + ww
            if re.search(patron, frase, re.I):
                break
        for cand, fin in ((t, x + w), (frase, x2)):
            if re.search(patron, cand, re.I):
                cx, cy = (x + fin) // 2, y + h // 2
                if zona and not (zona[0] <= cx <= zona[2] and zona[1] <= cy <= zona[3]):
                    continue
                return cx, cy
    return None


def despierto() -> bool:
    return "mWakefulness=Awake" in adb("shell", "dumpsys power | grep mWakefulness=")


def despertar() -> None:
    """Con la pantalla en AOD (Dozing) WAKEUP a veces no basta: se comprueba y se insiste."""
    adb("shell", "svc", "power", "stayon", "true")
    for _ in range(3):
        tecla("KEYCODE_WAKEUP", 1.5)
        if despierto():
            break
        tecla("KEYCODE_POWER", 1.5)
        if despierto():
            break
    else:
        raise SystemExit("El Mi 8 no se despierta")
    adb("shell", "wm", "dismiss-keyguard")
    time.sleep(1)
    if "isStatusBarKeyguard=true" in adb("shell", "dumpsys window | grep isStatusBarKeyguard"):
        adb("shell", "input", "swipe", "540", "1900", "540", "600", "300")
        time.sleep(2)
    sin_guia_proximidad()


def sin_guia_proximidad() -> None:
    """«No cubrir la zona del auricular» (algo tapa el sensor): VOLUME_UP y EN SEGUIDA VOLUME_DOWN
    (autorizado por Néstor; nunca VOLUME_UP suelto). No sale en el volcado: OCR."""
    for _ in range(3):
        if not ocr(r"cubrir la zona|zona del auricular"):
            return
        adb("shell", "input keyevent KEYCODE_VOLUME_UP && input keyevent KEYCODE_VOLUME_DOWN")
        time.sleep(2)
    raise SystemExit("Sigue la guía del sensor de proximidad: ¿algo tapa la parte de arriba del Mi 8?")


def dormir() -> None:
    adb("shell", "rm", "-f", "/sdcard/u.xml")
    adb("shell", "svc", "power", "stayon", "false")
    tecla("KEYCODE_HOME", 1)
    tecla("KEYCODE_SLEEP")


# ---------------------------------------------------------------- datos
def item(ronda: str, n: str | int) -> dict:
    for x in json.loads((Path(ronda) / "SUBIDA.json").read_text()):
        if int(x["numero"]) == int(n):
            return x
    raise SystemExit(f"No hay vídeo {n} en {ronda}/SUBIDA.json")


def nombre_movil(it: dict) -> str:
    return f"hz_{Path(it['archivo']).name}"


# ---------------------------------------------------------------- árabe por Keep
def al_portapapeles(texto: str) -> None:
    """Keep recibe el texto compartido; con el teclado ya abierto (la ventana sube), pulsación
    larga SOBRE una palabra → «Seleccionar todo» → «Cortar» (deja la nota vacía y Keep no la
    guarda). El menú flotante no sale en el volcado: se busca con OCR. Pulsar detrás de la
    última letra da otro menú (Seleccionar/Pegar…) cuyos toques se cuelan: por eso la palabra."""
    (TMP / "sh" / "t.txt").write_text(texto)
    adb("push", str(TMP / "sh" / "t.txt"), "/data/local/tmp/t.txt")
    adb("shell", f'am start -a android.intent.action.SEND -t text/plain -p {KEEP} '
                 '--es android.intent.extra.TEXT "$(cat /data/local/tmp/t.txt)"')
    time.sleep(4)
    clave = (re.search(r"\w{3,}", texto) or re.search(r".+", texto)).group(0)   # sin emojis: el volcado los cambia
    cuerpo = lambda: next((n for n in nodos() if n["clase"].endswith("EditText") and clave in n["text"]), None)  # noqa: E731
    c = cuerpo()
    if not c:
        raise SystemExit("Keep no ha abierto el texto")
    tap(c["x"], c["y"], 2.5)              # abre el teclado: la ventana sube
    c = cuerpo()
    # Keep alinea según el primer carácter con dirección: árabe → la primera palabra queda
    # pegada al borde derecho; latín (#tiktokshop…) → al izquierdo.
    primero = next((ch for ch in texto if ch.isalpha()), "a")
    arabe = "\u0600" <= primero <= "\u06ff"
    for intento in range(3):
        x = c["x2"] - 100 - 40 * intento if arabe else c["x1"] + 120 + 40 * intento
        adb("shell", "input", "swipe", str(x), str(c["y"]), str(x), str(c["y"]), "1000")
        time.sleep(1.3)
        p = ocr(r"Seleccionar todo")
        if p and not ocr(r"^Autocompletar$"):
            break
        tap(c["x"], c["y"], 1)            # quita el menú equivocado (ESC cerraría Keep)
    else:
        captura("keep_menu")
        raise SystemExit("Keep: no sale el menú de selección (keep_menu)")
    tap(*p, 1.2)
    p = ocr(r"^Cortar$")
    if not p:
        captura("keep_cortar")
        raise SystemExit("Keep: no veo «Cortar» (keep_cortar)")
    tap(*p, 1.2)
    if cuerpo():
        raise SystemExit("Keep: el texto no se ha cortado")
    tecla(4, 1)                           # teclado
    tecla(4, 2)                           # cierra Keep (nota vacía: no se guarda)
    adb("shell", "rm", "-f", "/data/local/tmp/t.txt")


def pegar() -> None:
    """Chip del portapapeles de Gboard (centro de la barra de sugerencias)."""
    time.sleep(1)
    tap(*CHIP_PORTAPAPELES, 1.5)


CHIP_PORTAPAPELES = (540, 1476)           # con el teclado abierto


# ---------------------------------------------------------------- fases
def preparar(ronda: str, n: str) -> None:
    it = item(ronda, n)
    src = Path(ronda) / it["archivo"]
    limpiar()
    adb("shell", "mkdir", "-p", CARPETA_MOVIL)
    destino = f"{CARPETA_MOVIL}/{nombre_movil(it)}"
    adb("push", str(src), destino, timeout=300)
    adb("shell", "touch", destino)        # push conserva la fecha original: sin esto no sale el primero
    adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d", f"file://{destino}")
    time.sleep(3)
    print(f"{it['numero']:02d} {src.name} → {destino}")


def abrir_tiktok() -> None:
    """`monkey` no lo deja delante: se abre la actividad. Permiso de cámara la primera vez."""
    adb("shell", "am", "force-stop", PAQUETE)
    adb("shell", "am", "start", "-n", f"{PAQUETE}/com.ss.android.ugc.aweme.splash.SplashActivity")
    time.sleep(10)
    sin_guia_proximidad()
    pulsar(r"^PERMITIR$", 2, 1)


def editor(ronda: str, n: str) -> None:
    it = item(ronda, n)
    despertar()
    abrir_tiktok()
    tap(*MAS, 5)                          # «+» → cámara
    pulsar(r"^PERMITIR$", 2, 1)
    if not buscar(r"^CÁMARA$", 3):
        captura("1_camara")
        raise SystemExit("No se abrió la cámara (1_camara)")
    tap(*GALERIA, 4)                      # miniatura de la galería, abajo a la izquierda
    if not buscar(r"^Selección múltiple$", 3):
        raise SystemExit("No se abrió la galería")
    tap(*PRIMERA_MINIATURA, 2)            # círculo del vídeo más nuevo (el que se acaba de copiar)
    captura("1_video")
    if not pulsar(r"^Siguiente \(1\)$", 6):
        raise SystemExit("No veo «Siguiente (1)» tras elegir el vídeo (1_video)")
    if not buscar(r"^Siguiente$", 4):
        raise SystemExit("No se abrió el editor")

    if not it.get("voz", {}).get("si"):
        poner_sonido(it.get("sonido") or {})
    else:
        # TikTok pega solo un sonido sugerido; si no es comercial, «Producto» sale desactivado
        # («Usa un sonido comercial…», 31/10) y además taparía la voz: se quita con su X
        pulsar(r"^Cerrar$", 3, 2)
        if not buscar(r"^Añadir sonido$", 2):
            captura("2_sonido")
            raise SystemExit("No consigo quitar el sonido sugerido (2_sonido)")
    captura("2_sonido")
    if not pulsar(r"^Siguiente$", 6):
        raise SystemExit("No veo «Siguiente» en el editor (2_sonido)")
    if not buscar(r"^Publicar$", 4):
        raise SystemExit("No se abrió la pantalla de publicar")

    if it["caption"].strip():
        al_portapapeles(it["caption"])
        campo = next((x for x in nodos() if x["clase"].endswith("EditText")), None)
        tap(campo["x"], campo["y"], 2) if campo else tap(*CAPTION, 2)
        pegar()
        tecla(62, 1)                      # espacio: cierra la lista de hashtags sugeridos
        tecla(4, 1.5)                     # oculta el teclado
        campo = next((x for x in nodos() if x["clase"].endswith("EditText")), None)
        if not campo or re.search(r"\w{3,}", it["caption"]).group(0) not in campo["text"]:
            captura("3_caption")
            raise SystemExit("El caption no se ha pegado (3_caption)")
    captura("3_caption")

    producto(it)
    sin_etiqueta_ia()
    captura("5_final")
    print("Listo para publicar (5_final)")


def _sonido(fila: str, busqueda: str = "Suns", sugerencia: str = r"^Suns Official Sound Studio$",
            comprobar: str = r"^Sun") -> None:
    """Píldora del sonido (TikTok pone uno sugerido) → lupa → `busqueda` → la sugerencia
    `sugerencia` (o Intro si no hay) → la fila que diga `fila` (OCR: la lista no sale en el volcado)."""
    tap(*PILDORA_SONIDO, 4)
    tap(*LUPA_SONIDO, 3)
    escribir(" " + busqueda)              # el primer carácter a veces se pierde
    time.sleep(3)
    if sugerencia:
        if not pulsar(sugerencia, 6, 3):
            raise SystemExit(f"No sale la sugerencia {sugerencia!r}")
    else:
        tap(*BUSCAR_SONIDO, 6)            # «Buscar» (Intro no busca)
    p = None
    for _ in range(3):
        p = ocr(fila, (0, 900, 1080, 2150))
        if p:
            break
        time.sleep(2)
    if not p:
        captura("2_buscar_sonido")
        raise SystemExit(f"No veo la fila {fila!r} (2_buscar_sonido)")
    tap(CHECK_SONIDO_X, p[1] - 60, 5)
    tap(540, 600, 3)                      # toca el vídeo: cierra el panel
    for _ in range(2):
        if buscar(comprobar, 3):
            return
        tap(540, 600, 3)                  # a veces el primer toque no cierra el panel
    captura("2_editor")
    raise SystemExit("El editor no muestra el sonido (2_editor)")


def al_editor_video() -> None:
    """Vuelve al editor (el botón «Siguiente» a la vista) sin pasarse: un atrás de más descarta."""
    for _ in range(4):
        if buscar(r"^Siguiente$", 2):
            return
        tecla(4, 2)
    raise SystemExit("No consigo volver al editor tras fallar el sonido")


def poner_sonido(sonido: dict | None = None) -> None:
    """Como en los carruseles, robusto: «Suns» (1.4M publicaciones) dos veces y, si no, otro
    comercial del mismo estilo de la misma búsqueda (Suns 336K, Sunrise… de Official Sound Studio).
    Si el viral lleva MÚSICA concreta, `sonido` del SUBIDA.json trae uno comercial parecido:
    {"busqueda", "sugerencia" (regex o ""), "fila" (regex OCR de su fila), "comprobar" (regex
    del nombre en el editor)}; si falla dos veces, vuelve a «Suns»."""
    sonido = sonido or {}
    propio = [dict(fila=sonido["fila"], busqueda=sonido["busqueda"], sugerencia=sonido.get("sugerencia", ""),
                   comprobar=sonido.get("comprobar") or sonido["fila"])] * 2 if sonido.get("busqueda") else []
    suns = [dict(fila=f) for f in (r"1[.,]4M", r"1[.,]4M", r"\d+[.,]?\d*K publicaciones", r"publicaciones")]
    for kw in propio + suns:
        try:
            _sonido(**kw)
            return
        except SystemExit as e:
            print(f"AVISO sonido: {e}; pruebo otro", flush=True)
            al_editor_video()
    raise SystemExit("No consigo poner ningún sonido comercial")


def boton_anadir() -> tuple[int, int] | None:
    """El «Añadir» del resultado: a veces con desc button_add_product, a veces (bloque «Sugerido
    para ti») sin nada en el volcado → OCR."""
    for x in nodos():
        if re.search(r"button_add_product", x["desc"] + x["id"]) or (x["text"] == "Añadir" and x["y"] > 300):
            return x["x"], x["y"]
    xy = ocr(r"^Añadir$", (0, 400, 1080, 2100))
    if xy:
        return xy
    # el blanco sobre rojo no siempre lo lee: el botón queda 174 px por debajo de «Existencias»
    e = ocr(r"Existencias", (0, 400, 1080, 2100))
    return (880, e[1] + 174) if e else None


def rebuscar(pid: str) -> None:
    """Vuelve a buscar el ID. En la pantalla de resultados el buscador sube arriba (y≈160) y la
    X de (985, 281) caía fuera: el ID se pegaba detrás del anterior y no salía nada (1/11)."""
    campo = next((n for n in nodos() if n["clase"].endswith("EditText")), None)
    tap(*((campo["x"], campo["y"]) if campo else BUSCAR_PRODUCTOS), 1.5)
    adb("shell", "input", "keyevent", "123", *["67"] * 40)   # MOVE_END + borrar
    escribir(pid)
    tecla(66, 6)


def producto(it: dict) -> None:
    pid = it["product_id"]
    if not pulsar(r"^Añadir enlace$", 3):
        raise SystemExit("No veo «Añadir enlace»")
    if not pulsar(r"^Producto$", 7):
        raise SystemExit("No veo «Producto»")
    pulsar(r"Entendido", 2.5, 2)          # aviso de protección de comisión (a veces)
    tap(*BUSCAR_PRODUCTOS, 2)
    escribir(pid)
    tecla(66, 6)
    # A veces sale en blanco aunque el producto sí tenga afiliado (Néstor, 29/10): borrar y
    # volver a buscar, varias veces.
    for i in range(5):
        for _ in range(4):
            if boton_anadir():
                break
            time.sleep(3)
        else:
            rebuscar(pid)
            continue
        break
    captura("4_producto")
    if buscar(r"No se han encontrado", intentos=1):
        raise SystemExit(f"{pid}: no sale al buscarlo (¿fuera del escaparate o sin stock?)")
    xy = boton_anadir()
    if not xy:
        raise SystemExit("No veo «Añadir» en el resultado (4_producto)")
    tap(*xy, 5)
    if not buscar(r"edit_anchor_name_input", intentos=3):
        captura("4_tras_anadir")
        if buscar(r"Obtener una muestra", intentos=1):
            tecla(4, 2)                   # se pulsó la tarjeta, no «Añadir»: otra vez, en el botón
            if (xy := boton_anadir()):
                tap(*xy, 5)
        # «¿Añadir producto al vídeo?» y similares (no salen en el volcado)
        if not buscar(r"edit_anchor_name_input", intentos=1):
            if not pulsar(r"^(Añadir|Confirmar|Continuar|Aceptar|Entendido)$", 4, 1):
                if (c := ocr(r"^(Añadir|Confirmar|Continuar|Aceptar|Entendido)$", (0, 900, 1080, 2150))):
                    tap(*c, 4)
    if not buscar(r"edit_anchor_name_input", intentos=3):
        raise SystemExit("No se abrió el nombre del enlace (4_producto, 4_tras_anadir)")
    al_portapapeles(it["nombre_enlace"][:30])
    for intento in range(3):
        # a veces Gboard enseña sus iconos en vez del chip y el toque abre «Usar el Traductor de Google»
        pulsar(r"^Cancelar$", 1.5, 1)
        campo = buscar(r"edit_anchor_name_input", intentos=3)
        tap(campo["x"], campo["y"], 1.5)
        tecla(123, 0.3)
        for _ in range(35):
            adb("shell", "input", "keyevent", "67")
        pegar()
        pulsar(r"^Cancelar$", 1.5, 1)
        campo = buscar(r"edit_anchor_name_input", intentos=2)
        if campo and campo["text"].strip() == it["nombre_enlace"][:30].strip():
            break
        print(f"AVISO enlace: no se pegó (intento {intento + 1})", flush=True)
        al_portapapeles(it["nombre_enlace"][:30])   # copia fresca: así vuelve a salir el chip
    if not campo or campo["text"].strip() != it["nombre_enlace"][:30].strip():
        captura("4_enlace")
        raise SystemExit("El nombre del enlace no se ha pegado (4_enlace)")
    tecla(4, 1.5)
    if not pulsar(r"edit_anchor_add_button", 5):
        raise SystemExit("No veo «Añadir» del enlace (4_enlace)")
    if not buscar(re.escape(it["nombre_enlace"][:30].strip()), 3):
        captura("4_enlace")
        raise SystemExit("El producto no aparece en la publicación (4_enlace)")


def sin_etiqueta_ia() -> None:
    """La etiqueta IA va en «Más opciones»: si está activada, se desactiva."""
    if not pulsar(r"^Más opciones$", 3, 2):
        print("AVISO: no encuentro «Más opciones» para mirar la etiqueta IA")
        return
    n = buscar(r"generado por IA", intentos=2)
    if n:
        sw = next((x for x in nodos() if x["clase"].endswith("Switch") and abs(x["y"] - n["y"]) < 90), None)
        if sw and sw["checked"]:
            tap(sw["x"], sw["y"], 2)
            print("etiqueta IA desactivada")
    captura("5_opciones")
    tecla(4, 2)


MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()


def leer_selector() -> tuple[int, int, int] | None:
    """Fila central del selector de «Programar publicación»: (días desde hoy, hora, minuto)."""
    from PIL import Image

    ocr("^$")                             # solo para la captura
    Image.open(TMP / "sh" / "ocr.png").crop((40, 1372, 1040, 1476)).save(TMP / "sh" / "banda.png")
    t = subprocess.run(["tesseract", str(TMP / "sh" / "banda.png"), "-", "-l", "spa", "--psm", "6"],
                       capture_output=True, text=True).stdout.strip().lower()
    m = re.search(r"(\d{1,2})\s+(\d{1,2})$", t)
    if not m:
        return None
    # tesseract lee «11» como «1» en la banda entera: hora y minuto se releen sueltos y ampliados
    b, num = Image.open(TMP / "sh" / "banda.png"), []
    for x0, x1 in ((380, 720), (720, 1000)):
        b.crop((x0, 0, x1, b.height)).resize(((x1 - x0) * 3, b.height * 3)).save(TMP / "sh" / "num.png")
        r = subprocess.run(["tesseract", str(TMP / "sh" / "num.png"), "-", "--psm", "7",
                            "-c", "tessedit_char_whitelist=0123456789"], capture_output=True, text=True).stdout.strip()
        num.append(int(r) if r.isdigit() and int(r) < 60 else None)
    # la lectura ampliada solo manda si completa la otra («1» → «11»); sola se equivoca (58 → 98)
    lee = lambda z, g: z if z is not None and len(str(z)) > len(g) and g in str(z) else int(g)
    hora = lee(num[0] if num[0] is not None and num[0] < 24 else None, m.group(1))
    minuto = lee(num[1], m.group(2))
    print(f"selector: {t!r} → {hora}:{minuto:02d}", flush=True)
    if t.startswith("hoy"):
        dias = 0
    else:
        d = re.search(r"([a-z]{3})\w*\.?\s+(\d{1,2})", t)
        if not d or d.group(1) not in MESES:
            return None
        hoy = datetime.now(MADRID).date()
        f = hoy.replace(month=MESES.index(d.group(1)) + 1, day=int(d.group(2)))
        if f < hoy:
            f = f.replace(year=hoy.year + 1)
        dias = (f - hoy).days
    return dias, hora, minuto


def fijar_selector(cuando: datetime) -> None:
    """Gira las tres ruedas (106 px = 1 unidad, deslizando despacio para que no se embalen)."""
    objetivo = ((cuando.date() - datetime.now(MADRID).date()).days, cuando.hour, cuando.minute)
    for _ in range(25):
        actual = leer_selector()
        if actual is None:
            raise SystemExit("No leo el selector de fecha (banda.png)")
        if actual == objetivo:
            return
        for k, x in enumerate((254, 592, 877)):
            dif = objetivo[k] - actual[k]
            if dif:
                paso = max(-7, min(7, dif))
                adb("shell", "input", "swipe", str(x), "1424", str(x), str(1424 - 106 * paso), "900")
                time.sleep(1.5)
                break
    raise SystemExit(f"No consigo poner {cuando:%d/%m %H:%M} en el selector (banda.png)")


def publicar(ronda: str, n: str, cuando: str | None = None) -> None:
    """Sin `cuando`, publica ya. Con `cuando` («AAAA-MM-DD HH:MM», hora de Madrid) la deja
    programada en TikTok (como pronto 30 min después; hasta 10 días)."""
    it = item(ronda, n)
    if cuando:
        hora = datetime.strptime(cuando, "%Y-%m-%d %H:%M").replace(tzinfo=MADRID)
        if not pulsar(r"^Más opciones$", 3):
            raise SystemExit("No veo «Más opciones»")
        if not pulsar(r"^Programar publicación$", 4):
            raise SystemExit("No veo «Programar publicación»")
        fijar_selector(hora)
        captura("6_programa")
        if not pulsar(r"^Listo$", 3):
            raise SystemExit("No veo «Listo» en el selector")
        tecla(4, 2)                       # cierra «Más opciones»
    captura("6_antes")
    if not pulsar(r"^(Publicar|Programar)$", 12):
        raise SystemExit("No veo el botón Publicar/Programar")
    pulsar(r"^Denegar", 2, 2)             # «añadir accesos directos» (a veces)
    # No cerrar TikTok hasta que termine de subir: programado → aviso «Consulta tus
    # publicaciones programadas en tu perfil»; publicado → desaparece el «%» de subida.
    # El aviso dura 3-4 s y a veces no se llega a leer: vale también salir del editor
    # (ya no hay botón Publicar) sin «%» de subida durante 60 s.
    inicio, visto = time.time(), False
    while time.time() < inicio + 300:
        pulsar(r"^No permitir$", 1, 1)    # diálogo de contactos que a veces sale al volver al feed
        textos = " ".join(x["text"] + " " + x["desc"] for x in nodos())
        if re.search(r"programadas|se ha publicado", textos):
            visto = True
            break
        if (time.time() > inicio + 60 and not re.search(r"\bPublicar\b|\bProgramar\b", textos)
                and not re.search(r"\d+ ?%", textos)):
            visto = True
            break
        time.sleep(4)
    if not visto:
        captura("7_sin_confirmar")
        raise SystemExit("Pulsé Publicar pero no veo que haya terminado de subir (7_sin_confirmar.jpg)")
    estado = f"programado {cuando}" if cuando else "publicado"
    with open(Path(ronda) / "SUBIDAS.log", "a") as f:
        f.write(f"{datetime.now(MADRID):%Y-%m-%d %H:%M} {int(n):02d} {it['product_id']} {estado}\n")
    captura("7_publicado")
    print(f"{int(n):02d} {estado}")


def al_escaparate(pid: str) -> None:
    """Como en subir_carrusel_movil.py: la búsqueda de «Añadir enlace» solo mira el escaparate,
    así que antes se abre la ficha (https, no snssdk: esa no enseña el botón) y se añade."""
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
        "-d", f"https://www.tiktok.com/view/product/{pid}", PAQUETE)
    time.sleep(9)
    sin_guia_proximidad()
    captura("0_ficha")
    if buscar(r"(se ha eliminado|Producto no disponible)", intentos=1):
        raise SystemExit(f"{pid}: ficha «eliminado/no disponible» (0_ficha)")
    if not buscar(r"(Añadido al escaparate|En el escaparate|Quitar del escaparate)", intentos=1):
        hecho = pulsar(r"Añadir al escaparate", 4, 1)
        if not hecho:
            adb("shell", "input", "swipe", "540", "1700", "540", "900", "500")
            time.sleep(2)
            # «Gana X € por cada venta» es un panel plegado (^^): al abrirlo sale el botón
            g = buscar(r"^Gana .*por cada venta|Comisión del", intentos=1)
            xy = (g["x"], g["y"]) if g else ocr(r"por cada venta")
            if xy:
                tap(*xy, 3)
                captura("0_panel")
            hecho = pulsar(r"Añadir al escaparate", 4, 1)
            if not hecho and (xy := ocr(r"Añadir al escaparate")):
                tap(*xy, 4)
                hecho = True
        if not hecho:
            print(f"{pid}: sin «Añadir al escaparate» en la ficha; sigo con la búsqueda por ID", flush=True)
        captura("0_escaparate")
    adb("shell", "am", "force-stop", PAQUETE)


def limpiar() -> None:
    for f in adb("shell", "ls", CARPETA_MOVIL).split():
        if f.startswith("hz_"):
            ruta = f"{CARPETA_MOVIL}/{f}"
            adb("shell", "rm", "-f", ruta)
            adb("shell", f"content delete --uri content://media/external/video/media --where \"_data LIKE '%/{f}'\"")
            adb("shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d", f"file://{ruta}")


def todo(ronda: str, n: str, *resto: str) -> None:
    """todo <ronda> <n> [AAAA-MM-DD HH:MM] [--sin-publicar]. Con fecha y hora (Madrid) queda programado."""
    flags = [x for x in resto if x.startswith("--")]
    cuando = " ".join(x for x in resto if not x.startswith("--")) or None
    despertar()
    try:
        al_escaparate(item(ronda, n)["product_id"])
        preparar(ronda, n)
        editor(ronda, n)
        if "--sin-publicar" not in flags:
            publicar(ronda, n, cuando)
    finally:
        if "--sin-publicar" not in flags:
            adb("shell", "am", "force-stop", PAQUETE)
            limpiar()
            dormir()


def programar(ronda: str, *pares: str) -> None:
    """programar <ronda> 05=2026-10-29T23:49 06=2026-10-30T00:18 … — los deja uno a uno
    programados en TikTok. Si una hora ya no está a ≥35 min, la corre hasta que lo esté."""
    for par in pares:
        n, f = par.split("=")
        hora = datetime.strptime(f, "%Y-%m-%dT%H:%M").replace(tzinfo=MADRID)
        minimo = datetime.now(MADRID) + timedelta(minutes=40)
        if hora < minimo:
            hora = minimo.replace(second=0, microsecond=0)
        print(f"{int(n):02d} → {hora:%Y-%m-%d %H:%M}", flush=True)
        try:
            todo(ronda, n, f"{hora:%Y-%m-%d %H:%M}")
        except SystemExit as e:           # uno que falla no para la cola
            print(f"{int(n):02d} FALLÓ: {e}", flush=True)


# Coordenadas del Mi 8 (1080x2248), calibradas el 29/10 con el vídeo 01 de la ronda 6
MAS = (540, 2036)
GALERIA = (110, 2014)
PRIMERA_MINIATURA = (310, 400)            # el círculo de selección (selección múltiple activa)
PILDORA_SONIDO = (530, 189)
LUPA_SONIDO = (1014, 1204)
CHECK_SONIDO_X = 952
CAPTION = (349, 446)
BUSCAR_PRODUCTOS = (540, 304)

if __name__ == "__main__":
    (TMP / "sh").mkdir(parents=True, exist_ok=True)
    fase, *resto = sys.argv[1:]
    {"preparar": preparar, "editor": editor, "publicar": publicar, "limpiar": limpiar,
     "todo": todo, "programar": programar}[fase](*resto)
