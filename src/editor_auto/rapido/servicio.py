"""Lógica del Editor rápido: créditos, fichas de vídeo, cortes y runner.

- 1 crédito = 1 VÍDEO: hasta 5 min del original gasta 1, de 5 a 10 min gasta 2
  (docs/PRECIOS_CREDITOS.md de nebulabs-media, 15/11/2026). Antes fue 1 crédito = 1 minuto
  (sin `unidad`) y luego 1 crédito = 1 segundo (`unidad: "s"`): los saldos viejos se pasan
  solos a vídeos la primera vez que se leen (minutos → igual; segundos → /60 hacia arriba).
- V1: saldo en el Redis del Editor, SIN pagos reales. Alta = N vídeos gratis
  (`EDITOR_RAPIDO_FREE_CREDITS`, 3 por defecto) la primera vez que se ve el email.
- Se cobra al pulsar «Cortar» y se devuelve solo si el trabajo falla (idempotente).
- El retoque «devolver un corte» no cuesta créditos en V1.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.editor_auto.repos.redis_base import get_editor_redis

RITMOS = ("natural", "sin_pausas")
FORMATOS = ("9:16", "original")
IDIOMAS = ("auto", "es", "en")

POSICIONES = ("abajo", "centro", "arriba")
_POS_Y = {"abajo": 0.78, "centro": 0.5, "arriba": 0.18}
# Colores de resalte que ofrece la web (el usuario puede sobrescribir el del estilo).
COLORES = ("#FFFFFF", "#FDE047", "#F97316", "#EF2D2D", "#EC4899", "#7C3AED", "#2563EB", "#22C55E")
# Fuentes ofrecidas: ids de `style_mapper._FONT_CANDIDATES` (tipografías incluidas en assets/fonts).
FUENTES = (
    ("montserrat", "Montserrat"), ("montserratBlack", "Montserrat Black"), ("anton", "Anton"),
    ("luckiest", "Luckiest Guy"), ("bangers", "Bangers"), ("marker", "Rotulador"),
    ("caveat", "Manuscrita"), ("fredoka", "Fredoka"),
)
_K_CUENTAS = "editor_rapido:cuentas"
logger = logging.getLogger("editor_auto.rapido")
TZ = ZoneInfo("Europe/Madrid")
# Eventos y agregados por día: 180 días por defecto.
EVENTOS_TTL_S = int(os.getenv("EDITOR_RAPIDO_EVENTOS_DIAS", "180")) * 86400
MAX_EVENTOS = 300  # por vídeo
MAX_INDICE = 500   # vídeos del índice global (admin)

MAX_MINUTOS = int(os.getenv("EDITOR_RAPIDO_MAX_MINUTOS", "10"))
MAX_BYTES = int(os.getenv("EDITOR_RAPIDO_MAX_MB", "1024")) * 1024 * 1024
# Cortes más cortos que esto no se enseñan en la lista de retoque.
MIN_CORTE_S = 0.25

_LOCK = threading.Lock()  # un solo proceso de API: basta para el saldo


def gratis_inicial() -> int:
    try:
        return max(0, int(os.getenv("EDITOR_RAPIDO_FREE_CREDITS", "3")))
    except ValueError:
        return 3


def cr(x) -> float | int:
    """Créditos en pasos de medio (0,5 = 30 s). Entero si es redondo, para que el JSON
    siga diciendo 105 y no 105.0."""
    try:
        v = round(float(x or 0) * 2) / 2
    except (TypeError, ValueError):
        v = 0.0
    return int(v) if v == int(v) else v


MIN_POR_CREDITO = 5  # un vídeo de hasta 5 min gasta 1 crédito; de 5 a 10 min, 2
UNIDAD = "v"         # 1 crédito = 1 vídeo ("s" = segundos y sin campo = minutos: saldos viejos)


def creditos_de(duracion_s: float) -> int:
    """Vídeos que gasta: 1 hasta 5:00 (incluido), 2 de ahí a 10 min."""
    try:
        seg = float(duracion_s)
    except (TypeError, ValueError):
        seg = 0.0
    return max(1, math.ceil(seg / (MIN_POR_CREDITO * 60) - 1e-9))


def raiz_datos() -> Path:
    explicita = os.getenv("EDITOR_RAPIDO_DIR")
    if explicita:
        p = Path(explicita)
    else:
        from src.api.temp_storage import upload_subdir
        p = upload_subdir("editor_rapido")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ───────────────────────── Opciones de estilo ─────────────────────────

def estilos_subtitulos() -> list[dict]:
    from src.catalogo_edicion import subtitulos
    out = []
    for x in subtitulos("editor_auto"):
        m = x.get("motor") or {}
        out.append({
            "id": x["id"], "nombre": x.get("nombre", x["id"]), "fuente": x.get("fuente"),
            "color_texto": m.get("text"), "color_resalte": m.get("hl"),
            "modo_resalte": m.get("mode"), "borde": m.get("stroke"),
        })
    return out


def flechas_disponibles() -> list[dict]:
    """Flechas de bucle del catálogo (las animaciones de Navidad no: no son una flecha)."""
    from src.catalogo_edicion import cargar, flechas
    grupos = {g["id"]: g.get("nombre", g["id"]) for g in cargar().get("grupos_flecha", [])}
    out = []
    for f in flechas("editor_auto"):
        if f.get("animacion", "bucle") != "bucle":
            continue
        fid = f["fichero"].rsplit(".", 1)[0]
        g = grupos.get(f.get("grupo"))
        out.append({"id": fid, "nombre": f"{g} · {f['nombre']}" if g else f["nombre"], "fichero": f["fichero"]})
    return out


def fichero_flecha(fid: str) -> str | None:
    return next((f["fichero"] for f in flechas_disponibles() if f["id"] == fid), None)


def png_flecha(fid: str) -> Path | None:
    """PNG de una flecha (fotograma del .mov con transparencia), cacheado en disco."""
    fichero = fichero_flecha(fid)
    if not fichero:
        return None
    from src.editor_auto.config import arrows_folder
    origen = Path(arrows_folder()) / fichero
    if not origen.is_file():
        return None
    destino_dir = raiz_datos() / "_flechas_png"
    destino_dir.mkdir(parents=True, exist_ok=True)
    png = destino_dir / f"{fid}.png"
    if not png.exists() or png.stat().st_size == 0:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "0.4", "-i", str(origen), "-frames:v", "1",
                 "-vf", "scale=256:-1", str(png)],
                capture_output=True, timeout=30, check=True,
            )
        except Exception:  # noqa: BLE001
            png.unlink(missing_ok=True)
            return None
    return png if png.exists() else None


def opciones(prefijo_api: str) -> dict:
    return {
        "estilos": estilos_subtitulos(),
        "colores": list(COLORES),
        "fuentes": [{"id": i, "nombre": n} for i, n in FUENTES],
        "flechas": [
            {"id": f["id"], "nombre": f["nombre"], "png_url": f"{prefijo_api}/flechas/{f['id']}.png"}
            for f in flechas_disponibles()
        ],
        "posiciones": list(POSICIONES),
    }


def validar_subtitulos(d: dict | None) -> dict:
    """Normaliza y valida los ajustes de subtítulos. ValueError si algo no existe."""
    d = dict(d or {})
    estilos = {e["id"] for e in estilos_subtitulos()}
    estilo = d.get("estilo") or (estilos_subtitulos()[0]["id"] if estilos else None)
    if estilo is not None and estilo not in estilos:
        raise ValueError(f"Estilo de subtítulos desconocido: {estilo}")
    fuente = d.get("fuente")
    if fuente and fuente not in {i for i, _ in FUENTES}:
        raise ValueError(f"Fuente desconocida: {fuente}")
    pos = d.get("posicion") or "abajo"
    if pos not in POSICIONES:
        raise ValueError(f"Posición desconocida: {pos}")
    return {"activo": bool(d.get("activo", True)), "estilo": estilo, "color": d.get("color") or None,
            "fuente": fuente or None, "posicion": pos}


def validar_flecha(d: dict | None) -> dict:
    d = dict(d or {})
    activo = bool(d.get("activo", False))
    fid = d.get("id")
    if fid and not fichero_flecha(fid):
        raise ValueError(f"Flecha desconocida: {fid}")
    if activo and not fid:
        disp = flechas_disponibles()
        fid = disp[0]["id"] if disp else None
    return {"activo": activo, "id": fid or None}


# ───────────────────────── Redis ─────────────────────────

def _k_saldo(email: str) -> str:
    return f"rapido:saldo:{email}"


def _k_ficha(vid: str) -> str:
    return f"rapido:video:{vid}"


def _k_lista(email: str) -> str:
    return f"rapido:videos:{email}"


# Caducidad de los créditos: APAGADA por ahora (None = no caducan). Se guarda
# `ultima_recarga` para poder activarla más adelante (p. ej. distinta según el pack).
CADUCIDAD_DIAS: int | None = None


def caduca_en(s: dict) -> float | None:
    """Momento (epoch) en que caduca el saldo, o None si los créditos no caducan."""
    if not CADUCIDAD_DIAS:
        return None
    base = float(s.get("ultima_recarga") or s.get("creado") or time.time())
    return base + CADUCIDAD_DIAS * 86400


def saldo(email: str) -> dict:
    """Saldo del usuario; lo crea con los créditos gratis la primera vez.
    Si la caducidad está activa (CADUCIDAD_DIAS) y ha vencido, el saldo se pone a 0."""
    r = get_editor_redis()
    with _LOCK:
        s = r.get_json(_k_saldo(email))
        if s is None:
            ahora = time.time()
            s = {"creditos": gratis_inicial(), "gratis_dados": gratis_inicial(), "creado": ahora,
                 "ultima_recarga": ahora, "unidad": UNIDAD}
            r.set_json(_k_saldo(email), s)
            r.sadd(_K_CUENTAS, email)
            return s
        cambiado = False
        if s.get("unidad") != UNIDAD:  # saldo de cuando 1 crédito era 1 minuto o 1 segundo
            div = 60 if s.get("unidad") == "s" else 1
            s["creditos"] = math.ceil(float(s.get("creditos", 0) or 0) / div - 1e-9)
            s["gratis_dados"] = math.ceil(int(s.get("gratis_dados", 0) or 0) / div - 1e-9)
            s["unidad"] = UNIDAD
            cambiado = True
        if not s.get("ultima_recarga"):  # cuentas de antes de la caducidad: cuentan desde hoy
            s["ultima_recarga"] = time.time()
            cambiado = True
        fin = caduca_en(s)
        if fin is not None and cr(s.get("creditos", 0)) > 0 and time.time() > fin:
            s["caducados"] = cr(cr(s.get("caducados", 0)) + cr(s["creditos"]))
            s["creditos"] = 0
            cambiado = True
        if cambiado:
            r.set_json(_k_saldo(email), s)
        return s


def _guardar_saldo(email: str, s: dict) -> None:
    get_editor_redis().set_json(_k_saldo(email), s)


def ajustar_creditos(email: str, delta: float, *, recarga: bool = False) -> float | int:
    """Suma (o resta) créditos. Devuelve el saldo nuevo (nunca < 0).
    `recarga=True` (compra o regalo) apunta `ultima_recarga` (base de la caducidad, si se
    activa); una devolución por fallo no la cambia."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        s["creditos"] = cr(max(0, cr(s.get("creditos", 0)) + cr(delta)))
        if recarga and cr(delta) > 0:
            s["ultima_recarga"] = time.time()
        _guardar_saldo(email, s)
        get_editor_redis().sadd(_K_CUENTAS, email)
        return s["creditos"]


