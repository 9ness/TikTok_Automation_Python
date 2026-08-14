"""Fusiona las ventas apuntadas en "Top vendidos" con su producto de origen.

Hasta ahora, marcar una venta desde la carpeta de Top vendidos guardaba la
entrada con la referencia de la COPIA (`top_vendidos|carpeta|producto`) en vez
de la del producto del curso. Consecuencias: el mismo producto salía dos veces
en el ranking y —lo que se notó— el listado de Top vendidos no veía esas
ventas, así que el orden "los que más venden primero" no cambiaba.

El código ya no las escribe así (`product_repo._ref_vendido`), y el listado las
suma para no perderlas. Esto limpia las que quedaron: suma sus unidades a la
entrada de origen y borra la copia.

    docker compose exec api python scripts/fusionar_vendidos_top.py            # solo mira
    docker compose exec api python scripts/fusionar_vendidos_top.py --aplicar  # lo hace
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nicho_pov_bof.repos import product_repo  # noqa: E402
from src.nicho_pov_bof.services import top_vendidos  # noqa: E402


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    r = product_repo._require_redis()  # noqa: SLF001
    refs = [str(x) for x in (r.smembers(product_repo._VENDIDOS_INDEX) or [])]  # noqa: SLF001
    huerfanas = [x for x in refs if x.startswith(f"{top_vendidos.SOURCE}|")]
    if not huerfanas:
        print("No hay ventas apuntadas en Top vendidos. Nada que fusionar.")
        return 0

    print(f"{len(huerfanas)} venta(s) apuntadas en la copia:\n")
    for ref in huerfanas:
        _, carpeta, producto = ref.split("|", 2)
        copia = r.get_json(product_repo._key_vendido(ref)) or {}  # noqa: SLF001
        origen = top_vendidos.origen_de(carpeta, producto)
        unidades = int(copia.get("unidades") or 1)
        titulo = (copia.get("titulo") or "")[:50]
        if not origen:
            print(f"  {ref} · {unidades}u · {titulo} → SIN ORIGEN en el manifiesto (se deja)")
            continue
        ref_origen = f"{origen['source']}|{origen['folder']}|{origen['producto']}"
        doc = r.get_json(product_repo._key_vendido(ref_origen)) or {}  # noqa: SLF001
        total = int(doc.get("unidades") or 0) + unidades
        print(f"  {ref} · {unidades}u · {titulo} → {ref_origen} (quedará en {total}u)")
        if not aplicar:
            continue
        if doc:
            doc["unidades"] = total
            doc["vendido_at"] = min(
                float(doc.get("vendido_at") or 0) or float(copia.get("vendido_at") or 0),
                float(copia.get("vendido_at") or 0) or float(doc.get("vendido_at") or 0),
            )
        else:
            # No estaba en el ranking: se queda la copia, pero con la
            # referencia del original.
            doc = {**copia, **origen, "unidades": unidades}
        r.set_json(product_repo._key_vendido(ref_origen), doc)  # noqa: SLF001
        r.sadd(product_repo._VENDIDOS_INDEX, ref_origen)  # noqa: SLF001
        r.delete(product_repo._key_vendido(ref))  # noqa: SLF001
        r.srem(product_repo._VENDIDOS_INDEX, ref)  # noqa: SLF001

    print("\nHecho." if aplicar else "\nEn seco: repite con --aplicar para hacerlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
