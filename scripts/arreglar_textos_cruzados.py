"""Repasa las carpetas cuyos textos se cruzaron al extraerlos.

Dos productos con el MISMO título en una carpeta es la firma de que el modelo
mezcló las imágenes de la tanda (ver `text_extractor`): la colchoneta acabó con
el nombre de una silla gaming y el error viajó a Top vendidos al copiarla.

Ojo: repetir título NO siempre es un error — el Drive del curso trae el mismo
producto varias veces. Por eso aquí se vuelve a extraer con el motor nuevo (que
reintenta los repetidos de uno en uno) y solo se guarda si el resultado tiene
MENOS duplicados que lo que había. Si el modelo insiste, es que eran el mismo
producto de verdad y no se toca nada.

    python scripts/arreglar_textos_cruzados.py            # solo mira
    python scripts/arreglar_textos_cruzados.py --aplicar  # guarda lo que mejore
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nicho_pov_bof.repos import product_repo  # noqa: E402
from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis  # noqa: E402
from src.nicho_pov_bof.services import text_extractor  # noqa: E402


def duplicados(productos: dict) -> dict[str, list[str]]:
    """`{titulo: [ids]}` de los títulos que se repiten en la carpeta."""
    por_titulo: dict[str, list[str]] = {}
    for pid, doc in productos.items():
        t = (doc.get("titulo") or "").strip().lower()
        if t:
            por_titulo.setdefault(t, []).append(pid)
    return {t: ids for t, ids in por_titulo.items() if len(ids) > 1}


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        print("Redis no configurado.")
        return 2

    # Se recorren las carpetas de cada fuente (no las claves de Redis: el
    # cliente no lista por patrón). Top vendidos queda fuera a propósito: sus
    # textos se copian del original, no se extraen.
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import drive_client, top_vendidos

    pendientes: list[tuple[str, str, dict]] = []
    for source in config.fuentes_a_barrer():
        if source == top_vendidos.SOURCE:
            continue
        try:
            carpetas = [c["name"] for c in drive_client.list_product_folders(source)]
        except Exception as e:  # noqa: BLE001
            print(f"no pude listar {source}: {e}")
            continue
        for folder in carpetas:
            doc = product_repo.load_folder(source, folder)
            dups = duplicados(doc.get("productos") or {})
            if dups:
                pendientes.append((source, folder, dups))

    print(f"{len(pendientes)} carpeta(s) con títulos repetidos\n")
    arregladas = intactas = fallidas = 0

    for source, folder, dups in pendientes:
        antes = sum(len(v) for v in dups.values())
        print(f"— {source}/{folder}: {antes} producto(s) con título repetido")
        try:
            nuevos = text_extractor.extract_folder_texts(
                source, folder, on_log=lambda m: print("   ", m),
            )
        except Exception as e:  # noqa: BLE001
            print(f"    no se pudo extraer: {e}")
            fallidas += 1
            continue
        if not nuevos:
            print("    sin textos nuevos, lo dejo como está")
            fallidas += 1
            continue

        despues = sum(len(v) for v in duplicados(nuevos).values())
        if despues >= antes:
            print(f"    sigue con {despues}: eran el mismo producto de verdad, no toco")
            intactas += 1
            continue

        print(f"    {antes} → {despues} repetidos: lo guardo")
        if aplicar:
            copia = Path("temp_work") / (
                f"backup_{source}_{folder}_{int(time.time())}.json".replace("/", "_")
            )
            copia.parent.mkdir(parents=True, exist_ok=True)
            copia.write_text(
                json.dumps(product_repo.load_folder(source, folder), ensure_ascii=False),
                encoding="utf-8",
            )
            product_repo.save_extracted_texts(source, folder, nuevos)
        arregladas += 1

    print(
        f"\nCarpetas arregladas: {arregladas} · sin cambios: {intactas} · "
        f"con fallo: {fallidas}"
        + ("" if aplicar else "  (en seco: repite con --aplicar)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
