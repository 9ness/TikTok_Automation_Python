"""Lectura/escritura de las CUENTAS WEB (nebulabs-media) en Upstash.

El front de cliente (`nebulabs-media`, microservicio Vercel) guarda cada
cuenta en la MISMA instancia Upstash que Editor Auto pero con prefijo
`nebulabs:` para no colisionar:

    nebulabs:user:{emailLower}  → JSON de la cuenta web (auth/rol/plan/trial)
    nebulabs:users              → SET de emails (índice)

Schema de la cuenta web (contrato con `nebulabs-media/lib/users.ts`):
    id, email, name, picture?, role (standard|plus|pro|admin),
    planId (str|null), trialVideos (int), banned (bool),
    createdAt, lastLoginAt

Este repo deja al panel de configuración LEER esas cuentas y modificar
rol/plan/ban sin pasar por la web — el puente es el email
(`EditorUser.account_email`).
"""

from __future__ import annotations

from typing import Any

from .redis_base import EditorRedis

_WEB_PREFIX = "nebulabs:"


class _WebRedis(EditorRedis):
    """EditorRedis con prefijo `nebulabs:` en vez de `editor_auto:`.

    Reutiliza el mismo transporte Upstash (url/token del .env) — solo cambia
    el namespace para apuntar a los datos que escribe el front de cliente.
    """

    def __init__(self) -> None:
        super().__init__()
        self.prefix = _WEB_PREFIX


_INSTANCE: _WebRedis | None = None


def _r() -> _WebRedis:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = _WebRedis()
    return _INSTANCE


def _user_key(email: str) -> str:
    return f"user:{email.strip().lower()}"


class WebAccountRepo:
    """Acceso de solo-puente a las cuentas web (`nebulabs:`)."""

    def is_available(self) -> bool:
        return _r().is_available()

    def get(self, email: str | None) -> dict[str, Any] | None:
        """Devuelve la cuenta web por email, o None si no existe/sin email."""
        if not email:
            return None
        return _r().get_json(_user_key(email))

    def list_all(self) -> list[dict[str, Any]]:
        """Todas las cuentas web (para el selector de vinculación)."""
        emails = _r().smembers("users")
        out: list[dict[str, Any]] = []
        for e in emails:
            acc = _r().get_json(_user_key(e))
            if acc:
                out.append(acc)
        return out

    def _save(self, account: dict[str, Any]) -> bool:
        email = (account.get("email") or "").strip().lower()
        if not email:
            return False
        ok = _r().set_json(_user_key(email), account)
        _r().sadd("users", email)
        return ok

    def set_role(self, email: str, role: str) -> dict[str, Any] | None:
        """Cambia el rol (standard|plus|pro|admin). Read-modify-write."""
        acc = self.get(email)
        if not acc:
            return None
        acc["role"] = role
        return acc if self._save(acc) else None

    def set_plan(self, email: str, plan_id: str | None) -> dict[str, Any] | None:
        """Asigna/quita el plan contratado (id de tarifa o None=solo trial)."""
        acc = self.get(email)
        if not acc:
            return None
        acc["planId"] = plan_id
        return acc if self._save(acc) else None

    def set_banned(self, email: str, banned: bool) -> dict[str, Any] | None:
        acc = self.get(email)
        if not acc:
            return None
        acc["banned"] = bool(banned)
        return acc if self._save(acc) else None

    def set_trial_videos(self, email: str, n: int) -> dict[str, Any] | None:
        acc = self.get(email)
        if not acc:
            return None
        acc["trialVideos"] = int(n)
        return acc if self._save(acc) else None


_REPO: WebAccountRepo | None = None


def get_web_account_repo() -> WebAccountRepo:
    global _REPO
    if _REPO is None:
        _REPO = WebAccountRepo()
    return _REPO
