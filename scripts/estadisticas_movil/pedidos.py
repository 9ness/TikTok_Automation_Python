# Ganancias › Pedidos de afiliados (pestaña ya elegida y rango puesto) → JSON por pedido
# uso: abrir en el móvil Ganancias › Pedidos de afiliados, elegir pestaña y rango (máx. 90 días),
#      y luego: python3 -I pedidos.py salida.json   (MOVIL_ADB=ip:puerto)
import subprocess, re, html, json, sys, time, os
D = os.environ.get("MOVIL_ADB", "100.123.211.22:40281")
def adb(*a): return subprocess.run(["adb", "-s", D, *a], capture_output=True, text=True).stdout
def dump():
    for _ in range(3):
        adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
        s = adb("exec-out", "cat", "/sdcard/u.xml")
        r = [html.unescape(m.group(1)) for m in re.finditer(r'(?:text|content-desc)="([^"]+)"', s)]
        if r: return r
        time.sleep(1)
    return []
TIPOS = {"Vídeo", "Carousel", "Carrusel", "LIVE", "Escaparate", "Tarjeta de producto", "Anuncio", "Imagen", "Foto"}
pedidos, quietos, ultimo = {}, 0, None
while quietos < 4:
    t = dump(); nuevos = 0
    idx = [i for i, s in enumerate(t) if s.startswith("ID del pedido:")]
    for n, i in enumerate(idx):
        bloque = t[i: idx[n + 1] if n + 1 < len(idx) else len(t)]
        pid = bloque[0].split(":")[1].strip()
        p = {"id": pid, "estado": bloque[1] if len(bloque) > 1 else ""}
        for j, s in enumerate(bloque):
            if "~tplv" in s and j + 1 < len(bloque): p["producto"] = bloque[j + 1]
            elif s in TIPOS: p["tipo"] = s
            elif re.fullmatch(r"[A-Z]{2}", s): p["pais"] = s
            elif re.search(r"€.*x \d+|x \d+$", s) and "€" in s: p["importe"] = s
            elif s.startswith("Porcentaje de comisión") and j + 2 < len(bloque): p["pct"] = bloque[j + 1]; p["comision"] = bloque[j + 2]
            elif s.startswith("#") or (len(s) > 25 and "#" in s and "producto" in p and "caption" not in p and s != p.get("producto")): p["caption"] = s
        viejo = pedidos.get(pid)
        if not viejo: nuevos += 1
        if not viejo or len(p) > len(viejo): pedidos[pid] = p
    quietos = quietos + 1 if not nuevos else 0
    json.dump(list(pedidos.values()), open(sys.argv[1], "w"), ensure_ascii=False, indent=1)   # guarda en cada vuelta: un corte no pierde lo leído
    print(len(pedidos), flush=True)
    adb("shell", "input", "swipe", "720", "2700", "720", "1000", "400"); time.sleep(1.6)
json.dump(list(pedidos.values()), open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
from collections import Counter
print(len(pedidos), "pedidos", Counter(p.get("tipo", "?") for p in pedidos.values()))
