"""Registro unificado de fuentes del proyecto.

Una sola fuente de verdad para los selectores de fuente de todos los nichos
(Presidentes, Pronósticos, Quitar Copy, Subs sobre Vídeo).

Devuelve una lista combinada de:
  - **Bundled**: TTF/OTF que viven en `assets/fonts/` del repo. Cross-platform,
    versionadas con el código. El usuario puede añadir las suyas con
    `add_uploaded_font()` y aparecen al instante.
  - **System**: fuentes Windows estándar (Impact, Arial Black, etc.) que
    existen en `C:\\Windows\\Fonts\\` en dev local y se resuelven a sus
    equivalentes en Linux vía `font_resolver`. Solo se incluyen las que
    el OS actual puede resolver realmente.

Las entradas devueltas tienen forma:
    {"name": "Rubik Bold", "path": "<abs path>", "source": "bundled"|"system"}

Las paths son siempre absolutas; los runners pueden pasarlas tal cual a
`PIL.ImageFont.truetype()` (o `safe_truetype` para auto-resolve).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from src.font_resolver import _bundled_fonts_dir, resolve_font


# Fuentes Windows conocidas (etiqueta amistosa → basename para resolve_font).
# `resolve_font` traduce a Linux automáticamente. Si el path resuelto no
# existe en el OS actual, la fuente se omite de la lista (no aparece como
# opción rota en el selector).
_SYSTEM_FONTS: dict[str, str] = {
    "Impact": r"C:\Windows\Fonts\impact.ttf",
    "Arial Black": r"C:\Windows\Fonts\ariblk.ttf",
    "Arial Bold": r"C:\Windows\Fonts\arialbd.ttf",
    "Bahnschrift": r"C:\Windows\Fonts\bahnschrift.ttf",
    "Comic Sans Bold": r"C:\Windows\Fonts\comicbd.ttf",
    "Verdana Bold": r"C:\Windows\Fonts\verdanab.ttf",
    "Tahoma Bold": r"C:\Windows\Fonts\tahomabd.ttf",
    "Trebuchet MS Bold": r"C:\Windows\Fonts\trebucbd.ttf",
    "Georgia Bold": r"C:\Windows\Fonts\georgiab.ttf",
    "Rockwell Extra Bold": r"C:\Windows\Fonts\ROCKEB.TTF",
    "Consolas Bold": r"C:\Windows\Fonts\consolab.ttf",
}

_ALLOWED_EXTS = {".ttf", ".otf"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _bundled_dir() -> Path:
    return Path(_bundled_fonts_dir())


def _label_from_filename(filename: str) -> str:
    """`Rubik-Bold.ttf` → 'Rubik Bold'; `ROCKEB.TTF` → 'Rockeb'."""
    stem = Path(filename).stem
    # Reemplazar separadores comunes por espacio
    s = re.sub(r"[_\-\.]+", " ", stem).strip()
    # Title-case respetando palabras tipo "TikTok" (todo-mayúsculas-cortas se respetan)
    parts = []
    for p in s.split():
        if len(p) >= 2 and p.isupper():
            parts.append(p.title())
        else:
            parts.append(p[:1].upper() + p[1:])
    return " ".join(parts) or stem


def _scan_bundled() -> Iterable[dict]:
    bdir = _bundled_dir()
    if not bdir.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(bdir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _ALLOWED_EXTS:
            continue
        out.append({
            "name": _label_from_filename(entry.name),
            "path": str(entry.resolve()),
            "filename": entry.name,
            "source": "bundled",
        })
    return out


def _scan_system() -> Iterable[dict]:
    out: list[dict] = []
    for label, win_path in _SYSTEM_FONTS.items():
        resolved = resolve_font(win_path)
        # Solo incluir si la fuente existe realmente en este OS.
        if not resolved or not os.path.exists(resolved):
            continue
        out.append({
            "name": label,
            "path": resolved,
            "filename": os.path.basename(resolved),
            "source": "system",
        })
    return out


def list_fonts() -> list[dict]:
    """Devuelve TODAS las fuentes disponibles (bundled + system, en ese orden).

    No usa cache porque la carpeta `assets/fonts/` puede crecer en cualquier
    momento (uploads). El escaneo es trivial (<10 archivos) y barato.
    """
    seen_paths: set[str] = set()
    out: list[dict] = []
    for f in list(_scan_bundled()) + list(_scan_system()):
        if f["path"] in seen_paths:
            continue
        seen_paths.add(f["path"])
        out.append(f)
    return out


def _cross_platform_basename(path: str) -> str:
    """Devuelve el basename del path tratando `/` y `\\` como separadores.

    `os.path.basename` en Linux NO trata `\\` como separador, así que un
    path Windows como `C:\\Windows\\Fonts\\impact.ttf` devuelve la cadena
    entera. Aquí dividimos manualmente por ambos separadores para que la
    comparación basename funcione cross-platform — necesario porque el
    frontend puede mandar paths Windows guardados en presets viejos
    incluso cuando el backend corre en Linux.
    """
    if not path:
        return ""
    # Reemplazar backslashes por forward slashes y tomar el último segmento.
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def find_by_path(path: str) -> dict | None:
    """Resuelve un path (absoluto o basename bundled) a la entrada del registry."""
    target = os.path.normpath(os.path.abspath(path)) if path else ""
    target_base = _cross_platform_basename(path).lower()
    for f in list_fonts():
        if os.path.normpath(f["path"]) == target:
            return f
        if _cross_platform_basename(f["path"]).lower() == target_base:
            return f
    return None


def add_uploaded_font(filename: str, content: bytes) -> dict:
    """Guarda `content` como `assets/fonts/<filename>` y devuelve su entry.

    Raises ValueError si la extensión no es TTF/OTF, el contenido está vacío,
    o el tamaño supera el límite. El nombre se sanitiza para evitar path
    traversal (`../`) o caracteres raros.
    """
    if not content:
        raise ValueError("El archivo está vacío.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValueError(
            f"El archivo pesa {len(content) / 1024 / 1024:.1f} MB; "
            f"máximo {_MAX_UPLOAD_BYTES // 1024 // 1024} MB."
        )
    safe = _safe_filename(filename)
    if Path(safe).suffix.lower() not in _ALLOWED_EXTS:
        raise ValueError(
            f"Extensión no soportada: '{Path(safe).suffix}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_EXTS))}."
        )
    bdir = _bundled_dir()
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / safe
    # No machacar fuentes ya existentes — añadir sufijo numérico.
    if dest.exists():
        stem, ext = dest.stem, dest.suffix
        i = 2
        while True:
            candidate = bdir / f"{stem}_{i}{ext}"
            if not candidate.exists():
                dest = candidate
                break
            i += 1
    dest.write_bytes(content)
    return {
        "name": _label_from_filename(dest.name),
        "path": str(dest.resolve()),
        "filename": dest.name,
        "source": "bundled",
    }


def remove_bundled_font(filename: str) -> bool:
    """Borra una fuente bundled por filename. Solo afecta a `assets/fonts/`
    — no toca fuentes del sistema. Devuelve True si borró algo."""
    safe = _safe_filename(filename)
    target = _bundled_dir() / safe
    if target.is_file() and target.suffix.lower() in _ALLOWED_EXTS:
        target.unlink()
        return True
    return False


def _safe_filename(name: str) -> str:
    """Sanitiza el nombre: solo basename, sin separadores, alfanumérico + `._-`."""
    base = Path(name).name  # quita cualquier ruta
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "", base).strip()
    if not cleaned:
        raise ValueError(f"Nombre de archivo inválido: '{name}'.")
    return cleaned
