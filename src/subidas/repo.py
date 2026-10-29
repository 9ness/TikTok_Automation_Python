"""Contador diario de publicaciones (vídeos y carruseles) por usuario.

Un documento por usuario y mes (`subidas:<usuario>:<YYYY-MM>`):

    {"dias": {"2026-11-01": {"videos": 5, "carruseles": 15, "nota": "",
                             "actualizado": "2026-11-01T02:10:00+01:00"}}}

Lo escriben los agentes al terminar cada tanda de subida (MCP
`registrar_subidas`); la pantalla `/subidas` solo lo lee. Mismo patrón que
`src/estadisticas/repo.py`: cliente REST de las plantillas con prefijo propio.
"""

from __future__ import annotations

import calendar
import datetime as dt
import os
import zoneinfo

from src.plantillas.repos.redis_base import PlantillasRedis

ZONA = zoneinfo.ZoneInfo("Europe/Madrid")
MODOS = ("sumar", "fijar")

_INSTANCE: PlantillasRedis | None = None


def _redis() -> PlantillasRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = PlantillasRedis()
        _INSTANCE.prefix = os.getenv("SUBIDAS_REDIS_PREFIX", "subidas:")
    return _INSTANCE


def ahora() -> dt.datetime:
    return dt.datetime.now(ZONA)


def _key(usuario: str, mes: str) -> str:
    return f"{(usuario or '').strip().lower()}:{mes}"


def validar_mes(mes: str) -> str:
    """`YYYY-MM` válido o ValueError. Vacío = el mes de hoy (Madrid)."""
    mes = (mes or "").strip() or ahora().strftime("%Y-%m")
    try:
        dt.datetime.strptime(mes, "%Y-%m")
    except ValueError as e:
        raise ValueError(f"Mes no válido: {mes!r} (formato AAAA-MM).") from e
    return mes


def validar_fecha(fecha: str) -> str:
    """`YYYY-MM-DD` válida o ValueError. Vacía = hoy (Madrid)."""
    fecha = (fecha or "").strip() or ahora().strftime("%Y-%m-%d")
    try:
        dt.date.fromisoformat(fecha)
    except ValueError as e:
        raise ValueError(f"Fecha no válida: {fecha!r} (formato AAAA-MM-DD).") from e
    return fecha


def _dias(usuario: str, mes: str) -> dict:
    r = _redis()
    if not r.is_available():
        return {}
    doc = r.get_json(_key(usuario, mes)) or {}
    dias = doc.get("dias") if isinstance(doc, dict) else None
    return dias if isinstance(dias, dict) else {}


def _dias_transcurridos(mes: str, hoy: dt.date) -> int:
    """Días del mes que ya han empezado: todo el mes si es pasado, hasta hoy
    si es el actual y 0 si es futuro."""
    a, m = int(mes[:4]), int(mes[5:7])
    total = calendar.monthrange(a, m)[1]
    if (a, m) < (hoy.year, hoy.month):
        return total
    if (a, m) > (hoy.year, hoy.month):
        return 0
    return hoy.day


def leer_mes(usuario: str, mes: str = "") -> dict:
    """Días del mes (ordenados) y sus totales."""
    mes = validar_mes(mes)
    dias = _dias(usuario, mes)
    filas = [
        {"fecha": f, "videos": int(d.get("videos") or 0),
         "carruseles": int(d.get("carruseles") or 0),
         "nota": str(d.get("nota") or ""), "actualizado": d.get("actualizado") or ""}
        for f, d in sorted(dias.items()) if isinstance(d, dict)
    ]
    videos = sum(x["videos"] for x in filas)
    carruseles = sum(x["carruseles"] for x in filas)
    transcurridos = _dias_transcurridos(mes, ahora().date())
    total = videos + carruseles
    return {
        "usuario": usuario,
        "mes": mes,
        "dias": filas,
        "totales": {
            "videos": videos,
            "carruseles": carruseles,
            "total": total,
            "dias_con_subida": sum(1 for x in filas if x["videos"] or x["carruseles"]),
            "dias_transcurridos": transcurridos,
            "media_dia": {
                "videos": round(videos / transcurridos, 1) if transcurridos else 0,
                "carruseles": round(carruseles / transcurridos, 1) if transcurridos else 0,
                "total": round(total / transcurridos, 1) if transcurridos else 0,
            },
        },
    }


def registrar(usuario: str, *, fecha: str = "", videos: int = 0, carruseles: int = 0,
              nota: str | None = None, modo: str = "sumar") -> dict:
    """Apunta las publicaciones de un día. `sumar` las añade a lo que había
    (una tanda más); `fijar` pone el número exacto (corregir). La `nota`
    vacía deja la que había; con `sumar` se añade detrás y con `fijar` la
    sustituye. Devuelve el día y los totales del mes."""
    if modo not in MODOS:
        raise ValueError(f"Modo no válido: {modo!r} (sumar o fijar).")
    fecha = validar_fecha(fecha)
    for nombre, v in (("videos", videos), ("carruseles", carruseles)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"`{nombre}` tiene que ser un entero >= 0.")
    r = _redis()
    if not r.is_available():
        raise RuntimeError("Redis no está configurado.")
    mes = fecha[:7]
    dias = _dias(usuario, mes)
    previo = dias.get(fecha) if isinstance(dias.get(fecha), dict) else {}
    nota_previa = str(previo.get("nota") or "")
    nota = (nota or "").strip()
    if modo == "sumar":
        videos += int(previo.get("videos") or 0)
        carruseles += int(previo.get("carruseles") or 0)
        if nota and nota_previa:
            nota = f"{nota_previa} · {nota}"
    nota = nota or nota_previa
    dias[fecha] = {
        "videos": videos,
        "carruseles": carruseles,
        "nota": nota,
        "actualizado": ahora().isoformat(timespec="seconds"),
    }
    if not r.set_json(_key(usuario, mes), {"dias": dias}):
        raise RuntimeError("No se pudo guardar en Redis.")
    out = leer_mes(usuario, mes)
    out["dia"] = {"fecha": fecha, **dias[fecha]}
    return out
