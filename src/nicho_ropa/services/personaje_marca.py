"""El personaje fijo de Moda Mujer · Marca Personal.

Los prompts de imagen de marca (espejo y zapatos multi escena) piden adjuntar
en Flow "tu personaje de referencia" junto con la prenda: es lo que hace que
salga SIEMPRE la misma persona, que es la identidad de la cuenta. Antes esa
foto no vivía en ningún sitio de la app y había que buscarla cada vez — y una
IA que trabaje sola no tenía de dónde sacarla.

Una foto por usuario (cada uno lleva su cuenta de TikTok), en el Drive montado:
`<DRIVE_UPLOAD_ROOT>/personaje_marca/<usuario>.<ext>`.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.nicho_ropa import config

_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _dir() -> Path:
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / config.DRIVE_UPLOAD_ROOT / "personaje_marca" if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_ropa" / "personaje_marca"
    )
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _nombre(usuario: str) -> str:
    # El histórico va sin sufijo de usuario en todo el proyecto: es el de ness.
    return (usuario or "ness").strip().lower() or "ness"


def obtener(usuario: str) -> Path | None:
    base = _dir()
    for ext in _EXTS:
        p = base / f"{_nombre(usuario)}{ext}"
        if p.is_file():
            return p
    return None


def guardar(usuario: str, datos: bytes, filename: str = "") -> Path:
    """Sustituye el personaje del usuario (solo hay uno)."""
    borrar(usuario)
    ext = Path(filename or "").suffix.lower()
    destino = _dir() / f"{_nombre(usuario)}{ext if ext in _EXTS else '.jpg'}"
    destino.write_bytes(datos)
    return destino


def borrar(usuario: str) -> bool:
    quitado = False
    for ext in _EXTS:
        p = _dir() / f"{_nombre(usuario)}{ext}"
        if p.is_file():
            p.unlink(missing_ok=True)
            quitado = True
    return quitado


def estado(usuario: str) -> dict:
    """`hay` + `v` (mtime) para que la URL de la miniatura cambie al cambiarla."""
    p = obtener(usuario)
    return {"hay": bool(p), "v": int(p.stat().st_mtime) if p else 0}
