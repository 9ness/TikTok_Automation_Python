"""Banco de cuentas de EchoTik, con cuándo se gastó la primera llamada.

El plan gratuito da 100 llamadas AL MES. Cuando una cuenta se queda seca no
sirve de nada tirarla: dentro de un mes vuelve a tener sus 100. Antes se
sobrescribían las credenciales al cambiar de cuenta y la anterior se perdía —
con esto se guardan todas y se puede volver a la que ya haya renovado.

Lo que hace falta saber de cada una es **cuándo se usó por primera vez**: la
cuota renueva un mes después de esa fecha, no de cuando se dio de alta. Por eso
`primer_uso_at` lo pone el propio cliente al hacer la primera petición real, no
la UI al guardar.

Las contraseñas se guardan en claro porque hay que mandarlas a EchoTik en cada
request; nunca salen por la API (ver el enmascarado del router).
"""

from __future__ import annotations

import contextlib
import os
import random
import time

from src.tiktok_shop.repos.redis_base import get_shop_redis

_KEY = "echotik:cuentas"
_LOCK_KEY = "lock:echotik:cuentas"

# Cada cuánto renueva la cuota del plan gratuito. Es una estimación: EchoTik no
# publica si cuenta desde el alta o por mes natural, así que se toma el caso
# pesimista (30 días desde la PRIMERA llamada) y la UI lo enseña como "~".
DIAS_RENOVACION = 30
_SEG_RENOVACION = DIAS_RENOVACION * 24 * 3600


def _cargar() -> list[dict]:
    r = get_shop_redis()
    if not r.is_available():
        return []
    doc = r.get_json(_KEY)
    if not isinstance(doc, dict):
        return []
    items = doc.get("cuentas")
    return [c for c in items if isinstance(c, dict)] if isinstance(items, list) else []


def _guardar(cuentas: list[dict]) -> bool:
    r = get_shop_redis()
    if not r.is_available():
        return False
    return bool(r.set_json(_KEY, {"cuentas": cuentas}))


@contextlib.contextmanager
def _cerrojo(espera_s: float = 5.0):
    """Cerrojo mientras se lee-modifica-escribe la lista entera.

    Hace falta: la API corre con VARIOS workers y aquí se guarda siempre el
    documento completo. Sin él, un worker que acaba de leer la lista vacía
    (para dar de alta la cuenta activa) pisa la llamada que otro acababa de
    registrar — y lo que se pierde es justo `primer_uso_at`, que es el dato
    por el que existe este módulo.

    Si no se consigue, se sigue igual: perder una escritura es menos malo que
    dejar de contar la llamada.
    """
    r = get_shop_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_LOCK_KEY, str(os.getpid()), ttl_s=15):
                mio = True
                break
            time.sleep(0.1 + random.random() * 0.15)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_LOCK_KEY)


def _normalizar(c: dict) -> dict:
    """Rellena los campos que falten — hay cuentas guardadas antes de que
    existieran algunos, y un `None` a mitad rompería la UI."""
    return {
        "usuario": str(c.get("usuario") or "").strip(),
        "password": str(c.get("password") or "").strip(),
        "nota": str(c.get("nota") or "").strip()[:80],
        "alta_at": float(c.get("alta_at") or 0) or None,
        "primer_uso_at": float(c.get("primer_uso_at") or 0) or None,
        "ultimo_uso_at": float(c.get("ultimo_uso_at") or 0) or None,
        "llamadas": int(c.get("llamadas") or 0),
        "sin_cuota_at": float(c.get("sin_cuota_at") or 0) or None,
    }


def listar() -> list[dict]:
    """Todas las cuentas, la de uso más reciente primero."""
    cuentas = [_normalizar(c) for c in _cargar() if str(c.get("usuario") or "").strip()]
    cuentas.sort(key=lambda c: c["ultimo_uso_at"] or c["alta_at"] or 0, reverse=True)
    return cuentas


def buscar(usuario: str) -> dict | None:
    usuario = (usuario or "").strip()
    for c in listar():
        if c["usuario"] == usuario:
            return c
    return None


