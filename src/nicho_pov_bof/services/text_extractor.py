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
# `tienda` NO está aquí: si el modelo no la lee bien, se prefiere quedarse con
# el producto (título + caption, que es lo que se publica) y dejar la tienda
# vacía, en vez de tirar el producto entero. Antes se perdía la ficha completa
# por no distinguirse el nombre de la tienda en la captura.
REQUIRED_FIELDS = (
    "titulo",
    "titulo_tiktok_completo",
    "caption",
)
# Opcionales: si no vienen, el producto NO se descarta. `emojis` se añadió
# después, así que los productos extraídos antes no lo tienen y hay un
# respaldo por palabras clave en `services/emojis.py`.
OPTIONAL_FIELDS = ("emojis", "tienda", "precio")


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# Rellenos que devuelve el modelo cuando no ha sabido leer la imagen. El
# prompt le pide que NUNCA deje un campo vacío (para que no se salte
# productos), y el efecto secundario es que a veces escribe esto. Si se
# colara, acabaría QUEMADO en el vídeo como si fuera el nombre del producto.
_RELLENOS = (
    "informacion no disponible", "información no disponible",
    "no disponible", "no visible", "desconocido", "sin titulo",
    "sin título", "n/a", "na", "-", "?",
)
# OJO: no meter aquí palabras sueltas "que suenan a relleno". Se añadió
# "encountered" pensando que el modelo se lo inventaba y resultó ser el nombre
# REAL de una tienda ("Vendido por Encountered"), así que se estaba borrando un
# dato bueno. Un relleno se reconoce por la FORMA (frase de disculpa, corchetes),
# no por la palabra.


def _es_relleno(valor: str) -> bool:
    v = valor.strip().strip(".").lower()
    # "[Tienda no visible en la captura]" y similares: el modelo avisa entre
    # corchetes de que no lo ve, y eso acababa pintado como si fuera el dato.
    if v.startswith("[") and v.endswith("]"):
        return True
    return v in _RELLENOS


def _is_valid_entry(entry: object) -> bool:
    """Vale si es un dict con los 4 campos, todos string no vacío y ninguno
    un relleno del tipo "Información no disponible"."""
    if not isinstance(entry, dict):
        return False
    for f in REQUIRED_FIELDS:
        v = entry.get(f)
        if not isinstance(v, str) or not v.strip() or _es_relleno(v):
            return False
    return True


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
    pairs = [
        photo_pairing.desempatar_por_contenido(par, drive_client.fetch_photo)
        for par in photo_pairing.pair_folder(photos)
    ]
    return extract_from_pairs(
        pairs,
        system_prompt=_load_system_prompt(),
        fetch=drive_client.fetch_photo,
        on_log=on_log,
    )


