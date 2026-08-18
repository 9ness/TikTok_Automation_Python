"""Pasa las marcas del escaparate a la clave del título LITERAL.

La clave era `tienda|titulo`, y `titulo` lo REESCRIBE la IA (lo traduce y lo
resume a 5-9 palabras): cada vez que se re-extraían los textos salía distinto y
la marca se quedaba huérfana — se perdieron 439 de golpe al repasar el catálogo.

`titulo_tiktok_completo` es el título copiado letra a letra de la ficha, y ese
no cambia. Esto añade al índice la clave nueva de cada producto que HOY se ve
marcado (por índice viejo o por el flag de dentro del producto).

No borra nada: la clave vieja se sigue mirando al leer, así que se puede lanzar
sin miedo y es idempotente.

    docker exec tiktok-api sh -lc 'cd /app && PYTHONPATH=/app python3 scripts/migrar_escaparate_literal.py --aplicar'
"""

from __future__ import annotations

import sys

USUARIOS = ["", "ana", "mauro"]      # "" es el índice compartido (ness)


def _productos_pov(pov, config, drive_client) -> list[dict]:
    """Todos los productos del catálogo del curso, con sus textos."""
    salida: list[dict] = []
    for source in config.SOURCES:
        try:
            carpetas = drive_client.list_product_folders(source)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  {source}: no se pudo listar el Drive ({e})")
            continue
        for carpeta in carpetas:
            doc = pov.load_folder(source, carpeta["name"])
            salida.extend((doc.get("productos") or {}).values())
    return salida


def main(aplicar: bool) -> int:
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.repos import product_repo as pov
    from src.nicho_pov_bof.services import drive_client

    productos = _productos_pov(pov, config, drive_client)
    print(f"productos con textos: {sum(1 for p in productos if p.get('titulo'))}")

    total = 0
    for usuario in USUARIOS:
        indice = pov.escaparate_index(usuario)
        if not indice:
            continue
        nuevas: set[str] = set()
        sin_literal = 0
        for prod in productos:
            if not pov.marcado_en_escaparate(prod, indice):
                continue
            claves = pov.claves_escaparate(prod)
            if not claves:
                continue
            if not str(prod.get("titulo_tiktok_completo") or "").strip():
                sin_literal += 1
                continue
            if claves[0] not in indice:
                nuevas.add(claves[0])
        etiqueta = usuario or "ness"
        print(
            f"{etiqueta}: {len(indice)} marcas · {len(nuevas)} pasan a la clave"
            f" literal · {sin_literal} sin título literal (se quedan como estaban)"
        )
        if aplicar:
            for clave in nuevas:
                tienda, _, titulo = clave.partition("|")
                pov.set_escaparate(tienda, titulo, True, usuario)
        total += len(nuevas)
    print(f"{'Migradas' if aplicar else 'Se migrarían'}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--aplicar" in sys.argv))
