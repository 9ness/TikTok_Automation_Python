"""Catálogo común de piezas de edición: flechas CTA y estilos de subtítulos.

Una sola lista (`catalogo.json`) que leen:
  - Editor Auto (`style_mapper`, `sticker_arrow`): qué flechas y estilos se
    ofrecen al cliente (`editor_auto: true`) y cómo se pintan.
  - TikTok Shop (`ready_video._ARROW_FILES`): rotación de flechas de las
    cuentas propias (`tiktok_shop: true`).
  - La web de Nebulabs Media: `scripts/catalogo_edicion.py web` le exporta
    las aprobadas con su vista previa.

Lo nuevo NO entra solo: un fichero que aparece en `Assets/flechas/` sin
estar aquí no se ofrece a nadie (`scripts/catalogo_edicion.py pendientes`).
Se aprueba a mano (`aprobar`), que es la revisión que pidió el dueño.

Campos de una flecha:
  fichero      nombre en `Assets/flechas/`
  grupo/color  para agrupar en la web (forma → color) sin saturar
  animacion    "bucle" (se repite mientras dura) | "entrada" (se reproduce
               UNA vez desde que aparece y se queda en el último fotograma:
               las de Navidad, que abren una caja y sacan la flecha)
  inteligente  entra en el sorteo del modo «Inteligente» (contraste)
  colocacion   {x, y, ancho} en % del vídeo: dónde va por defecto (las de
               Navidad están medidas para señalar el carrito de TikTok)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RUTA = Path(__file__).with_name("catalogo.json")


@lru_cache(maxsize=1)
def _cargar_cache(mtime: float) -> dict[str, Any]:
    return json.loads(RUTA.read_text(encoding="utf-8"))


def cargar() -> dict[str, Any]:
    try:
        return _cargar_cache(RUTA.stat().st_mtime)
    except (OSError, ValueError):
        return {"grupos_flecha": [], "flechas": [], "subtitulos": []}


def guardar(cat: dict[str, Any]) -> None:
    """Una pieza por línea: los diffs de aprobar/ocultar se leen solos."""
    out = ["{", f' "_leeme": {json.dumps(cat.get("_leeme", ""), ensure_ascii=False)},']
    claves = ("grupos_flecha", "flechas", "subtitulos")
    for i, k in enumerate(claves):
        out.append(f' "{k}": [')
        out.append(",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in cat.get(k, [])))
        out.append(" ]" + ("," if i < len(claves) - 1 else ""))
    out.append("}")
    RUTA.write_text("\n".join(out) + "\n", encoding="utf-8")
    _cargar_cache.cache_clear()


def flechas(destino: str | None = None) -> list[dict]:
    """Flechas del catálogo; con `destino` ("editor_auto" | "tiktok_shop")
    solo las aprobadas para ese uso, en el orden del fichero."""
    fl = cargar().get("flechas", [])
    if destino:
        fl = [f for f in fl if f.get(destino)]
    return list(fl)


def flecha(fichero: str) -> dict | None:
    return next((f for f in cargar().get("flechas", []) if f.get("fichero") == fichero), None)


def es_de_entrada(fichero: str) -> bool:
    f = flecha(fichero)
    return bool(f and f.get("animacion") == "entrada")


def subtitulos(destino: str | None = "editor_auto") -> list[dict]:
    s = cargar().get("subtitulos", [])
    if destino:
        s = [x for x in s if x.get(destino)]
    return list(s)


def estilo_subtitulos(preset_id: str) -> dict | None:
    """Claves del motor (`motor`) de un estilo, aprobado o no: un cliente que
    ya lo tenía guardado sigue saliendo igual aunque luego se oculte."""
    for x in cargar().get("subtitulos", []):
        if x.get("id") == preset_id:
            return x.get("motor")
    return None
