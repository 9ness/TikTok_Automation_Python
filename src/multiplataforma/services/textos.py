"""Texto de cada plataforma a partir del título/caption del producto.

Reglas:
- Enlace de Amazon → aviso literal del programa de afiliados
  (`prompts/aviso_amazon.md`) en TODAS las plataformas.
- Instagram: el enlace del pie no es clicable → «en mi perfil».
- Facebook: enlace en el primer comentario (texto aparte, `comentario`).
- Threads: enlace en el propio texto. Máx. 500 caracteres.
- Pinterest: el enlace va en el campo `link` del pin; título ≤100.
- Hashtags limitados por plataforma (`config.MAX_HASHTAGS`).
- Nunca acortadores (lo valida `enlaces.validar`).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.multiplataforma import config
from src.multiplataforma.services import enlaces

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_HUECO = re.compile(r"\{(\w+)\}")


@lru_cache(maxsize=None)
def plantilla(nombre: str) -> str:
    return (PROMPTS_DIR / f"{nombre}.md").read_text(encoding="utf-8").strip()


def aviso_amazon() -> str:
    return plantilla("aviso_amazon")


def normalizar_hashtags(hashtags: list[str] | str | None, maximo: int) -> list[str]:
    if isinstance(hashtags, str):
        hashtags = hashtags.replace(",", " ").split()
    vistos: list[str] = []
    for h in hashtags or []:
        t = re.sub(r"[^\w]", "", (h or "").lstrip("#"))
        if t and t.lower() not in {v.lower() for v in vistos}:
            vistos.append(t)
    return [f"#{t}" for t in vistos[:maximo]]


def rellenar(nombre: str, valores: dict[str, str]) -> str:
    """Rellena la plantilla; una línea cuyo único contenido era un hueco vacío desaparece."""
    lineas = []
    for linea in plantilla(nombre).splitlines():
        huecos = _HUECO.findall(linea)
        if huecos and all(not valores.get(h) for h in huecos) and not _HUECO.sub("", linea).strip():
            continue
        if not huecos and "enlace" in linea.lower() and not valores.get("enlace"):
            continue  # «👇 Enlace abajo:» sin enlace (virales): fuera
        lineas.append(_HUECO.sub(lambda m: valores.get(m.group(1), ""), linea).rstrip())
    texto = "\n".join(lineas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _recortar(texto: str, maximo: int, obligatorio: str = "") -> str:
    """Recorta el texto a `maximo` sin perder la parte obligatoria (enlace + aviso)."""
    if len(texto) <= maximo:
        return texto
    if obligatorio and obligatorio in texto:
        cabeza = texto.split(obligatorio, 1)[0]
        hueco = maximo - len(obligatorio) - 2
        if hueco > 10:
            return (cabeza[:hueco].rstrip() + "…\n" + obligatorio)[:maximo]
    return texto[: maximo - 1].rstrip() + "…"


def construir(*, titulo: str, caption: str = "", enlace: str = "", hashtags=None,
              plataformas=config.PLATAFORMAS) -> dict:
    """{'textos': {plataforma: texto}, 'comentario': str, 'titulo_pin': str}."""
    enlace = enlaces.validar(enlace)
    aviso = aviso_amazon() if enlace and enlaces.es_amazon(enlace) else ""
    titulo = (titulo or "").strip()
    caption = (caption or "").strip()
    textos: dict[str, str] = {}
    for p in plataformas:
        tags = " ".join(normalizar_hashtags(hashtags, config.MAX_HASHTAGS[p]))
        valores = {"titulo": titulo, "caption": caption, "enlace": enlace, "aviso_afiliado": aviso,
                   "hashtags": tags}
        texto = rellenar(p, valores)
        obligatorio = ""
        if p == "threads" and enlace:
            obligatorio = f"{enlace}\n\n{aviso}".strip()
        elif aviso:
            obligatorio = aviso
        textos[p] = _recortar(texto, config.MAX_CHARS[p], obligatorio)
    comentario = ""
    if "facebook" in plataformas and enlace:
        comentario = rellenar("facebook_comentario", {"enlace": enlace, "aviso_afiliado": aviso})
    return {
        "textos": textos,
        "comentario": comentario,
        "titulo_pin": (titulo or caption)[: config.MAX_TITULO_PINTEREST],
    }
