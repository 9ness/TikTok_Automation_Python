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


def leer(usuario: str = "") -> dict:
    """`{plantillas, valores}` del operador. La primera vez, las de fábrica.

    No se escribe al leer: el documento nace cuando el operador guarda algo.
    Así, si mañana se añade una plantilla nueva de fábrica, la ve todo el que
    no haya tocado las suyas.
    """
    de_fabrica = {
        "plantillas": [dict(p) for p in config.PLANTILLAS_INICIALES],
        "valores": {},
    }
    r = get_plantillas_redis()
    if not r.is_available():
        return de_fabrica
    doc = r.get_json(_key(usuario)) or {}
    guardadas = doc.get("plantillas")
    valores = doc.get("valores")
    if not isinstance(valores, dict):
        valores = {}
    if not isinstance(guardadas, list) or not guardadas:
        return {**de_fabrica, "valores": valores}
    return {
        "plantillas": [p for p in guardadas if isinstance(p, dict) and p.get("id")],
        "valores": {str(k): str(v) for k, v in valores.items()},
    }


def listar(usuario: str = "") -> list[dict]:
    """Solo las plantillas. Se mantiene por comodidad de quien no use `valores`."""
    return leer(usuario)["plantillas"]


def guardar(
    plantillas: list[dict], usuario: str = "", valores: dict | None = None,
) -> dict:
    """Guarda la lista COMPLETA y los huecos rellenados.

    `valores` son el `@` de la cuenta y demás: se guardan con las plantillas
    porque son del mismo operador y se escriben a la vez. Si llega `None` se
    respetan los que ya había — así, guardar una edición del texto no borra la
    cuenta que se escribió antes.
    """
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
    if valores is None:
        valores = leer(usuario)["valores"]
    guardados = {str(k): str(v).strip() for k, v in (valores or {}).items() if str(v).strip()}
    doc = {"plantillas": limpias, "valores": guardados, "at": time.time()}
    if not r.set_json(_key(usuario), doc):
        raise RuntimeError("Redis rechazó el guardado.")
    return {"plantillas": limpias, "valores": guardados}


def restaurar(usuario: str = "") -> dict:
    """Vuelve a las plantillas de fábrica CONSERVANDO los huecos.

    Se borra el documento y se reescriben solo los valores: restaurar es para
    deshacer un texto que se ha estropeado, no para tener que volver a escribir
    el `@` de tu cuenta.
    """
    r = get_plantillas_redis()
    valores = leer(usuario)["valores"] if r.is_available() else {}
    if r.is_available():
        r.delete(_key(usuario))
        if valores:
            r.set_json(_key(usuario), {"valores": valores, "at": time.time()})
    return {
        "plantillas": [dict(p) for p in config.PLANTILLAS_INICIALES],
        "valores": valores,
    }
