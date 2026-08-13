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
    """Fija el ajuste manual del día (lo subido fuera de la app).

    Admite NEGATIVOS: poner -3 resta tres al contador. Hace falta para cuando
    se marca de más (un producto tocado dos veces, algo que al final no se
    publicó), que antes no había forma de deshacer si ya no estaba marcado.

    El ajuste se guarda tal cual; lo que no puede bajar de cero es el TOTAL, y
    de eso se encarga `resumen`.
    """
    if tipo not in TIPOS:
        raise ValueError(f"tipo debe ser {' o '.join(TIPOS)}, recibido: {tipo!r}")
    doc = _doc(usuario)
    doc[f"ajuste_{tipo}"] = int(valor)
    _guardar(usuario, doc)
    return resumen(usuario)


def hora_de(tipo: str, referencia: str, usuario: str = "") -> float:
    """Cuándo se marcó (0 si no está marcado hoy)."""
    return float((_doc(usuario).get(tipo) or {}).get(referencia) or 0)


def resumen_mes(usuario: str = "", mes: str = "") -> dict:
    """Lo publicado cada día del mes, para el historial.

    `mes` en formato `YYYY-MM` (por defecto, el de hoy). Se leen los días de
    una tacada (`mget_json`): son 31 claves y pedirlas una a una hacía 31
    viajes a Redis para pintar un calendario.
    """
    from calendar import monthrange

    mes = mes or config.hoy()[:7]
    try:
        anio, num = int(mes[:4]), int(mes[5:7])
        dias = monthrange(anio, num)[1]
    except (ValueError, IndexError) as e:
        raise ValueError(f"mes debe ser YYYY-MM, recibido: {mes!r}") from e

    fechas = [f"{mes}-{d:02d}" for d in range(1, dias + 1)]
    r = get_cuotas_redis()
    docs = (
        r.mget_json([_key(usuario, f) for f in fechas])
        if r.is_available() else [None] * len(fechas)
    )

    salida = {"mes": mes, "usuario": _slug(usuario), "dias": [], "total": {}}
    totales = dict.fromkeys(TIPOS, 0)
    for fecha, doc in zip(fechas, docs):
        doc = doc or {}
        dia = {"fecha": fecha}
        for tipo in TIPOS:
            n = max(0, len(doc.get(tipo) or {}) + int(doc.get(f"ajuste_{tipo}") or 0))
            dia[tipo] = n
            totales[tipo] += n
        salida["dias"].append(dia)
    salida["total"] = totales
    salida["topes"] = {
        "videos": config.TOPE_VIDEOS, "carruseles": config.TOPE_CARRUSELES,
    }
    return salida


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
        # Nunca por debajo de cero: un ajuste negativo puede pasarse de lo que
        # hay marcado y un contador en -2 no significa nada.
        usados = max(0, len(marcados) + ajuste)
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
