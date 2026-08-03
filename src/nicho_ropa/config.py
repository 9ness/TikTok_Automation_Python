"""Nicho Ropa Sin Personas (Programa 4 — módulo 8 del curso).

Qué lo diferencia del Nicho POV BOF, que es el que más se le parece:

- El Drive de fotos se comparte **por enlace**, no aparece en "Compartido
  conmigo". Se lee con `--drive-root-folder-id`, que convierte esa carpeta en
  la raíz del remote.
- Es UNA sola carpeta con todos los productos dentro, no una fuente con
  carpetas de producto. De momento solo hay camisetas.
- El vídeo final **no lleva texto quemado** — ni gancho, ni título, ni CTA, ni
  flecha. El producto se enseña y ya. Y va **mudo por defecto**: el operador
  le pone la música al publicar.

Lo que SÍ se reutiliza del Nicho POV BOF, porque es idéntico y funciona:
`photo_pairing` (emparejar foto limpia + captura con título, incluidos los
nombres duplicados) y la descarga de fotos por file ID.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Drive de origen (SOLO LECTURA)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"

# Carpetas de producto, dentro del Drive compartido "Productos España". Con
# `--drive-root-folder-id` rclone trata la carpeta como la raíz del remote, así
# que los paths van vacíos ("gdrive:").
#
# Una MISMA prenda vale para los dos nichos de ropa: en percha (sin nadie) o
# puesta por una modelo. Lo que cambia es el prompt, no la foto — por eso estas
# carpetas no son exclusivas de este módulo aunque el curso las separe.
CARPETAS: dict[str, dict[str, str]] = {
    "camisetas": {
        "label": "Camisetas / Conjuntos",
        "id": "10jSRauIlUVFXo3Dr6RCi8iO1gIY2TDIL",
    },
    "mono": {
        "label": "Mono (mujer)",
        "id": "1MXBSXZRwqbo1F25OAM-MhO-qTf4SmxyK",
    },
    "pantalon_corto": {
        "label": "Pantalón corto (mujer)",
        "id": "11enOhq4DL_lmdttQWqgowmA1MRqrR3_0",
    },
    "bikinis": {
        "label": "Bikinis",
        "id": "1T-nqij3xl4Dp-h2JvGJofCq6Wzoia25a",
    },
}

CARPETA_DEFECTO = "camisetas"


def es_carpeta_conocida(slug: str) -> bool:
    return slug in CARPETAS


def carpeta_label(slug: str) -> str:
    return CARPETAS.get(slug, {}).get("label", slug)


def carpeta_id(slug: str = "") -> str:
    """ID de Drive de una carpeta. Override global por `.env` para pruebas."""
    forzado = (os.getenv("NICHO_ROPA_FOLDER_ID") or "").strip()
    if forzado:
        return forzado
    meta = CARPETAS.get(slug or CARPETA_DEFECTO)
    if not meta:
        raise ValueError(
            f"Carpeta desconocida: {slug!r}. Válidas: {sorted(CARPETAS)}"
        )
    return meta["id"]


def redis_prefix() -> str:
    return os.getenv("NICHO_ROPA_REDIS_PREFIX", "nicho_ropa:")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


# El prompt de vídeo tiene dos versiones y la diferencia es UNA frase: la de la
# mano acariciando la ropa. Se guarda una sola vez y la versión sin manos es
# ese texto menos esa línea, para que no puedan quedar desincronizados.
LINEA_MANOS = "Una mano aparece en escena y acaricia la ropa."


def prompt_video(con_manos: bool) -> str:
    texto = (prompts_dir() / "prompt_video.md").read_text(encoding="utf-8").strip()
    if con_manos:
        return texto
    return " ".join(texto.replace(LINEA_MANOS, "").split())


def prompt_video_percha() -> str:
    """Segundo estilo del nicho: la prenda colgada en una percha, sin nadie.

    Sale de `Camisetas／Conjuntos/Ropa/Pronts/Ropa Percha.docx`. No estaba en la
    carpeta de Skool — apareció al mirar el Drive de productos. Es el otro
    prompt de los seis de ropa que NO lleva modelo (los demás sí, y esos son
    del módulo 7).

    Va aparte y no como variante del de alfombra porque no comparte texto: es
    otro escenario entero, no la misma toma con o sin manos.
    """
    return (prompts_dir() / "prompt_video_percha.md").read_text(encoding="utf-8").strip()


def prompt_imagen() -> str:
    return (prompts_dir() / "prompt_imagen.md").read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
# Mismo patrón que el resto del Programa 4: todo cuelga de TIKTOK_SHOP_AI_PRO.
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas"


def video_dir() -> Path:
    """Dónde quedan los vídeos montados.

    Va al mismo Drive montado que el resto del Programa 4, bajo su propia
    carpeta. Si el mount no está (dev local), cae a `API_TEMP_ROOT`.
    """
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / DRIVE_UPLOAD_ROOT / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_ropa" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
