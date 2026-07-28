"""Estado por producto: textos extraídos + Subido / Vendió.

Un documento por CARPETA de productos (no uno por producto): una carpeta son
10 productos y siempre se consultan juntos, así que agruparlos evita 10
lecturas a Upstash cada vez que se abre la pantalla. Mismo criterio que
`month_plan_repo` del calendario, que agrupa por mes.

Key: `nicho_pov_bof:folder:<source>:<carpeta>`
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis


def _key(source: str, folder: str) -> str:
    return f"folder:{source}:{folder}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar el "
            "estado del Nicho POV BOF."
        )
    return r


def load_folder(source: str, folder: str) -> dict:
    """Estado de una carpeta. `{}` si aún no se ha guardado nada."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(source, folder)) or {}


def save_folder(source: str, folder: str, data: dict) -> None:
    data["updated_at"] = _now()
    _require_redis().set_json(_key(source, folder), data)


def get_product(source: str, folder: str, producto: str) -> dict:
    return (load_folder(source, folder).get("productos") or {}).get(producto, {})


def update_product(source: str, folder: str, producto: str, **fields) -> dict:
    """Parche parcial sobre un producto. Devuelve el producto ya actualizado.

    Se lee-modifica-escribe el documento entero de la carpeta. Con 10
    productos y un solo operador no hay carrera real que justifique algo más
    complejo.
    """
    data = load_folder(source, folder)
    productos = data.setdefault("productos", {})
    prod = productos.setdefault(producto, {})
    prod.update({k: v for k, v in fields.items() if v is not None})

    # Marcar "vendió" implica que se subió: el estado contrario es imposible
    # y confundiría los recuentos.
    if prod.get("sold"):
        prod["uploaded"] = True

    prod["updated_at"] = _now()
    save_folder(source, folder, data)
    return prod


def save_extracted_texts(source: str, folder: str, textos: dict[str, dict]) -> None:
    """Guarda de golpe los textos de toda la carpeta (título, tienda, caption…).

    No pisa `uploaded`/`sold`: el operador puede re-extraer textos sin perder
    el progreso de subida.
    """
    data = load_folder(source, folder)
    productos = data.setdefault("productos", {})
    for prod_id, campos in textos.items():
        prod = productos.setdefault(prod_id, {})
        prod.update(campos)
        prod["textos_at"] = _now()
    data["textos_extraidos"] = True
    save_folder(source, folder, data)


def folder_summary(source: str, folder: str) -> dict:
    """Recuento para pintar la cabecera de la carpeta."""
    productos = (load_folder(source, folder).get("productos") or {})
    return {
        "total": len(productos),
        "uploaded": sum(1 for p in productos.values() if p.get("uploaded")),
        "sold": sum(1 for p in productos.values() if p.get("sold")),
        "con_textos": sum(1 for p in productos.values() if p.get("titulo")),
    }


def sold_products(source: str | None = None) -> list[dict]:
    """Productos marcados como vendidos, para el apartado de referencia.

    Recorre las carpetas que tengan estado guardado. Es una vista de consulta,
    no de uso intensivo, así que leer carpeta a carpeta es aceptable.
    """
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import drive_client

    out: list[dict] = []
    fuentes = [source] if source else list(config.SOURCES)
    for src in fuentes:
        try:
            carpetas = drive_client.list_product_folders(src)
        except Exception:
            continue
        for carpeta in carpetas:
            data = load_folder(src, carpeta["name"])
            for prod_id, prod in (data.get("productos") or {}).items():
                if prod.get("sold"):
                    out.append({
                        "source": src,
                        "folder": carpeta["name"],
                        "producto": prod_id,
                        **prod,
                    })
    return out