def guardar(usuario: str, password: str, nota: str = "") -> dict:
    """Da de alta la cuenta, o actualiza la contraseña si ya estaba.

    Al actualizar se CONSERVA el historial de uso: es la misma cuenta con la
    clave rotada, y perder `primer_uso_at` sería perder justo el dato por el
    que existe este módulo.
    """
    usuario = (usuario or "").strip()
    password = (password or "").strip()
    if not usuario or not password:
        raise ValueError("Usuario y contraseña son obligatorios.")

    with _cerrojo():
        cuentas = [_normalizar(c) for c in _cargar()]
        for c in cuentas:
            if c["usuario"] == usuario:
                c["password"] = password
                if nota:
                    c["nota"] = nota.strip()[:80]
                break
        else:
            c = _normalizar({
                "usuario": usuario, "password": password,
                "nota": nota, "alta_at": time.time(),
            })
            cuentas.append(c)

        if not _guardar(cuentas):
            raise RuntimeError(
                "Redis no está configurado — no se pudo guardar la cuenta."
            )
    return c


def borrar(usuario: str) -> bool:
    usuario = (usuario or "").strip()
    with _cerrojo():
        cuentas = [_normalizar(c) for c in _cargar()]
        quedan = [c for c in cuentas if c["usuario"] != usuario]
        if len(quedan) == len(cuentas):
            return False
        return _guardar(quedan)


def registrar_uso(usuario: str) -> None:
    """Suma una llamada a la cuenta activa. Nunca lanza.

    La llama el cliente en CADA petición, así que tiene que ser barata y
    silenciosa: si Redis falla, se pierde la cuenta de esa llamada pero la
    petición a EchoTik sigue adelante.
    """
    usuario = (usuario or "").strip()
    if not usuario:
        return
    try:
        with _cerrojo():
            _registrar_uso_sin_cerrojo(usuario)
    except Exception:
        pass


def _registrar_uso_sin_cerrojo(usuario: str) -> None:
    cuentas = [_normalizar(c) for c in _cargar()]
    ahora = time.time()
    for c in cuentas:
        if c["usuario"] != usuario:
            continue
        renueva = renueva_at(c)
        if renueva and ahora >= renueva:
            # Empieza ciclo nuevo: la cuota se ha renovado, así que el
            # contador vuelve a cero y `primer_uso_at` marca este ciclo.
            # Sin esto, `llamadas` sería acumulativo y una cuenta reciclada
            # parecería agotada para siempre.
            c["llamadas"] = 0
            c["primer_uso_at"] = ahora
            c["sin_cuota_at"] = None
        c["llamadas"] += 1
        c["ultimo_uso_at"] = ahora
        if not c["primer_uso_at"]:
            c["primer_uso_at"] = ahora
        _guardar(cuentas)
        return
    # Cuenta que nunca se dio de alta (venía del .env): se apunta sola,
    # así no hay forma de gastar llamadas sin dejar rastro.
    cuentas.append(_normalizar({
        "usuario": usuario, "password": "", "alta_at": ahora,
        "primer_uso_at": ahora, "ultimo_uso_at": ahora, "llamadas": 1,
    }))
    _guardar(cuentas)


def marcar_sin_cuota(usuario: str) -> None:
    """Deja constancia de que esta cuenta dio 'Usage Limit Exceeded'."""
    usuario = (usuario or "").strip()
    if not usuario:
        return
    try:
        with _cerrojo():
            cuentas = [_normalizar(c) for c in _cargar()]
            for c in cuentas:
                if c["usuario"] != usuario:
                    continue
                c["sin_cuota_at"] = time.time()
                # Si se agotó sin haber registrado el primer uso (cuenta
                # vieja), se toma esta fecha: la renovación no puede ser antes.
                if not c["primer_uso_at"]:
                    c["primer_uso_at"] = c["sin_cuota_at"]
                _guardar(cuentas)
                return
    except Exception:
        pass


def renueva_at(cuenta: dict) -> float | None:
    """Cuándo vuelve a tener llamadas, o None si nunca se ha usado."""
    primero = cuenta.get("primer_uso_at")
    return primero + _SEG_RENOVACION if primero else None


def disponible(cuenta: dict, ahora: float | None = None) -> bool:
    """¿Se puede tirar de esta cuenta ahora mismo?

    Sí si nunca se ha usado, si ya pasó el mes desde la primera llamada, o si
    ni se ha agotado ni llega a las 100 llamadas de este ciclo.
    """
    ahora = ahora if ahora is not None else time.time()
    renueva = renueva_at(cuenta)
    if renueva is None or ahora >= renueva:
        return True
    if cuenta.get("sin_cuota_at"):
        return False
    return int(cuenta.get("llamadas") or 0) < 100
