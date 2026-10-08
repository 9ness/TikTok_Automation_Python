"""Catálogo «🖼️ Carruseles virales» de «Replicar carrusel» (Programa 4).

El producto de un carrusel se puede dar de alta en la MISMA pantalla, sin
pasar por el POV BOF: foto limpia + captura de la ficha + URL de TikTok Shop.
Va a un catálogo del operador más (`carruseles_virales`, ver
`nicho_pov_bof.config.CATALOGOS_OPERADOR`), así que lo guarda
`mis_productos.guardar_producto` con el convenio de nombres de siempre y
todo lo de después (emparejado, textos, escaparate, la propia réplica) lo lee
sin nada especial. Es COMPARTIDO: Ana y Mauro lo ven y pueden replicar el
mismo carrusel viral en su cuenta.

Al guardar:
- se leen los textos de la ficha con el extractor del POV BOF (una llamada de
  Gemini, SOLO de ese producto, con su coste registrado en `/costs`);
- la URL va a `product_url` + `product_id` del producto y al índice global de
  fichas (`product_repo.guardar_url`), como cuando se pega a mano;
- el enlace del carrusel viral de origen, si se da, queda en `carrusel_url`
  para volver a replicarlo luego con otro usuario.
"""

from __future__ import annotations

import time

from src.replicar_viral.servicio import ErrorReplica

SOURCE = "carruseles_virales"
_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_BYTES = 12 * 1024 * 1024


def _validar_foto(datos: bytes, nombre: str, que: str) -> None:
    if not datos:
        raise ErrorReplica(f"Falta {que}.")
    if nombre and not nombre.lower().endswith(_EXTS):
        raise ErrorReplica(f"{que.capitalize()} tiene un formato no soportado ({nombre!r}): jpg, png o webp.")
    if len(datos) > MAX_BYTES:
        raise ErrorReplica(f"{que.capitalize()} pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.")


def _es_tiktok(url: str) -> bool:
    from src.nicho_pov_bof.repos import product_repo

    return product_repo._es_ficha_tiktok(url)


def extraer_textos(carpeta: str, producto: str, usuario: str = "") -> dict:
    """Textos de la ficha de UN producto (no de toda la carpeta: las demás ya
    los tienen y volver a leerlas costaría y podría cambiarles el título)."""
    from src.cost_tracking import finalize_and_persist, start_job
    from src.nicho_pov_bof.services import drive_client, photo_pairing, text_extractor

    fotos = drive_client.list_photos(SOURCE, carpeta)
    pares = [
        photo_pairing.desempatar_por_contenido(p, drive_client.fetch_photo)
        for p in photo_pairing.pair_folder(fotos) if str(p["producto"]) == str(producto)
    ]
    if not pares:
        return {}
    start_job(
        job_id=f"carrusel_producto_{int(time.time())}", program="tiktok_shop_ai_pro",
        mode="replicar_carrusel_textos", title=f"Textos producto carrusel {carpeta}/{producto}",
        user=usuario or "ness",
    )
    try:
        textos = text_extractor.extract_from_pairs(
            pares, system_prompt=text_extractor._load_system_prompt(),
            fetch=drive_client.fetch_photo,
        )
    finally:
        try:
            finalize_and_persist()
        except Exception:  # noqa: BLE001
            pass
    return textos.get(str(producto)) or {}