def cobrar(email: str, n: float) -> bool:
    """Descuenta `n` créditos si alcanzan. False si no hay saldo."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        n = cr(n)
        if cr(s.get("creditos", 0)) < n:
            return False
        s["creditos"] = cr(cr(s["creditos"]) - n)
        _guardar_saldo(email, s)
        return True


def listar_cuentas() -> list[dict]:
    """Cuentas con saldo: set Redis `editor_rapido:cuentas`; si está vacío, se rellena
    escaneando las claves de saldo (cuentas anteriores al set)."""
    r = get_editor_redis()
    emails = list(r.smembers(_K_CUENTAS) or [])
    if not emails:
        try:
            if hasattr(r, "_cmd"):
                patron = r._full_key(_k_saldo("*"))
                claves = r._cmd(["KEYS", patron]) or []
                pref = r._full_key(_k_saldo(""))
            else:  # FakeRedis de los tests
                claves = r.keys(_k_saldo("*"))
                pref = _k_saldo("")
            emails = [c[len(pref):] if c.startswith(pref) else c.split("rapido:saldo:", 1)[-1] for c in claves]
        except Exception:  # noqa: BLE001
            emails = []
        for e in emails:
            r.sadd(_K_CUENTAS, e)
    out = []
    for e in sorted(set(emails)):
        s = r.get_json(_k_saldo(e)) or {}
        out.append({"email": e, "creditos": cr(s.get("creditos", 0)),
                    "n_videos": len(r.smembers(_k_lista(e)) or [])})
    return out


def nueva_ficha(email: str, nombre: str, duracion_s: float, bytes_: int) -> dict:
    vid = uuid.uuid4().hex[:12]
    ficha = {
        "id": vid, "email": email, "nombre": nombre,
        "duracion_s": round(duracion_s, 2), "bytes": bytes_,
        "creditos": creditos_de(duracion_s),
        "estado": "subido",  # subido → cola → listo | error
        "creado": time.time(), "job_id": None, "ajustes": None,
        "cobrado": False, "devuelto": False,
        "duracion_final_s": None, "error": None, "version": 0,
        "devueltos": [],  # ids de cortes que el usuario ha devuelto
    }
    guardar_ficha(ficha)
    get_editor_redis().sadd(_k_lista(email), vid)
    return ficha


def guardar_ficha(ficha: dict) -> None:
    get_editor_redis().set_json(_k_ficha(ficha["id"]), ficha)


def cargar_ficha(vid: str, email: str | None = None) -> dict | None:
    if not vid.isalnum():
        return None
    f = get_editor_redis().get_json(_k_ficha(vid))
    if f is None or (email is not None and f.get("email") != email):
        return None
    return f


def listar_fichas(email: str, limite: int = 20) -> list[dict]:
    ids = get_editor_redis().smembers(_k_lista(email))
    fichas = [f for f in (cargar_ficha(i, email) for i in ids) if f]
    fichas.sort(key=lambda f: f.get("creado", 0), reverse=True)
    return fichas[:limite]


def borrar_ficha(ficha: dict) -> None:
    r = get_editor_redis()
    r.delete(_k_ficha(ficha["id"]))
    r.srem(_k_lista(ficha["email"]), ficha["id"])
    shutil.rmtree(carpeta(ficha["id"]), ignore_errors=True)


def devolver_creditos(ficha: dict) -> None:
    """Reembolsa lo cobrado si el trabajo falló. Idempotente."""
    with _LOCK:
        f = cargar_ficha(ficha["id"]) or ficha
        if not f.get("cobrado") or f.get("devuelto"):
            return
        f["devuelto"] = True
        guardar_ficha(f)
    ajustar_creditos(f["email"], cr(f.get("creditos", 0)))
    descontar_historial(f["email"], f.get("cobrado_fecha"), cr(f.get("creditos", 0)))


# ───────────────────────── Eventos, historial y puntuación ─────────────────────────

def fecha_dia(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), TZ).strftime("%Y-%m-%d")


def fecha_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).isoformat(timespec="seconds")


def _k_eventos(vid: str) -> str:
    return f"rapido:eventos:{vid}"


def _k_dia(dia: str) -> str:
    return f"rapido:dia:{dia}"


def _k_hist(email: str) -> str:
    return f"rapido:hist:{email}"


_K_INDICE = "rapido:indice"


def _ttl(key: str) -> None:
    exp = getattr(get_editor_redis(), "expire", None)
    if exp:
        try:
            exp(key, EVENTOS_TTL_S)
        except Exception:  # noqa: BLE001
            pass


def _mget(keys: list[str]) -> list:
    r = get_editor_redis()
    f = getattr(r, "mget_json", None)
    return f(keys) if f else [r.get_json(k) for k in keys]


def registrar_evento(vid: str, email: str, tipo: str, datos: dict | None = None) -> dict | None:
    """Añade un evento a la lista del vídeo (`rapido:eventos:<vid>`, TTL 180 días, máx. 300).

    Nunca lanza: registrar no puede romper el flujo del usuario. Tipos usados: subido, cortar,
    listo, aviso, error, retocar, estilo, descarga, valoracion, borrado.
    """
    try:
        ahora = time.time()
        ev = {"t": round(ahora, 2), "fecha": fecha_iso(ahora), "tipo": tipo, "email": email, **(datos or {})}
        r = get_editor_redis()
        with _LOCK:
            lst = r.get_json(_k_eventos(vid))
            lst = lst if isinstance(lst, list) else []
            lst.append(ev)
            r.set_json(_k_eventos(vid), lst[-MAX_EVENTOS:])
            _ttl(_k_eventos(vid))
        return ev
    except Exception as e:  # noqa: BLE001
        logger.warning("[rapido] no se pudo registrar el evento %s de %s: %s", tipo, vid, e)
        return None


def leer_eventos(vid: str) -> list[dict]:
    lst = get_editor_redis().get_json(_k_eventos(vid))
    return lst if isinstance(lst, list) else []


def indexar(vid: str) -> None:
    """Pone el vídeo al principio del índice global (para el listado del admin)."""
    try:
        r = get_editor_redis()
        with _LOCK:
            idx = r.get_json(_K_INDICE)
            idx = [i for i in (idx if isinstance(idx, list) else []) if i != vid]
            r.set_json(_K_INDICE, [vid, *idx][:MAX_INDICE])
    except Exception as e:  # noqa: BLE001
        logger.warning("[rapido] no se pudo indexar %s: %s", vid, e)


def contar_uso(email: str, creditos: float, duracion_s: float) -> str:
    """Suma un vídeo cortado al agregado del día (global y del usuario). Devuelve la fecha."""
    dia = fecha_dia()
    try:
        r = get_editor_redis()
        with _LOCK:
            d = r.get_json(_k_dia(dia)) or {}
            usuarios = set(d.get("usuarios") or [])
            usuarios.add(email)
            d = {"videos": int(d.get("videos", 0)) + 1,
                 "segundos": round(float(d.get("segundos", 0.0)) + float(duracion_s), 1),
                 "usuarios": sorted(usuarios)}
            r.set_json(_k_dia(dia), d)
            _ttl(_k_dia(dia))
            h = r.get_json(_k_hist(email)) or {}
            dias = dict(h.get("dias") or {})
            x = dict(dias.get(dia) or {"videos": 0, "creditos": 0})
            x["videos"] = int(x.get("videos", 0)) + 1
            x["creditos"] = cr(cr(x.get("creditos", 0)) + cr(creditos))
            dias[dia] = x
            for viejo in sorted(dias)[:-180]:
                dias.pop(viejo, None)
            r.set_json(_k_hist(email), {"dias": dias,
                                        "creditos_total": cr(cr(h.get("creditos_total", 0)) + cr(creditos))})
    except Exception as e:  # noqa: BLE001
        logger.warning("[rapido] no se pudo contar el uso de %s: %s", email, e)
    return dia


def descontar_historial(email: str, dia: str | None, creditos: float) -> None:
    """Resta del historial los créditos devueltos tras un fallo."""
    if not creditos:
        return
    try:
        r = get_editor_redis()
        with _LOCK:
            h = r.get_json(_k_hist(email)) or {}
            dias = dict(h.get("dias") or {})
            if dia and dia in dias:
                dias[dia] = {**dias[dia], "creditos": cr(max(0, cr(dias[dia].get("creditos", 0)) - cr(creditos)))}
            r.set_json(_k_hist(email), {"dias": dias,
                                        "creditos_total": cr(max(0, cr(h.get("creditos_total", 0)) - cr(creditos)))})
    except Exception as e:  # noqa: BLE001
        logger.warning("[rapido] no se pudo descontar el historial de %s: %s", email, e)


def historial(email: str, dias: int = 30) -> dict:
    """Días con actividad del usuario (más reciente primero) y créditos gastados en total."""
    h = get_editor_redis().get_json(_k_hist(email)) or {}
    desde = fecha_dia(time.time() - (dias - 1) * 86400)
    out = [{"fecha": f, "videos": int(x.get("videos", 0)), "minutos_gastados": cr(x.get("creditos", 0))}
           for f, x in sorted((h.get("dias") or {}).items(), reverse=True) if f >= desde]
    return {"dias": out, "creditos_gastados_total": cr(h.get("creditos_total", 0))}


def actividad(dias: int = 7, limite_videos: int = 100) -> dict:
    """Admin: agregado por día (con ceros, de más antiguo a más reciente) + últimos vídeos."""
    ahora = time.time()
    fechas = [fecha_dia(ahora - i * 86400) for i in range(dias - 1, -1, -1)]
    datos = _mget([_k_dia(f) for f in fechas])
    lista = [{"fecha": f, "videos": int((d or {}).get("videos", 0)),
              "minutos": round(float((d or {}).get("segundos", 0.0)) / 60.0, 1),
              "usuarios": len((d or {}).get("usuarios") or [])} for f, d in zip(fechas, datos)]
    idx = get_editor_redis().get_json(_K_INDICE)
    ids = idx if isinstance(idx, list) else []
    todas = [f for f in _mget([_k_ficha(i) for i in ids]) if f and f.get("estado") != "subiendo"]
    resumenes = [resumen_admin(f) for f in todas]
    return {"dias": lista, "videos": resumenes[:limite_videos], **estadisticas(todas, resumenes)}


def _media(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def estadisticas(fichas: list[dict], resumenes: list[dict] | None = None) -> dict:
    """Admin: totales y desglose por usuario de los vídeos del índice (últimos 500)."""
    resumenes = resumenes or [resumen_admin(f) for f in fichas]

    def bloque(fs: list[dict], rs: list[dict]) -> dict:
        listos = [r for r in rs if r["estado"] == "listo"]
        return {
            "videos": len(rs), "listos": len(listos), "errores": sum(r["estado"] == "error" for r in rs),
            "minutos_subidos": round(sum(float(f.get("duracion_s") or 0) for f in fs) / 60, 1),
            "minutos_quitados": round(sum(max(0.0, float(f.get("duracion_s") or 0) - float(f.get("duracion_final_s") or f.get("duracion_s") or 0))
                                          for f in fs if f.get("estado") == "listo") / 60, 1),
            "descargados": sum(r["descargado"] for r in rs),
            "con_cortes_devueltos": sum(r["devueltos"] > 0 for r in listos),
            "valorados": sum(nota_valor(r["nota"]) is not None for r in rs),
            "nota_media": _media([nota_valor(r["nota"]) for r in rs]),
            "calidad_media": _media([r["calidad"] for r in listos]),
            "proceso_medio_s": _media([f.get("proceso_s") for f in fs if f.get("estado") == "listo"]),
        }

    por: dict[str, list[int]] = {}
    for k, f in enumerate(fichas):
        por.setdefault(f.get("email") or "?", []).append(k)
    usuarios = []
    for email, ks in por.items():
        b = bloque([fichas[k] for k in ks], [resumenes[k] for k in ks])
        b.update(email=email, ultimo=max(resumenes[k]["fecha"] for k in ks), creditos=saldo(email).get("creditos"))
        usuarios.append(b)
    usuarios.sort(key=lambda u: (-u["videos"], u["email"]))
    return {"totales": {**bloque(fichas, resumenes), "usuarios": len(usuarios)}, "usuarios": usuarios}


def resumen_admin(f: dict) -> dict:
    return {
        "id": f["id"], "email": f.get("email"), "nombre": f.get("nombre"),
        "fecha": fecha_iso(f.get("creado", 0)), "duracion_s": f.get("duracion_s"),
        "estado": f.get("estado"), "cortes": f.get("n_cortes"),
        "devueltos": len(f.get("devueltos") or []),
        "descargado": int(f.get("descargas", 0)) > 0, "nota": f.get("nota"), "calidad": calidad(f),
    }


_BONUS_NOTA = {1: -30, 2: -20, 3: 0, 4: 5, 5: 10}


def nota_valor(nota: Any) -> int | None:
    """1-5, «bien» (=5) o «mal» (=1). None si no es válida."""
    if isinstance(nota, bool):
        return None
    if isinstance(nota, str):
        t = nota.strip().lower()
        if t in ("bien", "mal"):
            return 5 if t == "bien" else 1
        nota = int(t) if t.isdigit() else None
    return nota if isinstance(nota, int) and 1 <= nota <= 5 else None


def calidad(f: dict) -> int | None:
    """Puntuación interna 0-100 de un corte (solo vídeos «listo»; None si aún no vale).

        calidad = 80
                  − 60 · (cortes devueltos / cortes totales)      el usuario deshizo cortes
                  + {1: −30, 2: −20, 3: 0, 4: +5, 5: +10}[nota]  valoración «¿Qué tal el corte?»
                  + 15 si descargó SIN devolver ningún corte
        (limitada a 0-100). Base 80 y no 100 para que el «descargó sin tocar» tenga recorrido.
    """
    if f.get("estado") != "listo":
        return None
    n = int(f.get("n_cortes") or 0)
    dev = len(f.get("devueltos") or [])
    c = 80.0
    if n > 0:
        c -= 60.0 * min(1.0, dev / n)
    if f.get("nota") in _BONUS_NOTA:
        c += _BONUS_NOTA[f["nota"]]
    if f.get("descarga_sin_retocar") and not dev:
        c += 15
    return int(round(max(0.0, min(100.0, c))))


# ───────────────────────── Dataset de entrenamiento ─────────────────────────

def dataset_dir() -> Path:
    """`EDITOR_RAPIDO_DATASET_DIR` o `<raíz de datos>/_dataset` (en el volumen del disco ampliado
    vía `API_TEMP_PATH`). La limpieza global de `api_uploads` no toca `editor_rapido`."""
    e = os.getenv("EDITOR_RAPIDO_DATASET_DIR")
    return Path(e) if e else raiz_datos() / "_dataset"


def guardar_dataset(ficha: dict) -> Path | None:
    """Deja en `<dataset>/<vid>/` el original (hardlink; copia si es otro disco), `cortes.json`,
    `cortes_finales.json` (los que siguen aplicados tras el retoque), `eventos.json` y `ficha.json`.

    Idempotente (se refresca en cada hito). No hace nada si el ticket llevaba `no_dataset`
    (ficha.no_dataset) ni si hay que COPIAR y quedan menos de `EDITOR_RAPIDO_DATASET_MIN_GB`
    (8 por defecto) libres: entonces avisa en el log. Nunca lanza. Sin caducidad automática.
    """
    if ficha.get("no_dataset"):
        return None
    vid = ficha["id"]
    try:
        orig = ruta_original(vid)
        if orig is None:
            return None
        destino = dataset_dir() / vid
        destino.mkdir(parents=True, exist_ok=True)
        dst = destino / orig.name
        if not dst.exists():
            try:
                os.link(orig, dst)
            except OSError:
                minimo = float(os.getenv("EDITOR_RAPIDO_DATASET_MIN_GB", "8")) * 1024 ** 3
                if shutil.disk_usage(destino).free < minimo:
                    logger.warning("[rapido] dataset: menos de %s GB libres, no se copia %s",
                                   os.getenv("EDITOR_RAPIDO_DATASET_MIN_GB", "8"), vid)
                    return None
                shutil.copy2(orig, dst)
        cortes = leer_cortes(vid)
        devueltos = set(ficha.get("devueltos") or [])
        (destino / "cortes.json").write_text(json.dumps(cortes, ensure_ascii=False), encoding="utf-8")
        (destino / "cortes_finales.json").write_text(
            json.dumps([c for c in cortes if c["id"] not in devueltos], ensure_ascii=False), encoding="utf-8")
        (destino / "eventos.json").write_text(json.dumps(leer_eventos(vid), ensure_ascii=False), encoding="utf-8")
        meta = {k: ficha.get(k) for k in ("id", "email", "nombre", "duracion_s", "duracion_final_s", "ajustes",
                                          "estado", "devueltos", "nota", "comentario", "n_cortes", "proceso_s",
                                          "descargas", "creado")}
        meta["calidad"] = calidad(ficha)
        (destino / "ficha.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return destino
    except Exception as e:  # noqa: BLE001
        logger.warning("[rapido] dataset: no se pudo guardar %s: %s", vid, e)
        return None


# ───────────────────────── Ficheros ─────────────────────────

def carpeta(vid: str) -> Path:
    p = raiz_datos() / vid
    p.mkdir(parents=True, exist_ok=True)
    return p


def ruta_original(vid: str) -> Path | None:
    for p in carpeta(vid).glob("original.*"):
        return p
    return None


def ruta_resultado(vid: str) -> Path:
    return carpeta(vid) / "resultado.mp4"


def ruta_cortado(vid: str) -> Path:
    """Corte sin subtítulos ni flecha: base para re-estilizar sin volver a cortar."""
    return carpeta(vid) / "cortado.mp4"


def poster(vid: str) -> Path | None:
    """JPG del primer segundo del resultado (iOS lo pide para <video poster>). Se crea al vuelo."""
    res = ruta_resultado(vid)
    if not res.exists():
        return None
    jpg = carpeta(vid) / "poster.jpg"
    if not jpg.exists() or jpg.stat().st_mtime < res.stat().st_mtime:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(res), "-frames:v", "1",
                 "-vf", "scale=-2:720", "-q:v", "4", str(jpg)],
                capture_output=True, timeout=30, check=True,
            )
        except Exception:  # noqa: BLE001
            return None
    return jpg if jpg.exists() else None


def duracion_video(path: str | Path) -> float:
    """Duración en segundos con ffprobe (0.0 si no es un vídeo legible)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        return max(0.0, float(out))
    except Exception:  # noqa: BLE001
        return 0.0


