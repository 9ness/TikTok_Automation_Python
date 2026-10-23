"""Enlaces de afiliado para Multiplataforma, desde la terminal del VPS.

Lo usa el agente diario (`~/multiplataforma/clasificar.sh`): lista los
productos de Mis tandas que aún no tienen enlace en ninguna cuenta de Meta y
guarda el que encuentre. Corre DENTRO del contenedor de la API (como el tick).

    python scripts/multiplataforma_enlaces.py pendientes [--n 25]
    python scripts/multiplataforma_enlaces.py guardar <cuenta> <producto_key> \
        (--asin B0XXXXXXXX | --shein URL | --sin-equivalente) --nota "…" [--temporada verano]
    python scripts/multiplataforma_enlaces.py carruseles
    python scripts/multiplataforma_enlaces.py encolar

`pendientes` saca un JSON por producto con la cuenta que le toca por nicho
(`carruseles.cuenta_para`: moda mujer → ama_shop, salud/belleza → viva_salud,
resto → viva_shop) y la foto copiada a `temp_work/multiplataforma_enlaces/`
(en el host: /mnt/HC_Volume_106974679/api_temp/multiplataforma_enlaces/).
Un producto de ness sale en viva_shop y en viva_salud: con enlace en una ya
cuenta como hecho.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from src.multiplataforma.repos import cuentas_repo, enlaces_repo
from src.multiplataforma.services import carruseles, tandas

FOTOS = Path("/app/temp_work/multiplataforma_enlaces")
FOTOS_HOST = "/mnt/HC_Volume_106974679/api_temp/multiplataforma_enlaces"


def pendientes(n: int) -> list[dict]:
    cuentas = {c.slug: c for c in cuentas_repo.listar() if c.activa and c.dueno}
    hechos: set[str] = set()
    for slug in cuentas:
        hechos |= set(enlaces_repo.todos(slug))  # con enlace o sin_equivalente
    vistos: set[str] = set()
    out = []
    for slug, c in cuentas.items():
        for p in tandas.productos(slug, sin_enlace=True)["productos"]:
            k = p["producto_key"]
            if k in hechos or k in vistos or not p["subidos_tiktok"]:
                continue
            vistos.add(k)
            # ama_shop solo tiene vídeos de Ana: todo lo suyo va ahí (SHEIN).
            destino = slug if slug == "ama_shop" else carruseles.cuenta_para(p["titulo"])
            if destino == "ama_shop" and slug != "ama_shop":
                destino = "viva_shop"  # moda de las cuentas de ness: Amazon en viva_shop
            out.append({"cuenta": destino, "tienda_afiliado": "shein" if destino == "ama_shop" else "amazon",
                        "producto_key": k, "titulo": p["titulo"], "tienda": p["tienda"],
                        "product_url": p["product_url"], "subidos_tiktok": p["subidos_tiktok"],
                        "ubicaciones": p["ubicaciones"][:3], "_fila": p["fila_id"], "_slug": slug})
    out.sort(key=lambda d: -d["subidos_tiktok"])
    out = out[:n]
    FOTOS.mkdir(parents=True, exist_ok=True)
    for d in out:
        try:
            src = tandas.foto_interna(cuentas[d["_slug"]], d.pop("_fila"), 600)
            dst = FOTOS / f"{d['producto_key']}{Path(str(src)).suffix or '.jpg'}"
            shutil.copyfile(src, dst)
            d["foto"] = f"{FOTOS_HOST}/{dst.name}"
        except Exception as e:  # noqa: BLE001 — sin foto: el agente mira la ficha de TikTok
            d["foto"] = ""
            d["foto_error"] = str(e)[:120]
        d.pop("_fila", None)
        d.pop("_slug", None)
    return out


def carruseles_pendientes() -> list[dict]:
    """Carruseles TERMINADOS que no están en ninguna cola porque a su producto
    le falta el enlace en la cuenta de su nicho (el tick los encola solo en
    cuanto lo tengan)."""
    from src.multiplataforma.repos import publicaciones_repo
    from src.replicar_viral import carrusel, servicio

    activas = {c.slug: c for c in cuentas_repo.listar() if c.activa}
    ya = {p.carrusel_id for p in publicaciones_repo.todas(limite=10**6) if p.tipo == "carrusel"}
    out = []
    for u in sorted({u for c in activas.values() for u in c.duenos()}):
        for f in servicio.lista(u, "carrusel", limite=0):
            if f["id"] in ya or not f.get("diapositivas") or f.get("hechas", 0) < f["diapositivas"]:
                continue
            prod = f.get("producto") or {}
            titulo = " ".join(str(prod.get("titulo") or "").split())
            slug = carruseles.cuenta_para(titulo)
            k = tandas.producto_key({"titulo": titulo, "tienda": prod.get("tienda", "")})
            if slug not in activas or enlaces_repo.todos(slug).get(k):
                continue
            base = carrusel.dir_replica(u, f["id"]) / "base"
            fotos = sorted(str(x).replace("/mnt/drive", "/home/nebulabsai/gdrive") for x in base.glob("*.jpg"))
            out.append({"tipo": "carrusel", "carrusel_id": f["id"], "usuario": u, "cuenta": slug,
                        "tienda_afiliado": "shein" if slug == "ama_shop" else "amazon",
                        "producto_key": k, "titulo": titulo, "tienda": prod.get("tienda", ""),
                        "product_url": prod.get("product_url", ""), "fotos": fotos[:3]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pendientes")
    p.add_argument("--n", type=int, default=25)
    g = sub.add_parser("guardar")
    g.add_argument("cuenta")
    g.add_argument("producto_key")
    g.add_argument("--asin", default="")
    g.add_argument("--shein", default="")
    g.add_argument("--sin-equivalente", action="store_true")
    g.add_argument("--nota", default="")
    g.add_argument("--temporada", default="")
    g.add_argument("--titulo", default="")
    sub.add_parser("carruseles")
    sub.add_parser("encolar")
    a = ap.parse_args()

    if a.cmd == "pendientes":
        print(json.dumps(pendientes(a.n), ensure_ascii=False, indent=1))
    elif a.cmd == "carruseles":
        print(json.dumps(carruseles_pendientes(), ensure_ascii=False, indent=1))
    elif a.cmd == "guardar":
        sin = "sin_equivalente" if a.sin_equivalente else ""
        kw = {"shein": a.shein or (sin if a.cuenta == "ama_shop" else ""),
              "asin": a.asin or (sin if a.cuenta != "ama_shop" else "")}
        r = tandas.guardar_enlace(a.cuenta, a.producto_key, nota=a.nota, temporada=a.temporada or None,
                                  titulo=a.titulo, **kw)
        print(json.dumps({k: r.get(k) for k in ("enlace", "sin_equivalente", "temporada")} if isinstance(r, dict) else r,
                         ensure_ascii=False))
    elif a.cmd == "encolar":
        out = {}
        for c in cuentas_repo.listar():
            if c.activa and c.dueno:
                inf = tandas.encolar(c.slug)
                out[c.slug] = {"encoladas": inf["total"], "omitidas": inf["omitidas"]}
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
