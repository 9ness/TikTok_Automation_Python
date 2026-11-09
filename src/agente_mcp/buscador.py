"""Buscar por tema en lo ya aprendido (`learnings.md`) y en las guías.

Un agente que empieza una tarea lee hoy ~54 KB de guía general y hasta 34 KB
de la del menú, y `learnings.md` (1.500 líneas) no lo lee nadie fuera del repo:
lo aprendido hace tres semanas se pierde y el error se repite. Aquí se busca
por palabras y se devuelve SOLO lo que toca: unas pocas líneas de aprendizajes
y los trozos de guía donde sale el tema, con su título para pedir la sección
entera (`seccion`).

Sin IA y sin red: texto plano, palabras sin acentos, y gana lo más reciente.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from src.agente_mcp import config

# `learnings.md` vive en la raíz del repo. En la imagen de la API solo entra
# `src/`, así que la ruta se puede dar por entorno (ver README de las guías).
RAIZ = Path(__file__).resolve().parents[2]

VACIAS = frozenset(
    "a al algo ante como con contra cual cuando de del desde donde el ella en entre "
    "era es esa ese eso esta este esto ha hay la las le lo los mas me muy ni no "
    "nos o para pero por que se si sin sobre su sus te un una uno unos y ya".split()
)

_FECHA = re.compile(r"^\s*[-*]\s*\[?(20\d\d-\d\d-\d\d)\]?\s*[·:\-–—]?\s*(.*)$")
_TITULO = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
_PALABRA = re.compile(r"[a-z0-9ñ]+")


def plano(texto: str) -> str:
    """Minúsculas y sin acentos (la ñ se queda)."""
    t = unicodedata.normalize("NFD", (texto or "").lower().replace("ñ", "\0"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("\0", "ñ")


def _raiz(p: str) -> str:
    """«carruseles» y «carrusel» son la misma palabra para buscar."""
    for fin in ("es", "s"):
        if len(p) > 4 and p.endswith(fin):
            return p[: -len(fin)]
    return p


def palabras(tema: str) -> list[str]:
    vistas: list[str] = []
    for p in _PALABRA.findall(plano(tema)):
        if p in VACIAS or (len(p) < 2 and not p.isdigit()):
            continue
        r = _raiz(p)
        if r not in vistas:
            vistas.append(r)
    return vistas


def _puntos(texto_plano: str, claves: list[str]) -> tuple[int, int]:
    """(cuántas palabras del tema salen, cuántas veces en total). Una clave
    casa con el principio de una palabra: «omni» con «omni», «omniflash». Las
    cortas y los números, solo enteras («mi» no es «minimax», «8» no es «80»)."""
    distintas = veces = 0
    for c in claves:
        fin = r"(?![a-z0-9ñ])" if len(c) <= 3 or c.isdigit() else ""
        n = len(re.findall(rf"(?<![a-z0-9ñ]){re.escape(c)}{fin}", texto_plano))
        if n:
            distintas += 1
            veces += n
    return distintas, veces


def _seguidas(texto_plano: str, tema: str) -> int:
    """Cuántas parejas de palabras del tema salen juntas y en ese orden:
    «mi 8» o «bandas negras» pesan más que las dos palabras sueltas."""
    w = _PALABRA.findall(plano(tema))
    return sum(1 for a, b in zip(w, w[1:]) if re.search(rf"(?<![a-z0-9ñ]){a}\W+{b}", texto_plano))


# ---------------------------------------------------------------------------
# Aprendizajes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Aprendizaje:
    fecha: str
    texto: str


def ruta_aprendizajes() -> Path:
    return Path(os.environ.get("APRENDIZAJES_MD") or (RAIZ / "learnings.md"))


def leer_aprendizajes(ruta: Path | None = None) -> list[Aprendizaje]:
    """Una entrada por línea con fecha. Si el fichero no está (imagen de la
    API sin él), lista vacía: la búsqueda en guías sigue funcionando."""
    ruta = ruta or ruta_aprendizajes()
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lineas:
        m = _FECHA.match(ln)
        if m and m.group(2).strip():
            out.append(Aprendizaje(m.group(1), m.group(2).strip()))
    return out


def buscar_aprendizajes(tema: str, entradas: list[Aprendizaje], maximo: int = 8,
                        largo: int = 420) -> list[dict]:
    claves = palabras(tema)
    if not claves:
        return []
    casan = []
    for e in entradas:
        p = plano(e.texto)
        distintas, veces = _puntos(p, claves)
        # Con varias palabras, una sola coincidencia suelta es ruido.
        if distintas and distintas >= min(len(claves), 2):
            casan.append((distintas, _seguidas(p, tema), e.fecha, veces, e))
    casan.sort(key=lambda x: x[:4], reverse=True)
    return [{"fecha": e.fecha, "texto": e.texto if len(e.texto) <= largo else e.texto[:largo].rstrip() + "…"}
            for *_, e in casan[:maximo]]


# ---------------------------------------------------------------------------
# Guías por secciones
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Seccion:
    guia: str      # ruta relativa a la carpeta de guías, p. ej. «comun/plataformas.md»
    titulo: str
    texto: str     # con su línea de título


def secciones(guias_dir: Path | None = None) -> list[Seccion]:
    """Cada guía troceada por sus títulos (`#` a `####`). Lo que va antes del
    primer título cuenta como sección «(inicio)»."""
    base = guias_dir or config.GUIAS_DIR
    out: list[Seccion] = []
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(base).as_posix()
        titulo, cuerpo, en_codigo = "(inicio)", [], False
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.lstrip().startswith("```"):
                en_codigo = not en_codigo
            m = None if en_codigo else _TITULO.match(ln)
            if m:
                if "".join(cuerpo).strip():
                    out.append(Seccion(rel, titulo, "\n".join(cuerpo).strip()))
                titulo, cuerpo = m.group(2).strip(), [ln]
            else:
                cuerpo.append(ln)
        if "".join(cuerpo).strip():
            out.append(Seccion(rel, titulo, "\n".join(cuerpo).strip()))
    return out


def _extracto(texto: str, claves: list[str], largo: int = 260) -> str:
    """El trozo de la sección alrededor de la primera palabra del tema."""
    una_linea = " ".join(texto.split())
    p = plano(una_linea)
    pos = min((i for i in (p.find(c) for c in claves) if i >= 0), default=0)
    ini = max(0, pos - largo // 3)
    trozo = una_linea[ini: ini + largo].strip()
    return ("…" if ini else "") + trozo + ("…" if ini + largo < len(una_linea) else "")


def buscar_guias(tema: str, secs: list[Seccion], maximo: int = 6) -> list[dict]:
    claves = palabras(tema)
    if not claves:
        return []
    casan = []
    for s in secs:
        p = plano(s.texto)
        distintas, veces = _puntos(p, claves)
        if distintas and distintas >= min(len(claves), 2):
            en_titulo = _puntos(plano(s.titulo), claves)[0]
            # Densidad y no solo veces: una sección corta que va del tema
            # gana a una larga que lo nombra de pasada.
            casan.append((distintas, en_titulo, min(_seguidas(p, tema), 1),
                          veces * 1000 // (len(s.texto) + 400), s))
    casan.sort(key=lambda x: x[:4], reverse=True)
    return [{"guia": s.guia, "seccion": s.titulo, "letras": len(s.texto),
             "extracto": _extracto(s.texto, claves)} for *_, s in casan[:maximo]]


def leer_seccion(guia: str, titulo: str, secs: list[Seccion]) -> Seccion | None:
    """La sección entera. El título casa sin acentos y por trozo («semaforo»
    encuentra «El semáforo antes de subir»); la guía, con o sin `.md`."""
    g = plano(guia).removesuffix(".md")
    t = plano(titulo).strip()
    de_la_guia = [s for s in secs if plano(s.guia).removesuffix(".md") in (g, f"comun/{g}")]
    for prueba in (lambda s: plano(s.titulo) == t, lambda s: t in plano(s.titulo)):
        for s in de_la_guia:
            if t and prueba(s):
                return s
    return None


def indice(guia: str, secs: list[Seccion]) -> list[dict]:
    g = plano(guia).removesuffix(".md")
    return [{"seccion": s.titulo, "letras": len(s.texto)} for s in secs
            if plano(s.guia).removesuffix(".md") in (g, f"comun/{g}")]


# ---------------------------------------------------------------------------
# Quién ve los aprendizajes
# ---------------------------------------------------------------------------
def ve_aprendizajes(usuario: str) -> bool:
    """Las guías son públicas; `learnings.md` es el cuaderno técnico de la
    casa (rutas, servidores, cuentas) y solo lo ven los usuarios de Néstor.
    `MCP_APRENDIZAJES_USUARIOS` (lista separada por comas) lo cambia."""
    from src.api import users

    lista = os.environ.get("MCP_APRENDIZAJES_USUARIOS")
    permitidos = {u.strip() for u in (lista if lista is not None else "ana,nestor2,nes_bugallo").split(",") if u.strip()}
    return users.es_admin(usuario) or usuario in permitidos
