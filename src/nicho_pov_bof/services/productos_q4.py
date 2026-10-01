"""La carpeta «Productos Q4»: productos del Inventario elegidos para la campaña.

Black Friday y Navidad piden volver a grabar productos que ya están en el
catálogo, esta vez con un guion más largo y el ángulo de la temporada. Se
COPIAN aquí —las dos fotos y los textos ya extraídos— en vez de apuntar al
original, por lo mismo que "Top vendidos": el progreso se guarda por
*(fuente, carpeta, producto)*, así que un vídeo nuevo sobre el original pisaría
el guion y el vídeo que quizá ya se publicó. Como copia, todo lo suyo (guion,
clips, vídeo, subido, rehacer) es independiente y la carpeta se trabaja igual
que cualquier otra.

Vive DENTRO del Inventario General (`config.CATALOGO_Q4`) y con el mismo
convenio de nombres (`3.png` limpia / `3(1).png` ficha): el listado de carpetas
y el emparejado de fotos la tratan como una más sin una línea especial.

- **Números append-only.** Un número borrado no se recicla: el nuevo heredaría
  el progreso del viejo.
- **Los textos se copian, no se vuelven a extraer** (ya se pagaron). Se añade
  `segundos_guion` —la duración que se pide al guion— y `origen`, para saber de
  dónde salió cada uno.

Manifiesto en Redis (`q4:manifiesto`): `ref origen -> número`. Hace idempotente
añadir el mismo producto dos veces.
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
_MANIFIESTO = "q4:manifiesto"
SOURCE = config.CATALOGO_Q4
CARPETA = config.CARPETA_Q4


def _clave(carpeta: str) -> str:
    meta = config.CARPETAS_ESPECIALES.get(carpeta or CARPETA)
    if not meta:
        raise ValueError(f"Carpeta especial desconocida: {carpeta!r}. Válidas: {list(config.CARPETAS_ESPECIALES)}")
    return meta["manifiesto"]
# Campos de texto que viajan con el producto. `envio` y `plazos` son lo que
# la ficha deja PROMETER: sin ellos la copia cae al precio y el guion puede
# ofrecer envío gratis o plazos que el producto no tiene (promoción
# incoherente).
_CAMPOS = (
    "titulo", "titulo_tiktok_completo", "tienda", "caption",
    "emojis", "precio", "precio_lista", "product_url", "envio", "plazos",
)


def manifiesto(carpeta: str = CARPETA) -> dict[str, str]:
    """`{"<source>|<folder>|<producto>": "<número en la carpeta especial>"}`."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return {}
    return r.get_json(_clave(carpeta)) or {}


def _guardar_manifiesto(doc: dict, carpeta: str = CARPETA) -> None:
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede llevar la cuenta "
            "de qué productos ya están en Productos Q4."
        )
    if not r.set_json(_clave(carpeta), doc):
        raise RuntimeError("Redis no aceptó guardar el índice de Productos Q4.")


def _dir(carpeta: str = CARPETA) -> Path:
    d = config.dir_zip(SOURCE) / carpeta
    d.mkdir(parents=True, exist_ok=True)
    return d


def _siguiente_numero(destino: Path, manifiesto_doc: dict) -> int:
    """El mayor número usado (en disco o en el manifiesto) + 1."""
    en_disco = {
        int(m.group(1))
        for f in destino.iterdir()
        if f.is_file() and (m := re.match(r"(\d+)", f.name))
    }
    apuntados = {int(n) for n in manifiesto_doc.values() if str(n).isdigit()}
    return max(en_disco | apuntados, default=0) + 1


