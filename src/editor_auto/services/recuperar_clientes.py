"""Recuperar clientes del Editor Auto con avisos por email (sin coste).

Tres reglas, sobre la foto de cuentas web y los trabajos de las estadísticas
locales (SQLite, ver `estadisticas.py`):

  - `sin_empezar`:    registrado hace ≥48 h, sin plan y sin usar la prueba
                      → «cómo empezar».
  - `prueba_gastada`: sin plan, prueba agotada y ≥3 días sin vídeos
                      → «¿qué te pareció?» + planes.
  - `plan_parado`:    con plan y ≥7 días sin mandar vídeos → recordatorio.

Como mucho UN email por regla y cuenta, nunca a admins, baneados ni a quien
se dio de baja (enlace de un clic, firmado). Por defecto todo es SIMULAR:
`candidatos()` dice a quién iría y no manda nada. Solo se envía con
`EDITOR_RECUPERAR_ENVIAR=1` en el .env (lo decide Néstor) y lo dispara el
loop del draft_sweeper una vez al día. Nunca lanza.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime
from html import escape
from typing import Any, Callable, Iterable

from src.editor_auto.services import estadisticas as est

logger = logging.getLogger("editor_auto.recuperar_clientes")

PRUEBA_INICIAL = 3          # TRIAL.firstVideos de nebulabs-media/lib/pricing.ts
HORAS_SIN_EMPEZAR = 48
DIAS_PRUEBA_GASTADA = 3
DIAS_PLAN_PARADO = 7
MAX_POR_PASADA = 20         # tope de emails por día (Gmail y prudencia)
REGLAS = ("sin_empezar", "prueba_gastada", "plan_parado")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS avisos (
  cuenta TEXT NOT NULL, regla TEXT NOT NULL, ts REAL NOT NULL,
  PRIMARY KEY (cuenta, regla)
);
CREATE TABLE IF NOT EXISTS bajas (cuenta TEXT PRIMARY KEY, ts REAL NOT NULL);
"""
_ULTIMA_PASADA = {"dia": ""}


def envio_activo() -> bool:
    return os.getenv("EDITOR_RECUPERAR_ENVIAR", "0").strip().lower() in ("1", "true", "si", "sí")


def _db():
    c = est._db()
    c.executescript(_ESQUEMA)
    return c


def _ts(iso: Any) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


# ── Baja con un clic ──────────────────────────────────────────────────────────
def _firma(cuenta: str) -> str:
    sal = (os.getenv("EDITOR_STATS_SALT") or os.getenv("API_KEY") or "nebulabs").encode()
    return hmac.new(sal, b"baja|" + cuenta.encode(), hashlib.sha256).hexdigest()[:20]


def enlace_baja(email: str) -> str:
    cid = est.cuenta_id(email) or ""
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or "https://factory.nebulabsmedia.com"
    return f"{base}/api/v1/editor-auto/web/baja?c={cid}&f={_firma(cid)}"


def dar_de_baja(cuenta: str, firma: str) -> bool:
    if not cuenta or not hmac.compare_digest(_firma(cuenta), firma or ""):
        return False
    try:
        with est._lock:
            c = _db()
            c.execute("INSERT OR IGNORE INTO bajas(cuenta, ts) VALUES (?, ?)", (cuenta, time.time()))
            c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[recuperar] baja falló: %s", e)
        return False


# ── Reglas ────────────────────────────────────────────────────────────────────
def _actividad() -> tuple[dict[str, float], float | None]:
    """(último vídeo por usuario del editor, inicio de los datos)."""
    c = _db()
    ultimo = {u: f for u, f in c.execute(
        "SELECT usuario, MAX(COALESCE(fin, inicio)) FROM trabajos GROUP BY usuario") if u}
    fila = c.execute("SELECT MIN(t) FROM (SELECT MIN(inicio) t FROM trabajos "
                     "UNION ALL SELECT MIN(actualizada) FROM cuentas)").fetchone()
    return ultimo, (fila[0] if fila else None)


