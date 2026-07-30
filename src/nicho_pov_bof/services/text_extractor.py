"""Extrae los textos de cada producto de una carpeta a partir de su CAPTURA
CON TÍTULO, usando Gemini multimodal.

Por qué UNA sola llamada con las 10 imágenes y no 10 llamadas sueltas: el
operador pulsa "Obtener textos" una vez para toda la carpeta (ver paso 5 de
`NICHO_POV_BOF_MODULE.md`). Además de ser más barato/rápido que 10
round-trips, es la única forma de que el modelo pueda VARIAR los textos
entre productos del mismo lote — 10 llamadas aisladas no verían lo que
generaron las demás y tenderían a repetir la misma fórmula.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.services import drive_client, photo_pairing
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None

# El prompt vive en `prompts/` del propio módulo (convención del proyecto:
# nunca hardcoded en el código). OJO: NO se usa `gemini.load_system_prompt`
# porque esa función resuelve rutas dentro de `tiktok_shop/prompts/` por su
# propia convención — aquí toca resolver la ruta a mano, hermana de `services/`.
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "text_extractor.md"

# Campos que debe traer cada entrada para considerarla válida. Si Gemini deja
# alguno vacío o el producto entero fuera del JSON, ese producto se omite en
# vez de tumbar la extracción de los demás.
# `gancho` y `cta` ya NO se piden: son fijos y los pone el montaje
# (`video_editor.textos_fijos`), por cumplimiento.
REQUIRED_FIELDS = (
    "titulo",
    "titulo_tiktok_completo",
    "tienda",
    "caption",
)


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _is_valid_entry(entry: object) -> bool:
    """Una entrada vale si es un dict con los 4 campos, todos string no vacío."""
    if not isinstance(entry, dict):
        return False
    return all(isinstance(entry.get(f), str) and entry.get(f).strip() for f in REQUIRED_FIELDS)


def extract_folder_texts(source: str, folder: str, *, on_log: OnLog = _noop) -> dict[str, dict]:
    """Extrae los textos de TODOS los productos de una carpeta en UNA llamada.

    Devuelve `{producto: {titulo, titulo_tiktok_completo, tienda, caption}}`
    (gancho y CTA son fijos, los pone `video_editor.textos_fijos`). La clave
    `producto` es la misma que usa
    `photo_pairing.pair_folder` (el número de producto dentro de la carpeta,
    p.ej. "1".."10"), así el caller puede cruzarla directamente con el resto
    del flujo por producto.

    Nunca revienta la carpeta entera: si Gemini falla, devuelve JSON
    inválido, o a un producto le falta la "captura con título", ese producto
    se omite del dict de salida y el motivo queda en `on_log`. Lo que sí se
    pudo extraer se devuelve igual.
    """
    photos = drive_client.list_photos(source, folder)
    pairs = photo_pairing.pair_folder(photos)

    # Sin captura con título no hay de dónde sacar texto para ese producto.
    usable = [p for p in pairs if p.get("titled")]
    skipped = [p["producto"] for p in pairs if not p.get("titled")]
    if skipped:
        on_log(f"[text_extractor] sin captura con título, se omiten: {skipped}")
    if not usable:
        on_log("[text_extractor] ninguna captura con título en la carpeta")
        return {}

    # Descarga las capturas (cacheadas en disco por drive_client.fetch_photo,
    # así que repetir la extracción no vuelve a bajar nada). `ids` queda en el
    # MISMO orden que `image_paths`: es la única forma de que Gemini sepa qué
    # imagen es qué producto (las imágenes no llevan nombre de fichero).
    ids: list[str] = []
    image_paths: list[str] = []
    for pair in usable:
        titled = pair["titled"]
        try:
            suffix = Path(titled.get("name", "")).suffix or ".jpg"
            path = drive_client.fetch_photo(titled["id"], suffix=suffix)
            image_paths.append(str(path))
            ids.append(pair["producto"])
        except Exception as e:
            on_log(f"[text_extractor] no se pudo descargar producto {pair['producto']}: {e}")

    if not image_paths:
        on_log("[text_extractor] no se pudo descargar ninguna captura")
        return {}

    on_log(f"[text_extractor] pidiendo a Gemini {len(image_paths)} textos ({ids})…")
    system_prompt = _load_system_prompt()
    user_prompt = (
        "Identificadores en el MISMO orden que las imágenes adjuntas "
        f"(imagen 1 = primer identificador, imagen 2 = segundo, etc.): "
        f"{json.dumps(ids, ensure_ascii=False)}"
    )

    try:
        raw = generate_json(system_prompt, user_prompt, images=image_paths)
    except Exception as e:
        # Gemini caído / cuota agotada / JSON inválido: sin textos esta vez,
        # pero la carpeta sigue navegable — el operador puede reintentar el
        # botón sin perder nada (las fotos ya están cacheadas en disco).
        on_log(f"[text_extractor] Gemini falló: {e}")
        return {}

    if not isinstance(raw, dict):
        on_log(f"[text_extractor] Gemini devolvió un tipo inesperado: {type(raw).__name__}")
        return {}

    result: dict[str, dict] = {}
    for producto_id in ids:
        entry = raw.get(producto_id)
        if _is_valid_entry(entry):
            result[producto_id] = {f: entry[f].strip() for f in REQUIRED_FIELDS}
        else:
            on_log(f"[text_extractor] respuesta incompleta para producto {producto_id}, se omite")

    on_log(f"[text_extractor] {len(result)}/{len(ids)} productos con texto extraído")
    return result
