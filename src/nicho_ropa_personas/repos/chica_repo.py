"""Las modelos creadas por cada usuario.

Es lo único de este nicho que NO se comparte: cada uno crea sus chicas y solo
ve las suyas. El motivo no es la privacidad, es que la cara es la identidad de
la cuenta — si Ana y Néstor publican con la misma modelo, TikTok ve dos
cuentas haciendo lo mismo con la misma persona.

Key: `nicho_ropa_personas:chicas:<usuario>` — un documento con todas las del
usuario, porque son cuatro o cinco y siempre se piden juntas para pintar la
lista de botones.
"""

from __future__ import annotations

import json
import time
import uuid

from src.nicho_ropa_personas.repos.redis_base import get_nicho_ropa_personas_redis


def _key(usuario: str) -> str:
    return f"chicas:{usuario or 'ness'}"


def _require_redis():
    r = get_nicho_ropa_personas_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar las "
            "modelos del Nicho Ropa Con Personas."
        )
    return r


def listar(usuario: str) -> list[dict]:
    """Las chicas del usuario, de la más nueva a la más vieja."""
    r = get_nicho_ropa_personas_redis()
    if not r.is_available():
        return []
    doc = r.get_json(_key(usuario)) or {}
    chicas = [c for c in (doc.get("chicas") or []) if isinstance(c, dict)]
    chicas.sort(key=lambda c: float(c.get("creada_at") or 0), reverse=True)
    return chicas


def guardar(usuario: str, nombre: str, ficha: dict) -> dict:
    """Añade una chica nueva y la devuelve.

    La ficha se guarda como TEXTO ya formateado además de como objeto: lo que
    el operador copia y pega en la IA de imagen es el JSON tal cual, y
    reformatearlo en cada lectura daría espaciados distintos según quién lo
    lea.
    """
    nombre = (nombre or "").strip() or "Chica sin nombre"
    r = _require_redis()
    doc = r.get_json(_key(usuario)) or {}
    chicas = [c for c in (doc.get("chicas") or []) if isinstance(c, dict)]
    chica = {
        "id": uuid.uuid4().hex[:8],
        "nombre": nombre,
        "ficha": ficha,
        "ficha_texto": json.dumps(ficha, ensure_ascii=False, indent=2),
        "creada_at": time.time(),
    }
    chicas.append(chica)
    doc["chicas"] = chicas
    r.set_json(_key(usuario), doc)
    return chica


def renombrar(usuario: str, chica_id: str, nombre: str) -> dict | None:
    r = _require_redis()
    doc = r.get_json(_key(usuario)) or {}
    chicas = [c for c in (doc.get("chicas") or []) if isinstance(c, dict)]
    for c in chicas:
        if c.get("id") == chica_id:
            c["nombre"] = (nombre or "").strip() or c.get("nombre", "")
            doc["chicas"] = chicas
            r.set_json(_key(usuario), doc)
            return c
    return None


def borrar(usuario: str, chica_id: str) -> bool:
    r = _require_redis()
    doc = r.get_json(_key(usuario)) or {}
    chicas = [c for c in (doc.get("chicas") or []) if isinstance(c, dict)]
    quedan = [c for c in chicas if c.get("id") != chica_id]
    if len(quedan) == len(chicas):
        return False
    doc["chicas"] = quedan
    r.set_json(_key(usuario), doc)
    return True