def _sellar_id(path, producto: str):
    """Escribe `#<producto>` en una banda arriba de la captura.

    El identificador viajaba SOLO en el texto del prompt ("imagen 1 = primer
    identificador…"), y con 8-10 imágenes en una tanda el modelo se desalinea:
    pasó en una carpeta entera, donde cada producto se quedó con el título del
    siguiente. Si el número va DENTRO de la imagen no hay orden que perder.

    Si algo falla (PIL, disco), se devuelve la foto original: mejor arriesgarse
    al desajuste que quedarse sin textos.
    """
    from pathlib import Path as _Path

    try:
        from PIL import Image, ImageDraw, ImageFont

        origen = _Path(str(path))
        destino = origen.with_name(f"{origen.stem}__id{producto}.jpg")
        if destino.is_file():
            return destino
        with Image.open(origen) as im:
            im = im.convert("RGB")
            banda = max(48, im.height // 22)
            lienzo = Image.new("RGB", (im.width, im.height + banda), "white")
            lienzo.paste(im, (0, banda))
            dib = ImageDraw.Draw(lienzo)
            try:
                fuente = ImageFont.truetype(
                    str(_Path(__file__).resolve().parents[3] / "assets" / "fonts"
                        / "Montserrat-Black.ttf"),
                    int(banda * 0.7),
                )
            except Exception:
                fuente = ImageFont.load_default()
            dib.text((12, 4), f"#{producto}", fill="black", font=fuente)
            lienzo.save(destino, quality=88)
        return destino
    except Exception:
        return path


def extract_from_pairs(
    pairs: list[dict],
    *,
    system_prompt: str,
    fetch,
    on_log: OnLog = _noop,
) -> dict[str, dict]:
    """El motor de la extracción, sin saber de dónde salen las fotos.

    Lo usan los dos nichos que leen capturas de TikTok Shop (POV BOF y Ropa
    Sin Personas): cambia el prompt y de qué Drive se bajan las fotos, pero la
    validación, el descarte de rellenos ("Información no disponible") y el
    reintento de los que el modelo se deja son idénticos.
    """
    # Lo normal es leer la captura con título. Pero hay productos que en Drive
    # solo tienen UNA foto, y a veces esa foto es el pantallazo de la
    # DESCRIPCIÓN — que también lleva el nombre del producto y la tienda. Antes
    # se omitían y el producto se quedaba "sin título" para siempre; ahora se
    # manda lo que haya y que Gemini lea lo que pueda.
    usable = [p for p in pairs if p.get("titled") or p.get("clean")]
    skipped = [p["producto"] for p in pairs if not (p.get("titled") or p.get("clean"))]
    if skipped:
        on_log(f"[text_extractor] sin ninguna foto, se omiten: {skipped}")
    respaldo = [p["producto"] for p in usable if not p.get("titled")]
    if respaldo:
        on_log(
            "[text_extractor] sin captura con título, se prueba con la única "
            f"foto que hay: {respaldo}"
        )
    if not usable:
        on_log("[text_extractor] ninguna foto utilizable en la carpeta")
        return {}

    # Descarga las capturas (cacheadas en disco por drive_client.fetch_photo,
    # así que repetir la extracción no vuelve a bajar nada). `ids` queda en el
    # MISMO orden que `image_paths`: es la única forma de que Gemini sepa qué
    # imagen es qué producto (las imágenes no llevan nombre de fichero).
    ids: list[str] = []
    image_paths: list[str] = []
    for pair in usable:
        titled = pair.get("titled") or pair["clean"]
        try:
            suffix = Path(titled.get("name", "")).suffix or ".jpg"
            path = fetch(titled["id"], suffix=suffix)
            image_paths.append(str(_sellar_id(path, pair["producto"])))
            ids.append(pair["producto"])
        except Exception as e:
            on_log(f"[text_extractor] no se pudo descargar producto {pair['producto']}: {e}")

    if not image_paths:
        on_log("[text_extractor] no se pudo descargar ninguna captura")
        return {}

    def _pedir(lote_ids: list[str], lote_paths: list[str]) -> dict[str, dict]:
        """Una llamada a Gemini con las imágenes dadas."""
        on_log(f"[text_extractor] pidiendo a Gemini {len(lote_paths)} textos ({lote_ids})…")
        user_prompt = (
            "Cada imagen lleva su identificador ESCRITO en una banda blanca "
            "arriba del todo, con el formato `#<id>`. Usa SIEMPRE ese número "
            "para devolver los textos de esa imagen; ignora el orden en que "
            "te lleguen. Identificadores esperados: "
            f"{json.dumps(lote_ids, ensure_ascii=False)}"
        )
        try:
            raw = generate_json(system_prompt, user_prompt, images=lote_paths)
        except Exception as e:
            # Gemini caído / cuota agotada / JSON inválido: sin textos esta
            # vez, pero la carpeta sigue navegable — se puede reintentar el
            # botón sin perder nada (las fotos ya están cacheadas en disco).
            on_log(f"[text_extractor] Gemini falló: {e}")
            return {}
        if not isinstance(raw, dict):
            on_log(
                f"[text_extractor] Gemini devolvió un tipo inesperado: "
                f"{type(raw).__name__}"
            )
            return {}
        salida: dict[str, dict] = {}
        for pid in lote_ids:
            entry = raw.get(pid)
            if _is_valid_entry(entry):
                doc = {f: entry[f].strip() for f in REQUIRED_FIELDS}
                for f in OPTIONAL_FIELDS:
                    v = entry.get(f)
                    # El precio se pide como número y el modelo lo manda tal
                    # cual la mitad de las veces (45.9, no "45.9"). Sin esto se
                    # tiraba en silencio y el producto salía sin precio, que es
                    # justo lo que decide si lleva el guion de plazos.
                    if f == "precio" and isinstance(v, (int, float)):
                        v = f"{v:g}"
                    # Los opcionales se limpian igual: mejor vacío (y el botón
                    # sale desactivado) que un relleno pintado como si fuera
                    # el nombre real de la tienda.
                    if isinstance(v, str) and v.strip() and not _es_relleno(v):
                        doc[f] = v.strip()
                salida[pid] = doc
        return salida

    result = _pedir(ids, image_paths)

    # Reintento de los que se hayan quedado fuera. En un lote de 10 imágenes
    # el modelo se deja alguna suelta (pasó con una captura muy alta,
    # 943x2048, que a solas sí leía bien). Cuesta UNA llamada más y solo
    # cuando hace falta, así que sale a cuenta frente a dejar el producto sin
    # título hasta que el operador se dé cuenta.
    faltan = [i for i in ids if i not in result]
    if faltan and len(faltan) < len(ids):
        on_log(f"[text_extractor] reintentando los que faltan: {faltan}")
        paths_faltan = [image_paths[ids.index(i)] for i in faltan]
        result.update(_pedir(faltan, paths_faltan))

    for pid in ids:
        if pid not in result:
            on_log(f"[text_extractor] sin texto utilizable para producto {pid}")

    on_log(f"[text_extractor] {len(result)}/{len(ids)} productos con texto extraído")
    return result
