"""En qué nicho cae cada producto, para saber qué personaje le toca.

Es una llamada de TEXTO —sobre los títulos ya extraídos, sin imágenes— y de
toda una carpeta de golpe, así que sale casi gratis: el mismo planteamiento que
el filtro de categoría del Nicho Carruseles.

Lo que decide no es la categoría comercial sino QUIÉN sale en el vídeo: unas
cápsulas de colágeno y una crema las vende la misma persona, aunque en una
tienda estén en pasillos distintos.
"""

from __future__ import annotations

from typing import Callable

from src.nicho_general import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None


def _prompt(productos: dict[str, str]) -> str:
    nichos = "\n".join(
        f'- {clave}: {meta["descripcion"]}' for clave, meta in config.NICHOS.items()
    )
    lista = "\n".join(f"{pid}. {titulo}" for pid, titulo in productos.items())
    return (
        "Clasifica cada producto de TikTok Shop según QUIÉN saldría en un "
        "vídeo vendiéndolo. No es la categoría de la tienda: lo que decide es "
        "qué tipo de persona lo usa y lo enseña.\n\n"
        f"Nichos:\n{nichos}\n\n"
        f"Productos:\n{lista}\n\n"
        "Devuelve SOLO un JSON con el número de cada producto y su nicho:\n"
        '{"1": "belleza", "2": "hogar", ...}\n'
        "Usa exactamente las claves de la lista. Si dudas entre dos, elige "
        "`generico`: un personaje que no pega se nota más que uno neutro."
    )


def clasificar(
    productos: dict[str, str], *, on_log: OnLog = _noop,
) -> dict[str, str]:
    """`{producto: nicho}` para los títulos que se le pasen.

    Lo que no se pueda clasificar se queda fuera del resultado en vez de
    inventarse un nicho: el caller decide si lo deja pendiente o lo manda a
    `generico`.
    """
    from src.tiktok_shop.api.gemini import generate_json

    productos = {k: v for k, v in productos.items() if (v or "").strip()}
    if not productos:
        return {}

    datos = generate_json(_prompt(productos), "")
    if not isinstance(datos, dict):
        raise ValueError(
            f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}"
        )

    salida: dict[str, str] = {}
    for pid in productos:
        crudo = str(datos.get(pid) or datos.get(str(pid)) or "").strip().lower()
        if crudo in config.NICHOS:
            salida[pid] = crudo
        elif crudo:
            # Se inventó un nombre: mejor genérico que un nicho que no existe.
            on_log(f"[nicho_general] nicho desconocido {crudo!r} en {pid}: va a genérico")
            salida[pid] = config.NICHO_DEFECTO
    faltan = [p for p in productos if p not in salida]
    if faltan:
        on_log(f"[nicho_general] sin clasificar: {', '.join(faltan)}")
    return salida
