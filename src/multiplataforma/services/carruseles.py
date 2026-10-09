"""Publicar en IG/FB/Threads/Pinterest los carruseles de «Replicar carrusel».

- `encolar(slug, carrusel_id, ...)`: copia las fotos del carrusel (con su
  texto quemado, o la de Flow si no lleva) a
  `Multiplataforma/<cuenta>/carruseles/<id>/NN.jpg` + su versión 4:5 para
  Instagram (`ig/NN.jpg`: IG rechaza 3:4 y 9:16), y encola UNA publicación
  `tipo="carrusel"` a la hora «carrusel» de la cuenta (17:00 por defecto,
  con el desfase de siempre), tras lo ya programado y no antes de `desde`.
- El enlace: `asin` (Amazon con el tag de la cuenta), `shein` (tal cual) o el
  ya guardado para ese producto (`enlaces_repo`, misma `producto_key` que Mis
  tandas: `tienda|título`). Sin enlace NO se encola: en Meta un carrusel sin
  enlace no vende y el de TikTok Shop no vale fuera de TikTok.
- El texto: el `caption` que se pase o el de la réplica sin lo que solo vale
  en TikTok (carrito, TikTok Shop). Hashtags sin los de TikTok + los de la
  tienda.
- La música NO va: la API de Meta no deja ponerla a fotos/carruseles. La
  sugerida (`musica.meta` de la réplica) se añade a mano si se quiere.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import time
import zoneinfo
from pathlib import Path

from src.multiplataforma import config
from src.multiplataforma.models import Publicacion
from src.multiplataforma.repos import enlaces_repo, publicaciones_repo
from src.multiplataforma.services import enlaces, ingesta, tandas, textos

TIPO = "carrusel"
ORIGEN = "carrusel"
_SOLO_TIKTOK = re.compile(r"carrito|tiktok|cesta naranja|bolsa naranja", re.I)


class ErrorCarrusel(ValueError):
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def carpeta(slug: str, carrusel_id: str) -> Path:
    return config.raiz_drive() / slug / "carruseles" / carrusel_id


def fotos_replica(doc: dict) -> list[Path]:
    """Las fotos listas del carrusel, en orden. Error si falta alguna."""
    from src.replicar_viral import carrusel

    usuario, id_ = doc.get("usuario") or "ness", doc["id"]
    fotos, faltan = [], []
    for d in doc.get("diapositivas") or []:
        p = carrusel.ruta_foto(usuario, id_, d["n"], "txt") or carrusel.ruta_foto(usuario, id_, d["n"], "base")
        if not p or (d.get("texto") and not carrusel.ruta_foto(usuario, id_, d["n"], "txt")):
            faltan.append(d["n"])
        elif p:
            fotos.append(p)
    if faltan:
        raise ErrorCarrusel(f"Al carrusel {id_} le faltan las diapositivas {faltan}")
    return fotos


def lienzo_ig(origen: Path, destino: Path) -> Path:
    """La foto entera en un lienzo 4:5 (1080×1350) con el fondo de la propia
    foto ampliada, desenfocada y oscurecida. Ya en 4:5 o más ancha: tal cual
    (re-codificada a JPEG)."""
    from PIL import Image, ImageEnhance, ImageFilter

    ancho, alto = config.IG_LIENZO_CARRUSEL
    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(origen) as im:
        im = im.convert("RGB")
        if im.width / im.height >= ancho / alto - 0.01:
            im.save(destino, "JPEG", quality=92)
            return destino
        escala = max(ancho / im.width, alto / im.height)
        fondo = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
        x, y = (fondo.width - ancho) // 2, (fondo.height - alto) // 2
        fondo = fondo.crop((x, y, x + ancho, y + alto)).filter(ImageFilter.GaussianBlur(40))
        fondo = ImageEnhance.Brightness(fondo).enhance(0.6)
        h = alto
        w = round(im.width * h / im.height)
        fondo.paste(im.resize((w, h), Image.LANCZOS), ((ancho - w) // 2, 0))
        fondo.save(destino, "JPEG", quality=92)
    return destino


def caption_meta(caption: str) -> str:
    """El caption de la réplica sin las frases que solo valen en TikTok."""
    frases = re.split(r"(?<=[.!?])\s+", (caption or "").strip())
    return " ".join(f for f in frases if f and not _SOLO_TIKTOK.search(f)).strip()


def hashtags_meta(hashtags: list[str], enlace: str) -> list[str]:
    tienda = "shein" if enlaces.es_shein(enlace) else "amazon" if enlaces.es_amazon(enlace) else ""
    propios = [h.lstrip("#") for h in hashtags or [] if h and "tiktok" not in h.lower()]
    return propios + config.HASHTAGS_TIENDA.get(tienda, [])


def _inicio_dia(fecha: str) -> float:
    try:
        d = dt.date.fromisoformat(fecha)
    except ValueError as e:
        raise ErrorCarrusel(f"desde: fecha «AAAA-MM-DD», no {fecha!r}") from e
    return dt.datetime(d.year, d.month, d.day, tzinfo=zoneinfo.ZoneInfo(config.ZONA_HORARIA)).timestamp()


def encolar(slug: str, carrusel_id: str, *, usuario: str = "", asin: str = "", shein: str = "",
            nota: str = "", caption: str = "", hashtags: list[str] | None = None, desde: str = "",
            plataformas: list[str] | None = None, ahora: float | None = None) -> dict:
    from src.replicar_viral import carrusel

    c = tandas.cuenta_o_error(slug)
    ahora = time.time() if ahora is None else ahora
    try:
        doc = carrusel.ver(usuario or c.dueno or "ness", carrusel_id)
    except Exception as e:  # noqa: BLE001 — ErrorReplica u otro: no existe
        raise ErrorCarrusel(f"No encuentro el carrusel {carrusel_id}: {e}", status=404) from e
    plataformas = [p for p in (plataformas or config.PLATAFORMAS) if p in config.PLATAFORMAS]
    if not plataformas:
        raise ErrorCarrusel("plataformas: ninguna válida")
    fotos = fotos_replica(doc)
    if len(fotos) < 2:
        raise ErrorCarrusel("Un carrusel necesita al menos 2 fotos")
    fotos = fotos[: config.MAX_FOTOS_CARRUSEL["instagram"]]

    prod = doc.get("producto") or {}
    titulo = " ".join(str(prod.get("titulo") or "").split())
    key = tandas.producto_key({"titulo": titulo, "tienda": prod.get("tienda", "")})
    if asin or shein:
        try:
            tandas.guardar_enlace(slug, key, asin=asin, shein=shein, nota=nota or f"carrusel {carrusel_id}",
                                  titulo=titulo)
        except tandas.ErrorTandas as e:
            raise ErrorCarrusel(str(e)) from e
    enlace = enlaces_repo.enlace_de(slug, key)
    if not enlace:
        raise ErrorCarrusel(f"El producto «{titulo}» no tiene enlace en {slug}: pasa `asin` o `shein` "
                            "(sin equivalente fiable, el carrusel no va a Meta)")

    destino = carpeta(slug, carrusel_id)
    imagenes, imagenes_ig = [], []
    for i, f in enumerate(fotos, start=1):
        p = destino / f"{i:02d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, p)
        imagenes.append(str(p))
        imagenes_ig.append(str(lienzo_ig(p, destino / "ig" / f"{i:02d}.jpg")))

    texto = (caption or "").strip() or caption_meta(doc.get("caption", ""))
    tags = [h.lstrip("#") for h in hashtags] if hashtags else hashtags_meta(doc.get("hashtags") or [], enlace)
    t = textos.construir(titulo="", caption=texto, enlace=enlace, hashtags=tags, plataformas=plataformas)

    ritmo = int((c.ritmo or {}).get(TIPO, config.RITMO_DEFAULT[TIPO])) or 1
    horas = (c.horas or {}).get(TIPO) or config.HORAS_DEFAULT[TIPO]
    base = max(ahora, ingesta._ultima_programada(slug, TIPO), _inicio_dia(desde) if desde else 0)
    pub = Publicacion(
        cuenta=slug, video_path=imagenes[0], tipo=TIPO, producto_ref=key,
        titulo=(titulo or texto)[: config.MAX_TITULO_PINTEREST], caption=texto, hashtags=tags,
        textos=t["textos"], comentario=t["comentario"], enlace=enlace, imagenes=imagenes,
        imagenes_ig=imagenes_ig, carrusel_id=carrusel_id, plataformas=plataformas, origen=ORIGEN,
        programada_en=0.0,
    )
    ya = next((p for p in publicaciones_repo.de_cuenta(slug) if p.clave == pub.clave), None)
    if ya:
        return {"publicacion": ya.to_dict(), "creada": False, "producto_key": key}
    pub.programada_en = next(ingesta.huecos(ritmo, horas, base, semilla=slug))
    pub, creada = publicaciones_repo.encolar(pub)
    return {"publicacion": pub.to_dict(), "creada": creada, "producto_key": key,
            "programada": dt.datetime.fromtimestamp(pub.programada_en, zoneinfo.ZoneInfo(config.ZONA_HORARIA))
            .strftime("%Y-%m-%d %H:%M"), "fotos": len(imagenes),
            "musica_sugerida": (doc.get("musica") or {}).get("meta") or {}}
