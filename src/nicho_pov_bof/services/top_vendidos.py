"""La cuarta fuente: los productos que YA vendieron, juntos para regrabarlos.

Es una fuente como "1 Prod Aleatorios", solo que sus productos no salen de un
Drive de un tercero sino del ranking de vendidos: se copian aquí las dos fotos
del producto y sus textos ya extraídos, de diez en diez, y a partir de ahí se
comporta igual que cualquier otra carpeta en TODOS los nichos (POV BOF, POV BOF
Largo, Creativos Pro…). Por eso vive en el Drive MONTADO con el mismo convenio
de nombres (`3.png` limpia / `3(1).png` ficha) y no necesita ni una línea
especial más allá de este fichero.

Dos decisiones que conviene no deshacer:

- **El sitio de un producto no cambia nunca.** Entra en el primer hueco libre y
  ahí se queda aunque luego venda más. Reordenar por ventas movería el producto
  de carpeta, y el progreso (subido, clips, guion, escaparate) se guarda por
  *(fuente, carpeta, producto)*: al moverlo se perdería todo y habría que
  regrabarlo. El orden por ventas se hace al PINTAR, que no cuesta nada.
- **Los textos se copian, no se vuelven a extraer.** El producto ya pasó por
  Gemini en su carpeta de origen; volver a pedirlos sería pagar dos veces por
  el mismo dato y encima podrían salir distintos.

Manifiesto en Redis (`top_vendidos:manifiesto`): `ref origen -> {carpeta,
producto}`. Es lo que hace la sincronización idempotente y lo que permite saber
de dónde vino cada uno (para sumarle las ventas al original en vez de crear una
entrada nueva en el ranking).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MANIFIESTO = "top_vendidos:manifiesto"
SOURCE = "top_vendidos"


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------
def manifiesto() -> dict[str, dict]:
    """`{"<source>|<folder>|<producto>": {"carpeta": ..., "producto": ...}}`."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return {}
    return r.get_json(_MANIFIESTO) or {}


def _guardar_manifiesto(doc: dict) -> None:
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede llevar la "
            "cuenta de qué productos ya están en Top vendidos."
        )
    if not r.set_json(_MANIFIESTO, doc):
        raise RuntimeError("Redis no aceptó guardar el índice de Top vendidos.")


def origen_de(carpeta: str, producto: str) -> dict | None:
    """De qué producto del Drive del curso salió este. `None` si no consta.

    Lo usa el botón "Vendió": la venta se le suma a la entrada de ORIGEN, que
    es la que está en el ranking. Si se apuntara aquí, el mismo producto
    contaría dos veces.
    """
    for ref, sitio in manifiesto().items():
        if sitio.get("carpeta") == carpeta and str(sitio.get("producto")) == str(producto):
            partes = ref.split("|")
            if len(partes) == 3:
                return {"source": partes[0], "folder": partes[1], "producto": partes[2]}
    return None


def ventas_por_producto(source: str, usuario: str = "") -> dict[str, dict]:
    """`{"<carpeta>|<producto>": {ventas, vendido_at}}` de esta fuente.

    Las ventas viven en el ranking, bajo la carpeta de ORIGEN, así que hay que
    cruzarlas por el manifiesto. Se hace una vez por listado (dos lecturas de
    Redis) y lo usan los tres nichos, que enseñan lo mismo.

    Fuera de "Top vendidos" devuelve `{}`: en las demás fuentes no hay nada que
    cruzar y así el caller puede llamarlo siempre sin preguntar.
    """
    if source != SOURCE:
        return {}
    from src.nicho_pov_bof.repos import product_repo

    ranking = {
        f"{v.get('source')}|{v.get('folder')}|{v.get('producto')}": v
        for v in product_repo.ranking_vendidos(usuario=usuario)
    }
    salida: dict[str, dict] = {}
    for ref, sitio in manifiesto().items():
        v = ranking.get(ref) or {}
        clave = f"{sitio.get('carpeta')}|{sitio.get('producto')}"
        # Ventas apuntadas AQUÍ y no al original. No debería pasar (ver
        # `product_repo._ref_vendido`), pero las que se marcaron antes de
        # arreglarlo existen y se perderían: se suman, que cada una es una
        # venta de verdad.
        propia = ranking.get(f"{SOURCE}|{clave}") or {}
        salida[clave] = {
            "ventas": int(v.get("unidades") or 0) + int(propia.get("unidades") or 0),
            "vendido_at": max(
                float(v.get("vendido_at") or 0), float(propia.get("vendido_at") or 0),
            ),
        }
    return salida