def candidatos(cuentas: Iterable[dict], usuarios_por_email: dict[str, str] | None = None,
               *, ahora: float | None = None) -> list[dict]:
    """A quién iría cada aviso hoy (no manda nada)."""
    ahora = ahora or time.time()
    usuarios = {k.lower(): v for k, v in (usuarios_por_email or {}).items()}
    try:
        c = _db()
        ya = {(a, r) for a, r in c.execute("SELECT cuenta, regla FROM avisos")}
        bajas = {b for (b,) in c.execute("SELECT cuenta FROM bajas")}
        ultimo, inicio = _actividad()
    except Exception as e:  # noqa: BLE001
        logger.warning("[recuperar] sin base de datos: %s", e)
        return []
    out: list[dict] = []
    for a in cuentas:
        email = str(a.get("email") or "").strip().lower()
        if "@" not in email or a.get("banned") or a.get("role") == "admin":
            continue
        cid = est.cuenta_id(email)
        if cid in bajas:
            continue
        plan = a.get("planId")
        prueba = int(a.get("trialVideos") or 0)
        alta = _ts(a.get("createdAt"))
        usuario = usuarios.get(email)
        ult = ultimo.get(usuario) if usuario else None
        regla, motivo = None, ""
        if not plan:
            if prueba >= PRUEBA_INICIAL and ult is None and alta \
                    and ahora - alta >= HORAS_SIN_EMPEZAR * 3600:
                regla = "sin_empezar"
                motivo = f"alta hace {int((ahora - alta) // 86400)} d sin mandar vídeos"
            elif prueba == 0:
                ref = ult or _ts(a.get("lastLoginAt")) or alta
                if ref and ahora - ref >= DIAS_PRUEBA_GASTADA * 86400:
                    regla = "prueba_gastada"
                    motivo = f"prueba gastada, {int((ahora - ref) // 86400)} d sin pagar"
        else:
            # Hace falta haber mirado al menos 7 días para decir que está parado.
            ref = ult or inicio
            if ref and ahora - ref >= DIAS_PLAN_PARADO * 86400:
                regla = "plan_parado"
                motivo = f"plan {plan}, {int((ahora - ref) // 86400)} d sin vídeos"
        if regla and (cid, regla) not in ya:
            out.append({"email": email, "cuenta": cid, "usuario": usuario,
                        "nombre": (a.get("name") or "").split(" ")[0][:30],
                        "regla": regla, "motivo": motivo, "plan": plan, "prueba": prueba})
    return out


# ── Emails ────────────────────────────────────────────────────────────────────
_TEXTOS = {
    "sin_empezar": {
        "asunto": "Tus vídeos gratis te están esperando",
        "parrafos": [
            "Te registraste en Nebulabs Media, pero aún no nos has mandado ningún vídeo.",
            "Es sencillo: grabas con el móvil, lo subes desde tu panel y te lo devolvemos "
            "editado, con los silencios cortados y subtítulos. La prueba es gratis.",
        ],
        "boton": "Subir mi primer vídeo", "ruta": "/panel",
    },
    "prueba_gastada": {
        "asunto": "¿Qué te pareció tu vídeo?",
        "parrafos": [
            "Ya has usado tus vídeos de prueba. Esperamos que te gustara el resultado.",
            "Si quieres seguir recibiendo tus vídeos editados, en la página de planes "
            "tienes los precios y lo que incluye cada uno.",
        ],
        "boton": "Ver los planes", "ruta": "/precios",
    },
    "plan_parado": {
        "asunto": "Tu plan sigue activo: ¿nos mandas un vídeo?",
        "parrafos": [
            "Hace unos días que no nos mandas vídeos y tu plan sigue activo.",
            "Cuando quieras, súbelo desde tu panel y te lo devolvemos editado.",
        ],
        "boton": "Ir a mi panel", "ruta": "/panel",
    },
}


def componer(cand: dict) -> tuple[str, str, str]:
    """(asunto, html, texto) del aviso."""
    t = _TEXTOS[cand["regla"]]
    web = os.getenv("NEBULABS_WEB_URL", "https://nebulabsmedia.com").rstrip("/")
    link = web + t["ruta"]
    baja = enlace_baja(cand["email"])
    hola = f"¡Hola {escape(cand.get('nombre') or '')}!".replace("¡Hola !", "¡Hola!")
    ps = "".join(f'<p style="margin:0 0 10px;font-size:15px;color:#374151;line-height:1.5">'
                 f"{escape(p)}</p>" for p in t["parrafos"])
    html = (
        '<div style="margin:0;padding:0;background:#f4f5f7">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;background:#ffffff;border-radius:16px;overflow:hidden;'
        'font-family:Arial,Helvetica,sans-serif">'
        '<tr><td style="background:#06b6d4;background:linear-gradient(90deg,#06b6d4,#7c3aed);'
        'padding:20px 28px"><span style="color:#ffffff;font-size:18px;font-weight:700">Nebulabs'
        '<span style="opacity:.85;font-weight:500"> Media</span></span></td></tr>'
        f'<tr><td style="padding:28px"><h1 style="margin:0 0 12px;font-size:20px;color:#111827">'
        f'{hola}</h1>{ps}'
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:20px 0 4px"><tr>'
        '<td style="border-radius:10px;background:#06b6d4">'
        f'<a href="{link}" style="display:inline-block;padding:13px 28px;font-size:15px;'
        f'font-weight:700;color:#ffffff;text-decoration:none">{escape(t["boton"])} →</a>'
        '</td></tr></table></td></tr>'
        '<tr><td style="background:#0f172a;padding:16px 28px">'
        '<span style="color:#94a3b8;font-size:12px">Nebulabs Media · Edición de vídeo · '
        f'<a href="{baja}" style="color:#94a3b8">No quiero más avisos</a></span>'
        '</td></tr></table></td></tr></table></div>'
    )
    texto = (hola.replace("&amp;", "&") + "\n\n" + "\n\n".join(t["parrafos"])
             + f"\n\n{t['boton']}: {link}\n\nNebulabs Media\nNo quiero más avisos: {baja}")
    return t["asunto"], html, texto


