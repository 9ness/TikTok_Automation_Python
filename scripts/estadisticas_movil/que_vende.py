"""Qué vende de verdad: producto × formato × lo publicado (Ama Shop y demás cuentas).

Cruza tres cosas que hasta ahora se miraban por separado:
  1. Lo publicado (Mis tandas: vídeos con su nicho/modo = FORMATO, y carruseles), con fecha de subida.
  2. Las ventas guardadas en la Factory (`ventas:<usuario>`: productos por mes y `contenidos` = pedidos por caption).
  3. Opcional: estadísticas de Studio por vídeo (`--studio fichero.json`, lista [{caption|video, estilo, vistas, clics}]),
     p. ej. lo apuntado en el panel con video_stats_lote.

Uso (en vps-trabajo):
    python3 -I scripts/estadisticas_movil/que_vende.py ana                 # informe en Markdown por pantalla
    python3 -I scripts/estadisticas_movil/que_vende.py ana --dias 14 --out informe.md --json datos.json
    python3 -I scripts/estadisticas_movil/que_vende.py --desde-fichero datos.json   # sin contenedor (re-análisis)

No imprime secretos ni gasta nada: solo lee Redis dentro del contenedor `tiktok-api`.
Las funciones de análisis son puras (tests en tests/test_que_vende.py).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict

ZONA = dt.timezone(dt.timedelta(hours=1))  # España en invierno; solo se usa para agrupar por día

# Palabras que no distinguen productos (ruido de títulos de TikTok Shop y captions).
VACIAS = {
    "de", "la", "el", "los", "las", "y", "con", "para", "en", "un", "una", "por", "del", "al", "mujer", "mujeres",
    "black", "friday", "nuevo", "nueva", "moda", "tiktokshop", "ofertasparati", "lo", "tienes", "carrito", "naranja",
    "que", "todo", "tu", "mi", "me", "es", "se", "su", "sus", "a", "o", "e", "di", "da", "mit", "von", "femme",
    "the", "and", "for", "with", "x", "t", "talla", "tallas",
}

# Ventas fuera de España llegan con el título traducido: se llevan a la palabra española.
TRADUCE = {"borsa": "bolso", "sac": "bolso", "tasche": "bolso", "bag": "bolso", "cabas": "tote",
           "nero": "negro", "noir": "negro", "schwarz": "negro"}


# ── Texto ──────────────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin hashtags, emojis ni signos."""
    t = re.sub(r"#\S+", " ", texto or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return " ".join(t.split())


def fichas(texto: str) -> set[str]:
    """Palabras significativas (≥3 letras, sin vacías ni números sueltos)."""
    palabras = (TRADUCE.get(w, w) for w in normalizar(texto).split())
    return {w for w in palabras if len(w) >= 3 and w not in VACIAS and not w.isdigit()}


def traducido(texto: str) -> bool:
    return any(w in TRADUCE for w in normalizar(texto).split())


def parecido(a: str, b: str) -> float:
    """Cuánto de `a` está en `b` (0..1). Asimétrico: `a` suele ser el título corto de la venta."""
    fa, fb = fichas(a), fichas(b)
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / len(fa)


def id_producto(url: str) -> str:
    m = re.search(r"/product/(\d+)", url or "")
    return m.group(1) if m else ""


# ── Formato ────────────────────────────────────────────────────────────────

def formato(v: dict) -> str:
    """Etiqueta de formato de un vídeo de Mis tandas (nicho + modo)."""
    nicho, modo = v.get("nicho") or "?", v.get("modo") or ""
    if nicho == "rv":
        return {"con_ia": "réplica viral Omni", "genjutsu": "réplica Genjutsu"}.get(modo, f"réplica {modo or 'sin IA'}")
    if nicho == "mm":
        return f"multimodo {modo.removeprefix('mm_')}" if modo else "multimodo"
    if nicho == "alea":
        return f"aleatorios {modo}" if modo else "aleatorios"
    if nicho == "pov":
        return "POV BOF"
    return f"{nicho} {modo}".strip()


# ── Agrupar lo publicado por producto ──────────────────────────────────────

def clave(item: dict) -> str:
    """Clave de producto: id de la URL de TikTok Shop o, si no hay, el título normalizado."""
    pid = id_producto(item.get("product_url", ""))
    if pid:
        return pid
    return "t:" + " ".join(sorted(fichas(item.get("titulo", ""))))[:80]


def publicados(datos: dict, desde: dt.date | None = None, hasta: dt.date | None = None) -> list[dict]:
    """Vídeos y carruseles subidos (con fecha) en el rango, en un formato común."""
    out = []
    for v in datos.get("videos", []):
        if not v.get("uploaded") or not v.get("uploaded_at"):
            continue
        out.append({"tipo": "Vídeo", "formato": formato(v), "fecha": _dia(v["uploaded_at"]), **_base(v)})
    for c in datos.get("carruseles", []):
        if not c.get("subido") or not c.get("subido_at"):
            continue
        out.append({"tipo": "Carrusel", "formato": "carrusel", "fecha": _dia(c["subido_at"]), **_base(c)})
    return [p for p in out if (desde is None or p["fecha"] >= desde) and (hasta is None or p["fecha"] <= hasta)]


def _base(x: dict) -> dict:
    return {"id": x.get("id", ""), "titulo": (x.get("titulo") or "").replace("\n", " "),
            "caption": x.get("caption", ""), "tienda": x.get("tienda", ""),
            "product_url": x.get("product_url", ""), "clave": clave(x)}


def _fecha(x) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def _dia(ts: float) -> dt.date:
    return dt.datetime.fromtimestamp(float(ts), ZONA).date()


def por_dia(pubs: list[dict]) -> dict[dt.date, dict[str, int]]:
    """Cuántos vídeos y carruseles se subieron cada día."""
    d: dict[dt.date, dict[str, int]] = defaultdict(lambda: {"Vídeo": 0, "Carrusel": 0})
    for p in pubs:
        d[p["fecha"]][p["tipo"]] += 1
    return dict(sorted(d.items()))


# ── Cruzar ventas ──────────────────────────────────────────────────────────

def mejor_pareja(texto: str, candidatos: list[dict], campos=("titulo", "caption"), umbral: float = 0.5) -> dict | None:
    """El publicado que más se parece a `texto` (título de venta o caption), o None si ninguno llega al umbral."""
    mejor, nota = None, umbral
    for c in candidatos:
        s = max(parecido(texto, c.get(k, "")) for k in campos)
        if s > nota or (s == nota and mejor is None and s >= umbral):
            mejor, nota = c, s
    return mejor


def ventas_por_producto(ventas: dict, todos_pubs: list[dict]) -> list[dict]:
    """Suma ventas/GMV de `meses[].productos` y las asocia a la clave de un producto publicado (si se encuentra)."""
    acc: dict[str, dict] = {}
    for mes in ventas.get("meses", []) or []:
        for pr in mes.get("productos", []) or []:
            titulo = pr.get("titulo", "")
            # Un título traducido (venta en IT/FR/DE) casa por palabras genéricas («bolso tote negro») con
            # cualquier bolso: se resuelve en la segunda pasada contra los títulos de venta en español.
            p = None if traducido(titulo) else mejor_pareja(titulo, todos_pubs)
            k = p["clave"] if p else "?:" + normalizar(titulo)[:60]
            a = acc.setdefault(k, {"clave": k, "titulos_venta": [], "ventas": 0, "gmv": 0.0, "paises": set(),
                                   "titulo": p["titulo"] if p else titulo, "encontrado": bool(p)})
            if titulo not in a["titulos_venta"]:
                a["titulos_venta"].append(titulo)
            a["ventas"] += int(pr.get("ventas") or 0)
            a["gmv"] += float(pr.get("gmv") or 0)
            if pr.get("pais"):
                a["paises"].add(pr["pais"])
    # Segunda pasada: una venta no localizada (p. ej. el mismo tote vendido en Italia con título en italiano)
    # se suma al producto localizado cuyo título de venta más se le parece.
    for k in [k for k, a in acc.items() if not a["encontrado"]]:
        a = acc[k]
        destino = max((b for b in acc.values() if b["encontrado"]),
                      key=lambda b: max(parecido(a["titulos_venta"][0], t) for t in b["titulos_venta"]), default=None)
        if destino and max(parecido(a["titulos_venta"][0], t) for t in destino["titulos_venta"]) >= 0.5:
            destino["titulos_venta"] += a["titulos_venta"]
            destino["ventas"] += a["ventas"]
            destino["gmv"] += a["gmv"]
            destino["paises"] |= a["paises"]
            del acc[k]
    for a in acc.values():
        a["gmv"] = round(a["gmv"], 2)
        a["paises"] = sorted(a["paises"])
    return sorted(acc.values(), key=lambda a: (-a["gmv"], -a["ventas"]))


def ventas_por_formato(ventas: dict, todos_pubs: list[dict]) -> dict[str, dict]:
    """Pedidos de `contenidos` (por caption) → formato del publicado con ese caption.

    Solo cuentan los publicados hasta `actualizado` (lo subido después no pudo vender esos pedidos). Si el mismo
    caption se usó en varios formatos, el pedido se reparte a partes iguales (no se sabe cuál vendió)."""
    corte = _fecha(ventas.get("actualizado"))
    if corte:
        todos_pubs = [p for p in todos_pubs if p["fecha"] <= corte]
    out: dict[str, dict] = defaultdict(lambda: {"pedidos": 0.0, "importe": 0.0, "captions": []})
    for c in ventas.get("contenidos", []) or []:
        cap = c.get("caption", "")
        iguales = [p for p in todos_pubs if parecido(cap, p["caption"]) >= 0.7 and parecido(p["caption"], cap) >= 0.5]
        formatos = sorted({p["formato"] for p in iguales}) or [f"sin localizar ({c.get('tipo', '?')})"]
        parte = 1 / len(formatos)
        for f in formatos:
            out[f]["pedidos"] += (c.get("pedidos") or 0) * parte
            out[f]["importe"] += float(c.get("importe") or 0) * parte
            out[f]["captions"].append(cap[:60])
    return {k: {**v, "pedidos": round(v["pedidos"], 2), "importe": round(v["importe"], 2)} for k, v in out.items()}


def con_studio(pubs: list[dict], studio: list[dict]) -> list[dict]:
    """Añade vistas/clics de Studio (por caption o id) a cada publicado. Devuelve una copia."""
    out = []
    for p in pubs:
        q = dict(p)
        for s in studio:
            if s.get("id") and s["id"] == p["id"] or (s.get("caption") and parecido(s["caption"], p["caption"]) >= 0.8):
                for k in ("vistas", "clics", "me_gusta", "ventas", "estilo"):
                    if k in s:
                        q[k] = s[k]
                break
        out.append(q)
    return out


def analizar(datos: dict, desde: dt.date | None = None, hasta: dt.date | None = None,
             studio: list[dict] | None = None) -> dict:
    todos = publicados(datos)
    rango = publicados(datos, desde, hasta)
    if studio:
        rango = con_studio(rango, studio)
    prods = ventas_por_producto(datos.get("ventas", {}), todos)
    n_por_clave: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in todos:
        n_por_clave[p["clave"]][p["formato"]] += 1
    for a in prods:
        fmts = n_por_clave.get(a["clave"], {})
        a["publicados"] = sum(fmts.values())
        a["formatos"] = dict(sorted(fmts.items(), key=lambda kv: -kv[1]))
        a["ventas_por_pub"] = round(a["ventas"] / a["publicados"], 2) if a["publicados"] else None
    fmt_pub: dict[str, int] = defaultdict(int)
    for p in todos:
        fmt_pub[p["formato"]] += 1
    fmt_ventas = ventas_por_formato(datos.get("ventas", {}), todos)
    formatos = []
    for f in sorted(set(fmt_pub) | set(fmt_ventas)):
        v = fmt_ventas.get(f, {"pedidos": 0, "importe": 0.0})
        n = fmt_pub.get(f, 0)
        formatos.append({"formato": f, "publicados": n, "pedidos": v["pedidos"], "importe": v["importe"],
                         "pedidos_por_100": round(100 * v["pedidos"] / n, 1) if n else None})
    formatos.sort(key=lambda x: (-x["importe"], -x["publicados"]))
    sin_venta = defaultdict(int)
    vendidos = {a["clave"] for a in prods}
    for p in todos:
        if p["clave"] not in vendidos:
            sin_venta[(p["clave"], p["titulo"][:60])] += 1
    return {
        "desde": desde, "hasta": hasta,
        "por_dia": por_dia(rango),
        "productos": prods,
        "formatos": formatos,
        "mas_publicados_sin_venta": sorted(((t, n) for (_, t), n in sin_venta.items()), key=lambda x: -x[1])[:10],
        "studio_top": sorted((p for p in rango if p.get("vistas") is not None), key=lambda p: -p["vistas"])[:5],
        "total_publicados": len(todos),
    }


# ── Informe ────────────────────────────────────────────────────────────────

def informe_md(r: dict, cuenta: str = "") -> str:
    L = [f"# Qué vende {cuenta}".rstrip(), ""]
    if r["desde"] or r["hasta"]:
        L.append(f"Subidas del {r['desde'] or '…'} al {r['hasta'] or '…'}; ventas: todo lo guardado en la Factory.")
        L.append("")
    L += ["## Subidas por día", "", "| Día | Vídeos | Carruseles |", "|---|---:|---:|"]
    for d, n in r["por_dia"].items():
        L.append(f"| {d:%a %d/%m} | {n['Vídeo']} | {n['Carrusel']} |")
    if not r["por_dia"]:
        L.append("| (nada marcado como subido en el rango) | | |")
    L += ["", "## Productos que venden", "", "| Producto | Ventas | GMV € | Publicados | Ventas/publicado | Formatos | Países |",
          "|---|---:|---:|---:|---:|---|---|"]
    for a in r["productos"]:
        fm = ", ".join(f"{k} ×{v}" for k, v in list(a["formatos"].items())[:3]) or "—"
        nom = a["titulo"][:50] + ("" if a["encontrado"] else " (no localizado en lo publicado)")
        vpp = "—" if a["ventas_por_pub"] is None else a["ventas_por_pub"]
        L.append(f"| {nom} | {a['ventas']} | {a['gmv']:.2f} | {a['publicados']} | {vpp} | {fm} | {' '.join(a['paises'])} |")
    L += ["", "## Formatos (pedidos por caption de Pedidos de afiliados)", "",
          "| Formato | Publicados | Pedidos | Importe € | Pedidos/100 pub. |", "|---|---:|---:|---:|---:|"]
    for f in r["formatos"]:
        p100 = "—" if f["pedidos_por_100"] is None else f["pedidos_por_100"]
        L.append(f"| {f['formato']} | {f['publicados']} | {f['pedidos']:g} | {f['importe']:.2f} | {p100} |")
    if r["mas_publicados_sin_venta"]:
        L += ["", "## Más publicados sin ninguna venta", ""]
        L += [f"- {t} — {n} publicados" for t, n in r["mas_publicados_sin_venta"]]
    if r["studio_top"]:
        L += ["", "## Top vistas (Studio)", ""]
        L += [f"- {p['titulo'][:50]} · {p['formato']} · {p.get('estilo', '')} · {p['vistas']} vistas · {p.get('clics', '—')} clics"
              for p in r["studio_top"]]
    L += ["", f"Total publicado registrado: {r['total_publicados']}. Pedidos repartidos a partes iguales si un caption se "
          "usó en varios formatos; los carruseles cuentan como formato «carrusel»."]
    return "\n".join(L) + "\n"


# ── Recogida (contenedor) ──────────────────────────────────────────────────

_CODIGO = r"""
import json
from src.mis_tandas import servicio as s, fotos as fo
from src.estadisticas import repo
u = %r
V = ("id","nicho","modo","titulo","caption","tienda","product_url","uploaded","uploaded_at")
C = ("id","titulo","caption","tienda","product_url","subido","subido_at","folder")
vids = [{k: f.get(k) for k in V} for f in s.filas(u)]
cars = []
for t in fo.tandas(u, todas=True).get("tandas", []):
    for it in t.get("items", []):
        cars.append({k: it.get(k) for k in C})
print(json.dumps({"usuario": u, "videos": vids, "carruseles": cars, "ventas": repo.leer(u)}, ensure_ascii=False, default=str))
"""


def recoger(usuario: str) -> dict:
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "PYTHONPATH=/app", "tiktok-api", "python", "-c",
                        _CODIGO % usuario], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("usuario", nargs="?", default="ana")
    ap.add_argument("--dias", type=int, default=7, help="días de subidas a mostrar (por defecto 7, hasta hoy)")
    ap.add_argument("--studio", help="JSON con estadísticas de Studio por vídeo")
    ap.add_argument("--desde-fichero", help="analizar un volcado guardado con --json en vez del contenedor")
    ap.add_argument("--json", help="guardar aquí el volcado crudo")
    ap.add_argument("--out", help="guardar el informe Markdown aquí")
    a = ap.parse_args(argv)
    datos = json.load(open(a.desde_fichero, encoding="utf-8")) if a.desde_fichero else recoger(a.usuario)
    if a.json:
        json.dump(datos, open(a.json, "w", encoding="utf-8"), ensure_ascii=False)
    hoy = dt.datetime.now(ZONA).date()
    studio = json.load(open(a.studio, encoding="utf-8")) if a.studio else None
    r = analizar(datos, hoy - dt.timedelta(days=a.dias - 1), hoy, studio)
    md = informe_md(r, datos.get("usuario", a.usuario))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
