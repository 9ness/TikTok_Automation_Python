"""Las estadísticas de ventas de TikTok Shop de un usuario.

Un documento por usuario (`estadisticas:ventas:<quien>`) con lo leído del
panel «Datos» de la app de TikTok (meses, días y productos con venta) y la
fecha de la última lectura. Lo escribe un agente leyendo el móvil; la pantalla
solo lo enseña y calcula al vuelo tasas, tipos y previsión.

Reusa el cliente REST de las plantillas con su propio prefijo: es el mismo
patrón de Upstash y no merece otra copia del wrapper.
"""

from __future__ import annotations

import os
import time

from src.plantillas.repos.redis_base import PlantillasRedis

_INSTANCE: PlantillasRedis | None = None


def _redis() -> PlantillasRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = PlantillasRedis()
        _INSTANCE.prefix = os.getenv("ESTADISTICAS_REDIS_PREFIX", "estadisticas:")
    return _INSTANCE


def _key(usuario: str) -> str:
    return f"ventas:{(usuario or '').strip().lower()}"


def leer(usuario: str) -> dict:
    r = _redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(usuario)) or {}


def guardar(usuario: str, doc: dict, *, fusionar: bool = True) -> dict:
    """Guarda lo leído. Con `fusionar`, meses y días se mezclan por clave con
    lo que ya había (una lectura de octubre no borra mayo)."""
    r = _redis()
    if not r.is_available():
        raise RuntimeError("Redis no está configurado.")
    previo = leer(usuario) if fusionar else {}
    out = {**previo, **{k: v for k, v in doc.items() if k not in ("meses", "dias")}}
    for campo, clave in (("meses", "mes"), ("dias", "fecha")):
        por = {x.get(clave): x for x in previo.get(campo) or [] if isinstance(x, dict)}
        for x in doc.get(campo) or []:
            if isinstance(x, dict) and x.get(clave):
                por[x[clave]] = {**por.get(x[clave], {}), **x}
        out[campo] = sorted(por.values(), key=lambda x: x.get(clave) or "")
    out.setdefault("actualizado", time.strftime("%Y-%m-%d"))
    if not r.set_json(_key(usuario), out):
        raise RuntimeError("No se pudo guardar en Redis.")
    return out