def enviar(cands: list[dict], *, enviar_fn: Callable[[list[str], str, str, str], dict] | None = None,
           log: Callable[[str], None] = logger.info) -> dict:
    """Manda los avisos (solo si EDITOR_RECUPERAR_ENVIAR=1) y los apunta."""
    if not envio_activo():
        return {"enviados": 0, "simulados": len(cands), "errores": 0}
    if enviar_fn is None:
        from src.editor_auto.services import email_notify
        enviar_fn = email_notify._send
    n_ok = n_err = 0
    c = _db()
    for cand in cands[:MAX_POR_PASADA]:
        asunto, html, texto = componer(cand)
        r = enviar_fn([cand["email"]], asunto, html, texto)
        if r.get("ok"):
            with est._lock:
                c.execute("INSERT OR IGNORE INTO avisos(cuenta, regla, ts) VALUES (?, ?, ?)",
                          (cand["cuenta"], cand["regla"], time.time()))
                c.commit()
            n_ok += 1
        else:
            n_err += 1
            log(f"[recuperar] no se pudo avisar ({cand['regla']}): {r.get('error')}")
    log(f"[recuperar] avisos enviados {n_ok}, fallidos {n_err}")
    return {"enviados": n_ok, "simulados": 0, "errores": n_err}


def _cuentas_y_usuarios() -> tuple[list[dict], dict[str, str]]:
    from src.editor_auto.repos import UserRepo
    from src.editor_auto.repos.web_account_repo import get_web_account_repo
    cuentas = get_web_account_repo().list_all()
    nombres = {(u.account_email or "").strip().lower(): u.name for u in UserRepo().list_all()
               if getattr(u, "account_email", None) and not getattr(u, "deleted", False)}
    return cuentas, nombres


def simular() -> dict:
    """Para la pantalla de Estadísticas: a quién iría hoy, sin mandar nada."""
    try:
        cuentas, nombres = _cuentas_y_usuarios()
    except Exception as e:  # noqa: BLE001
        return {"envio_activo": envio_activo(), "candidatos": [], "error": str(e)[:200]}
    cands = candidatos(cuentas, nombres)
    try:
        enviados = _db().execute("SELECT regla, COUNT(*) FROM avisos GROUP BY regla").fetchall()
        bajas = _db().execute("SELECT COUNT(*) FROM bajas").fetchone()[0]
    except Exception:  # noqa: BLE001
        enviados, bajas = [], 0
    return {
        "envio_activo": envio_activo(),
        "candidatos": [{"usuario": x["usuario"], "email": _ocultar(x["email"]),
                        "regla": x["regla"], "motivo": x["motivo"]} for x in cands],
        "enviados": dict(enviados), "bajas": bajas,
    }


def _ocultar(email: str) -> str:
    nombre, _, dominio = email.partition("@")
    return (nombre[:2] + "…@" + dominio) if dominio else "…"


def maybe_pasada(log: Callable[[str], None] = logger.info) -> dict | None:
    """Una vez al día, desde el loop del draft_sweeper. Sin el interruptor no hace nada."""
    if not envio_activo():
        return None
    hoy = est._hoy()
    if _ULTIMA_PASADA["dia"] == hoy or datetime.now().hour < 10:
        return None  # nada de emails de madrugada
    _ULTIMA_PASADA["dia"] = hoy
    try:
        cuentas, nombres = _cuentas_y_usuarios()
    except Exception as e:  # noqa: BLE001
        log(f"[recuperar] sin cuentas: {e}")
        return None
    return enviar(candidatos(cuentas, nombres), log=log)
