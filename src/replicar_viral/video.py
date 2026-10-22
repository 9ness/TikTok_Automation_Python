"""«Replicar virales» (vídeo): el MP4 YA MONTADO de la réplica de un viral.

No es `servicio.replicar` (que solo escribe el guion y los prompts de dos
clips mudos para montarlos en el POV BOF Largo): aquí el agente replica el
viral por su cuenta y lo que llega es el vídeo terminado. Dos modos:

- `con_ia`: clips generados con IA (Omni de GenAI Pro, 10 s, con la foto del
  producto como ingrediente), encuadre anti-marca, rótulo y metadatos limpios.
- `genjutsu`: igual que `con_ia` pero el viral entero rehecho con Genjutsu de
  Higgsfield (cambio de producto sobre el vídeo original). Cuenta como Viral.
- `sin_ia`: vídeo real (grabado) o montaje sin IA del viral con nuestro
  producto.

Se registra con el título del producto y su enlace de TikTok Shop y sale solo
en «Mis tandas» (fila `rv|<id>`) con descargar, subido, sin stock, rehacer,
semáforo y época. El documento vive con las demás réplicas
(`replicar_viral:<id>`, `tipo="video"`) pero en un índice PROPIO
(`replicar_viral:videos:<usuario>`): el general tiene tope de 200 y se lo
comparten guiones y carruseles. El MP4 va al Drive montado,
`TIKTOK_SHOP_AI_PRO/Replicar_Viral/<usuario>/<id>.mp4` (nunca a
`api_uploads/`, que se purga).

Opcional: `catalogo`/`carpeta`/`producto_ref` atan la réplica a un producto de
los catálogos del operador (`catalogo_ref`). Con eso, al marcarla subida en Mis
tandas cuenta en el contador por formato de ese producto (con_ia y
genjutsu = viral, sin_ia = físico; `nicho_pov_bof/services/marcas.py`).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from src.replicar_viral import servicio
from src.replicar_viral.servicio import ErrorReplica

RAIZ_DRIVE = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Replicar_Viral"
INDICE_VIDEOS = "replicar_viral:videos:{usuario}"
TIPO = "video"
MODOS: dict[str, str] = {
    "con_ia": "🤖 Con IA (Omni)",
    "genjutsu": "🌀 Con IA (Genjutsu)",
    "sin_ia": "🎥 Sin IA (real)",
}
EXT_VIDEO = (".mp4", ".mov", ".m4v")
MAX_INDICE = 2000
_ID = re.compile(r"[a-f0-9]{12}")
_PRODUCTO_ID = re.compile(r"/product/(\d{6,})")


# ---------------------------------------------------------------------------
# Disco
# ---------------------------------------------------------------------------
def _raiz() -> Path:
    from src.nicho_pov_bof.services.audio_bank import mount_root

    m = mount_root()
    return m / RAIZ_DRIVE if m else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "replicar_viral_videos"


def ruta_video(usuario: str, id_: str) -> Path:
    if not _ID.fullmatch(id_ or ""):
        raise ErrorReplica("Id de réplica inválido.", status=404)
    return _raiz() / (usuario or "ness") / f"{id_}.mp4"


def _es_video(cabecera: bytes) -> bool:
    """MP4/MOV: la caja `ftyp` va en los bytes 4-8 (o `moov`/`wide`/`mdat`
    en algunos MOV viejos)."""
    return len(cabecera) >= 12 and cabecera[4:8] in (b"ftyp", b"moov", b"wide", b"mdat", b"free")


def _copiar(origen: Path, destino: Path) -> None:
    with open(origen, "rb") as f:
        if not _es_video(f.read(16)):
            raise ErrorReplica("Eso no es un MP4/MOV.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".part")
    shutil.copyfile(origen, tmp)
    tmp.replace(destino)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
def product_url_de(product_id: str = "", product_url: str = "") -> tuple[str, str]:
    """(product_id, product_url) normalizados: con uno de los dos basta."""
    pid = re.sub(r"\D", "", str(product_id or ""))
    url = (product_url or "").strip()
    if not pid and url:
        m = _PRODUCTO_ID.search(url)
        pid = m.group(1) if m else ""
    if pid:
        url = f"https://www.tiktok.com/view/product/{pid}"
    elif url and "tiktok.com" not in url:
        raise ErrorReplica("El enlace del producto tiene que ser de TikTok Shop (tiktok.com/…/product/<id>).")
    return pid, url


def _lista_txt(x, tope: int = 30, largo: int = 4000) -> list[str]:
    if isinstance(x, str):
        x = [x] if x.strip() else []
    return [str(i).strip()[:largo] for i in (x or []) if str(i).strip()][:tope]


def _hashtags(x) -> list[str]:
    if isinstance(x, str):
        x = re.split(r"[\s,]+", x)
    salida: list[str] = []
    for h in x or []:
        h = str(h).strip().lstrip("#")
        if h and f"#{h}" not in salida:
            salida.append(f"#{h}")
    return salida[:15]


def _indexar(usuario: str, id_: str, quitar: bool = False) -> None:
    r = servicio._redis()
    if not r.is_available():
        return
    clave = INDICE_VIDEOS.format(usuario=usuario or "ness")
    ids = [i for i in ((r.get_json(clave) or {}).get("ids") or []) if i != id_]
    if not quitar:
        ids = [id_] + ids
    r.set_json(clave, {"ids": ids[:MAX_INDICE], "updated_at": time.time()})


def ver(usuario: str, id_: str) -> dict:
    doc = servicio.ver(usuario or "ness", id_)
    if doc.get("tipo") != TIPO:
        raise ErrorReplica("Esa réplica no es un vídeo montado.", status=404)
    return doc


def registrar(
    usuario: str, *, modo: str, origen: Path, titulo: str, url_viral: str = "",
    product_id: str = "", product_url: str = "", tienda: str = "", caption: str = "",
    hashtags=None, prompts=None, notas: str = "", replica_id: str = "",
    catalogo: str = "", carpeta: str = "", producto_ref: str = "",
) -> dict:
    """Guarda el MP4 montado de una réplica. Con `replica_id` REEMPLAZA el
    vídeo de esa réplica (rehecho): sube su `video_listo_at` y quita el
    «rehacer», así sale de su tanda y entra en una nueva (como en los nichos)."""
    usuario = usuario or "ness"
    ahora = time.time()
    ref = catalogo_ref(catalogo, carpeta, producto_ref)
    if replica_id:
        doc = ver(usuario, replica_id)
        if modo and modo not in MODOS:
            raise ErrorReplica(f"Modo «{modo}» no vale: {', '.join(MODOS)}.")
        if modo:
            doc["modo"] = modo
        prod = doc.setdefault("producto", {})
        if titulo:
            prod["titulo"] = " ".join(titulo.split())[:200]
        if tienda:
            prod["tienda"] = tienda.strip()[:120]
        if product_id or product_url:
            prod["product_id"], prod["product_url"] = product_url_de(product_id, product_url)
        if url_viral:
            doc["url"] = url_viral.strip()
        if caption:
            doc["caption"] = caption.strip()[:2200]
        if hashtags:
            doc["hashtags"] = _hashtags(hashtags)
        if prompts:
            doc["prompts"] = _lista_txt(prompts)
        if notas:
            doc["notas"] = notas.strip()[:2000]
        if ref:
            doc["catalogo_ref"] = ref
        destino = ruta_video(usuario, doc["id"])
        _copiar(origen, destino)
        doc.update({"video_path": str(destino), "video_listo_at": ahora, "rehacer": False,
                    "rehacer_nota": "", "rehecho": True, "actualizado_at": ahora})
        servicio.guardar(doc, indexar=False)
        _indexar(usuario, doc["id"])
        return doc

    if modo not in MODOS:
        raise ErrorReplica(f"Modo «{modo}» no vale: {', '.join(MODOS)}.")
    titulo = " ".join((titulo or "").split())[:200]
    if not titulo:
        raise ErrorReplica("Falta el título del producto (el que se quema en el vídeo y va al caption).")
    pid, purl = product_url_de(product_id, product_url)
    id_ = uuid.uuid4().hex[:12]
    destino = ruta_video(usuario, id_)
    _copiar(origen, destino)
    doc = {
        "id": id_, "tipo": TIPO, "usuario": usuario, "modo": modo,
        "creado_at": ahora, "video_listo_at": ahora,
        "url": (url_viral or "").strip(),
        "producto": {"titulo": titulo, "tienda": (tienda or "").strip()[:120],
                     "product_id": pid, "product_url": purl},
        "caption": (caption or "").strip()[:2200], "hashtags": _hashtags(hashtags),
        "prompts": _lista_txt(prompts), "notas": (notas or "").strip()[:2000],
        "video_path": str(destino),
        "uploaded": False, "uploaded_at": 0.0, "sin_stock": False,
        "rehacer": False, "rehacer_nota": "", "rehecho": False,
    }
    if ref:
        doc["catalogo_ref"] = ref
    servicio.guardar(doc, indexar=False)
    _indexar(usuario, id_)
    return doc


def catalogo_ref(catalogo: str = "", carpeta: str = "", producto: str = "") -> dict | None:
    """El producto del catálogo del operador al que pertenece la réplica, o
    None si no se dice. A medias (falta alguno) o de otro catálogo = error."""
    from src.nicho_pov_bof.services import marcas

    partes = [str(x or "").strip() for x in (catalogo, carpeta, producto)]
    if not any(partes):
        return None
    if not all(partes):
        raise ErrorReplica("Para atar la réplica a un producto hacen falta catalogo, carpeta y producto_ref.")
    if partes[0] not in marcas.FUENTES_MARCAS:
        raise ErrorReplica(f"Catálogo «{partes[0]}» no vale: {', '.join(marcas.FUENTES_MARCAS)}.")
    return {"source": partes[0], "folder": partes[1], "producto": partes[2]}


def ruta_bandeja(usuario: str, ruta_rel: str) -> Path:
    """La ruta relativa a la bandeja del agente
    (`TIKTOK_SHOP_AI_PRO/_agente/<usuario>/`), sin salirse de ella."""
    from src.agente_mcp import config as agente_config

    base = agente_config.bandeja_dir(usuario or "ness").resolve()
    rel = (ruta_rel or "").strip().lstrip("/")
    if not rel:
        raise ErrorReplica("Falta la ruta del vídeo dentro de la bandeja.")
    p = (base / rel).resolve()
    if base not in p.parents:
        raise ErrorReplica("Esa ruta está fuera de tu bandeja.", status=403)
    if p.suffix.lower() not in EXT_VIDEO:
        raise ErrorReplica("En la bandeja tiene que ser un .mp4 o .mov.")
    if not p.is_file():
        raise ErrorReplica(f"No está en la bandeja: {rel}", status=404)
    return p


def desde_bandeja(usuario: str, ruta_rel: str, **kw) -> dict:
    return registrar(usuario, origen=ruta_bandeja(usuario, ruta_rel), **kw)


def listar(usuario: str, modo: str = "") -> list[dict]:
    """Las réplicas en vídeo del usuario, lo último primero."""
    r = servicio._redis()
    if not r.is_available():
        return []
    ids = (r.get_json(INDICE_VIDEOS.format(usuario=usuario or "ness")) or {}).get("ids") or []
    claves = [servicio.CLAVE.format(id=i) for i in ids]
    docs = r.mget_json(claves) if hasattr(r, "mget_json") else [r.get_json(c) for c in claves]
    salida = []
    for d in docs:
        if not isinstance(d, dict) or d.get("tipo") != TIPO or d.get("usuario") != (usuario or "ness"):
            continue
        if modo and d.get("modo") != modo:
            continue
        salida.append(d)
    return salida


def resumen(doc: dict) -> dict:
    """Lo que enseña la lista (sin prompts largos)."""
    prod = doc.get("producto") or {}
    return {
        "id": doc.get("id", ""), "tipo": TIPO, "modo": doc.get("modo", ""),
        "modo_label": MODOS.get(doc.get("modo", ""), doc.get("modo", "")),
        "creado_at": doc.get("creado_at", 0), "video_listo_at": doc.get("video_listo_at", 0),
        "url": doc.get("url", ""), "titulo": prod.get("titulo", ""), "tienda": prod.get("tienda", ""),
        "product_id": prod.get("product_id", ""), "product_url": prod.get("product_url", ""),
        "caption": doc.get("caption", ""), "hashtags": doc.get("hashtags") or [],
        "prompts": len(doc.get("prompts") or []), "notas": doc.get("notas", ""),
        "uploaded": bool(doc.get("uploaded")), "sin_stock": bool(doc.get("sin_stock")),
        "rehacer": bool(doc.get("rehacer")), "rehacer_nota": doc.get("rehacer_nota", ""),
        "rehecho": bool(doc.get("rehecho")),
        "catalogo_ref": doc.get("catalogo_ref") or None,
        "id_tandas": f"rv|{doc.get('id', '')}",
        "existe": Path(doc.get("video_path") or "").is_file(),
    }


def borrar(usuario: str, id_: str) -> dict:
    doc = ver(usuario, id_)
    r = servicio._redis()
    if r.is_available():
        r.delete(servicio.CLAVE.format(id=id_))
    _indexar(usuario, id_, quitar=True)
    try:
        Path(doc.get("video_path") or ruta_video(usuario, id_)).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True, "id": id_}


def marcar(
    usuario: str, id_: str, *, uploaded: bool | None = None, sin_stock: bool | None = None,
    rehacer: bool | None = None, rehacer_nota: str | None = None,
) -> dict:
    """Subido / sin stock / rehacer, en el documento de la réplica (lo usan
    los botones de «Mis tandas»). Devuelve los campos cambiados."""
    doc = ver(usuario, id_)
    cambios: dict = {}
    if uploaded is not None:
        cambios["uploaded"] = bool(uploaded)
        cambios["uploaded_at"] = time.time() if uploaded else 0.0
    if sin_stock is not None:
        cambios["sin_stock"] = bool(sin_stock)
    if rehacer is not None:
        cambios["rehacer"] = bool(rehacer)
        cambios["rehacer_nota"] = (rehacer_nota or "").strip()[:300] if rehacer else ""
    if cambios:
        doc.update(cambios)
        servicio.guardar(doc, indexar=False)
    return cambios


def fotograma(doc: dict) -> Path | None:
    """Un fotograma del vídeo (a 1 s) para la miniatura, cacheado por versión."""
    from src.mis_tandas import config as mt_config

    origen = Path(doc.get("video_path") or "")
    if not origen.is_file():
        return None
    destino = Path(mt_config.cache_dir()) / f"rv_{doc.get('id')}_{int(doc.get('video_listo_at') or 0)}.jpg"
    if destino.is_file() and destino.stat().st_size > 0:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(origen), "-frames:v", "1",
                        "-vf", "scale=480:-2", str(destino)], check=True, timeout=60)
    except Exception:  # noqa: BLE001 — sin miniatura la fila sale igual
        return None
    return destino if destino.is_file() and destino.stat().st_size > 0 else None