def recopiar_textos(carpeta: str, *, on_log: OnLog = _noop) -> dict[str, dict]:
    """Vuelve a traer los textos del producto de ORIGEN de cada copia.

    Los productos de aquí ya pasaron por Gemini en su carpeta del curso, así
    que volver a leer sus capturas no solo es pagar dos veces: es arriesgarse a
    que el modelo cruce los textos entre imágenes de una tanda y la carpeta
    entera quede desplazada (pasó: un producto con el título de otro). Con el
    manifiesto sabemos de dónde vino cada uno y basta con copiar.
    """
    from src.nicho_pov_bof.repos import product_repo

    campos = (
        "titulo", "titulo_tiktok_completo", "tienda", "caption",
        "emojis", "precio", "precio_lista", "product_url",
    )
    salida: dict[str, dict] = {}
    for ref, sitio in manifiesto().items():
        if sitio.get("carpeta") != carpeta:
            continue
        partes = ref.split("|")
        if len(partes) != 3:
            continue
        origen = product_repo.get_product(partes[0], partes[1], partes[2])
        textos = {k: origen.get(k, "") for k in campos if origen.get(k)}
        if textos:
            salida[str(sitio.get("producto"))] = textos
    on_log(f"[top_vendidos] textos recopiados del origen: {len(salida)} producto(s)")
    return salida


