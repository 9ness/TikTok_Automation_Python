"""Claves API de los proyectos del VPS — la versión web de `~/.local/bin/clave`.

La usa `webhook_listener.py` (host, usuario `nebulabsai`) para que Accesos ›
«Claves API» guarde una clave en el `.env.local` de cualquier proyecto de
`~/proyectos` sin terminal. El contenedor de la API NO monta esos ficheros:
solo llega aquí por `/admin/claves` con la `X-API-Key`.

Reglas (las mismas que `clave`):
- `.env.local` si existe (o si no hay ninguno); si solo hay `.env`, ese.
- Se niega si el fichero no está en el `.gitignore` del proyecto.
- Sustituye la línea si la variable ya estaba, escribe atómico y deja 600.
- Prueba la clave contra su API y devuelve solo el código HTTP.
- NUNCA devuelve ni loguea el valor: el listado enseña nombre + últimos 4.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

BASE = os.path.realpath(os.environ.get("PROYECTOS_DIR", os.path.expanduser("~/proyectos")))
RE_PROYECTO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RE_VARIABLE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
RE_LINEA = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
MAX_VALOR = 4096
# Por debajo de esto no se enseña ni la cola: un valor corto se adivinaría entero.
MIN_PARA_COLA = 12


class ClaveError(Exception):
    """Error que se le puede enseñar al usuario tal cual (sin secretos)."""


def _dir_proyecto(proyecto: str) -> str:
    if not RE_PROYECTO.match(proyecto or ""):
        raise ClaveError("Proyecto no válido")
    d = os.path.realpath(os.path.join(BASE, proyecto))
    if os.path.dirname(d) != BASE or not os.path.isdir(d):
        raise ClaveError(f"No existe el proyecto {proyecto}")
    return d


def _fichero(d: str) -> str:
    local = os.path.join(d, ".env.local")
    env = os.path.join(d, ".env")
    if not os.path.exists(local) and os.path.isfile(env):
        return env
    return local


def _ignorado(d: str, fichero: str) -> bool | None:
    """True/False si es repo git; None si no lo es (no hay git donde filtrarse)."""
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, timeout=10)
        if r.returncode != 0:
            return None
        r = subprocess.run(["git", "-C", d, "check-ignore", "-q", fichero],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _mascara(valor: str) -> str:
    valor = valor.strip().strip("'\"")
    if not valor:
        return "(vacía)"
    if len(valor) < MIN_PARA_COLA:
        return "••••"
    return "••••" + valor[-4:]


def _variables(fichero: str) -> list[dict]:
    if not os.path.isfile(fichero):
        return []
    vistas: dict[str, str] = {}
    try:
        with open(fichero, encoding="utf-8", errors="replace") as f:
            for linea in f:
                m = RE_LINEA.match(linea)
                if m and m.group(1) not in vistas:
                    vistas[m.group(1)] = _mascara(m.group(2))
    except OSError:
        return []
    return [{"nombre": k, "mascara": v} for k, v in vistas.items()]


def listar() -> list[dict]:
    out = []
    for nombre in sorted(os.listdir(BASE), key=str.lower):
        d = os.path.join(BASE, nombre)
        if nombre.startswith(".") or not os.path.isdir(d):
            continue
        f = _fichero(d)
        out.append({
            "proyecto": nombre,
            "fichero": os.path.basename(f),
            "existe": os.path.isfile(f),
            "ignorado": _ignorado(d, f),
            "variables": _variables(f),
        })
    return out


def _escribir(fichero: str, variable: str, valor: str) -> bool:
    """Sustituye o añade `VARIABLE=valor`. Devuelve True si ya existía."""
    lineas: list[str] = []
    if os.path.isfile(fichero):
        with open(fichero, encoding="utf-8", errors="surrogateescape") as f:
            lineas = f.read().splitlines()
    nueva = f"{variable}={valor}"
    salida, habia = [], False
    for linea in lineas:
        m = RE_LINEA.match(linea)
        if m and m.group(1) == variable:
            if not habia:
                salida.append(nueva)
                habia = True
            continue
        salida.append(linea)
    if not habia:
        salida.append(nueva)
    d = os.path.dirname(fichero)
    fd, tmp = tempfile.mkstemp(prefix=".clave-", dir=d)  # mkstemp ya crea en 600
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write("\n".join(salida) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, fichero)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    os.chmod(fichero, 0o600)
    return habia


def _probar(variable: str, valor: str) -> int | str | None:
    """Código HTTP de la API de la clave, "red" si no se pudo llamar, None si no se sabe probar."""
    if variable.startswith("ANTHROPIC"):
        req = urllib.request.Request("https://api.anthropic.com/v1/models",
                                     headers={"x-api-key": valor, "anthropic-version": "2023-06-01"})
    elif variable.startswith(("GEMINI", "GOOGLE_GEMINI", "GOOGLE_API_KEY")):
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models",
                                     headers={"x-goog-api-key": valor})
    elif variable.startswith("OPENAI"):
        req = urllib.request.Request("https://api.openai.com/v1/models",
                                     headers={"Authorization": f"Bearer {valor}"})
    else:
        return None
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode() or 200
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return "red"


def guardar(proyecto: str, variable: str, valor: str) -> dict:
    d = _dir_proyecto(proyecto)
    if not RE_VARIABLE.match(variable or ""):
        raise ClaveError("Nombre de variable no válido (MAYÚSCULAS, números y _)")
    valor = re.sub(r"[\r\n ]", "", valor or "")
    if not valor:
        raise ClaveError("La clave está vacía: no guardo nada")
    if len(valor) > MAX_VALOR or any(ord(c) < 32 for c in valor):
        raise ClaveError("La clave tiene caracteres no válidos o es demasiado larga")
    fichero = _fichero(d)
    if _ignorado(d, fichero) is False:
        raise ClaveError(f"{os.path.basename(fichero)} NO está en el .gitignore de {proyecto}: no guardo nada")
    habia = _escribir(fichero, variable, valor)
    return {
        "proyecto": proyecto,
        "variable": variable,
        "fichero": os.path.basename(fichero),
        "accion": "sustituida" if habia else "añadida",
        "mascara": _mascara(valor),
        "prueba": _probar(variable, valor),
    }