def anadir(
    refs: list[str], *, segundos_guion: float = 0, on_log: OnLog = _noop,
    carpeta: str = CARPETA,
) -> dict:
    """Copia a «Productos Q4» los productos `"<source>|<carpeta>|<producto>"`.

    Solo AÑADE: los que ya están (según el manifiesto) se devuelven en
    `ya_estaban` sin tocarlos. `segundos_guion` > 0 fija la duración del guion
    de los nuevos (24 = tres clips de 8s).
    """
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    doc = manifiesto(carpeta)
    destino = _dir(carpeta)
    añadidos: list[dict] = []
    ya_estaban: list[dict] = []
    omitidos: list[dict] = []
    pares_por_carpeta: dict[tuple[str, str], dict] = {}

    def _par(source: str, folder: str, producto: str) -> dict:
        clave = (source, folder)
        if clave not in pares_por_carpeta:
            fotos = [
                drive_client.probe_dimensions(f)
                for f in drive_client.list_photos(source, folder)
            ]
            pares_por_carpeta[clave] = {
                str(x.get("producto")): x for x in photo_pairing.pair_folder(fotos)
            }
        return pares_por_carpeta[clave].get(str(producto)) or {}

    for ref in refs:
        partes = str(ref).split("|")
        if len(partes) != 3 or not all(partes):
            omitidos.append({"ref": ref, "motivo": "formato: <catálogo>|<carpeta>|<producto>"})
            continue
        source, folder, producto = partes
        if config.es_carpeta_especial(folder):
            omitidos.append({"ref": ref, "motivo": "ya es una copia de una carpeta especial"})
            continue
        if ref in doc:
            ya_estaban.append({"ref": ref, "producto": str(doc[ref])})
            continue
        try:
            par = _par(source, folder, producto)
        except Exception as e:  # noqa: BLE001 — una carpeta ilegible no para las demás
            omitidos.append({"ref": ref, "motivo": f"no pude leer su carpeta ({e})"})
            continue
        limpia = (par.get("clean") or {}).get("id") or ""
        ficha = (par.get("titled") or {}).get("id") or ""
        if not limpia:
            omitidos.append({"ref": ref, "motivo": "no encuentro su foto limpia"})
            continue

        numero = str(_siguiente_numero(destino, doc))
        copiadas: list[Path] = []
        try:
            for foto_id, sufijo in ((limpia, ""), (ficha, "(1)")):
                if not foto_id:
                    continue
                local = drive_client.fetch_photo(foto_id, suffix=".jpg")
                ext = Path(str(local)).suffix.lower()
                ext = ext if ext in _EXTS else ".jpg"
                final = destino / f"{numero}{sufijo}{ext}"
                shutil.copy2(local, final)
                copiadas.append(final)
        except Exception as e:  # noqa: BLE001
            # Sin las dos fotos el número quedaría a medias: se deshace.
            for f in copiadas:
                f.unlink(missing_ok=True)
            omitidos.append({"ref": ref, "motivo": f"no pude copiar sus fotos ({e})"})
            continue

        origen = product_repo.get_product(source, folder, producto)
        textos = {k: origen.get(k, "") for k in _CAMPOS if origen.get(k)}
        if origen.get("sin_stock"):
            textos["sin_stock"] = True
        textos["origen"] = ref
        if segundos_guion and segundos_guion > 0:
            textos["segundos_guion"] = float(segundos_guion)
        product_repo.save_extracted_texts(SOURCE, carpeta, {numero: textos})

        doc[ref] = numero
        _guardar_manifiesto(doc, carpeta)
        añadidos.append({"ref": ref, "producto": numero, "titulo": textos.get("titulo", "")})
        on_log(f"[especial] {ref} → {carpeta} #{numero}")

    _invalidar(carpeta)
    return {
        "carpeta": carpeta, "añadidos": añadidos, "ya_estaban": ya_estaban,
        "omitidos": omitidos, "total": len(doc),
    }


def _invalidar(carpeta: str = CARPETA) -> None:
    """Tras copiar, los listados cacheados (carpetas y fotos) ya no valen."""
    from src.nicho_pov_bof.services import drive_client, productos_web

    productos_web._invalidar()
    try:
        drive_client.list_product_folders(SOURCE, refresh=True)
        drive_client.list_photos(SOURCE, carpeta, refresh=True)
    except Exception:  # noqa: BLE001
        pass


def recopiar_promesas(carpeta: str = CARPETA) -> dict[str, dict]:
    """Vuelve a traer `envio`, `plazos` y `sin_stock` del original a cada copia.

    Para las copias hechas antes de que esos campos viajaran con el producto.
    """
    from src.nicho_pov_bof.repos import product_repo

    salida: dict[str, dict] = {}
    for ref, numero in manifiesto(carpeta).items():
        partes = ref.split("|")
        if len(partes) != 3:
            continue
        origen = product_repo.get_product(*partes)
        campos = {k: origen[k] for k in ("envio", "plazos") if origen.get(k)}
        campos["sin_stock"] = bool(origen.get("sin_stock"))
        salida[str(numero)] = campos
    if salida:
        product_repo.save_extracted_texts(SOURCE, carpeta, salida)
    return salida
