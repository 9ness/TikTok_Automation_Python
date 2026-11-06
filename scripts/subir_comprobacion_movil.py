"""Sube un vídeo de la cuenta árabe (Mi 8) por «Comprobación previa» (desde el 3/11/2026, Néstor):
ficha del producto → panel «Gana X €» → «Crear ahora» → «Vídeos» → «Cambiar nombre del producto»
(nombre del enlace, letra a letra) → letras rojas «Haz una comprobación previa de tu vídeo» →
vídeo + caption árabe + «Publicar» activado → «Comprobar». Se publica solo si pasa (≤10 min).
Cupo diario: 6 (o 10) comprobaciones; el contador sale tras la primera.

Uso: subir_comprobacion_movil.py <ronda> <n> [video]   («video» = reanudar con el vídeo ya elegido)
Lee <ronda>/SUBIDA.json (numero, archivo, product_id, nombre_enlace, caption); apunta en SUBIDAS.log.
Capturas de antes/después y de fallos en <ronda>/subida/. Ver docs/CUENTA_ARABE.md §5."""
import sys, time, re, unicodedata, subprocess, html
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subir_video_movil as m
R = Path(sys.argv[1])
(R / 'subida/cap/sh').mkdir(parents=True, exist_ok=True)
m.TMP = R / 'subida/cap'
def foto(nombre):
    open(R/f'subida/{nombre}.png','wb').write(subprocess.run(['timeout','20','adb','-s',m.SERIAL,'exec-out','screencap','-p'],capture_output=True).stdout)
def falla(msg, nombre='fallo'):
    foto(nombre); raise SystemExit(f'{msg} (subida/{nombre}.png)')
def ve(patron, intentos=4):
    """Volcado y, si no sale (pantallas web de la comprobación), OCR."""
    for _ in range(intentos):
        n = m.buscar(patron, 1, 0)
        if n: return (n['x'], n['y'])
        p = m.ocr(re.sub(r'^\^(\\s\*)?|\$$', '', patron))
        if p: return p
        time.sleep(1.5)
def debe(patron, espera=3, intentos=5):
    p = ve(patron, intentos)
    if not p: falla(f'no veo «{patron}»')
    m.tap(*p, espera)
n = sys.argv[2]; it = m.item(str(R), n)
DESDE = sys.argv[3] if len(sys.argv) > 3 else ''
nombre = unicodedata.normalize('NFKD', it['nombre_enlace']).encode('ascii','ignore').decode()
if DESDE != 'video':
    m.despertar(); m.preparar(str(R), n)
    def abrir_panel():
        m.adb("shell","am","force-stop",m.PAQUETE); time.sleep(2)
        m.adb("shell","am","start","-a","android.intent.action.VIEW","-d",f"https://www.tiktok.com/view/product/{it['product_id']}",m.PAQUETE)
        time.sleep(14); m.sin_guia_proximidad()
        if ve(r'artículo está agotado', 1): falla('producto AGOTADO: no se sube')   # sin «Crear ahora», el botón queda en «Añadido al escaparate» (6/11)
        for _ in range(4):
            if m.buscar(r'^\s*(Crear ahora|Añadir al escaparate)$', 1): return
            if m.pulsar(r'Gana .*€', 4, 1): continue
            m.adb("shell","input","swipe","540","1700","540","900"); time.sleep(2)
        falla('no se abre el panel «Gana X €»')
    for _ in range(2):
        abrir_panel()
        if m.buscar(r'^\s*Crear ahora$', 2): break
        if m.pulsar(r'^\s*Añadir al escaparate$', 4, 2):
            print('añadido al escaparate'); continue
        falla('ni «Crear ahora» ni «Añadir al escaparate»')
    debe(r'^\s*Crear ahora$')
    time.sleep(3)
    if not any(x['clase'].endswith('EditText') for x in m.nodos()):
        m.tap(540, 1278, 4)                   # «Vídeos» de «¿Cómo quieres promocionar…?» (no sale en el volcado)
    for _ in range(6):                        # diálogo nuevo (4/11): «¿Añadir producto al vídeo?» → «Añadir»;
        if any(x['clase'].endswith('EditText') for x in m.nodos()): break   # a veces tarda en salir (5/11)
        if ve(r'Añadir producto al', 2):
            p = m.ocr(r'^Añadir$')            # anclado: ve() quita el ^$ y casaba con el «¿Añadir» del título (6/11)
            if not p: falla('no veo el botón «Añadir»')
            m.tap(*p, 4); continue
        time.sleep(2)
    campo = next((x for x in m.nodos() if x['clase'].endswith('EditText')), None)
    if not campo: falla('no sale «Cambiar nombre del producto»')
    for intento in range(2):                  # con el móvil cargado se cuela un espacio o se pierde una letra
        m.tap(campo['x'], campo['y'], 1.5)
        m.tecla('KEYCODE_MOVE_END', .3)
        for _ in range(45): m.adb("shell","input","keyevent","67")
        if intento == 0:
            for ch in nombre:
                m.adb("shell","input","text","%s" if ch == ' ' else ch); time.sleep(.35)
        else:                                 # «Colageno» salía «Colage no» letra a letra (y por palabras se
            m.tecla(4, 1)                     #   comía letras): se pega desde el portapapeles, como el caption
            m.al_portapapeles(nombre); time.sleep(2)
            campo = next((x for x in m.nodos() if x['clase'].endswith('EditText')), None)
            if not campo: falla('al volver de Keep no veo el nombre')
            m.tap(campo['x'], campo['y'], 1.5); m.tecla('KEYCODE_MOVE_END', .3)
            for _ in range(45): m.adb("shell","input","keyevent","67")
            m.pegar()
        time.sleep(1)
        campo = next((x for x in m.nodos() if x['clase'].endswith('EditText')), None)
        if campo and html.unescape(campo['text']).strip().lower() == nombre.lower(): break   # el volcado da «&amp;»
        print(f'nombre mal escrito ({campo and campo["text"]!r}), reintento')
        if not campo: break
    if not campo or html.unescape(campo['text']).strip().lower() != nombre.lower(): falla(f'nombre mal escrito: {campo and campo["text"]!r}')
    m.tap(700, 371, 4)                        # letras rojas «Haz una comprobación previa de tu vídeo» (enlace dentro del texto)
    if not ve(r'Sube un', 5): falla('no sale la comprobación')
    m.tap(540, 908, 3)
    debe(r'Biblioteca de fotos', 3)
    if ve(r'Completar acción', 2): debe(r'^\s*Galería$', 3)
    if ve(r'^\s*Álbumes$', 2):
        debe(r'^\s*Álbumes$', 2); debe(r'Otros álbumes', 2); debe(r'^\s*Hmizat', 2)
    vids = [x for x in m.nodos() if x['text'].startswith('Vídeo tomado')]
    if len(vids) > 1: falla(f'el álbum tiene {len(vids)} vídeos')
    if vids: m.tap(vids[0]['x'], vids[0]['y'], 4)
    elif ve(r'Selecciona', 2): m.tap(150, 674, 4)   # selector que ya abre en el álbum Hmizat (sin volcado)
    else: falla('no sale el selector de vídeo')
