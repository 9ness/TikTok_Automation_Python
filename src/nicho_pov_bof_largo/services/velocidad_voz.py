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
import time

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis

log = logging.getLogger("api")

_KEY = "velocidad_voz"

# `reference_id` → car/s medidos. Lo que no esté aquí usa la media del banco.
#
# Son velocidades NATURALES, sin acelerar. El acelerón ya no es fijo: se
# calcula por vídeo (lo justo para que la voz quepa en los clips, nunca tanto
# que baje del mínimo), así que meterlo aquí dejaría la tabla sin sentido.
# `apuntar` recibe el tempo usado y lo descuenta antes de guardar.
MEDIDAS_INICIALES: dict[str, float] = {
    "a0bd834b585944ba8200643a8b5dc405": 23.6,  # audio hombre vendedor
    "560b6e4e2e824ef5b87e8158544974af": 20.2,  # Voz de Influencer
    "d2ee7bb7cb3946d1b1994c1e4a6ff44e": 18.7,  # MY COMBOY (El vaqueroff)
    "c5a26d53f9fa41dc92479d065a2c9b8e": 18.3,  # Voz Vendedor Colombiano
    "51cdce697d8c4624b3135d473b4754e6": 17.7,  # Vendedor Amable
    "a67aae7d95154eecb6ad61c766de7afb": 17.5,  # Ely Bell's influencer
    "b08746cb224a4277a14b901c3591c3b9": 17.2,  # voz publicidad
    "ad03df9a92704fa9a0d931225754d057": 16.9,  # Vendedora (joven)
    "3fa82ba878ca4740ac6bba8ae0c38d76": 16.7,  # Voz Clara Influencer 1
    "77087ce820a74b2793a67371db067e89": 16.0,  # Luquitas Influencer
    "9ba6a6e4ecd84af58b7913f3944f54f2": 15.4,  # influencer
    # Medidas con el mismo guion de 236 caracteres el 20 ago 2026, antes de
    # meterlas en el banco. La de Renzo es la más lenta que hay.
    "6b66be3c8bda4c1cb59dc1446362b290": 19.6,  # Experto de Marketing
    "b8db28cc8d7e4be4a6fc2cce8a260ca5": 18.2,  # Voz Influencer Tuxpa Woman
    "7f44c1fdaef9471488d531e66aa01e9a": 17.4,  # Influencer 1 colombiana
    "79ec4c10f80e4e0592b6e2f86b650e22": 14.0,  # Vendedor Entusiasta (Renzo)
}

# Fuera de esta banda la medida es basura (el audio salió cortado, o el guion
# se cambió después de locutar) y no se apunta.
_MIN_CPS, _MAX_CPS = 10.0, 30.0
# Cuánto pesa lo nuevo frente a lo que había. Con 0,3 una medida rara mueve
# poco y diez medidas seguidas sí cambian la cifra.
_PESO_NUEVO = 0.3


# La tabla se lee EN BUCLE: estimar cuánto durará un vídeo prueba las ~19 voces
# del banco, y listar una carpeta hace eso dos veces por producto. Sin esto,
# pintar diez productos eran 420 lecturas de Redis —más de un minuto de espera—
# y todas devolviendo lo mismo, porque la tabla solo cambia cuando se monta un
# vídeo. Se guarda en memoria unos segundos; `apuntar` la tira al escribir.
_MEMO: tuple[float, dict[str, float]] | None = None
_MEMO_TTL_S = 30.0


def _guardadas() -> dict[str, float]:
    global _MEMO

    if _MEMO is not None and (time.monotonic() - _MEMO[0]) < _MEMO_TTL_S:
        return _MEMO[1]
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        return {}
    doc = r.get_json(_KEY) or {}
    medidas = {
        str(k): float(v) for k, v in doc.items() if _MIN_CPS <= float(v) <= _MAX_CPS
    }
    _MEMO = (time.monotonic(), medidas)
    return medidas


def olvidar_memo() -> None:
    """Tira la copia en memoria. La llama `apuntar` tras escribir."""
    global _MEMO

    _MEMO = None


def caracteres_por_segundo(voz: str = "") -> float:
    """Velocidad de esa voz (su `reference_id`). La media si no se sabe."""
    if not voz:
        return config.CARACTERES_POR_SEGUNDO
    medidas = {**MEDIDAS_INICIALES, **_guardadas()}
    return medidas.get(str(voz)) or config.CARACTERES_POR_SEGUNDO


def apuntar(voz: str, caracteres: int, segundos: float, tempo: float = 1.0) -> None:
    """Apunta lo que ha tardado de verdad. Nunca lanza: es telemetría.

    `segundos` es la duración FINAL, ya acelerada. Se descuenta el tempo para
    guardar la velocidad natural de la voz, que es con la que se razona: si se
    guardara la acelerada, la tabla diría cosas distintas según a qué velocidad
    tocó locutar ese día.
    """
    if not voz or caracteres <= 0 or segundos <= 0:
        return
    cps = caracteres / (segundos * max(0.01, tempo))
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
        # La copia en memoria se queda vieja justo cuando acaba de cambiar el
        # dato: se tira para que la siguiente estimación use lo recién medido.
        olvidar_memo()
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
