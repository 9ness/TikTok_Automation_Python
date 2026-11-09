"""Horario de atención del bot (hora de España).

Formato de ``WHATSAPP_HORARIO``: tramos separados por ``;`` con los días
(1 = lunes … 7 = domingo) y la franja: ``12345=09:00-21:00;67=10:00-14:00``.
Vacío o ``siempre`` = abierto las 24 h. Un tramo que cruza la medianoche
(``22:00-02:00``) cuenta para el día en que empieza.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")

Tramo = tuple[set[int], int, int]  # días ISO, minuto de inicio, minuto de fin


def _minutos(hhmm: str) -> int:
    horas, _, mins = hhmm.strip().partition(":")
    valor = int(horas) * 60 + int(mins or 0)
    if not 0 <= valor <= 24 * 60:
        raise ValueError(f"hora fuera de rango: {hhmm!r}")
    return valor


def leer_horario(texto: str) -> list[Tramo]:
    """Convierte el texto en tramos. Lanza ValueError si está mal escrito."""
    texto = (texto or "").strip()
    if not texto or texto.lower() == "siempre":
        return []
    tramos: list[Tramo] = []
    for trozo in texto.split(";"):
        trozo = trozo.strip()
        if not trozo:
            continue
        dias_txt, sep, franja = trozo.partition("=")
        ini_txt, sep2, fin_txt = franja.partition("-")
        if not sep or not sep2:
            raise ValueError(f"tramo de horario mal escrito: {trozo!r}")
        dias = {int(d) for d in dias_txt.strip() if d.isdigit() and 1 <= int(d) <= 7}
        if not dias:
            raise ValueError(f"tramo sin días válidos: {trozo!r}")
        tramos.append((dias, _minutos(ini_txt), _minutos(fin_txt)))
    return tramos


def abierto(tramos: list[Tramo], ahora: datetime | None = None) -> bool:
    """True si a esa hora (por defecto, ahora en España) se atiende."""
    if not tramos:
        return True
    ahora = (ahora or datetime.now(ZONA)).astimezone(ZONA)
    minuto = ahora.hour * 60 + ahora.minute
    hoy = ahora.isoweekday()
    ayer = (ahora - timedelta(days=1)).isoweekday()
    for dias, ini, fin in tramos:
        if ini <= fin:
            if hoy in dias and ini <= minuto < fin:
                return True
        else:  # cruza la medianoche
            if (hoy in dias and minuto >= ini) or (ayer in dias and minuto < fin):
                return True
    return False