for _ in range(20):
    if not m.buscar(r'\d+%', 1, 0): break
    time.sleep(2)
time.sleep(2)
m.adb("shell","input","swipe","540","1400","540","700"); time.sleep(2)
if not m.buscar(r'Añade una descripción', 3): falla('no veo la descripción')
m.al_portapapeles(it['caption']); time.sleep(2)
d = m.buscar(r'Añade una descripción', 3)
if not d: falla('al volver de Keep no veo la descripción')
m.tap(540, d['y'] - 180 if d['y'] > 700 else 660, 2)   # el nodo ocupa el bloque; el texto está arriba
m.pegar(); m.tecla(4, 2)
if m.buscar(r'Añade una descripción', 1) and not any(re.search(r'#tiktokshop', x['text']) for x in m.nodos()):
    falla('caption sin pegar')
# el producto vinculado no sale en el volcado (allí solo está el caption, que también lo nombra):
# OCR en la fila de debajo de «Vincula un producto»
prod = None
for _ in range(3):                            # a veces queda abierto el desplegable de #hashtags y tapa la fila
    v = m.ocr(r'Vincula')
    prod = v and m.ocr(re.escape(nombre[:10]), (0, v[1], 1080, v[1] + 260))
    if prod: break
    m.tap(850, 590, 1.5)                      # quita el foco del caption (cierra las sugerencias)
    m.adb("shell","input","swipe","540","1400","540","800"); time.sleep(2)
if not prod: falla('producto vinculado no coincide')
foto(f'antes_{int(n):02d}')
debe(r'^\s*Comprobar$', 4)
p = ve(r'Entendido', 6)
if p: m.tap(*p, 3)
if not ve(r'comprobaciones', 4): falla('no vuelve a la lista de comprobaciones')
c = m.buscar(r'comprobaciones', 3); foto(f'despues_{int(n):02d}')
cupo = ' '.join(x['text'] for x in m.nodos() if re.search(r'^\d+$|de|comprobaciones', x['text']))[:80]
print(f'{int(n):02d} enviado · {cupo}')
with open(R/'SUBIDAS.log','a') as f: f.write(f"{time.strftime('%F %T')} {int(n):02d} {Path(it['archivo']).stem} enviado a comprobación previa (Publicar ON)\n")
