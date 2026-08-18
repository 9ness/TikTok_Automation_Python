"""Reengancha las marcas del escaparate que quedaron huérfanas.

La clave del índice es `tienda|titulo`. Cuando se vuelven a extraer los textos
y el modelo lee el título con otras palabras, la marca apunta a un nombre que
ya no existe y el producto sale SIN marcar. Pasó con cientos de golpe al
repasar el catálogo entero.

`save_extracted_texts` ya muda la marca al vuelo, así que esto es para las que
se quedaron por el camino antes de ese arreglo.

    docker exec tiktok-api sh -lc 'cd /app && PYTHONPATH=/app python3 scripts/reenganchar_escaparate.py'

Sin `--aplicar` solo cuenta. Es conservador a propósito: marcar de más hace que
el operador se salte un producto que NO está en el escaparate, y eso no se ve.
"""

from __future__ import annotations

import difflib
import sys

USUARIOS = ["", "ana", "mauro"]      # "" es el índice compartido (ness)
# Parecido mínimo con un producto de la MISMA tienda, y con cualquiera si la
# tienda tampoco cuadra. Y cuánto tiene que ganarle al segundo candidato: si
# dos productos de la marca se parecen igual, no se adivina.
MINIMO_MISMA_TIENDA = 0.85
MINIMO_OTRA_TIENDA = 0.93
MARGEN = 0.05


def _limpio(texto: str, pov) -> str:
    return " ".join(pov._normaliza(texto).split())


def _parecido(a: str, b: str) -> float:
    """Simétrico a propósito: con 'está contenido en', 'CC Cream SPF50+' daba
    1.00 contra 'CC Cream Oil Control SPF50+', que es OTRO producto."""
    ta = {x for x in a.split() if len(x) > 2}
    tb = {x for x in b.split() if len(x) > 2}
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    return max(difflib.SequenceMatcher(None, a, b).ratio(), jaccard)


def main(aplicar: bool) -> int:
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.repos import product_repo as pov
    from src.nicho_pov_bof.services import drive_client

    productos: list[dict] = []
    for source in config.SOURCES:
        try:
            carpetas = drive_client.list_product_folders(source)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  {source}: no se pudo listar el Drive ({e})")
            continue
        for carpeta in carpetas:
            doc = pov.load_folder(source, carpeta["name"])
            for pid, prod in (doc.get("productos") or {}).items():
                if prod.get("titulo"):
                    productos.append({
                        "folder": carpeta["name"], "pid": pid,
                        "tienda": prod.get("tienda", "") or "", "titulo": prod["titulo"],
                        "clave": pov.clave_escaparate(prod.get("tienda", ""), prod["titulo"]),
                    })

    total = 0
    for usuario in USUARIOS:
        indice = pov.escaparate_index(usuario)
        if not indice:
            continue
        vivas = {p["clave"] for p in productos}
        huerfanas = sorted(indice - vivas)
        nuevas: set[str] = set()
        dudosas = 0
        for h in huerfanas:
            tienda, _, titulo = h.partition("|")
            mismos = [p for p in productos if _limpio(p["tienda"], pov) == tienda]
            candidatos = mismos or productos
            minimo = MINIMO_MISMA_TIENDA if mismos else MINIMO_OTRA_TIENDA
            # Se puntúa por CLAVE: el mismo producto en dos carpetas da la
            # misma clave, así que no compiten entre ellos.
            mejor: dict[str, float] = {}
            for c in candidatos:
                r = _parecido(titulo, _limpio(c["titulo"], pov))
                mejor[c["clave"]] = max(mejor.get(c["clave"], 0.0), r)
            orden = sorted(mejor.items(), key=lambda kv: kv[1], reverse=True)
            if not orden:
                continue
            (clave, punt) = orden[0]
            segundo = orden[1][1] if len(orden) > 1 else 0.0
            if punt >= minimo and (punt - segundo) >= MARGEN:
                if clave not in indice:
                    nuevas.add(clave)
            elif punt >= 0.65:
                dudosas += 1
        etiqueta = usuario or "ness"
        print(
            f"{etiqueta}: {len(huerfanas)} huérfanas · {len(nuevas)} se reenganchan"
            f" · {dudosas} dudosas (a mano)"
        )
        if aplicar:
            for clave in nuevas:
                tienda, _, titulo = clave.partition("|")
                pov.set_escaparate(tienda, titulo, True, usuario)
        total += len(nuevas)
    print(f"{'Reenganchadas' if aplicar else 'Se reengancharían'}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--aplicar" in sys.argv))
