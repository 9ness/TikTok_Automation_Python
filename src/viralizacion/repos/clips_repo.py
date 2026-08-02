"""Propuestas de corte pendientes de revisar, por audio largo.

El análisis (Whisper + Gemini) tarda minutos y corre en la cola, así que la
propuesta tiene que sobrevivir a la petición HTTP que la pidió: se guarda aquí
y la UI la recoge cuando el job termina.

Schema (prefijo `viralizacion:`):
- `clips:<ponente>:<fichero>` -> {"clips": [...], "audio": "...", "at": ts}
- `clips:index`               -> SET de "<ponente>/<fichero>" con propuesta viva

Se borra al cortar: una propuesta ya aplicada solo estorba en la lista.
"""

from __future__ import annotations

import time

from src.viralizacion.repos.redis_base import get_viralizacion_redis

_INDEX = "clips:index"


def _require_redis():
    r = get_viralizacion_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar las "
            "propuestas de corte."
        )
    return r


def _key(ponente: str, fichero: str) -> str:
    return f"clips:{ponente}:{fichero}"


def _ref(ponente: str, fichero: str) -> str:
    return f"{ponente}/{fichero}"


def guardar(ponente: str, fichero: str, clips: list[dict]) -> None:
    r = _require_redis()
    r.set_json(_key(ponente, fichero), {
        "ponente": ponente,
        "fichero": fichero,
        "clips": clips,
        "at": time.time(),
    })
    r.sadd(_INDEX, _ref(ponente, fichero))


def get(ponente: str, fichero: str) -> dict | None:
    r = get_viralizacion_redis()
    if not r.is_available():
        return None
    doc = r.get_json(_key(ponente, fichero))
    return doc if isinstance(doc, dict) else None


def listar() -> list[dict]:
    """Todas las propuestas vivas, la más reciente primero."""
    r = get_viralizacion_redis()
    if not r.is_available():
        return []
    salida: list[dict] = []
    for ref in r.smembers(_INDEX):
        ponente, _, fichero = str(ref).partition("/")
        if not ponente or not fichero:
            continue
        doc = get(ponente, fichero)
        if doc:
            salida.append(doc)
        else:
            # Quedó la referencia pero no el documento (TTL, borrado a mano):
            # se limpia sola para que la lista no acumule fantasmas.
            r.srem(_INDEX, ref)
    salida.sort(key=lambda d: d.get("at") or 0, reverse=True)
    return salida


def borrar(ponente: str, fichero: str) -> None:
    r = get_viralizacion_redis()
    if not r.is_available():
        return
    r.delete(_key(ponente, fichero))
    r.srem(_INDEX, _ref(ponente, fichero))