def reparar_carpeta(carpeta: str, *, on_log: OnLog = _noop) -> dict:
    """Vuelve a copiar FOTOS y textos del original en toda una carpeta.

    `recopiar_textos` arregla los textos, pero si lo que se copió mal fue la
    foto no hay texto que valga: se veía una tumbona con el nombre de una silla
    gaming. Esto rehace las dos cosas desde el producto de origen, que es la
    única fuente fiable, y de paso dice qué productos de la carpeta no constan
    en el manifiesto (esos no se pueden reparar solos).
    """
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    destino = config.top_vendidos_dir() / carpeta
    if not destino.is_dir():
        raise ValueError(f"No existe la carpeta {carpeta!r} en Top vendidos.")

    doc = manifiesto()
    mios = {
        str(sitio.get("producto")): ref
        for ref, sitio in doc.items() if sitio.get("carpeta") == carpeta
    }
    fotos_ok = textos_ok = 0
    fallos: list[str] = []

    for numero, ref in sorted(mios.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        partes = ref.split("|")
        if len(partes) != 3:
            continue
        source, folder, producto = partes
        try:
            pares = photo_pairing.pair_folder([
                drive_client.probe_dimensions(f)
                for f in drive_client.list_photos(source, folder)
            ])
            par = next((x for x in pares if str(x.get("producto")) == producto), None)
            limpia = (par or {}).get("clean") or {}
            ficha = (par or {}).get("titled") or {}
            if not limpia.get("id"):
                fallos.append(f"{numero}: el original ya no tiene foto limpia")
            else:
                # Se borra lo que hubiera con ese número antes de copiar: si la
                # extensión cambia (.png → .jpg) quedarían las dos y el
                # emparejado volvería a elegir mal.
                for viejo in destino.glob(f"{numero}.*"):
                    viejo.unlink(missing_ok=True)
                for viejo in destino.glob(f"{numero}(1).*"):
                    viejo.unlink(missing_ok=True)
                for foto_id, sufijo in ((limpia.get("id"), ""), (ficha.get("id"), "(1)")):
                    if not foto_id:
                        continue
                    local = drive_client.fetch_photo(foto_id, suffix=".jpg")
                    ext = Path(str(local)).suffix.lower()
                    ext = ext if ext in _EXTS else ".jpg"
                    shutil.copy2(local, destino / f"{numero}{sufijo}{ext}")
                fotos_ok += 1
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{numero}: no pude copiar sus fotos ({e})")

        origen = product_repo.get_product(source, folder, producto)
        textos = {
            k: origen.get(k, "")
            for k in (
                "titulo", "titulo_tiktok_completo", "tienda", "caption",
                "emojis", "precio", "precio_lista", "product_url",
            )
            if origen.get(k)
        }
        if textos:
            product_repo.save_extracted_texts(SOURCE, carpeta, {numero: textos})
            textos_ok += 1

    # Productos que están en la carpeta pero no en el manifiesto: se copiaron
    # antes de que existiera o se metieron a mano, y no hay original al que
    # mirar. Se avisa en vez de dejarlos torcidos en silencio.
    en_disco = {
        m.group(1)
        for f in destino.iterdir()
        if f.is_file() and (m := re.match(r"(\d+)", f.name))
    }
    huerfanos = sorted(en_disco - set(mios), key=lambda x: int(x))
    if huerfanos:
        fallos.append(
            "sin original conocido (no se pueden reparar): " + ", ".join(huerfanos)
        )

    on_log(
        f"[top_vendidos] reparada {carpeta}: {fotos_ok} fotos y {textos_ok} textos "
        f"del original · {len(fallos)} aviso(s)"
    )
    _invalidar()
    try:
        drive_client.list_photos(SOURCE, carpeta, refresh=True)
    except Exception:  # noqa: BLE001
        pass
    return {"fotos": fotos_ok, "textos": textos_ok, "avisos": fallos[:10]}


def pendientes(usuario: str = "") -> int:
    """Cuántos productos del ranking aún no están en la carpeta.

    Es una resta de dos lecturas de Redis, sin tocar Drive: se pide en cada
    carga de la pantalla para poder avisar de que hay algo que traer, y si
    costara un listado del Drive no se podría.
    """
    from src.nicho_pov_bof.repos import product_repo

    doc = manifiesto()
    return sum(
        1 for v in product_repo.ranking_vendidos(usuario=usuario)
        if f"{v.get('source')}|{v.get('folder')}|{v.get('producto')}" not in doc
        and v.get("source") != SOURCE
    )


# ---------------------------------------------------------------------------
# Carpetas en disco (mismo shape que `drive_client`)
# ---------------------------------------------------------------------------
def _num_carpeta(nombre: str) -> int:
    m = re.search(r"(\d+)\s*$", nombre or "")
    return int(m.group(1)) if m else 0


def carpetas() -> list[str]:
    raiz = config.top_vendidos_dir()
    return sorted(
        (d.name for d in raiz.iterdir() if d.is_dir()),
        key=_num_carpeta,
    )


def listar_carpetas_como_drive() -> list[dict]:
    """Mismo shape que `drive_client.list_product_folders`."""
    return [{"name": c, "id": c} for c in carpetas()]


def listar_fotos_como_drive(carpeta: str) -> list[dict]:
    """Mismo shape que `drive_client.list_photos`.

    El `id` es la RUTA del fichero, igual que en "Mis productos": aquí no hay
    id de Google y la ruta es igual de única. `fetch_photo` ya lo entiende.
    """
    d = config.top_vendidos_dir() / carpeta
    if not d.is_dir():
        return []
    fotos = [
        {
            # El id lleva pegada la fecha del fichero. Es lo que permite
            # cachear la foto un día entero en el móvil sin arriesgarse a ver
            # una vieja: al regrabar o sustituir la foto cambia el mtime, con
            # él cambia la URL, y el navegador la pide de nuevo. Sin esto había
            # que servirlas con `no-cache` y se volvían a bajar en cada scroll
            # (las del curso vuelan porque su id de Google no cambia nunca).
            "id": f"{f}#{int(f.stat().st_mtime)}",
            "name": f.name,
            "size": f.stat().st_size,
            "mime": f"image/{f.suffix.lstrip('.').replace('jpg', 'jpeg')}",
        }
        for f in d.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS
    ]
    fotos.sort(key=lambda x: config.natural_sort_key(x["name"]))
    return fotos


def _siguiente_hueco() -> tuple[str, str]:
    """Carpeta y número donde va el próximo producto.

    Append-only: se mira el MAYOR número usado, no los huecos. Si se reciclara
    un hueco de un producto borrado, el nuevo heredaría el progreso del viejo
    (que se guarda por número de producto) y aparecería como ya subido.
    """
    existentes = carpetas()
    ultima = existentes[-1] if existentes else ""
    if ultima:
        usados = {
            int(m.group(1))
            for f in (config.top_vendidos_dir() / ultima).iterdir()
            if f.is_file() and (m := re.match(r"(\d+)", f.name))
        }
        siguiente = max(usados, default=0) + 1
        if siguiente <= config.MIS_PRODUCTOS_POR_CARPETA:
            return ultima, str(siguiente)
    nueva = f"{config.TOP_VENDIDOS_PREFIJO} {_num_carpeta(ultima) + 1}"
    (config.top_vendidos_dir() / nueva).mkdir(parents=True, exist_ok=True)
    return nueva, "1"


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------
def sincronizar(*, usuario: str = "", on_log: OnLog = _noop) -> dict:
    """Mete en Top vendidos los productos del ranking que aún no estén.

    Solo AÑADE. Un producto ya copiado no se toca aunque haya vendido más
    veces: su sitio es fijo (ver la cabecera del módulo).
    """
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    # El ranking es de QUIEN sincroniza: las ventas son suyas (ver
    # `product_repo._key_vendidos_index`). La carpeta de Top vendidos en Drive
    # sí es común — es un catálogo, no un progreso.
    ranking = product_repo.ranking_vendidos(usuario=usuario)
    doc = manifiesto()
    # De más vendido a menos, para que los primeros en entrar sean los mejores
    # (el orden de entrada es lo único que fija el sitio).
    pendientes = [
        v for v in ranking
        if f"{v.get('source')}|{v.get('folder')}|{v.get('producto')}" not in doc
        and v.get("source") != SOURCE
    ]
    if not pendientes:
        return {
            "añadidos": 0, "total": len(doc), "carpetas": len(carpetas()), "omitidos": [],
        }

    # Los que no se pueden copiar se DEVUELVEN, no solo se loguean: si no, el
    # botón sigue diciendo "traer 1 producto nuevo" para siempre y el producto
    # no aparece nunca en la lista sin que nadie sepa por qué.
    omitidos: list[dict] = []

    # Emparejar cuesta un listado por carpeta de origen; se hace UNA vez por
    # carpeta aunque tenga varios productos vendidos.
    pares_por_carpeta: dict[tuple[str, str], dict] = {}

    def _par(source: str, folder: str, producto: str) -> dict:
        clave = (source, folder)
        if clave not in pares_por_carpeta:
            try:
                fotos = [
                    drive_client.probe_dimensions(f)
                    for f in drive_client.list_photos(source, folder)
                ]
                pares_por_carpeta[clave] = {
                    str(x.get("producto")): x for x in photo_pairing.pair_folder(fotos)
                }
            except Exception as e:
                on_log(f"[top_vendidos] no pude leer {source}/{folder}: {e}")
                pares_por_carpeta[clave] = {}
        return pares_por_carpeta[clave].get(str(producto)) or {}

    añadidos = 0
    for v in pendientes:
        source, folder = str(v.get("source")), str(v.get("folder"))
        producto = str(v.get("producto"))
        ref = f"{source}|{folder}|{producto}"
        par = _par(source, folder, producto)
        limpia = (par.get("clean") or {}).get("id") or v.get("clean_photo_id") or ""
        ficha = (par.get("titled") or {}).get("id") or ""
        if not limpia:
            on_log(f"[top_vendidos] {ref}: sin foto limpia, lo dejo fuera")
            omitidos.append({
                "producto": v.get("titulo") or ref,
                "motivo": "no encuentro su foto limpia en la carpeta de origen",
            })
            continue

        carpeta, numero = _siguiente_hueco()
        destino = config.top_vendidos_dir() / carpeta
        try:
            for foto_id, sufijo in ((limpia, ""), (ficha, "(1)")):
                if not foto_id:
                    continue
                local = drive_client.fetch_photo(foto_id, suffix=".jpg")
                ext = Path(str(local)).suffix.lower()
                ext = ext if ext in _EXTS else ".jpg"
                shutil.copy2(local, destino / f"{numero}{sufijo}{ext}")
        except Exception as e:
            on_log(f"[top_vendidos] {ref}: no pude copiar las fotos ({e})")
            omitidos.append({
                "producto": v.get("titulo") or ref,
                "motivo": f"no pude copiar sus fotos ({e})",
            })
            continue

        # Los textos ya extraídos viajan con el producto: nada de volver a
        # pasar Gemini por algo que ya se pagó.
        origen = product_repo.get_product(source, folder, producto)
        textos = {
            k: origen.get(k, "")
            for k in (
                "titulo", "titulo_tiktok_completo", "tienda", "caption",
                "emojis", "precio", "precio_lista", "product_url",
            )
            if origen.get(k)
        }
        if textos:
            product_repo.save_extracted_texts(SOURCE, carpeta, {numero: textos})

        doc[ref] = {"carpeta": carpeta, "producto": numero}
        _guardar_manifiesto(doc)
        añadidos += 1
        on_log(f"[top_vendidos] {ref} → {carpeta} #{numero}")

    _invalidar()
    return {
        "añadidos": añadidos, "total": len(doc), "carpetas": len(carpetas()),
        "omitidos": omitidos[:10],
    }


def _invalidar() -> None:
    """Tras copiar hay carpetas nuevas; el listado cacheado ya no vale."""
    from src.nicho_pov_bof.services import drive_client

    try:
        drive_client.list_product_folders(SOURCE, refresh=True)
    except Exception:
        pass