def crear_producto(
    limpia: bytes, ficha: bytes, *, product_url: str, carrusel_url: str = "",
    nombre_limpia: str = "", nombre_ficha: str = "", usuario: str = "",
) -> dict:
    """Alta en «Carruseles virales» + textos + URL. Devuelve el producto."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import mis_productos
    from src.nicho_pov_bof.services import product_url as url_svc

    product_url = (product_url or "").strip()
    carrusel_url = (carrusel_url or "").strip()
    _validar_foto(limpia, nombre_limpia, "la foto del producto")
    _validar_foto(ficha, nombre_ficha, "la captura de la ficha")
    if not product_url or not _es_tiktok(product_url):
        raise ErrorReplica("Pega la URL del producto en TikTok Shop (tiktok.com/…).")
    if carrusel_url and "tiktok.com" not in carrusel_url:
        raise ErrorReplica("El enlace del carrusel viral tiene que ser de TikTok.")

    try:
        creado = mis_productos.guardar_producto(
            limpia, ficha, nombre_limpia=nombre_limpia, nombre_ficha=nombre_ficha, source=SOURCE,
        )
    except OSError as e:
        raise ErrorReplica(f"No se pudieron guardar las fotos: {e}", status=500) from e
    carpeta, producto = str(creado["carpeta"]), str(creado["producto"])
    try:
        product_repo.anadir_id_vigente(SOURCE, carpeta, producto)
    except Exception:  # noqa: BLE001 — las fotos ya están; esto es un apunte
        pass

    aviso = ""
    try:
        textos = extraer_textos(carpeta, producto, usuario)
    except Exception as e:  # noqa: BLE001 — el producto existe igual; se reintenta luego
        textos, aviso = {}, f"No se pudieron leer los textos de la ficha: {e}"
    if textos:
        product_repo.save_extracted_texts(SOURCE, carpeta, {producto: textos})
    elif not aviso:
        aviso = "Gemini no devolvió textos (¿cuota agotada o captura ilegible?). Reintenta con «Leer textos»."

    campos = {"product_url": product_url, "product_id": url_svc.id_desde_url(product_url),
              "creado_por": usuario or "ness"}
    if carrusel_url:
        campos["carrusel_url"] = carrusel_url
    prod = product_repo.update_product(SOURCE, carpeta, producto, **campos)
    if prod.get("titulo"):
        try:
            product_repo.guardar_url(prod, product_url)
        except Exception:  # noqa: BLE001 — `product_url` ya está en el documento
            pass
    return {**_fila(carpeta, producto, prod), "aviso": aviso}


def releer_textos(carpeta: str, producto: str, usuario: str = "") -> dict:
    """Reintenta la lectura de la ficha (si al dar de alta falló Gemini)."""
    from src.nicho_pov_bof.repos import product_repo

    textos = extraer_textos(carpeta, producto, usuario)
    if not textos:
        raise ErrorReplica("Gemini no devolvió textos de esa ficha.", status=502)
    product_repo.save_extracted_texts(SOURCE, carpeta, {str(producto): textos})
    prod = product_repo.get_product(SOURCE, carpeta, str(producto))
    if prod.get("product_url"):
        try:
            product_repo.guardar_url(prod, prod["product_url"])
        except Exception:  # noqa: BLE001
            pass
    return _fila(carpeta, str(producto), prod)


def guardar_carrusel_url(carpeta: str, producto: str, url: str) -> None:
    """Apunta en el producto el carrusel viral con el que se replicó (el último)."""
    from src.nicho_pov_bof.repos import product_repo

    if url:
        try:
            product_repo.update_product(SOURCE, carpeta, str(producto), carrusel_url=url)
        except Exception:  # noqa: BLE001
            pass


def _fila(carpeta: str, producto: str, prod: dict) -> dict:
    return {
        "source": SOURCE, "folder": carpeta, "producto": str(producto),
        "titulo": prod.get("titulo", ""), "tienda": prod.get("tienda", ""),
        "precio": prod.get("precio", ""), "product_url": prod.get("product_url", ""),
        "carrusel_url": prod.get("carrusel_url", ""), "creado_por": prod.get("creado_por", ""),
    }


def listar() -> list[dict]:
    """Todos los productos del catálogo (lo nuevo primero). Sin listar el
    Drive: los ids salen de `ids_vigentes`, que se apunta en el alta."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import mis_productos

    carpetas = mis_productos.carpetas(SOURCE)
    docs = product_repo.load_folders([(SOURCE, c) for c in carpetas])
    filas = []
    for carpeta, doc in zip(carpetas, docs):
        productos = doc.get("productos") or {}
        ids = {str(x) for x in (doc.get("ids_vigentes") or [])} | set(productos)
        for pid in sorted(ids, key=lambda x: (len(x), x)):
            filas.append(_fila(carpeta, pid, productos.get(pid) or {}))
    return list(reversed(filas))
