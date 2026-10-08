"""Cola de publicaciones.

- `pub:<id>`            documento de la publicación
- `pubs:pendientes`     SET de ids sin terminar (se ordenan por `programada_en`
                        al leer: el volumen es de decenas al día, no merece ZSET)
- `pubs:todas`          SET de todos los ids (histórico)
- `envios:<cuenta>:<plataforma>`  lista de timestamps de publicaciones reales,
                        para el límite de 24h móviles
"""

from __future__ import annotations

import time

from src.multiplataforma.models import Publicacion
from src.multiplataforma.repos import redis_base

_PENDIENTES = "pubs:pendientes"
_TODAS = "pubs:todas"
_DIA = 24 * 3600


def _key(pub_id: str) -> str:
    return f"pub:{pub_id}"


def get(pub_id: str) -> Publicacion | None:
    d = redis_base.get_redis().get_json(_key(pub_id))
    return Publicacion.from_dict(d) if d else None


def guardar(pub: Publicacion) -> Publicacion:
    pub.actualizada_en = time.time()
    r = redis_base.get_redis()
    r.set_json(_key(pub.id), pub.to_dict())
    r.sadd(_TODAS, pub.id)
    if pub.terminada:
        r.srem(_PENDIENTES, pub.id)
    else:
        r.sadd(_PENDIENTES, pub.id)
    return pub


def pendientes() -> list[Publicacion]:
    r = redis_base.get_redis()
    pubs = [p for p in (get(i) for i in r.smembers(_PENDIENTES)) if p]
    return sorted(pubs, key=lambda p: (p.programada_en, p.creada_en))


def todas(limite: int = 100) -> list[Publicacion]:
    r = redis_base.get_redis()
    pubs = [p for p in (get(i) for i in r.smembers(_TODAS)) if p]
    return sorted(pubs, key=lambda p: p.programada_en, reverse=True)[:limite]


def vencidas(ahora: float) -> list[Publicacion]:
    return [p for p in pendientes() if p.programada_en <= ahora]


def encolar(pub: Publicacion) -> tuple[Publicacion, bool]:
    """Guarda si no hay ya una pendiente con la misma clave. (pub, creada)."""
    for p in pendientes():
        if p.clave == pub.clave:
            return p, False
    return guardar(pub), True


# ---- límite de 24h ----
def _key_envios(cuenta: str, plataforma: str) -> str:
    return f"envios:{cuenta}:{plataforma}"


def envios_24h(cuenta: str, plataforma: str, ahora: float | None = None) -> int:
    ahora = time.time() if ahora is None else ahora
    marcas = redis_base.get_redis().get_json(_key_envios(cuenta, plataforma)) or []
    return sum(1 for t in marcas if ahora - float(t) < _DIA)


def registrar_envio(cuenta: str, plataforma: str, ahora: float | None = None) -> None:
    ahora = time.time() if ahora is None else ahora
    r = redis_base.get_redis()
    marcas = [t for t in (r.get_json(_key_envios(cuenta, plataforma)) or []) if ahora - float(t) < _DIA]
    marcas.append(ahora)
    r.set_json(_key_envios(cuenta, plataforma), marcas)
