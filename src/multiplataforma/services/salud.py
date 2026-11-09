"""Vigía de salud del publicador Multiplataforma: de datos en bruto a incidencias.

Solo biblioteca estándar: corre en el host. Recibe el JSON de
`scripts/multiplataforma_salud.py` (tokens, cola, reproducciones de FB) y la
cola de `tick.log`, y devuelve incidencias `{clave, nivel, texto, notificar}`.
`filtrar_nuevas` las deduplica con un estado en disco: cada una se avisa UNA
vez (y un recordatorio a la semana si sigue), y se avisa también cuando se
resuelve. No reintenta, no publica, no toca la cola.
"""

from __future__ import annotations

import collections
import datetime as dt
import re

HORA = 3600
DIA = 86400
ATRASO_S = 1 * HORA  # una publicación pendiente/error más de 1 h después de su hora = atascada
FALLIDO_VENTANA_S = 2 * DIA
TOKEN_AVISO_S = 3 * DIA
THREADS_SIN_RENOVAR_AVISO_S = 14 * DIA  # se renueva cada 7 días; dura 60
THREADS_SIN_RENOVAR_GRAVE_S = 50 * DIA
FB_EDAD_MIN_S = 2 * DIA
FB_CERO_MAX = 2
FB_MIN_REELS = 3
TICK_PARADO_S = 45 * 60  # el cron va cada 15 min
RECORDATORIO_S = 7 * DIA
SCOPE_COMENTARIO = "pages_manage_engagement"
ESTADOS_ATASCO = ("pendiente", "error")
NIVELES = ("info", "aviso", "grave")

_URL = re.compile(r"https?://\S+")
_NUM = re.compile(r"\d{5,}")
_BLOQUE = re.compile(r"^=== (\S+)\s*$", re.M)


def _inc(clave: str, nivel: str, texto: str, notificar: bool = False) -> dict:
    return {"clave": clave, "nivel": nivel, "texto": texto, "notificar": notificar}


def normalizar(msg: str) -> str:
    """Quita URLs e ids para agrupar el mismo error de distintas publicaciones."""
    return _NUM.sub("#", _URL.sub("<url>", str(msg or ""))).strip()[:160]


# ── tokens ─────────────────────────────────────────────────────────────────

def de_tokens(cuenta: str, tokens: dict, ahora: float) -> list[dict]:
    out = []
    for pl, t in (tokens or {}).items():
        base = f"token:{cuenta}:{pl}"
        if not t.get("valido"):
            out.append(_inc(f"{base}:invalido", "grave",
                            f"{cuenta} · el token de {pl} no vale ({t.get('error') or 'sin detalle'}): no se publica ahí. "
                            "Hay que reconectar la cuenta en /conectar-meta.", notificar=True))
            continue
        exp = t.get("expira")
        if exp and exp - ahora < TOKEN_AVISO_S:
            dias = max(0, (exp - ahora) / DIA)
            out.append(_inc(f"{base}:caduca", "grave",
                            f"{cuenta} · el token de {pl} caduca en {dias:.1f} días. Reconectar en /conectar-meta.",
                            notificar=True))
        if pl == "facebook" and t.get("scopes") is not None and SCOPE_COMENTARIO not in t["scopes"]:
            out.append(_inc(f"{base}:sin_comentario", "info",
                            f"{cuenta} · el token de FB no tiene {SCOPE_COMENTARIO}: los reels salen sin el comentario "
                            "con el enlace de afiliado."))
    return out


def de_threads(cuenta: str, tokens: dict, renovado: float | None, ahora: float) -> list[dict]:
    if "threads" not in (tokens or {}) or not renovado:
        return []
    edad = ahora - renovado
    if edad >= THREADS_SIN_RENOVAR_GRAVE_S:
        return [_inc(f"threads:{cuenta}:sin_renovar", "grave",
                     f"{cuenta} · el token de Threads lleva {edad / DIA:.0f} días sin renovarse (caduca a los 60).",
                     notificar=True)]
    if edad >= THREADS_SIN_RENOVAR_AVISO_S:
        return [_inc(f"threads:{cuenta}:sin_renovar", "aviso",
                     f"{cuenta} · el token de Threads lleva {edad / DIA:.0f} días sin renovarse (debería ser cada 7): "
                     "mira `threads_renovados` en tick.log.")]
    return []


# ── cola ───────────────────────────────────────────────────────────────────

def de_cola(pubs: list[dict], ahora: float) -> list[dict]:
    atascadas: dict = collections.defaultdict(list)
    fallidas: dict = collections.defaultdict(list)
    for p in pubs or []:
        prog = p.get("programada_en") or 0
        for pl, est in (p.get("estado") or {}).items():
            if pl not in (p.get("plataformas") or [pl]):
                continue
            if est in ESTADOS_ATASCO and ahora - prog > ATRASO_S:
                atascadas[(p["cuenta"], pl)].append(p)
            elif est == "fallido" and ahora - prog < FALLIDO_VENTANA_S:
                fallidas[(p["cuenta"], pl)].append(p)
    out = []
    for (cuenta, pl), ps in sorted(atascadas.items()):
        horas = (ahora - min(p["programada_en"] for p in ps)) / HORA
        out.append(_inc(f"cola:{cuenta}:{pl}:atascada", "aviso",
                        f"{cuenta} · {len(ps)} publicación(es) de {pl} sin salir (la más vieja hace {horas:.0f} h): "
                        f"{_primer_error(ps, pl)}"))
    for (cuenta, pl), ps in sorted(fallidas.items()):
        out.append(_inc(f"cola:{cuenta}:{pl}:fallida", "aviso",
                        f"{cuenta} · {len(ps)} publicación(es) de {pl} FALLIDAS en 48 h: {_primer_error(ps, pl)}"))
    return out


