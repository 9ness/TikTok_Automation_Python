"""Modos y extras del Editor rápido (16/11/2026).

- MODO = cómo se edita el vídeo entero («Básico» = corte + subtítulos + flecha; «Réplica»
  copiará la edición de un viral, aún sin hacer).
- EXTRA = casilla que añade una capa sobre el corte normal sin pedir nada nuevo (salvo
  «Nombre del producto», que pide un texto corto). Cada extra suma su precio al del vídeo.

Lo marcado `solo_admin` solo se devuelve en /opciones y solo se acepta en /cortar si el
ticket es de admin (Néstor lo prueba antes de abrirlo a todos): un usuario normal → 403.
Los precios viven en las tablas de abajo: cambiar un precio = cambiar una línea.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

_PROMPTS = Path(__file__).parent / "prompts"

# El modelo del gancho va aquí y solo aquí (al salir otro se cambia esta línea).
MODELO_GANCHO = "claude-sonnet-5-5"
ESFUERZO_GANCHO = "low"

MODOS: dict[str, dict[str, Any]] = {
    "basico": {"nombre": "Básico", "descripcion": "Quita pausas y repeticiones, con tus subtítulos y flecha.",
               "desde_creditos": 1, "solo_admin": False, "disponible": True},
    "replica": {"nombre": "Réplica", "descripcion": "Pega un viral de TikTok y copia su edición en tu vídeo.",
                "desde_creditos": 3, "solo_admin": True, "disponible": True},
    "conversacion": {"nombre": "Varias personas",
                     "descripcion": "Para cuando te duplicas y haces de varios personajes con el móvil fijo, "
                                    "o habláis dos o más: os junta en el plano y cada uno lleva su color de subtítulos.",
                     "desde_creditos": 2, "solo_admin": True, "disponible": True},
}

# Color de los subtítulos de cada persona en «Conversación» (la 1ª = quien más habla).
COLORES_HABLANTES = ["#FFFFFF", "#FDE047", "#5EEAD4"]

# Orden = orden en que se aplican: voz y fotos antes de los subtítulos; gancho y nombre al final.
EXTRAS: dict[str, dict[str, Any]] = {
    "voz": {"nombre": "Mejorar voz", "descripcion": "Quita ruido de fondo y nivela el volumen.",
            "creditos": 0.5, "solo_admin": True, "fase": "antes"},
    "fotos": {"nombre": "Fotos de apoyo", "descripcion": "Si nombras a un famoso o una marca, sale su foto.",
              "creditos": 0.5, "solo_admin": True, "fase": "antes"},
    "gancho": {"nombre": "Clip gancho", "descripcion": "Copia tu mejor frase al principio para enganchar.",
               "creditos": 0.5, "solo_admin": True, "fase": "despues"},
    "nombre_producto": {"nombre": "Nombre del producto", "descripcion": "Texto fijo arriba con el nombre.",
                        "creditos": 0.5, "solo_admin": True, "fase": "despues", "pide_texto": True},
}

MAX_NOMBRE_PRODUCTO = 40


def modos(admin: bool) -> list[dict]:
    return [{"id": k, **v} for k, v in MODOS.items() if admin or not v["solo_admin"]]


def extras(admin: bool) -> list[dict]:
    return [{"id": k, **{c: v[c] for c in ("nombre", "descripcion", "creditos", "solo_admin")},
             "pide_texto": bool(v.get("pide_texto"))}
            for k, v in EXTRAS.items() if admin or not v["solo_admin"]]


class Prohibido(Exception):
    """Algo solo de admin pedido por un usuario normal (→ 403)."""


def validar(modo: str, ids: list[str], nombre_producto: str | None, admin: bool) -> tuple[str, list[str], str | None]:
    """Devuelve (modo, extras en orden de aplicación, nombre). ValueError → 422; Prohibido → 403."""
    m = MODOS.get(modo)
    if m is None:
        raise ValueError(f"Modo desconocido: {modo}")
    if m["solo_admin"] and not admin:
        raise Prohibido(f"El modo «{m['nombre']}» aún no está disponible.")
    if not m["disponible"]:
        raise ValueError(f"El modo «{m['nombre']}» llegará pronto.")
    pedidos = set(ids or [])
    raros = pedidos - set(EXTRAS)
    if raros:
        raise ValueError(f"Extra desconocido: {', '.join(sorted(raros))}")
    for e in pedidos:
        if EXTRAS[e]["solo_admin"] and not admin:
            raise Prohibido(f"El extra «{EXTRAS[e]['nombre']}» aún no está disponible.")
    nombre = (nombre_producto or "").strip() or None
    if "nombre_producto" in pedidos:
        if not nombre:
            raise ValueError("Escribe el nombre del producto.")
        if len(nombre) > MAX_NOMBRE_PRODUCTO:
            raise ValueError(f"Nombre del producto: máximo {MAX_NOMBRE_PRODUCTO} letras.")
    return modo, [e for e in EXTRAS if e in pedidos], nombre


# Enlaces de TikTok que acepta el modo Réplica (www, m, vm, vt…).
_URL_TIKTOK = re.compile(r"^https?://([a-z0-9-]+\.)*tiktok\.com/\S+$", re.I)


def validar_referencia(modo: str, url: str | None) -> str | None:
    """Enlace del viral para «replica» (obligatorio ahí; en otro modo se ignora). ValueError → 422."""
    if modo != "replica":
        return None
    url = (url or "").strip()
    if not url:
        raise ValueError("Pega el enlace del vídeo de TikTok que quieres copiar.")
    if len(url) > 300 or not _URL_TIKTOK.match(url):
        raise ValueError("El enlace tiene que ser de un vídeo de tiktok.com.")
    return url


def precio_modo(modo: str) -> float:
    """Lo que el modo suma al corte (Básico = 0; «desde» incluye ya el crédito del corte)."""
    m = MODOS.get(modo) or {}
    return max(0.0, float(m.get("desde_creditos", 1)) - 1.0)


def config_replica(sacado: dict) -> dict[str, Any]:
    """vip_overlays con el estilo y el ritmo leídos del viral (sin fotos de internet: gastan)."""
    cfg = {k: v for k, v in (sacado or {}).items() if k != "_flujo"}
    cfg.update(fotos=False, fotos_internet=False)
    return cfg


def precio(ids: list[str]) -> float:
    return sum(float(EXTRAS[e]["creditos"]) for e in ids if e in EXTRAS)


# ───────────────────────── Gancho (Claude Sonnet) ─────────────────────────

def elegir_gancho(palabras: list[dict], duracion: float, on_log: Callable[[str], None]) -> dict | None:
    """Frase gancho de 1-3 s elegida por Sonnet → {t0, t1, frase, motivo} o None.

    Nunca lanza: sin Claude, respuesta rara o frase fuera de límites → None (sin gancho)."""
    try:
        from src.editor_auto.api import claude_client
        if not claude_client.activo():
            on_log("[rapido] Gancho: Claude no configurado — sin gancho.")
            return None
        compact = [{"w": str(w.get("word", "")).strip(), "s": round(float(w.get("start", 0)), 2),
                    "e": round(float(w.get("end", w.get("start", 0))), 2)}
                   for w in palabras if str(w.get("word", "")).strip()][:1500]
        if not compact:
            return None
        r = claude_client.analyze_transcript_json(
            system_prompt=(_PROMPTS / "gancho.md").read_text(encoding="utf-8"),
            user_payload={"duracion_s": round(duracion, 2), "palabras": compact},
            modelo_forzado=MODELO_GANCHO, esfuerzo=ESFUERZO_GANCHO, detalle="editor_rapido.gancho",
        )
        if not isinstance(r, dict) or r.get("t0") is None or r.get("t1") is None:
            on_log("[rapido] Gancho: la IA no encontró ninguna frase que enganche.")
            return None
        t0, t1 = float(r["t0"]), float(r["t1"])
        # Mismos límites que vip_overlays._sanitize: 1,2-3 s y fuera de los 2 primeros segundos.
        if not (t0 > 2.0 and 1.2 <= t1 - t0 <= 3.0 and t1 <= duracion + 0.05):
            on_log(f"[rapido] Gancho descartado ({t0:.2f}-{t1:.2f}s fuera de límites).")
            return None
        return {"t0": round(t0, 3), "t1": round(min(t1, duracion), 3),
                "frase": str(r.get("frase") or "")[:200], "motivo": str(r.get("motivo") or "")[:200]}
    except Exception as e:  # noqa: BLE001 — un extra nunca rompe la edición
        on_log(f"[rapido] ⚠️ Gancho: la IA falló ({str(e)[:150]}).")
        return None


# ───────────────────────── Títulos gancho (Claude Haiku) ─────────────────────────

# El modelo de los títulos va aquí y solo aquí (al salir otro se cambia esta línea).
MODELO_TITULOS = "claude-haiku-5-5"
MAX_TITULOS_VIDEO = 3      # generaciones gratis por vídeo
MAX_CHARS_TITULO = 60
TIPOS_TITULO = ("curiosidad", "problema", "pov", "beneficio", "pregunta")


class TitulosError(Exception):
    """La IA no está disponible o devolvió algo inservible (→ 502)."""


def generar_titulos(palabras: list[dict], idioma: str = "auto") -> list[dict]:
    """5 títulos gancho [{texto, tipo}] a partir de las palabras del vídeo (Haiku).

    Lanza TitulosError si Claude no está configurado, falla o no devuelve ningún título válido."""
    from src.editor_auto.api import claude_client
    if not claude_client.activo():
        raise TitulosError("La IA no está configurada.")
    texto = " ".join(str(w.get("word", "")).strip() for w in palabras if str(w.get("word", "")).strip())
    if not texto:
        raise TitulosError("No hay texto en la transcripción.")
    try:
        r = claude_client.analyze_transcript_json(
            system_prompt=(_PROMPTS / "titulos.md").read_text(encoding="utf-8"),
            user_payload={"idioma": idioma or "auto", "transcripcion": texto[:12000]},
            modelo_forzado=MODELO_TITULOS, esfuerzo="low", detalle="editor_rapido.titulos",
        )
    except Exception as e:  # noqa: BLE001
        raise TitulosError(f"La IA falló: {str(e)[:150]}") from e
    lista = r.get("titulos") if isinstance(r, dict) else r
    out: list[dict] = []
    for t in lista if isinstance(lista, list) else []:
        if not isinstance(t, dict):
            continue
        txt = " ".join(str(t.get("texto") or "").split())
        if not txt:
            continue
        tipo = str(t.get("tipo") or "").strip().lower()
        out.append({"texto": txt[:MAX_CHARS_TITULO].rstrip(), "tipo": tipo if tipo in TIPOS_TITULO else "curiosidad"})
    if not out:
        raise TitulosError("La IA no devolvió títulos.")
    return out[:5]


# ───────────────────────── Configuración de cada herramienta ─────────────────────────

def config_voz() -> dict[str, Any]:
    return {}  # los valores por defecto de audio_clean (rnnoise + nivelar a -16 LUFS)


def config_fotos(idioma: str) -> dict[str, Any]:
    return {"entidades_ia": "claude", "max_photos": 3, "entity_types": "personas y marcas",
            "system_prompt_entidades": (_PROMPTS / "fotos_entidades.md").read_text(encoding="utf-8"),
            "ai_language": None if idioma == "auto" else idioma, "whisper_model_size": "small"}


def config_gancho(gancho: dict) -> dict[str, Any]:
    """vip_overlays con todo apagado salvo el clip gancho, y el plan ya decidido."""
    return {"gancho": False, "gancho_clip": True, "fotos": False, "fotos_internet": False,
            "zooms": False, "sfx": False, "color_grade": False, "loudnorm": False,
            "plan_fijo": {"gancho": {"clip": {"t0": gancho["t0"], "t1": gancho["t1"]}},
                          "rotulos": [], "fotos": [], "zooms": []}}


def config_nombre(nombre: str) -> dict[str, Any]:
    return {"texto": nombre}


class Cronometro:
    """Segundos de servidor de cada extra (para fijar precios con datos reales)."""

    def __init__(self) -> None:
        self.s: dict[str, float] = {}

    def medir(self, eid: str):
        crono = self

        class _M:
            def __enter__(self):
                self.t = time.time()

            def __exit__(self, *a):
                crono.s[eid] = round(crono.s.get(eid, 0.0) + time.time() - self.t, 2)
                return False

        return _M()
