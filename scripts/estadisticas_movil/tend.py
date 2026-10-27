# uso: python3 -I tend.py MM  → d_2026-MM.json con GMV, ventas, impresiones y clics por día
import subprocess, re, html, json, sys, time, calendar
import os as _os
W = _os.environ.get("EST_DIR", "/tmp/est"); _os.makedirs(W, exist_ok=True)
import os
D = os.environ.get("MOVIL_ADB", "100.123.211.22:40281")
POS = {"05": (220, 2423), "06": (553, 2423), "07": (883, 2423), "08": (1217, 2423),
       "09": (220, 2590), "10": (553, 2590)}
ABR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
mm = sys.argv[1]
def adb(*a, b=False):
    r = subprocess.run(["adb", "-s", D, *a], capture_output=True, text=not b)
    return r.stdout
def tap(x, y, s=1.5): adb("shell", "input", "tap", str(int(x)), str(int(y))); time.sleep(s)
def dump():
    adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    s = adb("exec-out", "cat", "/sdcard/u.xml")
    return [(int(m.group(2)), int(m.group(3)), html.unescape(m.group(1)))
            for m in re.finditer(r'(?:text|content-desc)="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]', s)]
def textos():
    for _ in range(3):
        t = [t for _, _, t in dump()]
        if t: return t
        time.sleep(1)
    return []
def swipe(a, b, x1=720, x2=720, ms=400): adb("shell", "input", "swipe", str(x1), str(a), str(x2), str(b), str(ms)); time.sleep(1.5)
def ocr():
    open(f"{W}/c.png", "wb").write(adb("exec-out", "screencap", "-p", b=True))
    subprocess.run(["convert", f"{W}/c.png", "-crop", "1360x260+30+1990", "-colorspace", "gray",
                    "-resize", "200%", f"{W}/h.png"])
    return subprocess.run(["tesseract", f"{W}/h.png", "-", "--psm", "6", "-l", "spa"],
                          capture_output=True, text=True).stdout.replace("\n", " ")
def num(s):
    s = s.replace("€", "").strip()
    k = 1000 if s.endswith("K") else 1
    s = s.rstrip("K").strip()
    s = s.replace(",", ".") if k > 1 else s.replace(".", "").replace(",", ".")
    return round(float(s) * k, 2)

# a Datos y al mes
for _ in range(5):
    t = textos()
    if "Datos" in t[:3] and "Lista de productos" not in t: break
    if any("ltimos 7" in x for x in t): tap(1366, 930, 3); continue
    adb("shell", "input", "keyevent", "KEYCODE_BACK"); time.sleep(2)
else:
    sys.exit("no llego a Datos")
for _ in range(3): swipe(1200, 3000)
tap(880, 960); tap(1173, 2417); tap(*POS[mm]); tap(720, 2917, 3); tap(240, 1760, 2)
t = textos()
rango = next(x for x in t if "GMT" in x)
assert ABR[int(mm) - 1] in rango, rango
ndias = int(re.search(r"–\s*(\d+)", rango).group(1))
vt = [(x, y) for x, y, s in dump() if s == "Ver tendencias"][0]
tap(vt[0] + 100, vt[1] + 30, 3)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import graf
def cap(n):
    open(f"{W}/s{n}.png", "wb").write(adb("exec-out", "screencap", "-p", b=True))
    return f"{W}/s{n}.png"
dias = {d: {"fecha": f"2026-{mm}-{d:02d}"} for d in range(1, ndias + 1)}
METRICAS = [("gmv", (200, 1695)), ("ventas", (683, 1695)), ("impresiones", (1200, 1695)), ("clics", None)]
# SOLO=gmv,clics repite solo esas métricas y conserva lo demás del fichero
if os.environ.get("SOLO"):
    METRICAS = [m for m in METRICAS if m[0] in os.environ["SOLO"].split(",")]
    if os.path.exists(f"{W}/d_2026-{mm}.json"):
        for x in json.load(open(f"{W}/d_2026-{mm}.json")): dias[int(x["fecha"][-2:])].update(x)
try:
  for clave, pos in METRICAS:
      if pos: tap(*pos, 2.5)
      else:
          swipe(1695, 1695, 1300, 200, 600); tap(1080, 1695, 2.5)
      tap(400, 2620, 1); a = cap(clave + "1"); tap(1100, 2620, 1); b = cap(clave + "2")
      vals, pares, ypix = graf.leer([a, b], ndias)
      ok = [(d, x, y) for d, (x, y, _) in enumerate(ypix, 1) if y is not None]
      planos = [p for p in ok if sum(abs(q[2] - p[2]) <= 2 for q in ok) >= 3] or ok
      anclas = {}
      def ancla(cands):
          for d, x, y in cands[:4]:
              tap(x, 2620, 1)
              m = re.search(r"\b[a-z]{3,4}\.? ?(\d{1,2})\s*\|.*?(?:atr\.|producto)\s+([\dO](?:[\d.,]|\s(?=\d{3}\b))*\d\s*K?)(?=\s*€|\s|$)", ocr().strip(), re.I)
              if not m: continue
              dd = int(m.group(1))
              yy = ypix[dd - 1][1] if 1 <= dd <= ndias else None
              if yy is None: continue
              try: anclas[yy] = num(re.sub(r"(?<=\d)\s(?=\d)", "", m.group(2).replace("O", "0"))); return
              except ValueError: pass
      ancla(sorted(ok, key=lambda z: z[2]))
      ancla(sorted(planos, key=lambda z: -z[2]))
      if len(anclas) == 2 and len(set(anclas)) == 2:
          (y1, v1), (y2, v2) = anclas.items()
          a_, b_ = (v1 - v2) / (y1 - y2), v1 - (v1 - v2) / (y1 - y2) * y1
          vals = [None if y is None else round(max(a_ * y + b_, 0), 2) for _, y, _f in ypix]
      else:
          print("SIN ANCLAS", clave, anclas, flush=True); vals = [None] * ndias
      print(clave, anclas, vals, flush=True)
      for d, v in enumerate(vals, 1):
          if v is not None: dias[d][clave] = v if clave == "gmv" else round(v)
finally:
    adb("shell", "input", "keyevent", "KEYCODE_BACK"); time.sleep(1)
json.dump(list(dias.values()), open(f"{W}/d_2026-{mm}.json", "w"), ensure_ascii=False, indent=1)
print(mm, ndias, sum(1 for v in dias.values() if len(v) == 5), "días completos")
