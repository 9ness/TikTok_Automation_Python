"""A qué velocidad locuta cada voz, medido con los vídeos ya montados.

El guion se escribe ANTES de saber qué voz va a locutarlo, así que la duración
hay que estimarla por caracteres. Con una sola cifra para todas se falla por
mucho: sobre 20 vídeos medidos, la misma frase da 23,6 car/s con "audio hombre
vendedor" y 15,4 con "influencer" — un guion de 350 caracteres son 15s con una
y 23s con la otra, y de eso depende cuántos clips hay que generar.

Aquí se guarda la velocidad de cada voz y se AFINA sola: cada vídeo montado
apunta (caracteres del guion / duración real del audio) y se promedia con lo
que había. Cuantos más vídeos, mejor la estimación — sin tocar código.

Las cifras de arranque salen de medir los 20 primeros vídeos del nicho.
"""

from __future__ import annotations

import logging

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis

log = logging.getLogger("api")

_KEY = "velocidad_voz"

# `reference_id` → car/s medidos. Lo que no esté aquí usa la media del banco.
#
# OJO: estas cifras YA incluyen el acelerón de `config.VOZ_TEMPO`. Se midieron
# sin él y se multiplicaron una vez al ponerlo, porque si no el filtro de voces
# creería que van más lentas de lo que van y descartaría voces que sí caben.
# Las que se apunten a partir de ahora salen medidas del audio final, así que
# ya lo llevan dentro sin hacer nada.
MEDIDAS_INICIALES: dict[str, float] = {
    "a0bd834b585944ba8200643a8b5dc405": 26.0,  # audio hombre vendedor
    "560b6e4e2e824ef5b87e8158544974af": 22.2,  # Voz de Influencer
    "d2ee7bb7cb3946d1b1994c1e4a6ff44e": 20.6,  # MY COMBOY (El vaqueroff)
    "c5a26d53f9fa41dc92479d065a2c9b8e": 20.1,  # Voz Vendedor Colombiano
    "51cdce697d8c4624b3135d473b4754e6": 19.5,  # Vendedor Amable
    "a67aae7d95154eecb6ad61c766de7afb": 19.2,  # Ely Bell's influencer
    "b08746cb224a4277a14b901c3591c3b9": 18.9,  # voz publicidad
    "ad03df9a92704fa9a0d931225754d057": 18.6,  # Vendedora (joven)
    "3fa82ba878ca4740ac6bba8ae0c38d76": 18.4,  # Voz Clara Influencer 1
    "77087ce820a74b2793a67371db067e89": 17.6,  # Luquitas Influencer
    "9ba6a6e4ecd84af58b7913f3944f54f2": 16.9,  # influencer
    # Medidas con el mismo guion de 236 caracteres el 20 ago 2026, antes de
    # meterlas en el banco. La de Renzo es la más lenta que hay.
    "6b66be3c8bda4c1cb59dc1446362b290": 21.6,  # Experto de Marketing
    "b8db28cc8d7e4be4a6fc2cce8a260ca5": 20.0,  # Voz Influencer Tuxpa Woman
    "7f44c1fdaef9471488d531e66aa01e9a": 19.1,  # Influencer 1 colombiana
    "79ec4c10f80e4e0592b6e2f86b650e22": 15.4,  # Vendedor Entusiasta (Renzo)
}

# Fuera de esta banda la medida es basura (el audio salió cortado, o el guion
# se cambió después de locutar) y no se apunta.
_MIN_CPS, _MAX_CPS = 10.0, 30.0
# Cuánto pesa lo nuevo frente a lo que había. Con 0,3 una medida rara mueve
# poco y diez medidas seguidas sí cambian la cifra.
_PESO_NUEVO = 0.3


def _guardadas() -> dict[str, float]:
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        return {}
    doc = r.get_json(_KEY) or {}
    return {str(k): float(v) for k, v in doc.items() if _MIN_CPS <= float(v) <= _MAX_CPS}


def caracteres_por_segundo(voz: str = "") -> float:
    """Velocidad de esa voz (su `reference_id`). La media si no se sabe."""
    if not voz:
        return config.CARACTERES_POR_SEGUNDO
    medidas = {**MEDIDAS_INICIALES, **_guardadas()}
    return medidas.get(str(voz)) or config.CARACTERES_POR_SEGUNDO


def apuntar(voz: str, caracteres: int, segundos: float) -> None:
    """Apunta lo que ha tardado de verdad. Nunca lanza: es telemetría."""
    if not voz or caracteres <= 0 or segundos <= 0:
        return
    cps = caracteres / segundos
    if not _MIN_CPS <= cps <= _MAX_CPS:
        return
    try:
        r = get_nicho_pov_bof_largo_redis()
        if not r.is_available():
            return
        doc = r.get_json(_KEY) or {}
        previa = float(doc.get(str(voz)) or MEDIDAS_INICIALES.get(str(voz)) or 0)
        doc[str(voz)] = round(
            cps if not previa else previa * (1 - _PESO_NUEVO) + cps * _PESO_NUEVO, 2
        )
        r.set_json(_KEY, doc)
    except Exception as e:  # noqa: BLE001
        log.warning("no se pudo apuntar la velocidad de la voz: %s", e)


def tabla() -> list[dict]:
    """Lo medido de cada voz, para poder mirarlo."""
    medidas = {**MEDIDAS_INICIALES, **_guardadas()}
    etiquetas = {
        v["id"]: v["label"] for sexo in config.VOCES for v in config.VOCES[sexo]
    }
    return sorted(
        (
            {"id": vid, "label": etiquetas.get(vid, vid), "car_s": cps}
            for vid, cps in medidas.items()
        ),
        key=lambda x: -x["car_s"],
    )
