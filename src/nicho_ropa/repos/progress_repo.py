"""Qué carpetas ha dado cada uno por hechas (o dejado pendientes de subir).

Como el `progress_repo` del Nicho POV BOF, pero con una diferencia: aquí la
misma carpeta se trabaja en varios MODOS (espejo, selfie, calle dividido…) y
cada uno es un vídeo distinto de la misma prenda. Terminar la carpeta 3 frente
al espejo no la termina en la calle, así que el progreso va por modo.

Y por usuario, igual que allí: Ana y Mauro trabajan el mismo inventario en
cuentas distintas, y que una termine una carpeta no la termina para el otro.

Un documento por usuario: `progreso:<usuario>` →
`{"completadas": {"<modo>": [slug, …]}, "pendientes": {"<modo>": [slug, …]}}`.
"""

from __future__ import annotations

from src.nicho_ropa.repos.redis_base import get_nicho_ropa_redis


def _key(usuario: str) -> str:
    return f"progreso:{usuario or 'ness'}"


def _load(usuario: str) -> dict:
    r = get_nicho_ropa_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(usuario)) or {}


def estado(usuario: str, modo: str) -> tuple[set[str], set[str]]:
    """`(completadas, pendientes)` de ese usuario en ese modo."""
    doc = _load(usuario)
    return (
        set((doc.get("completadas") or {}).get(modo) or []),
        set((doc.get("pendientes") or {}).get(modo) or []),
    )


def marcar(
    usuario: str, modo: str, carpeta: str, *,
    completada: bool | None = None, pendiente: bool | None = None,
) -> tuple[set[str], set[str]]:
    """Cambia lo que se pida (lo que llegue a None no se toca)."""
    r = get_nicho_ropa_redis()
    if not r.is_available():
        raise RuntimeError("Redis no está configurado: no se puede guardar el progreso.")
    doc = r.get_json(_key(usuario)) or {}
    for campo, valor in (("completadas", completada), ("pendientes", pendiente)):
        if valor is None:
            continue
        lista = set((doc.setdefault(campo, {})).get(modo) or [])
        if valor:
            lista.add(carpeta)
        else:
            lista.discard(carpeta)
        doc[campo][modo] = sorted(lista)
    # Completar una carpeta la saca de "pendiente de subir": si está hecha, ya
    # se subió. Al revés no: puede estar pendiente sin estar terminada.
    if completada:
        pend = set((doc.setdefault("pendientes", {})).get(modo) or [])
        pend.discard(carpeta)
        doc["pendientes"][modo] = sorted(pend)
    r.set_json(_key(usuario), doc)
    return estado(usuario, modo)
