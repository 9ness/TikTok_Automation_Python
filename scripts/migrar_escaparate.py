"""Pasa las marcas VIEJAS del escaparate al índice único.

Hasta que el escaparate pasó a ser único por producto, "metido en el
escaparate" era un flag dentro de cada producto de cada carpeta. Ese flag lo
sigue leyendo el Nicho POV BOF (para no perder lo ya marcado), pero los demás
nichos leen SOLO el índice — así que un producto marcado antes aparecía sin
marcar en Creativos Pro, en el Largo o en Cine. Que es justo lo que se vio: 119
marcas invisibles fuera del POV BOF.

Esto las copia al índice. Es idempotente (el índice es un SET) y no borra nada:
se puede volver a lanzar sin miedo.

    docker exec tiktok-api sh -lc 'cd /app && PYTHONPATH=/app python3 scripts/migrar_escaparate.py'

Con `--dry-run` solo cuenta, no escribe.
"""

from __future__ import annotations

import sys

# Los usuarios con progreso propio. El escaparate es de cada uno: Ana y Mauro
# son otras personas con su propia cuenta de TikTok.
USUARIOS = ["ness", "ana", "mauro"]


def main(dry_run: bool) -> int:
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.repos import product_repo as pov
    from src.nicho_pov_bof.services import drive_client

    total_migradas = 0
    for usuario in USUARIOS:
        indice = pov.escaparate_index(usuario)
        migradas = ya_estaban = sin_textos = 0
        for source in config.SOURCES:
            try:
                carpetas = drive_client.list_product_folders(source)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  {source}: no se pudo listar el Drive ({e})")
                continue
            for carpeta in carpetas:
                doc = pov.load_folder_para(source, carpeta["name"], usuario)
                for prod in (doc.get("productos") or {}).values():
                    if not prod.get("en_escaparate"):
                        continue
                    clave = pov.clave_escaparate(
                        prod.get("tienda", ""), prod.get("titulo", ""),
                    )
                    if not clave:
                        # Sin textos no hay con qué identificar el producto.
                        sin_textos += 1
                    elif clave in indice:
                        ya_estaban += 1
                    else:
                        if not dry_run:
                            pov.set_escaparate(
                                prod.get("tienda", ""), prod.get("titulo", ""),
                                True, usuario,
                            )
                            indice.add(clave)
                        migradas += 1
        total_migradas += migradas
        print(
            f"  {usuario:6} índice={len(indice):3} ya estaban={ya_estaban:3} "
            f"{'migrarían' if dry_run else 'migradas'}={migradas:3} "
            f"sin textos={sin_textos}"
        )
    return total_migradas


if __name__ == "__main__":
    seco = "--dry-run" in sys.argv
    print("SIMULACRO (no escribe)" if seco else "MIGRANDO")
    n = main(seco)
    print(f"\nTotal: {n} marca(s)")
