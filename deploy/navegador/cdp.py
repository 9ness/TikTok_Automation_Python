"""Manejar el Chrome remoto del VPS por CDP (127.0.0.1:9222) con Playwright.

Uso (sub = trozo de la URL de la pestaña):
  cdp.py tabs
  cdp.py shot  <sub> <salida.png>
  cdp.py goto  <sub> <url>            # navega ESA pestaña
  cdp.py click <sub> <x> <y>
  cdp.py press <sub> <tecla>
  cdp.py type  <sub> <texto>          # escribe en lo que tenga el foco
  cdp.py paste <sub> <fichero.txt>    # inserta el texto del fichero (execCommand insertText)
  cdp.py upload <sub> <fichero>       # sube a un <input type=file> (el primero)
  cdp.py eval  <sub> <js>
  cdp.py evalf <sub> <fichero.js>
  cdp.py wheel <sub> <x> <y> <dy>
  cdp.py open  <url>                 # pestaña nueva
  cdp.py close <sub>                 # cerrar pestaña
Siempre trae la pestaña al frente (una pestaña en segundo plano no pinta y se cuelga).
"""
import os
import sys
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def pagina(ctx, sub):
    for pg in ctx.pages:
        if sub in pg.url:
            return pg
    raise SystemExit(f"no hay pestaña con '{sub}'")


def main():
    # Cada acción del agente cuenta como actividad: `navegador auto` apaga Chrome tras 45 min
    # sin clientes, y las consultas cortas de un agente que espera un clip no lo evitaban.
    try:
        os.utime("/run/navegador.ultimo")
    except OSError:
        pass
    cmd = sys.argv[1]
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        ctx = b.contexts[0]
        if cmd == "tabs":
            for pg in ctx.pages:
                print(pg.url[:110], "|", pg.title()[:50])
            return
        if cmd == "open":                 # abrir una pestaña nueva en <url>
            pg = ctx.new_page()
            pg.goto(sys.argv[2], wait_until="domcontentloaded")
            print("abierta", pg.url[:100])
            return
        pg = pagina(ctx, sys.argv[2])
        if cmd == "close":                # cerrar la pestaña (la sesión queda en el perfil)
            pg.close()
            print("cerrada", sys.argv[2])
            return
        pg.bring_to_front()
        a = sys.argv[3:]
        if cmd == "shot":
            pg.wait_for_timeout(1200)
            pg.screenshot(path=a[0])
            print("ok", pg.url[:90])
        elif cmd == "goto":
            pg.goto(a[0], wait_until="domcontentloaded")
            pg.wait_for_timeout(4000)
            print("ok", pg.url[:100], "|", pg.title()[:50])
        elif cmd == "click":
            pg.mouse.click(float(a[0]), float(a[1]))
            pg.wait_for_timeout(800)
            print("click", a[0], a[1])
        elif cmd == "press":
            pg.keyboard.press(a[0])
            print("press", a[0])
        elif cmd == "type":
            pg.keyboard.type(a[0], delay=8)
            print("typed", len(a[0]))
        elif cmd == "paste":
            texto = open(a[0], encoding="utf-8").read().strip()
            r = pg.evaluate(
                """(t) => { const el = document.activeElement; el.focus();
                   if (el.isContentEditable) { document.execCommand('selectAll'); document.execCommand('insertText', false, t); return 'ce:' + el.innerText.length; }
                   if ('value' in el) { el.select(); document.execCommand('insertText', false, t); return 'val:' + el.value.length; }
                   return 'sin editor'; }""",
                texto,
            )
            print("paste", r)
        elif cmd == "upload":
            pg.set_input_files("input[type=file]", a[0])
            pg.wait_for_timeout(3000)
            print("upload", a[0])
        elif cmd == "eval":
            print(pg.evaluate(a[0]))
        elif cmd == "evalf":              # el JS viene de un fichero (evita líos de comillas)
            print(pg.evaluate(open(a[0], encoding="utf-8").read()))
        elif cmd == "wheel":
            pg.mouse.move(float(a[0]), float(a[1]))
            pg.mouse.wheel(0, float(a[2]))
            pg.wait_for_timeout(600)
            print("wheel", a[2])


main()
