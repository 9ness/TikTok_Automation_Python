"""Login gate para la app — usado en main.py.

Estrategia:
- Credenciales (usuario + bcrypt hash) en variables de entorno (.env)
- Sesión persistida en cookie firmada (HMAC) — 30 días por defecto
- Rate limiting por IP (5 intentos fallidos en 5 min → bloqueo 15 min)
- 2 usuarios fijos: ness y buga (configurables via USERNAME_*/PASSWORD_HASH_*)

Por qué streamlit-authenticator: módulo oficial, gestiona el cookie firmado,
form de login con bcrypt, y el ciclo de session_state. Sobre él añadimos
nuestra capa de rate-limit por IP (no la trae built-in).

CLI helper para generar hashes:

    python -m src.auth hash 'tu_password_aqui'
    # imprime el hash bcrypt para pegar en .env

Variables de entorno requeridas:
    AUTH_COOKIE_KEY=<token random 32 bytes hex — firma del cookie>
    AUTH_COOKIE_NAME=tiktok_factory_auth   # opcional, default éste
    AUTH_COOKIE_EXPIRY_DAYS=30             # opcional, default 30
    USERNAME_NESS=ness                     # nombre de usuario en login form
    PASSWORD_HASH_NESS=$2b$12$...          # bcrypt hash
    USERNAME_BUGA=buga
    PASSWORD_HASH_BUGA=$2b$12$...

Uso desde main.py (justo después de st.set_page_config):

    from src.auth import require_login
    current_user = require_login()
    # Si el código sigue, el user está autenticado.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional

import streamlit as st


# ============================================================
# Rate limiting por IP — sliding window con dict en memoria
# ============================================================
# Singleton: vive entre reruns de Streamlit (idéntico patrón al JobQueue)

_RL_LOCK = threading.Lock()
_RL_STATE: dict[str, dict] = {}  # ip → {failures: [timestamps...], blocked_until: ts}

# Config: 5 fallos en 5 min → bloqueo 15 min. Configurable por env var.
RL_MAX_FAILURES = int(os.getenv("AUTH_RL_MAX_FAILURES", "5"))
RL_WINDOW_S = int(os.getenv("AUTH_RL_WINDOW_S", "300"))      # 5 min
RL_BLOCK_S = int(os.getenv("AUTH_RL_BLOCK_S", "900"))         # 15 min


def _get_client_ip() -> str:
    """Devuelve la IP del cliente. Detrás de Tailscale Funnel / proxy
    inverso, viene en X-Forwarded-For. Si no podemos detectar, devolvemos
    'unknown' — el rate limiting agregará todos los unknowns juntos
    (degradación segura, no abre puerta)."""
    try:
        headers = st.context.headers  # type: ignore[attr-defined]
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
        if xff:
            # Primera IP de la cadena = cliente original
            return xff.split(",")[0].strip()
        return (
            headers.get("X-Real-Ip")
            or headers.get("x-real-ip")
            or "unknown"
        )
    except Exception:
        return "unknown"


def _is_rate_limited(ip: str) -> tuple[bool, int]:
    """Devuelve (blocked, seconds_remaining). Limpia entradas viejas."""
    now = time.time()
    with _RL_LOCK:
        entry = _RL_STATE.get(ip, {"failures": [], "blocked_until": 0.0})

        # Si está bloqueado y aún no expiró
        if entry["blocked_until"] > now:
            return True, int(entry["blocked_until"] - now)

        # Limpiar fallos fuera de la ventana
        entry["failures"] = [t for t in entry["failures"] if now - t < RL_WINDOW_S]

        # Reset blocked si ya pasó
        if entry["blocked_until"] and entry["blocked_until"] <= now:
            entry["blocked_until"] = 0.0
            entry["failures"] = []  # reset al desbloquear

        _RL_STATE[ip] = entry
        return False, 0


def _record_failure(ip: str) -> None:
    """Registra un fallo y bloquea si supera el umbral."""
    now = time.time()
    with _RL_LOCK:
        entry = _RL_STATE.setdefault(ip, {"failures": [], "blocked_until": 0.0})
        entry["failures"].append(now)
        # Limpiar fallos fuera de la ventana
        entry["failures"] = [t for t in entry["failures"] if now - t < RL_WINDOW_S]
        if len(entry["failures"]) >= RL_MAX_FAILURES:
            entry["blocked_until"] = now + RL_BLOCK_S
            print(
                f"[auth] IP {ip} bloqueada por {RL_BLOCK_S}s tras "
                f"{len(entry['failures'])} fallos en {RL_WINDOW_S}s"
            )


def _record_success(ip: str) -> None:
    """Limpia el contador al loguear correctamente."""
    with _RL_LOCK:
        if ip in _RL_STATE:
            _RL_STATE[ip] = {"failures": [], "blocked_until": 0.0}


# ============================================================
# Carga de credenciales desde env
# ============================================================
def _load_users_from_env() -> dict:
    """Construye el dict de credentials que streamlit-authenticator espera,
    leyendo USERNAME_<KEY> y PASSWORD_HASH_<KEY> del entorno.

    Detecta automáticamente todos los pares definidos. Si añades
    USERNAME_PEPE/PASSWORD_HASH_PEPE al .env, aparece como tercer usuario
    sin tocar código.
    """
    users = {}
    seen_keys = set()
    for env_key in os.environ:
        if env_key.startswith("USERNAME_"):
            suffix = env_key[len("USERNAME_"):]
            seen_keys.add(suffix)

    for key in seen_keys:
        username = os.getenv(f"USERNAME_{key}", "").strip()
        pwd_hash = os.getenv(f"PASSWORD_HASH_{key}", "").strip()
        if not username or not pwd_hash:
            continue
        users[username] = {
            "name": username.capitalize(),
            "password": pwd_hash,
            "email": f"{username}@nebulabs.local",
            "failed_login_attempts": 0,
            "logged_in": False,
        }
    return users


# ============================================================
# require_login() — gate principal usado por main.py
# ============================================================
def require_login() -> str:
    """Muestra el login screen si no hay sesión y detiene la ejecución
    hasta que el usuario se autentique. Si ya está logueado, devuelve
    el username y deja seguir la ejecución de main.py.

    Renderiza también el botón Logout en la sidebar para sesiones activas.
    """
    # Lazy import — evitamos cargar streamlit-authenticator cuando no haya
    # auth configurado en el .env (modo dev local sin login).
    try:
        import streamlit_authenticator as stauth
    except ImportError:
        st.error(
            "❌ Falta dependencia: `streamlit-authenticator`. Instala con "
            "`pip install streamlit-authenticator`. Si estás en el VPS, "
            "actualiza requirements.txt y reinstala el venv."
        )
        st.stop()

    cookie_key = os.getenv("AUTH_COOKIE_KEY", "").strip()
    cookie_name = os.getenv("AUTH_COOKIE_NAME", "tiktok_factory_auth").strip()
    expiry_days = int(os.getenv("AUTH_COOKIE_EXPIRY_DAYS", "30"))

    users = _load_users_from_env()

    # Modo "auth desactivada" — útil en dev local. Se activa NO definiendo
    # ningún USERNAME_* + PASSWORD_HASH_* y sin AUTH_COOKIE_KEY.
    if not users or not cookie_key:
        if not users and not cookie_key:
            # Sin auth configurada: dev mode, no bloqueamos
            st.session_state.setdefault("_authed_user", "dev")
            return "dev"
        # Config a medias = error fatal
        st.error(
            "❌ Auth mal configurada. Necesitas en .env:\n"
            "  - AUTH_COOKIE_KEY (token random)\n"
            "  - Al menos un par USERNAME_X / PASSWORD_HASH_X\n\n"
            "Genera el hash con: `python -m src.auth hash 'tu_password'`"
        )
        st.stop()

    credentials = {"usernames": users}

    # Una sola instancia de Authenticate por sesión Streamlit
    if "_authenticator" not in st.session_state:
        st.session_state._authenticator = stauth.Authenticate(
            credentials=credentials,
            cookie_name=cookie_name,
            cookie_key=cookie_key,
            cookie_expiry_days=expiry_days,
        )
    authenticator = st.session_state._authenticator

    # ========== RATE LIMITING (antes del form) ==========
    client_ip = _get_client_ip()
    blocked, secs_left = _is_rate_limited(client_ip)
    if blocked:
        st.error(
            f"🚫 Demasiados intentos fallidos desde tu IP. "
            f"Vuelve a intentarlo en {secs_left // 60}m {secs_left % 60}s."
        )
        st.stop()

    # ========== LOGIN FORM (renderizado por la lib) ==========
    # streamlit-authenticator escribe el resultado en session_state:
    #   - 'authentication_status' (True | False | None)
    #   - 'username', 'name'
    try:
        authenticator.login(location="main")
    except Exception as e:
        st.error(f"❌ Error en login form: {e}")
        st.stop()

    auth_status = st.session_state.get("authentication_status")

    if auth_status is True:
        # Usuario autenticado — registramos éxito (limpia rate-limit) y
        # dejamos continuar el resto de main.py
        _record_success(client_ip)
        username = st.session_state.get("username", "")
        # Logout button + nombre en sidebar
        with st.sidebar:
            st.divider()
            st.caption(f"👤 Conectado: **{username}**")
            authenticator.logout(button_name="🚪 Cerrar sesión", location="sidebar")
        return username

    if auth_status is False:
        # Login fallido — registramos para rate limit
        _record_failure(client_ip)
        st.error("❌ Usuario o contraseña incorrectos.")
        st.caption(
            f"Intentos fallidos rate-limited a {RL_MAX_FAILURES} cada "
            f"{RL_WINDOW_S//60}min. Si te bloqueas, espera {RL_BLOCK_S//60}min."
        )
        st.stop()

    # auth_status == None → primer render, form mostrado, esperando input
    st.info("🔒 Introduce tus credenciales para acceder a TikTok Factory.")
    st.stop()


# ============================================================
# CLI helper: generar hash bcrypt
# ============================================================
def _cli_hash(password: str) -> str:
    """Genera hash bcrypt compatible con streamlit-authenticator."""
    try:
        import bcrypt
    except ImportError:
        print("Falta bcrypt. Instala con: pip install bcrypt", file=sys.stderr)
        sys.exit(1)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _cli_main():
    """Entry point del CLI: `python -m src.auth hash 'mypassword'`"""
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "hash":
        password = args[1]
        if len(password) < 8:
            print("⚠️  Recomendación: password de al menos 8 caracteres.",
                  file=sys.stderr)
        print(_cli_hash(password))
        return
    if len(args) >= 1 and args[0] == "gen-cookie-key":
        import secrets
        print(secrets.token_hex(32))
        return
    print("Uso:")
    print("  python -m src.auth hash 'mypassword'    # genera bcrypt hash")
    print("  python -m src.auth gen-cookie-key       # genera AUTH_COOKIE_KEY")
    sys.exit(1)


if __name__ == "__main__":
    _cli_main()
