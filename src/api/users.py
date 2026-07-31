"""Quién puede entrar, con qué rol y con qué PIN.

Hasta ahora los usuarios vivían SOLO en `.env` (`USERNAME_X` +
`PASSWORD_HASH_X`), lo que obliga a editar el fichero y reiniciar para dar de
alta a alguien — y hace imposible que el propio usuario se ponga su clave.

Ahora:
- La LISTA de usuarios y sus roles están aquí, en código (son tres personas,
  no hace falta un panel de administración).
- El PIN lo elige cada uno la primera vez que entra y se guarda en Redis
  (bcrypt). Los hashes de `.env` se siguen aceptando para no invalidar la
  sesión de quien ya tenía contraseña.

Roles:
- `admin`  → todo el panel, y puede ver la cola de los demás.
- `pro`    → solo el programa "Tiktok Shop AI Pro". Es lo que necesitan
             quienes solo suben productos.
"""

from __future__ import annotations

import os

from src.viralizacion.repos.redis_base import get_viralizacion_redis

ADMIN = "admin"
PRO = "pro"

# El `key` es el username real (el que viaja en el cookie). `ness` se queda
# como estaba a propósito: cambiarlo invalidaría su sesión y su contraseña.
USUARIOS: dict[str, dict] = {
    "ness": {"nombre": "Néstor", "rol": ADMIN},
    "mauro": {"nombre": "Mauro", "rol": PRO},
    "ana": {"nombre": "Ana", "rol": PRO},
}

# Prefijo de Redis para los PIN. Va sobre el cliente de viralización porque es
# el que ya existe con namespace propio; la clave lleva su propio prefijo.
_PIN_KEY = "auth:pin"


def existe(username: str) -> bool:
    return username in USUARIOS


def rol_de(username: str) -> str:
    return USUARIOS.get(username, {}).get("rol", PRO)


def es_admin(username: str | None) -> bool:
    return bool(username) and rol_de(username) == ADMIN


def nombre_de(username: str) -> str:
    return USUARIOS.get(username, {}).get("nombre", username)


def listar() -> list[dict]:
    """Usuarios para la pantalla de entrada, con si ya tienen PIN puesto."""
    return [
        {
            "username": u,
            "nombre": d["nombre"],
            "rol": d["rol"],
            "tiene_pin": tiene_pin(u),
        }
        for u, d in USUARIOS.items()
    ]


# ---------------------------------------------------------------------------
# PIN
# ---------------------------------------------------------------------------
def _hash_env(username: str) -> str:
    """Hash bcrypt de `.env`, si ese usuario lo tiene (caso de `ness`)."""
    for env_key in os.environ:
        if not env_key.startswith("USERNAME_"):
            continue
        if os.getenv(env_key, "").strip() != username:
            continue
        return os.getenv(f"PASSWORD_HASH_{env_key[len('USERNAME_'):]}", "").strip()
    return ""


def _hash_redis(username: str) -> str:
    r = get_viralizacion_redis()
    if not r.is_available():
        return ""
    doc = r.get_json(f"{_PIN_KEY}:{username}")
    if isinstance(doc, dict):
        return str(doc.get("hash") or "")
    return ""


def hash_de(username: str) -> str:
    """El hash que hay que validar: manda el de Redis sobre el de `.env`.

    Así, si alguien se cambia el PIN desde la app, el de `.env` deja de valer
    sin tener que tocar el fichero.
    """
    return _hash_redis(username) or _hash_env(username)


def tiene_pin(username: str) -> bool:
    return bool(hash_de(username))


def guardar_pin(username: str, pin: str) -> None:
    """Guarda el PIN (bcrypt) en Redis. Lanza si algo no cuadra."""
    if not existe(username):
        raise ValueError(f"Usuario desconocido: {username!r}")
    pin = (pin or "").strip()
    # Cuatro dígitos mínimo: es un PIN de móvil, no una contraseña, pero
    # menos de eso se adivina a mano en un rato.
    if len(pin) < 4:
        raise ValueError("El PIN tiene que tener al menos 4 caracteres.")
    try:
        import bcrypt
    except ImportError as e:
        raise RuntimeError("bcrypt no está instalado en el servidor.") from e
    h = bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    r = get_viralizacion_redis()
    if not r.is_available():
        raise RuntimeError("Redis no está configurado — no se puede guardar el PIN.")
    r.set_json(f"{_PIN_KEY}:{username}", {"hash": h})
