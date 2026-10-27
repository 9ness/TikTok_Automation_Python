# pedidos → origen por mes + contenidos. Fecha del pedido por su ID (crece con el tiempo):
# fecha_ms = (id >> 22) + OFFSET, OFFSET calibrado con pedidos de fecha conocida (Ver detalles).
import json, sys, re, datetime
from collections import defaultdict
ped = json.load(open(sys.argv[1])); OFFSET = int(sys.argv[2])
NOM = {"Vídeo": "Vídeo", "Carousel": "Carrusel", "Carrusel": "Carrusel", "LIVE": "LIVE", "Escaparate": "Escaparate"}
def eur(s):
    m = re.search(r"([\d.]+,\d+|\d+(?:\.\d+)?)\s*€|€\s*([\d.]+,\d+|\d+(?:\.\d+)?)", s or "")
    if not m: return 0.0
    v = m.group(1) or m.group(2)
    return float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
def uds(s):
    m = re.search(r"x\s*(\d+)", s or ""); return int(m.group(1)) if m else 1
origen = defaultdict(lambda: defaultdict(lambda: {"pedidos": 0, "importe": 0.0, "comision": 0.0, "es_pedidos": 0, "es_importe": 0.0}))
cont = {}
for p in ped:
    f = datetime.datetime.utcfromtimestamp(((int(p["id"]) >> 22) + OFFSET) / 1000)
    mes = f.strftime("%Y-%m")
    k = "Anuncios" if p.get("anuncio") else NOM.get(p.get("tipo"), p.get("tipo") or "Otros")
    imp = eur(p.get("importe")) * uds(p.get("importe")); com = eur(p.get("comision"))
    o = origen[mes][k]
    if "no apto" in (p.get("estado") or "").lower():   # «No apto»: pago fallido, devuelto… no da ni un euro
        o["no_aptos"] = o.get("no_aptos", 0) + 1; continue
    o["pedidos"] += 1; o["importe"] += imp; o["comision"] += com
    if p.get("pais") in (None, "ES"): o["es_pedidos"] += 1; o["es_importe"] += imp
    if k in ("Vídeo", "Carrusel"):
        c = cont.setdefault((k, p.get("caption", "")), {"caption": p.get("caption", ""), "tipo": k, "pedidos": 0, "importe": 0.0, "comision": 0.0})
        c["pedidos"] += 1; c["importe"] += imp; c["comision"] += com
r = lambda d: {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}
out = {"meses": [{"mes": m, "origen": {k: r(v) for k, v in o.items()}} for m, o in sorted(origen.items())],
       "contenidos": [r(c) for c in sorted(cont.values(), key=lambda c: -c["importe"])][:60]}
import os; json.dump(out, open(os.path.join(os.environ.get("EST_DIR", "/tmp/est"), "origen.json"), "w"), ensure_ascii=False, indent=1)
for m in out["meses"]: print(m["mes"], {k: (v["pedidos"], v["importe"]) for k, v in m["origen"].items()})
