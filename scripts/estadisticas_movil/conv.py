# junta m_2026-*.json en el doc de estadísticas (números + tipo)
import json, glob, re, sys
import os as _os
W = _os.environ.get("EST_DIR", "/tmp/est"); _os.makedirs(W, exist_ok=True)
def n(s):
    if s is None or s == "": return None
    s = str(s).replace("€", "").replace(" ", "").strip()
    mult = 1
    if s.endswith("K"): mult, s = 1000, s[:-1]
    if s.endswith("M"): mult, s = 1_000_000, s[:-1]
    s = s.replace(".", "").replace(",", ".") if mult == 1 else s.replace(",", ".")
    return round(float(s) * mult, 2)
TIPOS = [
 ("Suplementos", r"creatin|whey|prote[ií]n|gumm|gominola|vitamin|col[aá]geno|magnesio|omega|suplement|ashwag|melaton|pre.?entreno|bcaa"),
 ("Belleza y cuidado", r"crema|cr[eè]me|s[eé]rum|cc cream|champ[uú]|cabello|pelo|maquill|perfume|facial|piel|depil|haarverw|gezicht|u[ñn]as|cosm|labial|rizador|secador|plancha de pelo|cepillo"),
 ("Calzado", r"zapat|zueco|crocs|sneaker|bota|sandalia|chancl|schuh|scarpe|chaussure"),
 ("Ropa", r"camiset|pantal|short|sudadera|chaqueta|vestido|leggin|mallas|calcet|ropa interior|intimo|sous-v[eê]tement|unterw|underwear|boxer|sujetador|abrigo|jersey|camisa|bikini|pijama|gorra"),
 ("Muebles", r"silla|divano|matelas|chaise|sedia|sill[oó]n|stuhl|sof[aá]|mesa|escritorio|estanter|zapatero|meuble|mueble|armario|c[oó]moda|cama|colch[oó]n|taburete|banco"),
 ("Jardín y exterior", r"jard[ií]n|garten|gazebo|carpa|camping|playa|paddle|sup |piscina|barbacoa|tumbona|carro|carrito|cart|chariot|wagen|manguera|cortac[eé]sped"),
 ("Cocina", r"cocina|sart[eé]n|olla|freidora|vac[ií]o|vakuum|sottovuoto|cafeter|batidora|licuad|cuchill|tupper|horno|termo|botella|vaso|plato|airfryer|robot de cocina"),
 ("Electrónica", r"auricular|cargador|cable|altavoz|smart|reloj inteligente|c[aá]mara|proyector|tablet|m[oó]vil|bater[ií]a|power ?bank|led|l[aá]mpara|bombilla|ventilador|aspirador|robot|volant|steering|racing|gaming|teclado|rat[oó]n|monitor|philips"),
 ("Hogar", r"alfombra|rug|cortina|coj[ií]n|manta|edred[oó]n|toalla|tendedero|basura|cubo|organizador|almacen|limpi|fregona|percha|espejo|reloj|decoraci|vela|ba[ñn]o|bains|esterilizador"),
 ("Deporte y fitness", r"gym|fitness|deport|yoga|pesa|mancuern|bici|bicicleta|vibraci|vibration|v[eé]lo|correr|running|el[aá]stic|entrena"),
 ("Bricolaje", r"herramienta|engaste|taladro|tool|werkzeug|outil"),
 ("Alimentación", r"matcha|t[eé] |caf[eé]|aceite de oliva|chocolate|miel"),
 ("Navidad y fiestas", r"navidad|weihnacht|no[eë]l|natale|christmas|disfraz|halloween|m[aá]scara"),
 ("Coche", r"coche|car |salpicadero|auto |veh[ií]culo"),
 ("Viaje", r"maleta|reisetasche|mochila|equipaje|neceser|koffer|valigia"),
 ("Salud y bienestar", r"aroma|aceite esencial|masaje|ohrenschmalz|o[ií]dos|masajead|ortop|tens|inhalador|termómetro|tensi[oó]metro"),
 ("Bebé y niños", r"beb[eé]|ni[ñn]o|infantil|juguete|momcozy|cochecito|pa[ñn]al"),
 ("Mascotas", r"perro|gato|mascota|katze|hund|chat |\bpet"),
]
def tipo(t):
    tl = t.lower()
    for nom, rx in TIPOS:
        if re.search(rx, tl): return nom
    return "Otros"
meses = []
for f in sorted(glob.glob(f"{W}/m_2026-*.json")):
    d = json.load(open(f))
    m = {"mes": d["mes"]}
    for k in ("gmv", "ventas", "impresiones", "clics", "comision", "gmv_comision", "art_comision", "base_comision"):
        if d.get(k) is not None: m[k] = n(d[k])
    m["productos"] = [{"titulo": p["titulo"], "pais": p["pais"], "gmv": n(p["gmv"]), "ventas": int(n(p["ventas"]) or 0),
                       "tipo": tipo(p["titulo"])} for p in d.get("productos", []) if (n(p["gmv"]) or 0) > 0 and "~tplv" not in p["titulo"]]
    meses.append(m)
json.dump({"meses": meses}, open(f"{W}/doc.json", "w"), ensure_ascii=False, indent=1)
for m in meses:
    print(m["mes"], m.get("gmv"), m.get("ventas"), m.get("clics"), len(m["productos"]),
          sum(1 for p in m["productos"] if p["tipo"] == "Otros"))
if "-o" in sys.argv:
    for m in meses:
        for p in m["productos"]:
            if p["tipo"] == "Otros": print("  OTROS", p["titulo"][:90])
