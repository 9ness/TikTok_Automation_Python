"""Envío de emails del Editor Auto vía Gmail SMTP.

Pensado para el aviso "tus vídeos del día están listos". Usa una cuenta
Gmail con **contraseña de aplicación** (no la normal — Google bloquea apps
inseguras). Config por env:

    EDITOR_SMTP_USER=nebulabsaimedia@gmail.com
    EDITOR_SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx   # 16 chars de la app password
    EDITOR_SMTP_FROM_NAME=NeBulabs AI           # opcional (nombre remitente)

Si no está configurado, `is_configured()` devuelve False y los callers
deben hacer no-op (compartir carpeta sin email). NUNCA lanza al caller:
`send_videos_ready` captura todo y devuelve un dict con el resultado.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("editor_auto.email_notify")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def _user() -> str:
    return (os.getenv("EDITOR_SMTP_USER") or "").strip()


def _password() -> str:
    # Quita espacios — Google muestra la app password en bloques "xxxx xxxx".
    return (os.getenv("EDITOR_SMTP_APP_PASSWORD") or "").replace(" ", "").strip()


def _from_name() -> str:
    return (os.getenv("EDITOR_SMTP_FROM_NAME") or "NeBulabs AI").strip()


def is_configured() -> bool:
    return bool(_user() and _password())


def _send(to: list[str], subject: str, html: str, text: str) -> dict:
    """Envía un email a `to`. Devuelve {ok, sent, error}."""
    recipients = [e.strip() for e in to if e and "@" in e]
    if not recipients:
        return {"ok": False, "sent": 0, "error": "sin destinatarios válidos"}
    if not is_configured():
        return {"ok": False, "sent": 0, "error": "SMTP no configurado"}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{_from_name()} <{_user()}>"
    msg["To"] = ", ".join(recipients)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
            server.starttls(context=ctx)
            server.login(_user(), _password())
            server.send_message(msg)
        logger.info("[email] enviado a %d destinatario(s): %s", len(recipients), subject)
        return {"ok": True, "sent": len(recipients), "error": None}
    except Exception as e:
        logger.warning("[email] fallo enviando: %s", e)
        return {"ok": False, "sent": 0, "error": str(e)}


def send_videos_ready(
    *, to: list[str], client_name: str, count: int | None = None,
    folder_link: str | None = None,
) -> dict:
    """Email 'tus vídeos del día están listos'."""
    nice = client_name or "Hola"
    n_txt = f"{count} vídeo(s)" if count else "Tus vídeos"
    link_html = (
        f'<p><a href="{folder_link}" '
        f'style="background:#10b981;color:#fff;padding:10px 18px;'
        f'border-radius:8px;text-decoration:none;display:inline-block">'
        f'Ver mis vídeos</a></p>'
        if folder_link else ""
    )
    link_txt = f"\nCarpeta: {folder_link}\n" if folder_link else ""
    subject = "✅ Tus vídeos del día están listos"
    html = (
        f"<div style='font-family:sans-serif;font-size:15px;color:#111'>"
        f"<p>Hola {nice},</p>"
        f"<p><strong>{n_txt} ya están editados y disponibles</strong> en tu "
        f"carpeta de salida de Drive.</p>"
        f"{link_html}"
        f"<p style='color:#666;font-size:13px'>NeBulabs AI · edición automática</p>"
        f"</div>"
    )
    text = (
        f"Hola {nice},\n\n{n_txt} ya están editados y disponibles en tu "
        f"carpeta de salida de Drive.{link_txt}\n\nNeBulabs AI"
    )
    return _send(recipients_subject(to), subject, html, text)


def recipients_subject(to: list[str]) -> list[str]:
    """Normaliza la lista de destinatarios (helper trivial, dedup)."""
    seen: set[str] = set()
    out: list[str] = []
    for e in to or []:
        e = (e or "").strip()
        if e and e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return out