# ───────────────────────── Cortes ─────────────────────────

def calcular_cortes(proyecto: dict) -> list[dict]:
    """Cortes = huecos entre los tramos conservados, con el texto que se fue.

    `proyecto` es el `editproject_<job>.json` del cortador (keep_intervals,
    words, video_duration_s). Cada corte lleva un `id` estable (posición en
    esta lista BASE) para poder devolverlo después.
    """
    dur = float(proyecto.get("video_duration_s") or 0.0)
    keeps = sorted((float(a), float(b)) for a, b in proyecto.get("keep_intervals", []))
    palabras = proyecto.get("words", [])
    huecos: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in keeps:
        if a - cursor >= MIN_CORTE_S:
            huecos.append((cursor, a))
        cursor = max(cursor, b)
    if dur - cursor >= MIN_CORTE_S:
        huecos.append((cursor, dur))
    cortes = []
    for i, (a, b) in enumerate(huecos):
        txt = " ".join(
            str(w.get("word", "")).strip() for w in palabras
            if a <= (float(w["start"]) + float(w["end"])) / 2 <= b
        ).strip()
        cortes.append({
            "id": i, "inicio": round(a, 2), "fin": round(b, 2),
            "duracion": round(b - a, 2), "texto": txt,
            "tipo": "palabras" if txt else "silencio",
        })
    return cortes