def _primer_error(ps: list[dict], pl: str) -> str:
    errs = collections.Counter(normalizar((p.get("errores") or {}).get(pl)) for p in ps)
    errs.pop("", None)
    return errs.most_common(1)[0][0] if errs else "sin mensaje de error"


# ── Facebook a cero ────────────────────────────────────────────────────────

def de_fb_cero(cuenta: str, reels: list[dict], ahora: float) -> list[dict]:
    """Todos los reels de >48 h con dato están a 0-2 reproducciones."""
    viejos = [r["plays"] for r in reels or [] if r.get("plays") is not None and ahora - (r.get("ts") or ahora) >= FB_EDAD_MIN_S]
    if len(viejos) < FB_MIN_REELS or max(viejos) > FB_CERO_MAX:
        return []
    return [_inc(f"fb:{cuenta}:cero", "aviso",
                 f"{cuenta} · Facebook a cero: {len(viejos)} reels de más de 48 h con 0-{FB_CERO_MAX} reproducciones "
                 "(app de Meta en desarrollo, tarea 225).")]


# ── tick.log ───────────────────────────────────────────────────────────────

def bloques_log(texto: str) -> list[tuple[float, str]]:
    """[(ts, cuerpo)] de cada tick («=== <ISO>» abre un bloque)."""
    marcas = list(_BLOQUE.finditer(texto or ""))
    out = []
    for i, m in enumerate(marcas):
        try:
            ts = dt.datetime.fromisoformat(m.group(1)).timestamp()
        except ValueError:
            continue
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        out.append((ts, texto[m.end():fin]))
    return out


def de_log(texto: str, ahora: float, ultimos: int = 4) -> list[dict]:
    bloques = bloques_log(texto)
    if not bloques:
        return [_inc("tick:sin_datos", "aviso", "tick.log no tiene ningún tick reconocible.")]
    out = []
    ultimo_ts = bloques[-1][0]
    if ahora - ultimo_ts > TICK_PARADO_S:
        out.append(_inc("tick:parado", "grave",
                        f"El tick de Multiplataforma no corre desde hace {(ahora - ultimo_ts) / 60:.0f} min "
                        "(cron cada 15): no se publica nada.", notificar=True))
    recientes = bloques[-ultimos:]
    rotos = [c for _, c in recientes if "Traceback" in c]
    if rotos:
        lineas = [ln.strip() for ln in rotos[-1].splitlines() if ln.strip()]
        final = next((ln for ln in reversed(lineas) if re.match(r"^\w[\w.]*(Error|Exception)\b", ln)), lineas[-1] if lineas else "")
        out.append(_inc("tick:excepcion", "grave",
                        f"El tick revienta ({len(rotos)} de los últimos {len(recientes)}): {normalizar(final)}"))
    # Los errores de cada publicación ya salen de la cola (`de_cola`); aquí solo lo que para el tick.
    return out


# ── todo junto y deduplicado ───────────────────────────────────────────────

def analizar(datos: dict, log_texto: str | None, ahora: float) -> list[dict]:
    out = []
    for cuenta, c in sorted((datos.get("cuentas") or {}).items()):
        tokens = c.get("tokens") or {}
        out += de_tokens(cuenta, tokens, ahora)
        out += de_threads(cuenta, tokens, c.get("threads_renovado"), ahora)
        out += de_fb_cero(cuenta, c.get("fb_reels") or [], ahora)
    out += de_cola(datos.get("pubs") or [], ahora)
    if log_texto is not None:
        out += de_log(log_texto, ahora)
    return out


def filtrar_nuevas(incidencias: list[dict], estado: dict, ahora: float) -> tuple[list[dict], dict]:
    """(avisos a mandar, estado nuevo). Nueva o más grave → aviso; sigue 7 días → recordatorio; desaparece → resuelta."""
    nuevo: dict = {}
    avisos = []
    for inc in incidencias:
        previo = estado.get(inc["clave"])
        mas_grave = previo and NIVELES.index(inc["nivel"]) > NIVELES.index(previo.get("nivel", "info"))
        if previo is None or mas_grave:
            avisos.append(inc)
            nuevo[inc["clave"]] = {"nivel": inc["nivel"], "desde": ahora, "avisado": ahora, "texto": inc["texto"]}
        elif ahora - previo.get("avisado", 0) >= RECORDATORIO_S and inc["nivel"] != "info":
            dias = (ahora - previo.get("desde", ahora)) / DIA
            avisos.append({**inc, "texto": f"Sigue igual desde hace {dias:.0f} días · {inc['texto']}", "notificar": False})
            nuevo[inc["clave"]] = {**previo, "avisado": ahora, "texto": inc["texto"]}
        else:
            nuevo[inc["clave"]] = {**previo, "texto": inc["texto"]}
    for clave, previo in estado.items():
        if clave not in nuevo and previo.get("nivel") != "info":
            avisos.append(_inc(clave, "info", f"✅ Resuelto: {previo.get('texto', clave)}"))
    return avisos, nuevo
