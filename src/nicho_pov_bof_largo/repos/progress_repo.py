"""Tracking de carpetas de producto ya completadas en el Nicho POV BOF Largo.

Es un CALCO del `progress_repo` del Nicho POV BOF, pero con el cliente Redis y
el prefijo propios (`nicho_pov_bof_largo:`): las carpetas se comparten, el
progreso NO. Haber terminado una carpeta en el POV BOF no significa haberla
hecho aquí — son vídeos distintos del mismo producto.

Key: `nicho_pov_bof_largo:completed:<source>` → SET de nombres de carpeta.
"""

from __future__ import annotations

from src.nicho_pov_bof import config as pov_config

from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis


def _key(source: str, usuario: str = "", estilo: str = "") -> str:
    """Clave del progreso. Es POR USUARIO y POR MODO de guion.

    `ness` se queda en la clave sin usuario (su histórico), igual que en el
    POV BOF, para no perder por dónde iba al separar cuentas. Y el modo por
    defecto tampoco lleva sufijo, por lo mismo: recorrer el catálogo con
    "precio" es lo que se llevaba haciendo hasta ahora.

    El modo va aquí porque una carpeta hecha con un gancho NO está hecha con el
    otro: son dos vueltas al catálogo, no una repetida.
    """
    from src.nicho_pov_bof_largo import config as largo_config

    # La copia de seguridad comparte progreso con la fuente del curso: son las
    # MISMAS carpetas, solo cambia de dónde se leen las fotos.
    source = pov_config.fuente_canonica(source)
    base = (
        f"completed:{source}"
        if not usuario or usuario == "ness"
        else f"completed:{source}:{usuario}"
    )
    # Igual que en `product_repo`: sin modo explícito se resuelve solo, para
    # que ningún sitio se quede escribiendo el progreso del otro.
    if not estilo:
        estilo = get_modo(source, usuario)
    estilo = (estilo or largo_config.ESTILO_GUION_DEFECTO).strip()
    return base if estilo == largo_config.ESTILO_GUION_DEFECTO else f"{base}:m:{estilo}"


def _require_redis():
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho POV BOF Largo. Define UPSTASH_REDIS_REST_URL y "
            "UPSTASH_REDIS_REST_TOKEN."
        )
    return r


def get_completed(source: str, usuario: str = "", estilo: str = "") -> set[str]:
    """Nombres de carpeta marcados como completados en esta fuente y modo."""
    return set(_require_redis().smembers(_key(source, usuario, estilo)))


def is_completed(source: str, folder: str, usuario: str = "", estilo: str = "") -> bool:
    return _require_redis().sismember(_key(source, usuario, estilo), folder)


def mark_completed(source: str, folder: str, usuario: str = "", estilo: str = "") -> None:
    _require_redis().sadd(_key(source, usuario, estilo), folder)


def unmark_completed(
    source: str, folder: str, usuario: str = "", estilo: str = "",
) -> None:
    """Rollback — degrada en silencio si Redis no está."""
    r = get_nicho_pov_bof_largo_redis()
    if r.is_available():
        r.srem(_key(source, usuario, estilo), folder)


# ---------------------------------------------------------------------------
# Carpetas con los vídeos hechos pero SIN subir todavía
# ---------------------------------------------------------------------------
# SET propio, no un flag dentro de las completadas: se preparan vídeos de días
# futuros y esa carpeta no está cerrada —queda por subirlos—, y una ya cerrada
# puede seguir sin subir.


def _key_pendientes(source: str, usuario: str = "", estilo: str = "") -> str:
    """La MISMA partición que `_key` (usuario + modo de guion), otro SET.

    Se deriva de `_key` en vez de repetir su lógica para que no se separen: el
    modo de guion decide la clave y ahí ya está resuelto.
    """
    return "pending_upload:" + _key(source, usuario, estilo).removeprefix("completed:")


def get_pendientes(source: str, usuario: str = "", estilo: str = "") -> set[str]:
    """Degrada a vacío si Redis no está: es un aviso de color, no puede dejar
    sin listado de carpetas."""
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        return set()
    return set(r.smembers(_key_pendientes(source, usuario, estilo)))


def set_pendiente(
    source: str, folder: str, pendiente: bool, usuario: str = "", estilo: str = "",
) -> None:
    r = _require_redis()
    clave = _key_pendientes(source, usuario, estilo)
    if pendiente:
        r.sadd(clave, folder)
    else:
        r.srem(clave, folder)


# ---------------------------------------------------------------------------
# Con qué modo de guion se está recorriendo el catálogo
# ---------------------------------------------------------------------------
# Vive AQUÍ y no en el documento de la carpeta a propósito: ese documento ya va
# separado por modo, así que guardar dentro "cuál es mi modo" se muerde la cola
# —no habría forma de saber cuál leer sin saberlo antes—.
#
# Es del CATÁLOGO, no de cada carpeta: la idea es recorrerlo entero con un
# gancho y luego otra vez con el otro. Y por usuario, porque cada uno va por su
# vuelta.
#
# Memoria corta: `_key` de los productos lo consulta en cada acceso, y sin esto
# sería una ida a Upstash por cada lectura de carpeta.
_MEMO: dict[str, tuple[float, str]] = {}
_MEMO_TTL_S = 5.0


def _key_modo(source: str, usuario: str = "") -> str:
    source = pov_config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"modo:{source}"
    return f"modo:{source}:{usuario}"


def get_modo(source: str, usuario: str = "") -> str:
    """Con qué modo de guion se está trabajando este catálogo."""
    import time

    from src.nicho_pov_bof_largo import config as largo_config

    clave = _key_modo(source, usuario)
    guardado = _MEMO.get(clave)
    if guardado and time.monotonic() - guardado[0] < _MEMO_TTL_S:
        return guardado[1]
    r = get_nicho_pov_bof_largo_redis()
    valor = largo_config.ESTILO_GUION_DEFECTO
    if r.is_available():
        doc = r.get_json(clave) or {}
        valor = str(doc.get("estilo") or largo_config.ESTILO_GUION_DEFECTO)
    if valor not in largo_config.ESTILOS_GUION:
        valor = largo_config.ESTILO_GUION_DEFECTO
    _MEMO[clave] = (time.monotonic(), valor)
    return valor


def set_modo(source: str, estilo: str, usuario: str = "") -> None:
    r = _require_redis()
    clave = _key_modo(source, usuario)
    r.set_json(clave, {"estilo": estilo})
    _MEMO.pop(clave, None)
