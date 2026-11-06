# Suma los pedidos nuevos a lo guardado, sin duplicar → doc para guardar_estadisticas.
# uso: pedidos_sumar.py pedidos.json estadisticas.json contados.json salida.json MES [ID_A:FECHA ID_B:FECHA]
#   estadisticas.json = salida de estadisticas_ventas · MES = AAAA-MM de ayer
#   con las dos anclas el mes de cada pedido se interpola por ID (primera lectura, que cruza meses)
# contados.json NO se toca: se escribe salida.json.contados y se mueve encima SOLO si guardar_estadisticas fue bien.
import json, sys, re, datetime
A_EUR = {"€": 1, "zł": 0.235, "Kč": 0.04, "Ft": 0.0025, "lei": 0.2, "kr": 0.09, "£": 1.15}   # aproximado, solo para ordenar y sumar
NOM = {"Carousel": "Carrusel", "Carrusel": "Carrusel", "Vídeo": "Vídeo", "LIVE": "LIVE", "Escaparate": "Escaparate"}
ped_f, est_f, cont_f, out_f, MES = sys.argv[1:6]
anclas = [(int(a.split(":")[0]), datetime.date.fromisoformat(a.split(":")[1])) for a in sys.argv[6:8]]
def mes_de(i):
    if len(anclas) < 2: return MES
    (a, fa), (b, fb) = anclas
    return (fa + datetime.timedelta(days=(int(i) - a) / (b - a) * (fb - fa).days)).strftime("%Y-%m")
raros = set()
def dinero(s):
    m = re.search(r"(\d[\d.,]*)\s*([^\d\s.,]+)|([^\d\s.,x]+)\s*(\d[\d.,]*)", s or "")
    if not m: return 0.0
    v, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    v = float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
    if mon not in A_EUR: raros.add(mon); return 0.0
    return v * A_EUR[mon]
uds = lambda s: int((re.search(r"x\s*(\d+)", s or "") or [0, 1])[1])
t = open(est_f).read(); est = json.loads(t[t.index("{"):t.rindex("}") + 1]); cont = {}   # mcp.py puede imprimir algo antes
try: cont = json.load(open(cont_f))
except FileNotFoundError: pass
meses = {m["mes"]: m for m in est.get("meses", [])}
contenidos = {(c.get("tipo"), c.get("caption")): c for c in est.get("contenidos", [])}
tocados = set()
def aplica(p, mes, signo):
    """Suma (o resta) un pedido en origen, productos y contenidos del mes."""
    m = meses.setdefault(mes, {"mes": mes}); tocados.add(mes)
    o = m.setdefault("origen", {}).setdefault(p["k"], {"pedidos": 0, "importe": 0.0, "comision": 0.0, "es_pedidos": 0, "es_importe": 0.0})
    o["pedidos"] += signo; o["importe"] = round(o["importe"] + signo * p["imp"], 2); o["comision"] = round(o["comision"] + signo * p["com"], 2)
    if p["pais"] == "ES": o["es_pedidos"] += signo; o["es_importe"] = round(o["es_importe"] + signo * p["imp"], 2)
    prods = m.setdefault("productos", [])
    x = next((q for q in prods if q.get("titulo") == p["producto"] and q.get("pais") == p["pais"]), None)
    if not x: x = {"titulo": p["producto"], "pais": p["pais"], "gmv": 0.0, "ventas": 0, "tipo": "Otros"}; prods.append(x)
    x["gmv"] = round(x["gmv"] + signo * p["imp"], 2); x["ventas"] += signo
    og = x.setdefault("origen", {}); og[p["k"]] = og.get(p["k"], 0) + signo
    if p["k"] in ("Vídeo", "Carrusel"):
        c = contenidos.setdefault((p["k"], p["caption"]), {"caption": p["caption"], "tipo": p["k"], "pedidos": 0, "importe": 0.0, "comision": 0.0})
        c["pedidos"] += signo; c["importe"] = round(c["importe"] + signo * p["imp"], 2); c["comision"] = round(c["comision"] + signo * p["com"], 2)
nuevos = restados = no_aptos = 0
for r in json.load(open(ped_f)):
    i = r["id"]; malo = "no apto" in (r.get("estado") or "").lower()
    if i in cont:   # ya sumado: solo importa si ha pasado a «No apto»
        if malo and not cont[i].get("no_apto"):
            aplica(cont[i], cont[i]["mes"], -1); cont[i]["no_apto"] = True; restados += 1
        continue
    p = {"mes": mes_de(i), "k": "Anuncios" if r.get("anuncio") else NOM.get(r.get("tipo"), r.get("tipo") or "Otros"),
         "pais": r.get("pais") or "ES", "producto": r.get("producto", ""), "caption": r.get("caption", ""),
         "imp": round(dinero(r.get("importe")) * uds(r.get("importe")), 2), "com": round(dinero(r.get("comision")), 2)}
    if malo:
        o = meses.setdefault(p["mes"], {"mes": p["mes"]}).setdefault("origen", {}).setdefault(p["k"], {"pedidos": 0, "importe": 0.0, "comision": 0.0, "es_pedidos": 0, "es_importe": 0.0})
        o["no_aptos"] = o.get("no_aptos", 0) + 1; tocados.add(p["mes"]); p["no_apto"] = True; no_aptos += 1
    else:
        aplica(p, p["mes"], 1); nuevos += 1
    cont[i] = p
doc = {"meses": [{"mes": m, "origen": meses[m].get("origen", {}), "productos": meses[m].get("productos", [])} for m in sorted(tocados)],
       "contenidos": sorted(contenidos.values(), key=lambda c: -c.get("importe", 0))[:60]}
json.dump(doc, open(out_f, "w"), ensure_ascii=False, indent=1)
json.dump(cont, open(out_f + ".contados", "w"), ensure_ascii=False)
print(f"nuevos {nuevos} · restados {restados} · no aptos {no_aptos} · meses {sorted(tocados)} · ultimo_id {max(map(int, cont), default=0)}")
if raros: print("MONEDA SIN CAMBIO (sumada a 0):", raros)
