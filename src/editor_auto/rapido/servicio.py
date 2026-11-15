"""Lógica del Editor rápido: créditos, fichas de vídeo, cortes y runner.

- 1 crédito = 1 minuto de vídeo ORIGINAL (redondeo hacia arriba).
- V1: saldo en el Redis del Editor, SIN pagos reales. Alta = N créditos gratis
  (`EDITOR_RAPIDO_FREE_CREDITS`, 5 por defecto) la primera vez que se ve el email.
- Se cobra al pulsar «Cortar» y se devuelve solo si el trabajo falla (idempotente).
- El retoque «devolver un corte» no cuesta créditos en V1.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

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

MAX_MINUTOS = int(os.getenv("EDITOR_RAPIDO_MAX_MINUTOS", "30"))
MAX_BYTES = int(os.getenv("EDITOR_RAPIDO_MAX_MB", "1024")) * 1024 * 1024
# Cortes más cortos que esto no se enseñan en la lista de retoque.
MIN_CORTE_S = 0.25

_LOCK = threading.Lock()  # un solo proceso de API: basta para el saldo


def gratis_inicial() -> int:
    try:
        return max(0, int(os.getenv("EDITOR_RAPIDO_FREE_CREDITS", "5")))
    except ValueError:
        return 5


def creditos_de(duracion_s: float) -> int:
    """Minutos del original redondeados hacia arriba (mínimo 1)."""
    return max(1, math.ceil(float(duracion_s) / 60.0 - 1e-9))


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


def saldo(email: str) -> dict:
    """Saldo del usuario; lo crea con los créditos gratis la primera vez."""
    r = get_editor_redis()
    with _LOCK:
        s = r.get_json(_k_saldo(email))
        if s is None:
            s = {"creditos": gratis_inicial(), "gratis_dados": gratis_inicial(), "creado": time.time()}
            r.set_json(_k_saldo(email), s)
            r.sadd(_K_CUENTAS, email)
        return s


def _guardar_saldo(email: str, s: dict) -> None:
    get_editor_redis().set_json(_k_saldo(email), s)


def ajustar_creditos(email: str, delta: int) -> int:
    """Suma (o resta) créditos. Devuelve el saldo nuevo (nunca < 0)."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        s["creditos"] = max(0, int(s.get("creditos", 0)) + int(delta))
        _guardar_saldo(email, s)
        get_editor_redis().sadd(_K_CUENTAS, email)
        return s["creditos"]


def cobrar(email: str, n: int) -> bool:
    """Descuenta `n` créditos si alcanzan. False si no hay saldo."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        if int(s.get("creditos", 0)) < n:
            return False
        s["creditos"] = int(s["creditos"]) - n
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
        out.append({"email": e, "creditos": int(s.get("creditos", 0)),
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
    ajustar_creditos(f["email"], int(f.get("creditos", 0)))


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

    def _ctx(a: float, b: float, msg: str):
        return ToolContext(user_id=ficha["email"], user_name=ficha["email"], job_id=job.id,
                           temp_folder=str(carp), on_log=on_log, on_progress=_escalar(on_progress, a, b, msg))

    if sub.get("activo", True):
        out = carp / f"subs_{job.id}.mp4"
        try:
            from src.editor_auto.tools.subs_auto import SubsAutoTool
            SubsAutoTool().run(input_path=str(actual), output_path=str(out),
                               config=config_subtitulos(sub, idioma), ctx=_ctx(t0, t1, "Subtítulos…"))
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

    vid = job.params["video_id"]
    modo = job.params.get("modo", "auto")
    ficha = cargar_ficha(vid)
    if ficha is None:
        raise RuntimeError(f"Ficha {vid} no encontrada")
    carp = carpeta(vid)
    salida = carp / f"render_{job.id}.mp4"
    cortado = ruta_cortado(vid)
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
                proyecto.unlink(missing_ok=True)
            os.replace(salida, cortado)
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
        guardar_ficha(ficha)
        on_progress(1.0, "Listo")
        return str(final)
    except Exception as e:  # noqa: BLE001
        salida.unlink(missing_ok=True)
        ficha = cargar_ficha(vid) or ficha
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
