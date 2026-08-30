"""Las plantillas de mensajes de cada operador.

Un documento por usuario (`plantillas:usuario:<quien>`) con la lista entera:
son cuatro textos, así que guardarlos juntos ahorra una lectura por plantilla y
deja el orden en manos del operador sin tener que llevar un índice aparte.

Por usuario y NO compartido a propósito: el mensaje habla en primera persona
(su nivel de creador, su GMV, su @), así que el de Ana no le sirve a Mauro.
"""

from __future__ import annotations

import time

from src.plantillas import config
from src.plantillas.repos.redis_base import get_plantillas_redis


def _key(usuario: str) -> str:
    # Sin sufijo es la de `ness`, igual que el progreso de los nichos: así el
    # histórico no se queda huérfano al meter el multiusuario.
    quien = (usuario or "").strip().lower()
    return f"usuario:{quien}" if quien and quien != "ness" else "usuario"


def listar(usuario: str = "") -> list[dict]:
    """Las plantillas del operador. La primera vez, las de fábrica.

    No se escriben al leer: el documento nace cuando el operador guarda algo.
    Así, si mañana se añade una plantilla nueva de fábrica, la ve todo el que
    no haya tocado las suyas.
    """
    r = get_plantillas_redis()
    if not r.is_available():
        return [dict(p) for p in config.PLANTILLAS_INICIALES]
    doc = r.get_json(_key(usuario)) or {}
    guardadas = doc.get("plantillas")
    if not isinstance(guardadas, list) or not guardadas:
        return [dict(p) for p in config.PLANTILLAS_INICIALES]
    return [p for p in guardadas if isinstance(p, dict) and p.get("id")]


def guardar(plantillas: list[dict], usuario: str = "") -> list[dict]:
    """Guarda la lista COMPLETA (la pantalla manda siempre el conjunto)."""
    r = get_plantillas_redis()
    if not r.is_available():
        raise RuntimeError("Redis no está configurado: no se puede guardar.")
    limpias = []
    for p in plantillas:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        texto = str(p.get("texto") or "").strip()
        if not pid or not texto:
            continue
        limpias.append({
            "id": pid,
            "titulo": str(p.get("titulo") or "").strip() or pid,
            "nota": str(p.get("nota") or "").strip(),
            "texto": texto,
        })
    if not r.set_json(_key(usuario), {"plantillas": limpias, "at": time.time()}):
        raise RuntimeError("Redis rechazó el guardado.")
    return limpias


def restaurar(usuario: str = "") -> list[dict]:
    """Vuelve a las de fábrica. Borra el documento en vez de reescribirlo: así
    las plantillas nuevas que se añadan al código también aparecen."""
    r = get_plantillas_redis()
    if r.is_available():
        r.delete(_key(usuario))
    return [dict(p) for p in config.PLANTILLAS_INICIALES]
