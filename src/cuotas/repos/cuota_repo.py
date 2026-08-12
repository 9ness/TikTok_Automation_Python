"""Cuánto se ha publicado hoy, por usuario.

Se guarda QUÉ se ha marcado, no un número suelto: un diccionario
`referencia -> hora`. Así:

- Marcar dos veces el mismo producto no suma dos (pasa: se toca el botón, no
  se ve el cambio y se vuelve a tocar).
- Desmarcar resta de verdad.
- Se sabe A QUÉ HORA se subió cada uno, que es lo que pidió el operador para
  comprobar que un producto repetido quedó bien marcado.

El día va en la CLAVE (`cuotas:<usuario>:<fecha>`), así que el contador se
reinicia solo a medianoche sin ninguna tarea programada: a las 00:00 la clave
es otra. La fecha se calcula en la zona del operador (ver `config.ZONA`).

`ajuste` es un número suelto que se suma al recuento: sirve para el día en que
se estrena esto (ya llevabas vídeos subidos y no estaban marcados) o para
cuadrar a mano si algo se cuenta de menos.

Key: `cuotas:<usuario>:<YYYY-MM-DD>` → {"videos": {ref: ts}, "carruseles": {…},
                                        "ajuste_videos": n, "ajuste_carruseles": n}
"""

from __future__ import annotations

import time

from src.cuotas import config
from src.cuotas.repos.redis_base import get_cuotas_redis

TIPOS = ("videos", "carruseles")


def _slug(usuario: str) -> str:
    return (usuario or "").strip() or "ness"


def _key(usuario: str, fecha: str = "") -> str:
    return f"{_slug(usuario)}:{fecha or config.hoy()}"


def _doc(usuario: str, fecha: str = "") -> dict:
    r = get_cuotas_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(usuario, fecha)) or {}


def _guardar(usuario: str, doc: dict, fecha: str = "") -> None:
    r = get_cuotas_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede llevar la cuenta "
            "de lo publicado hoy."
        )
    # Igual que en Creativos: una escritura que falla en silencio es peor que
    # un error, porque el contador sigue pintando un número que no existe.
    if not r.set_json(_key(usuario, fecha), doc):
        raise RuntimeError("Redis no aceptó guardar el contador del día.")


def marcar(tipo: str, referencia: str, usuario: str = "", subido: bool = True) -> dict:
    """Apunta (o quita) una publicación de hoy. Devuelve el resumen del día."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo debe ser {' o '.join(TIPOS)}, recibido: {tipo!r}")
    doc = _doc(usuario)
    marcados = dict(doc.get(tipo) or {})
    if subido:
        marcados[referencia] = time.time()
    else:
        marcados.pop(referencia, None)
    doc[tipo] = marcados
    _guardar(usuario, doc)
    return resumen(usuario)


def ajustar(tipo: str, valor: int, usuario: str = "") -> dict:
    """Fija el ajuste manual del día (lo subido fuera de la app)."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo debe ser {' o '.join(TIPOS)}, recibido: {tipo!r}")
    doc = _doc(usuario)
    doc[f"ajuste_{tipo}"] = max(0, int(valor))
    _guardar(usuario, doc)
    return resumen(usuario)


def hora_de(tipo: str, referencia: str, usuario: str = "") -> float:
    """Cuándo se marcó (0 si no está marcado hoy)."""
    return float((_doc(usuario).get(tipo) or {}).get(referencia) or 0)


def resumen(usuario: str = "") -> dict:
    """Lo publicado hoy con sus topes, listo para pintar la barra."""
    doc = _doc(usuario)
    salida = {"fecha": config.hoy(), "usuario": _slug(usuario)}
    topes = {
        "videos": (config.TOPE_VIDEOS, config.AVISO_VIDEOS),
        "carruseles": (config.TOPE_CARRUSELES, config.AVISO_CARRUSELES),
    }
    for tipo, (tope, aviso) in topes.items():
        marcados = doc.get(tipo) or {}
        ajuste = int(doc.get(f"ajuste_{tipo}") or 0)
        usados = len(marcados) + ajuste
        salida[tipo] = {
            "usados": usados,
            "marcados": len(marcados),
            "ajuste": ajuste,
            "tope": tope,
            "aviso": aviso,
            # `avisar` es lo que pinta la barra en ámbar: el operador quiere
            # frenar ANTES del tope, no al llegar.
            "avisar": usados >= aviso,
            "lleno": usados >= tope,
        }
    return salida
