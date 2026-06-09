"""Envío de emails del Editor Auto vía Gmail SMTP.

Pensado para el aviso "tus vídeos del día están listos". Usa una cuenta
Gmail con **contraseña de aplicación** (no la normal — Google bloquea apps
inseguras). Config por env:

    EDITOR_SMTP_USER=nebulabsaimedia@gmail.com
    EDITOR_SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx   # 16 chars de la app password
    EDITOR_SMTP_FROM_NAME=Nebulabs Media           # opcional (nombre remitente)

Si no está configurado, `is_configured()` devuelve False y los callers
deben hacer no-op (compartir carpeta sin email). NUNCA lanza al caller:
`send_videos_ready` captura todo y devuelve un dict con el resultado.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime
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
    return (os.getenv("EDITOR_SMTP_FROM_NAME") or "Nebulabs Media").strip()


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
    if count == 1:
        n_txt, verbo, adj = "Tu vídeo", "está", "editado y listo"
    elif count and count > 1:
        n_txt, verbo, adj = f"Tus {count} vídeos", "están", "editados y listos"
    else:
        n_txt, verbo, adj = "Tus vídeos", "están", "editados y listos"

    # Fecha en español para el asunto (distingue el aviso de cada día).
    _MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    _hoy = datetime.now()
    fecha = f"{_hoy.day} de {_MESES[_hoy.month - 1]}"

    # Botón con gradiente de marca (cyan → violeta del logo). Fallback de color
    # sólido para clientes que no renderizan gradientes.
    button = (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="margin:20px 0 4px"><tr>'
        '<td style="border-radius:10px;background:#06b6d4;'
        'background:linear-gradient(90deg,#06b6d4,#7c3aed)">'
        f'<a href="{folder_link}" style="display:inline-block;padding:13px 28px;'
        'font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;'
        'border-radius:10px">Ver mis vídeos →</a>'
        '</td></tr></table>'
        if folder_link else ""
    )
    link_txt = f"\nTus vídeos: {folder_link}\n" if folder_link else ""
    subject = f"✅ Tus vídeos del {fecha} ya están listos"

    html = (
        '<div style="margin:0;padding:0;background:#f4f5f7">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;background:#ffffff;border-radius:16px;'
        'overflow:hidden;font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="background:#06b6d4;'
        'background:linear-gradient(90deg,#06b6d4,#7c3aed);padding:20px 28px">'
        '<span style="color:#ffffff;font-size:18px;font-weight:700;'
        'letter-spacing:.5px">Nebulabs'
        '<span style="opacity:.85;font-weight:500"> Media</span></span></td></tr>'
        '<tr><td style="padding:28px">'
        f'<h1 style="margin:0 0 12px;font-size:20px;color:#111827">'
        f'¡Hola {nice}! 👋</h1>'
        f'<p style="margin:0 0 6px;font-size:15px;color:#374151;line-height:1.5">'
        f'<strong>{n_txt}</strong> del día de hoy ya {verbo} '
        f'<strong>{adj}</strong> en tu carpeta de Drive.</p>'
        f'{button}'
        '<p style="margin:18px 0 0;font-size:13px;color:#6b7280;line-height:1.5">'
        '¿Tienes alguna duda? Escríbenos respondiendo a este correo o por '
        '<a href="https://wa.me/34631543618" '
        'style="color:#0ea5e9;font-weight:700;text-decoration:none">WhatsApp</a>. '
        '¡Gracias por confiar en nosotros! 🙌</p>'
        '</td></tr>'
        '<tr><td style="background:#0f172a;padding:16px 28px">'
        '<span style="color:#94a3b8;font-size:12px">'
        'Nebulabs Media · Edición de vídeo</span></td></tr>'
        '</table></td></tr></table></div>'
    )
    text = (
        f"¡Hola {nice}!\n\n{n_txt} del día de hoy ya {verbo} {adj} "
        f"en tu carpeta de Drive.{link_txt}\n"
        f"¿Alguna duda? Escríbenos respondiendo a este correo o por WhatsApp: "
        f"https://wa.me/34631543618\n\n¡Gracias por confiar en nosotros!\n\nNebulabs Media"
    )
    return _send(recipients_subject(to), subject, html, text)


def send_unsent_reminder(
    *, to: list[str], client_name: str, count: int, cutoff_label: str,
    panel_link: str | None = None,
) -> dict:
    """Recordatorio 'tienes vídeos subidos SIN mandar a edición' antes del cierre."""
    nice = client_name or "Hola"
    n_txt = "1 vídeo subido" if count == 1 else f"{count} vídeos subidos"
    link = panel_link or "https://nebulabsmedia.com/panel"
    subject = f"⏰ Tienes {n_txt} sin mandar a edición"
    button = (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0 4px"><tr>'
        '<td style="border-radius:10px;background:#06b6d4;background:linear-gradient(90deg,#06b6d4,#7c3aed)">'
        f'<a href="{link}" style="display:inline-block;padding:13px 28px;font-size:15px;'
        'font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px">'
        'Mandar a edición →</a></td></tr></table>'
    )
    html = (
        '<div style="margin:0;padding:0;background:#f4f5f7">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;background:#ffffff;border-radius:16px;overflow:hidden;font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="background:#06b6d4;background:linear-gradient(90deg,#06b6d4,#7c3aed);padding:20px 28px">'
        '<span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:.5px">Nebulabs'
        '<span style="opacity:.85;font-weight:500"> Media</span></span></td></tr>'
        '<tr><td style="padding:28px">'
        f'<h1 style="margin:0 0 12px;font-size:20px;color:#111827">¡Hola {nice}! 👋</h1>'
        f'<p style="margin:0 0 6px;font-size:15px;color:#374151;line-height:1.5">'
        f'Tienes <strong>{n_txt}</strong> de hoy que aún <strong>no has mandado a edición</strong>. '
        f'Mándalos antes del cierre (<strong>{cutoff_label}</strong>) para recibirlos hoy.</p>'
        f'{button}'
        '<p style="margin:18px 0 0;font-size:13px;color:#6b7280;line-height:1.5">'
        'Si no los mandas, los moveremos a un próximo día disponible para que no se pierdan.</p>'
        '</td></tr>'
        '<tr><td style="background:#0f172a;padding:16px 28px">'
        '<span style="color:#94a3b8;font-size:12px">Nebulabs Media · Edición de vídeo</span></td></tr>'
        '</table></td></tr></table></div>'
    )
    text = (
        f"¡Hola {nice}!\n\nTienes {n_txt} de hoy SIN mandar a edición. "
        f"Mándalos antes del cierre ({cutoff_label}) para recibirlos hoy: {link}\n\n"
        f"Si no, los moveremos a un próximo día disponible para que no se pierdan.\n\nNebulabs Media"
    )
    return _send(recipients_subject(to), subject, html, text)


def _day_label(iso: str) -> str:
    """'2026-06-09' → '9 jun'."""
    _M = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return f"{d} {_M[m - 1]}"
    except Exception:
        return iso


def send_drafts_moved(
    *, to: list[str], client_name: str, count: int, target_days: list[str],
    panel_link: str | None = None,
) -> dict:
    """Email 'movimos tus vídeos sin enviar a otros días' (no se pierden)."""
    nice = client_name or "Hola"
    n_txt = "1 vídeo" if count == 1 else f"{count} vídeos"
    days_txt = ", ".join(_day_label(d) for d in target_days) or "un próximo día"
    link = panel_link or "https://nebulabsmedia.com/panel"
    subject = f"📦 Movimos {n_txt} sin enviar a otro día"
    button = (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0 4px"><tr>'
        '<td style="border-radius:10px;background:#06b6d4;background:linear-gradient(90deg,#06b6d4,#7c3aed)">'
        f'<a href="{link}" style="display:inline-block;padding:13px 28px;font-size:15px;'
        'font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px">'
        'Ver mis vídeos →</a></td></tr></table>'
    )
    html = (
        '<div style="margin:0;padding:0;background:#f4f5f7">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;background:#ffffff;border-radius:16px;overflow:hidden;font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="background:#06b6d4;background:linear-gradient(90deg,#06b6d4,#7c3aed);padding:20px 28px">'
        '<span style="color:#ffffff;font-size:18px;font-weight:700;letter-spacing:.5px">Nebulabs'
        '<span style="opacity:.85;font-weight:500"> Media</span></span></td></tr>'
        '<tr><td style="padding:28px">'
        f'<h1 style="margin:0 0 12px;font-size:20px;color:#111827">¡Hola {nice}! 👋</h1>'
        f'<p style="margin:0 0 6px;font-size:15px;color:#374151;line-height:1.5">'
        f'Tenías <strong>{n_txt}</strong> subidos que no llegaste a mandar a edición. '
        f'Para que no se pierdan, los hemos movido a <strong>{days_txt}</strong>.</p>'
        '<p style="margin:6px 0 0;font-size:15px;color:#374151;line-height:1.5">'
        'Entra en tu panel, ábrelos en ese día y pulsa <strong>“Mandar a edición”</strong> cuando quieras.</p>'
        f'{button}'
        '</td></tr>'
        '<tr><td style="background:#0f172a;padding:16px 28px">'
        '<span style="color:#94a3b8;font-size:12px">Nebulabs Media · Edición de vídeo</span></td></tr>'
        '</table></td></tr></table></div>'
    )
    text = (
        f"¡Hola {nice}!\n\nTenías {n_txt} subidos sin mandar a edición. Para que no se "
        f"pierdan, los movimos a {days_txt}. Ábrelos en ese día y pulsa 'Mandar a edición': {link}\n\nNebulabs Media"
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
