"""Rutas del Google Drive: una sola fuente para la raíz y para lo que se guarda en Redis.

Transversal a todos los programas (como `cost_tracking`). Dos problemas que resuelve:

1. **La raíz del proyecto en el Drive cambia** (nov 2026: `NEBULABS_AUTOMATED_TIKTOK`
   pasa a `Nebulabs/TikTok`, y el Programa 4 a `Nebulabs/TikTok/TikTok Shop`). El código
   no escribe esos nombres a mano: usa `PROYECTO_REL` y `AI_PRO_REL`, que salen de las
   variables `NEBULABS_DRIVE_DIR` y `AI_PRO_DRIVE_DIR`.

2. **Redis no guarda rutas absolutas** (Néstor, 4/11/2026). Al ESCRIBIR, toda ruta dentro
   del Drive montado se guarda relativa con el prefijo `drive:` (`drive:Nebulabs/TikTok/…`);
   al LEER se vuelve absoluta para el sitio donde corre el código (`/mnt/drive` en el
   contenedor, `~/gdrive` en el host). Las absolutas viejas se siguen entendiendo, y los
   `ALIAS` llevan una ruta vieja a donde está ahora la carpeta: mover una carpeta del Drive
   = moverla + añadir un alias (o migrar Redis con `scripts/redis_rutas_relativas.py`).

Los repos de Redis llaman a `relativizar()` en `set_json`/`sadd` y a `absolutizar()` en
`get_json`/`smembers`: el resto del código sigue viendo rutas absolutas como siempre.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PREFIJO = "drive:"

# Raíces con las que se ha montado el Drive alguna vez (contenedor y host). Al leer o
# escribir, cualquiera de ellas se reconoce como «dentro del Drive».
MONTAJES_CONOCIDOS = ("/mnt/drive", "/home/nebulabsai/gdrive", str(Path.home() / "gdrive"))

# Carpeta del proyecto TikTok dentro del Drive (antes NEBULABS_AUTOMATED_TIKTOK).
PROYECTO_REL = os.getenv("NEBULABS_DRIVE_DIR", "NEBULABS_AUTOMATED_TIKTOK").strip().strip("/")
# Carpeta del Programa 4 (Tiktok Shop AI Pro) dentro del Drive.
AI_PRO_REL = os.getenv("AI_PRO_DRIVE_DIR", f"{PROYECTO_REL}/TIKTOK_SHOP_AI_PRO").strip().strip("/")

# Carpeta de Creator Reward (antes TIKTOK_CR, con TIKTOK_ASSETS dentro).
CR_REL = os.getenv("CR_DRIVE_DIR", f"{PROYECTO_REL}/TIKTOK_CR").strip().strip("/")

# Material del curso (copias de «Productos España», paquetes, Skool). Antes colgaba
# directamente de la carpeta del proyecto.
CURSO_REL = os.getenv("CURSO_DRIVE_DIR", PROYECTO_REL).strip().strip("/")

# Rutas viejas → dónde están ahora (relativas a la raíz del Drive, sin barra final).
# Se aplican de la más larga a la más corta. Se pueden ampliar sin tocar código con
# `DRIVE_ALIAS_JSON` ('{"viejo/prefijo": "nuevo/prefijo"}').
_ALIAS_BASE: dict[str, str] = {}
if PROYECTO_REL != "NEBULABS_AUTOMATED_TIKTOK":
    _ALIAS_BASE["NEBULABS_AUTOMATED_TIKTOK"] = PROYECTO_REL
if AI_PRO_REL != f"{PROYECTO_REL}/TIKTOK_SHOP_AI_PRO":
    _ALIAS_BASE["NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO"] = AI_PRO_REL
    _ALIAS_BASE[f"{PROYECTO_REL}/TIKTOK_SHOP_AI_PRO"] = AI_PRO_REL
if CURSO_REL != PROYECTO_REL:
    for _d in ("BACKUPS_Productos_Espana", "BACKUPS_Skool", "PAQUETE_Productos_Espana_2026-08-19"):
        _ALIAS_BASE[f"NEBULABS_AUTOMATED_TIKTOK/{_d}"] = f"{CURSO_REL}/{_d}"
        _ALIAS_BASE[f"{PROYECTO_REL}/{_d}"] = f"{CURSO_REL}/{_d}"
# La TIKTOK_SHOP_AI_PRO que había suelta en la raíz del Drive (Nicho General la usaba
# por error): se movió dentro del Programa 4.
_ALIAS_BASE["TIKTOK_SHOP_AI_PRO"] = os.getenv(
    "AI_PRO_RAIZ_VIEJA_DIR", "TIKTOK_SHOP_AI_PRO").strip().strip("/")
if _ALIAS_BASE["TIKTOK_SHOP_AI_PRO"] == "TIKTOK_SHOP_AI_PRO":
    del _ALIAS_BASE["TIKTOK_SHOP_AI_PRO"]
if CR_REL != f"{PROYECTO_REL}/TIKTOK_CR":
    _ALIAS_BASE["NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR"] = CR_REL
    _ALIAS_BASE[f"{PROYECTO_REL}/TIKTOK_CR"] = CR_REL


def _alias_env() -> dict[str, str]:
    crudo = os.getenv("DRIVE_ALIAS_JSON", "").strip()
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        print("[rutas_drive] DRIVE_ALIAS_JSON no es JSON válido; se ignora")
        return {}
    return {str(k).strip("/"): str(v).strip("/") for k, v in datos.items() if k}


ALIAS: dict[str, str] = {**_ALIAS_BASE, **_alias_env()}


def raiz_drive() -> Path:
    """Dónde está montado el Drive aquí. `DRIVE_MOUNT_ROOT` manda; si no, el primer
    montaje que exista; si no hay ninguno (tests, dev), `/mnt/drive`."""
    env = os.getenv("DRIVE_MOUNT_ROOT", "").strip()
    if env:
        return Path(env)
    for c in ("/mnt/drive", str(Path.home() / "gdrive")):
        if Path(c).is_dir():
            return Path(c)
    return Path("/mnt/drive")


def _montajes() -> list[str]:
    vistos: list[str] = []
    for m in (os.getenv("DRIVE_MOUNT_ROOT", "").strip(), *MONTAJES_CONOCIDOS):
        m = m.rstrip("/")
        if m and m not in vistos:
            vistos.append(m)
    # Los más largos primero (por si uno contiene a otro).
    return sorted(vistos, key=len, reverse=True)


def aplicar_alias(rel: str) -> str:
    """Lleva una ruta relativa vieja a su sitio actual según `ALIAS`."""
    for viejo in sorted(ALIAS, key=len, reverse=True):
        if rel == viejo or rel.startswith(viejo + "/"):
            return ALIAS[viejo] + rel[len(viejo):]
    return rel


def _quitar_montaje(s: str) -> str | None:
    for m in _montajes():
        if s == m:
            return ""
        if s.startswith(m + "/"):
            return s[len(m) + 1:]
    return None


def es_ruta_drive(s: Any) -> bool:
    return isinstance(s, str) and (s.startswith(PREFIJO) or _quitar_montaje(s) is not None)


def a_relativa(s: Any) -> Any:
    """`/mnt/drive/X` o `~/gdrive/X` → `drive:X` (con alias aplicado). Lo demás, igual."""
    if not isinstance(s, str) or not s:
        return s
    if s.startswith(PREFIJO):
        return PREFIJO + aplicar_alias(s[len(PREFIJO):])
    rel = _quitar_montaje(s)
    if rel is None:
        return s
    return PREFIJO + aplicar_alias(rel)


def a_absoluta(s: Any) -> Any:
    """`drive:X` o una absoluta de cualquier montaje → ruta absoluta en ESTE sitio,
    con alias aplicado. Lo que no es del Drive se devuelve tal cual."""
    if not isinstance(s, str) or not s:
        return s
    if s.startswith(PREFIJO):
        rel = s[len(PREFIJO):]
    else:
        rel = _quitar_montaje(s)
        if rel is None:
            return s
    rel = aplicar_alias(rel)
    raiz = str(raiz_drive()).rstrip("/")
    return f"{raiz}/{rel}" if rel else raiz


def _recorrer(obj: Any, fn) -> Any:
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _recorrer(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recorrer(v, fn) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_recorrer(v, fn) for v in obj)
    return obj


def relativizar(obj: Any) -> Any:
    """Copia de `obj` (dict/list/str anidados) con las rutas del Drive en relativo.
    Solo cambia VALORES; las claves de los dict no se tocan."""
    return _recorrer(obj, a_relativa)


def absolutizar(obj: Any) -> Any:
    """Copia de `obj` con las rutas del Drive en absoluto para este sitio."""
    return _recorrer(obj, a_absoluta)


def ruta(*partes: str) -> Path:
    """Ruta absoluta dentro del Drive: `ruta(AI_PRO_REL, "Replicar_Viral")`."""
    return raiz_drive().joinpath(*[p.strip("/") for p in partes if p])