def tramos_a_conservar(duracion: float, cortes: list[dict], devueltos: set[int]) -> list[tuple[float, float]]:
    """Complemento de los cortes que siguen aplicados (los devueltos se quedan)."""
    activos = sorted((c["inicio"], c["fin"]) for c in cortes if c["id"] not in devueltos)
    keeps, cursor = [], 0.0
    for a, b in activos:
        if a > cursor:
            keeps.append((cursor, a))
        cursor = max(cursor, b)
    if duracion > cursor:
        keeps.append((cursor, duracion))
    return keeps


def leer_cortes(vid: str) -> list[dict]:
    p = carpeta(vid) / "cortes.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def resumen(ficha: dict) -> dict | None:
    """Qué se quitó: nº de cortes aplicados y segundos, a partir de cortes.json y la ficha."""
    if ficha.get("estado") != "listo":
        return None
    devueltos = set(ficha.get("devueltos") or [])
    activos = [c for c in leer_cortes(ficha["id"]) if c["id"] not in devueltos]
    orig = float(ficha.get("duracion_s") or 0.0)
    final = ficha.get("duracion_final_s")
    quitados = sum(float(c["duracion"]) for c in activos)
    if not activos and final is not None:
        quitados = max(0.0, orig - float(final))
    return {
        "pausas": len(activos),
        "repeticiones": 0,  # el cortador no distingue repeticiones de pausas en cortes.json
        "segundos_quitados": round(quitados, 1),
        "duracion_original_s": round(orig, 1),
        "duracion_final_s": final,
    }


