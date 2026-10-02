"""Acceso a las réplicas guardadas, para otros módulos (el POV BOF Largo lee
de aquí el guion y los prompts de su estilo «Réplica viral»)."""

from __future__ import annotations

from src.replicar_viral.servicio import CLAVE, _redis


def obtener(replica_id: str) -> dict | None:
    """El documento completo de una réplica, o None si no existe."""
    if not replica_id:
        return None
    r = _redis()
    if not r.is_available():
        return None
    doc = r.get_json(CLAVE.format(id=replica_id))
    return doc if isinstance(doc, dict) else None
