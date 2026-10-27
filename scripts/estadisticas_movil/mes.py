# uso: python3 -I mes.py MM  (en la pantalla Datos, arriba del todo)
import subprocess, re, html, json, sys, time
import os as _os
W = _os.environ.get("EST_DIR", "/tmp/est"); _os.makedirs(W, exist_ok=True)
import os
D = os.environ.get("MOVIL_ADB", "100.123.211.22:40281")
POS = {"05": (220, 2423), "06": (553, 2423), "07": (883, 2423), "08": (1217, 2423),
       "09": (220, 2590), "10": (553, 2590)}
mm = sys.argv[1]
def adb(*a): return subprocess.run(["adb", "-s", D, *a], capture_output=True, text=True).stdout
def tap(x, y): adb("shell", "input", "tap", str(x), str(y)); time.sleep(1.5)
def dump():
    adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    s = adb("exec-out", "cat", "/sdcard/u.xml")
    return [(int(m.group(2)), int(m.group(3)), html.unescape(m.group(1)))
            for m in re.finditer(r'(?:text|content-desc)="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]', s)]
def textos(): return [t for _, _, t in dump()]
def tras(t, etiqueta):
    i = t.index(etiqueta)
    return next(x for x in t[i+1:i+4] if re.search(r"\d", x) and x != "-")
def swipe(a, b): adb("shell", "input", "swipe", "720", str(a), "720", str(b), "400"); time.sleep(2)

for _ in range(5):
    t = textos()
    if "Datos" in t[:3] and "Lista de productos" not in t and "Tendencias" not in t: break
    adb("shell", "input", "keyevent", "KEYCODE_BACK"); time.sleep(2)
else:
    sys.exit("no llego a Datos")
for _ in range(3): swipe(1200, 3000)
tap(880, 960); tap(1173, 2417); tap(*POS[mm]); tap(720, 2917); time.sleep(3); tap(240, 1760); time.sleep(2)
t = textos()
out = {"mes": f"2026-{mm}", "rango": next(x for x in t if "GMT" in x)}
ABR = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"][int(mm)-1]
assert ABR in out["rango"], f"mes equivocado: {out['rango']}"
for k, e in [("gmv", "GMV atr."), ("ventas", "Ventas de artículos atr."),
             ("impresiones", "Impresiones del producto"), ("clics", "Clics en el producto")]:
    out[k] = tras(t, e)
tap(533, 1760); time.sleep(2); t = textos()
for k, e in [("gmv_comision", "GMV de comisiones"), ("art_comision", "Artículos vendidos con comisión"),
             ("base_comision", "Base de la comisión"), ("comision", "Comisiones estimadas")]:
    out[k] = tras(t, e)
tap(240, 1760)
# productos: bajar hasta ver "Ver todo"
for _ in range(6):
    v = [(x, y) for x, y, s in dump() if s == "Ver todo" and 300 < y < 2900]
    if v: break
    swipe(2500, 1800)
x, y = v[0]; tap(x + 60, y + 30); time.sleep(3)
t = textos()
out["rango_productos"] = next((x for x in t if "GMT" in x), "")
assert ABR in out["rango_productos"], f"productos de otro mes: {out['rango_productos']}"
vistos, igual = {}, 0
for _ in range(80):
    t = textos(); n0 = len(vistos)
    for i, x in enumerate(t):
        if re.fullmatch(r"[A-Z]{2}", x) and i + 4 < len(t) and t[i+1] == "GMV atr.":
            tit = t[i-1]
            vals = [y for y in t[i+2:i+6] if re.match(r"^[\d.,]+\s*€$|^\d[\d.,]*$", y)]
            if (tit, x) not in vistos and len(vals) >= 2:
                vistos[(tit, x)] = (next((v for v in vals if "€" in v), ""), next((v for v in vals if "€" not in v), ""))
    if any(re.sub(r"\s", "", v[0]) == "0€" for v in vistos.values()): break
    if len(vistos) == n0:
        igual += 1
        if igual >= 2: break
    else: igual = 0
    swipe(2700, 900)
out["productos"] = [{"titulo": k[0], "pais": k[1], "gmv": v[0], "ventas": v[1]} for k, v in vistos.items() if re.sub(r"\s", "", v[0]) != "0€"]
adb("shell", "input", "keyevent", "KEYCODE_BACK"); time.sleep(2)
json.dump(out, open(f"{W}/m_2026-{mm}.json", "w"), ensure_ascii=False, indent=1)
print(mm, out["rango"], out["rango_productos"], out["gmv"], out["ventas"], out["clics"], out["comision"], len(vistos))
