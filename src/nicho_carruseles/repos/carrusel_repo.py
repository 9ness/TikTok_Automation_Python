"""Lo que este nicho sabe de cada producto: si vale para carrusel y sus dos
mensajes.

Un documento por CARPETA, no uno por producto — misma razón que en
`nicho_pov_bof.repos.product_repo`: una carpeta son diez productos y siempre se
miran juntos.

Key: `nicho_carruseles:folder:<source>:<carpeta>`

Es COMPARTIDO entre usuarios a propósito. La categoría del producto y los dos
mensajes son datos objetivos que cuestan llamadas a Gemini; que Ana clasifique
una carpeta y Mauro tenga que volver a pagarla sería tirar cuota. Lo de cada
uno —qué ha subido, qué fotos ha generado, por qué carpeta va— vive aparte
(`subidos_repo`, `progress_repo`, y las fotos en su carpeta del Drive).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.nicho_carruseles import config
from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis


def _key(source: str, folder: str) -> str:
    # La fuente se canoniza igual que en el POV BOF: leer una carpeta desde la
    # copia de seguridad es leer LA MISMA carpeta del curso.
    return f"folder:{config.fuente_canonica(source)}:{folder}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_carruseles_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar el "
            "estado del Nicho Carruseles."
        )
    return r


def load_folder(source: str, folder: str) -> dict:
    """Estado de la carpeta. `{}` si nunca se ha tocado."""
    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(source, folder)) or {}


def productos(source: str, folder: str) -> dict[str, dict]:
    return dict(load_folder(source, folder).get("productos") or {})


def save_folder(source: str, folder: str, data: dict) -> None:
    data["updated_at"] = _now()
    _require_redis().set_json(_key(source, folder), data)


def update_product(source: str, folder: str, producto: str, **campos) -> dict:
    data = load_folder(source, folder)
    prods = data.setdefault("productos", {})
    prod = prods.setdefault(str(producto), {})
    prod.update({k: v for k, v in campos.items() if v is not None})
    prod["updated_at"] = _now()
    save_folder(source, folder, data)
    return prod


def guardar_categorias(source: str, folder: str, cats: dict[str, str]) -> dict[str, dict]:
    """Guarda de golpe la categoría de toda la carpeta.

    No pisa el interruptor manual (`apto`): si el operador ya dijo a mano que
    un producto vale, volver a clasificar la carpeta no se lo quita.
    """
    data = load_folder(source, folder)
    prods = data.setdefault("productos", {})
    for pid, categoria in cats.items():
        prod = prods.setdefault(str(pid), {})
        prod["categoria"] = categoria
        prod["categoria_at"] = _now()
    data["clasificada"] = True
    save_folder(source, folder, data)
    return prods


def guardar_mensajes(source: str, folder: str, mensajes: dict[str, dict]) -> dict[str, dict]:
    """Guarda los dos mensajes de cada producto de la carpeta."""
    data = load_folder(source, folder)
    prods = data.setdefault("productos", {})
    for pid, doc in mensajes.items():
        prod = prods.setdefault(str(pid), {})
        for campo in ("mensaje1", "mensaje2"):
            valor = str(doc.get(campo) or "").strip()
            if valor:
                prod[campo] = valor
        prod["mensajes_at"] = _now()
    save_folder(source, folder, data)
    return prods


def es_apto(prod: dict) -> bool:
    """¿Este producto vale para carrusel?

    Manda el interruptor manual si está puesto (`apto` True/False); si no, la
    categoría que dijo la IA. Sin clasificar todavía = no apto, para que la
    pantalla no se llene de productos que nadie ha mirado.
    """
    manual = prod.get("apto")
    if isinstance(manual, bool):
        return manual
    return str(prod.get("categoria") or "") in config.CATEGORIAS_APTAS


def escenario_de(prod: dict) -> str:
    """Dónde tiene que estar la chica de la foto 1 de este producto.

    Sale de la categoría (un colchón pide cama, un sofá pide sofá), y el
    operador puede forzarlo a mano. Un producto que él marcó apto pero que la IA
    dejó en `otro` se lleva el escenario genérico: es el que vale para todo.
    """
    manual = str(prod.get("escenario") or "")
    if manual in config.ESCENARIOS:
        return manual
    categoria = str(prod.get("categoria") or "")
    return config.ESCENARIO_POR_CATEGORIA.get(categoria, "generico")