def ruta_palabras(vid: str) -> Path:
    """Palabras de los subtítulos (Whisper sobre el corte, con las correcciones del usuario)."""
    return carpeta(vid) / "palabras.json"


def leer_palabras(vid: str) -> list[dict] | None:
    p = ruta_palabras(vid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


MAX_TEXTO_PALABRA = 60


def corregir_palabras(vid: str, cambios: list[dict]) -> int:
    """Cambia el texto de palabras por índice ({i, texto}); texto vacío la quita del
    subtítulo (el audio no se toca). ValueError si no hay transcripción o un índice no existe."""
    palabras = leer_palabras(vid)
    if not palabras:
        raise ValueError("Este vídeo aún no tiene subtítulos que corregir.")
    n = 0
    for c in cambios:
        i = int(c.get("i", -1))
        if not 0 <= i < len(palabras):
            raise ValueError(f"Palabra {i} no existe.")
        texto = " ".join(str(c.get("texto") or "").split())[:MAX_TEXTO_PALABRA]
        if texto != str(palabras[i].get("word", "")).strip():
            palabras[i]["word"] = texto
            n += 1
    if n:
        ruta_palabras(vid).write_text(json.dumps(palabras, ensure_ascii=False), encoding="utf-8")
    return n


def config_subtitulos(sub: dict, idioma: str) -> dict[str, Any]:
    """Config de `subs_auto` para los ajustes del editor rápido, reutilizando el mapeo del
    Editor Auto (`style_mapper`: estilo del catálogo → claves del motor)."""
    from src.editor_auto.services.style_mapper import build_tool_flow
    estilo = {"cuts": {"enabled": False},
              "subtitle": {"enabled": True, "presetId": sub.get("estilo"), "fontId": sub.get("fuente"),
                           "mode": "phrase", "y": _POS_Y.get(sub.get("posicion"), 0.78)}}
    cfg = next(st.config for st in build_tool_flow(estilo) if st.tool_id == "subs_auto")
    color = sub.get("color")
    if color:
        cfg["highlight_color"] = color
        if cfg.get("highlight_mode") == "none":
            cfg["highlight_mode"] = "color_swap"
    cfg["model_size"] = os.getenv("EDITOR_RAPIDO_WHISPER_MODEL", "small")
    cfg["language"] = None if idioma == "auto" else idioma
    cfg["corregir_nombres"] = False  # sin llamada a IA de pago
    cfg["reference_text"] = ""
    return cfg


def config_flecha(fl: dict, idioma: str) -> dict[str, Any]:
    from src.editor_auto.services.style_mapper import build_tool_flow
    fichero = fichero_flecha(fl.get("id") or "") or "flecha_roja.mov"
    estilo = {"cuts": {"enabled": False}, "subtitle": {"enabled": False},
              "arrow": {"enabled": True, "shapeId": fichero, "x": 0.5, "y": 0.62, "scale": 0.8}}
    cfg = next(st.config for st in build_tool_flow(estilo) if st.tool_id == "sticker_arrow")
    cfg["whisper_model_size"] = os.getenv("EDITOR_RAPIDO_WHISPER_MODEL", "small")
    cfg["ai_language"] = None if idioma == "auto" else idioma
    return cfg


def config_cortador(ajustes: dict) -> dict[str, Any]:
    idioma = ajustes.get("idioma", "auto")
    return {
        "vad_enabled": True,
        "amplitude_enabled": True,
        "ai_clean_enabled": os.getenv("EDITOR_RAPIDO_AI_CLEAN", "0") == "1",
        "ai_language": None if idioma == "auto" else idioma,
        "output_aspect": ajustes.get("formato", "9:16"),
        "ritmo": ajustes.get("ritmo", "natural"),
    }


# ───────────────────────── Runner (cola) ─────────────────────────

def _escalar(on_progress: Callable[[float, str], None], a: float, b: float, defecto: str):
    """Sub-progreso [0..1] de una herramienta → tramo [a..b] del trabajo."""
    return lambda f, m="": on_progress(a + max(0.0, min(1.0, float(f))) * (b - a), m or defecto)


def _estilizar(base: Path, destino: Path, ficha: dict, job,
               on_log: Callable[[str], None], on_progress: Callable[[float, str], None],
               tramos: tuple[float, float, float]) -> tuple[Path, list[str]]:
    """Subtítulos y flecha sobre `base` (el corte). Devuelve (fichero a entregar, avisos).

    Un fallo de subs o flecha NO pierde el trabajo: se entrega lo último que salió bien.
    """
    from src.editor_auto.tools.base import ToolContext

    ajustes = ficha.get("ajustes") or {}
    sub = ajustes.get("subtitulos") or {}
    fl = ajustes.get("flecha") or {}
    idioma = ajustes.get("idioma", "auto")
    t0, t1, t2 = tramos
    actual, avisos = base, []
    carp = carpeta(ficha["id"])

    def _ctx(a: float, b: float, msg: str, extras: dict | None = None):
        return ToolContext(user_id=ficha["email"], user_name=ficha["email"], job_id=job.id,
                           temp_folder=str(carp), on_log=on_log, on_progress=_escalar(on_progress, a, b, msg),
                           extras=extras or {})

    if sub.get("activo", True):
        out = carp / f"subs_{job.id}.mp4"
        try:
            from src.editor_auto.tools.subs_auto import SubsAutoTool
            # Palabras ya transcritas de este corte (con correcciones) → sin Whisper.
            palabras = leer_palabras(ficha["id"])
            extras = {"palabras": palabras} if palabras else {"guardar_palabras": str(ruta_palabras(ficha["id"]))}
            SubsAutoTool().run(input_path=str(actual), output_path=str(out),
                               config=config_subtitulos(sub, idioma), ctx=_ctx(t0, t1, "Subtítulos…", extras))
            if not out.exists() or out.stat().st_size == 0:
                raise RuntimeError("no se generó el vídeo con subtítulos")
            actual = out
        except Exception as e:  # noqa: BLE001
            out.unlink(missing_ok=True)
            avisos.append("No se pudieron poner los subtítulos: " + str(e)[:150])
            on_log(f"[rapido] ⚠️ {avisos[-1]}")
    on_progress(t1, "Subtítulos listos")
    if fl.get("activo"):
        out = carp / f"flecha_{job.id}.mp4"
        try:
            from src.editor_auto.tools.sticker_arrow import StickerArrowTool
            StickerArrowTool().run(input_path=str(actual), output_path=str(out),
                                   config=config_flecha(fl, idioma), ctx=_ctx(t1, t2, "Flecha…"))
            if not out.exists() or out.stat().st_size == 0:
                raise RuntimeError("no se generó el vídeo con flecha")
            if actual != base:
                actual.unlink(missing_ok=True)
            actual = out
        except Exception as e:  # noqa: BLE001
            out.unlink(missing_ok=True)
            avisos.append("No se pudo poner la flecha: " + str(e)[:150])
            on_log(f"[rapido] ⚠️ {avisos[-1]}")
    if actual == base:
        shutil.copyfile(actual, destino)
    else:
        os.replace(actual, destino)
    return destino, avisos


def ejecutar(job, on_log: Callable[[str], None], on_progress: Callable[[float, str], None]) -> str:
    """Corta (`auto`), re-corta con cortes devueltos (`retoque`) o solo re-estiliza (`estilo`).

    Tras cortar se guarda `cortado.mp4` (sin subs) y se aplican subtítulos y flecha según
    `ficha.ajustes`. Progreso: corte 0-0.6, subs 0.6-0.9, flecha 0.9-1 (en `estilo`: subs
    0-0.7, flecha 0.7-1). Si falla el CORTE se devuelven los créditos y se relanza el error;
    si fallan subs/flecha se entrega el corte con un aviso en la ficha.
    """
    from src.editor_auto.tools.base import ToolContext
    from src.editor_auto.tools.silence_cutter import SilenceCutterTool

    t_ini = time.time()
    vid = job.params["video_id"]
    modo = job.params.get("modo", "auto")
    ficha = cargar_ficha(vid)
    if ficha is None:
        raise RuntimeError(f"Ficha {vid} no encontrada")
    carp = carpeta(vid)
    salida = carp / f"render_{job.id}.mp4"
    cortado = ruta_cortado(vid)
    n_cortes = None
    try:
        if modo == "estilo":
            if not cortado.exists():  # vídeos cortados antes de existir el estilo: su resultado no lleva subs
                if not ruta_resultado(vid).exists():
                    raise RuntimeError("No hay vídeo cortado para re-estilizar")
                shutil.copyfile(ruta_resultado(vid), cortado)
            tramos = (0.0, 0.7, 1.0)
        else:
            entrada = ruta_original(vid)
            if entrada is None:
                raise RuntimeError("No está el vídeo original")
            ctx = ToolContext(
                user_id=ficha["email"], user_name=ficha["email"], job_id=job.id,
                temp_folder=str(carp), on_log=on_log,
                on_progress=_escalar(on_progress, 0.0, 0.6, "Cortando…"),
            )
            cfg = config_cortador(ficha.get("ajustes") or {})
            if modo == "retoque":
                cortes = leer_cortes(vid)
                keeps = tramos_a_conservar(
                    float(ficha["duracion_s"]), cortes, set(job.params.get("devueltos") or []),
                )
                cfg["manual_keep_intervals"] = [[a, b] for a, b in keeps]
            SilenceCutterTool().run(
                input_path=str(entrada), output_path=str(salida), config=cfg, ctx=ctx,
            )
            if not salida.exists() or salida.stat().st_size == 0:
                raise RuntimeError("El cortador no generó el vídeo")
            if modo == "auto":
                proyecto = carp / f"editproject_{job.id}.json"
                cortes = []
                if proyecto.exists():
                    cortes = calcular_cortes(json.loads(proyecto.read_text(encoding="utf-8")))
                (carp / "cortes.json").write_text(json.dumps(cortes, ensure_ascii=False), encoding="utf-8")
                n_cortes = len(cortes)
                proyecto.unlink(missing_ok=True)
            os.replace(salida, cortado)
            ruta_palabras(vid).unlink(missing_ok=True)  # corte nuevo → tiempos nuevos
            tramos = (0.6, 0.9, 1.0)
        final = ruta_resultado(vid)
        ficha = cargar_ficha(vid) or ficha
        entrega, avisos = _estilizar(cortado, carp / f"entrega_{job.id}.mp4", ficha, job, on_log, on_progress, tramos)
        os.replace(entrega, final)
        # Coste: todo local (Silero, faster-whisper, ffmpeg) → sin API de pago.
        try:
            from src import cost_tracking
            cost_tracking.record_custom(
                kind="editor_rapido", units=float(ficha["creditos"]),
                unit_label="min", cost_usd=0.0, detail=f"modo={modo}",
            )
        except Exception:  # noqa: BLE001
            pass
        ficha = cargar_ficha(vid) or ficha
        ficha["estado"] = "listo"
        ficha["version"] = int(ficha.get("version", 0)) + 1
        ficha["duracion_final_s"] = round(duracion_video(final), 2)
        ficha["error"] = None
        ficha["aviso"] = " ".join(avisos) or None
        if modo == "retoque":
            ficha["devueltos"] = sorted(set(job.params.get("devueltos") or []))
        if n_cortes is not None:
            ficha["n_cortes"] = n_cortes
        ficha["proceso_s"] = round(time.time() - t_ini, 1)
        guardar_ficha(ficha)
        res = resumen(ficha) or {}
        registrar_evento(vid, ficha["email"], "listo", {
            "modo": modo, "duracion_original_s": res.get("duracion_original_s"),
            "duracion_final_s": ficha["duracion_final_s"], "n_cortes": ficha.get("n_cortes"),
            "n_aplicados": res.get("pausas"), "segundos_quitados": res.get("segundos_quitados"),
            "proceso_s": ficha["proceso_s"],
        })
        if avisos:
            registrar_evento(vid, ficha["email"], "aviso", {"modo": modo, "avisos": avisos})
        guardar_dataset(ficha)
        on_progress(1.0, "Listo")
        return str(final)
    except Exception as e:  # noqa: BLE001
        salida.unlink(missing_ok=True)
        ficha = cargar_ficha(vid) or ficha
        registrar_evento(vid, ficha["email"], "error", {"modo": modo, "error": str(e)[:300],
                                                        "proceso_s": round(time.time() - t_ini, 1)})
        if modo == "auto":
            ficha["estado"] = "error"
            ficha["error"] = str(e)[:300]
            guardar_ficha(ficha)
            devolver_creditos(ficha)
        else:  # retoque/estilo fallan: se mantiene el resultado anterior
            ficha["estado"] = "listo" if ruta_resultado(vid).exists() else "error"
            ficha["error"] = ("No se pudo aplicar el retoque: " if modo == "retoque"
                              else "No se pudo cambiar el estilo: ") + str(e)[:200]
            guardar_ficha(ficha)
        raise
