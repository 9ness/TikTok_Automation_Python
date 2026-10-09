"""Replicar un CARRUSEL de fotos viral con un producto nuestro (Programa 4).

Calco del «replicador de carruseles» de la web del curso (clase del 7 oct
2026, `docs/clases/2026-10-07_clase_miercoles.md` § C), pero sin gastar
créditos de imagen:

1. Enlace de TikTok → tikwm devuelve las URLs de las diapositivas (`images`).
2. Gemini (una llamada, la misma que `servicio.replicar`) ve TODAS las
   diapositivas + la foto limpia y la ficha del producto, y devuelve por
   diapositiva: papel, texto quemado adaptado y prompt de imagen para Flow.
3. El operador/agente genera las fotos en Google Flow A MANO (nunca por API)
   y las sube aquí; la app les quema el texto con el motor del nicho
   Carruseles (`nicho_carruseles.services.texto_foto.quemar`) y las da todas
   en un ZIP.

El documento vive junto a las réplicas de vídeo (`replicar_viral:<id>`, mismo
índice) con `tipo="carrusel"`. Las fotos NO van a Redis: en el Drive montado,
`TIKTOK_SHOP_AI_PRO/Replicar_Carrusel/<usuario>/<id>/{orig,base,txt}/NN.jpg`.
Si una foto está o no se mira en disco, no en el documento: dos subidas a la
vez no se pisan.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import requests

from src.replicar_viral import catalogo, musica, servicio
from src.replicar_viral.servicio import ErrorReplica

PROMPT = Path(__file__).parent / "prompts" / "replicar_carrusel.md"
RAIZ_DRIVE = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Replicar_Carrusel"
MAX_DIAPOS = 12
LADO_GEMINI = 1080
ROLES = ("gancho", "problema", "producto", "prueba", "cta")
TIPOS_FOTO = ("orig", "base", "txt")
_ID = re.compile(r"[a-f0-9]{12}")


# ---------------------------------------------------------------------------
# Disco
# ---------------------------------------------------------------------------
def _raiz() -> Path:
    from src.nicho_pov_bof.services.audio_bank import mount_root

    m = mount_root()
    return m / RAIZ_DRIVE if m else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "replicar_carrusel"


def dir_replica(usuario: str, id_: str) -> Path:
    if not _ID.fullmatch(id_ or ""):
        raise ErrorReplica("Id de réplica inválido.", status=404)
    return _raiz() / (usuario or "ness") / id_


def ruta_foto(usuario: str, id_: str, n: int, tipo: str) -> Path | None:
    """La foto `tipo` (orig = la del viral, base = la generada en Flow,
    txt = la generada con el texto quemado) de la diapositiva `n`, si existe."""
    if tipo not in TIPOS_FOTO:
        raise ErrorReplica(f"Tipo de foto desconocido: {tipo}.")
    p = dir_replica(usuario, id_) / tipo / f"{int(n):02d}.jpg"
    return p if p.is_file() else None


def _a_jpeg(datos: bytes, destino: Path, lado: int | None = None) -> Path:
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(datos))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ErrorReplica(f"Eso no es una imagen válida: {e}") from e
    if lado:
        img.thumbnail((lado, lado * 2))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, "JPEG", quality=92)
    return destino


def _formato(ruta: Path) -> str:
    """9:16 si la diapositiva es alargada (TikTok la sirve a 1080×1920);
    3:4 si es más cuadrada (1080×1440, la de la mayoría de carruseles)."""
    from PIL import Image

    with Image.open(ruta) as img:
        w, h = img.size
    return "9:16" if h / max(w, 1) >= 1.6 else "3:4"


# ---------------------------------------------------------------------------
# tikwm
# ---------------------------------------------------------------------------
def datos_carrusel(url: str) -> dict:
    """Las diapositivas de un carrusel de TikTok: {titulo, autor, vistas, imagenes}.

    Si el enlace es un vídeo, lo dice (eso va por «Replicar viral»)."""
    datos = servicio.consultar_tikwm(url)
    imagenes = [i for i in (datos.get("images") or []) if isinstance(i, str) and i.startswith("http")]
    if not imagenes:
        raise ErrorReplica("Ese enlace es un vídeo, no un carrusel de fotos: usa «Replicar viral».")
    return {
        "titulo": datos.get("title") or "",
        "autor": (datos.get("author") or {}).get("unique_id") or "",
        "vistas": datos.get("play_count") or 0,
        "imagenes": imagenes,
        "musica": musica.de_tikwm(datos),
    }


def _bajar(url: str) -> bytes:
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise ErrorReplica(f"No se pudo bajar una diapositiva: {e}", status=502) from e
    return r.content


# ---------------------------------------------------------------------------
# Limpieza de lo que devuelve la IA
# ---------------------------------------------------------------------------
_CUPON_VERBO = re.compile(r"\b(aplica|usa|canjea|activa|aprovecha)\s+(tus?|el|los)\s+cup[oó]n(es)?\b", re.I)
_CUPON_TUYO = re.compile(r"\b(con\s+)?tus?\s+cup[oó]n(es)?\b", re.I)


def sin_cupones_afirmados(texto: str) -> str:
    """«aplica tus cupones» / «tu cupón» → «revisa si tienes cupones»: no
    sabemos si el que lo lee tiene cupón, y afirmarlo es una promesa falsa."""
    t = _CUPON_VERBO.sub("revisa si tienes cupones", texto or "")
    return _CUPON_TUYO.sub("revisa si tienes cupones", t)


_SIN_TEXTO = "No text, no letters, no captions, no watermarks, no logos added on the image."


def _normalizar(resultado: dict, n_diapos: int, formato: str) -> dict:
    diapos = [d for d in (resultado.get("diapositivas") or []) if isinstance(d, dict)][:n_diapos]
    while len(diapos) < n_diapos:  # la IA se saltó alguna: hueco vacío, que se vea
        diapos.append({"rol": "producto", "texto": "", "prompt_imagen": ""})
    salida = []
    for i, d in enumerate(diapos, start=1):
        rol = str(d.get("rol") or "").strip().lower()
        prompt = str(d.get("prompt_imagen") or "").strip()
        if prompt and "no text" not in prompt.lower():
            prompt = f"{prompt.rstrip('. ')}. {_SIN_TEXTO}"
        if prompt and formato not in prompt:
            prompt = f"Vertical {formato} photo. {prompt}"
        salida.append({
            "n": i,
            "rol": rol if rol in ROLES else "producto",
            "texto_original": str(d.get("texto_original") or "").strip(),
            "sale_producto": bool(d.get("sale_producto")),
            "ambiente": str(d.get("ambiente") or "").strip(),
            "texto": sin_cupones_afirmados(str(d.get("texto") or "").strip()),
            "usa_foto_producto": bool(d.get("usa_foto_producto")),
            "prompt_imagen": prompt,
        })
    if salida and not any(d["usa_foto_producto"] for d in salida):
        # Sin ninguna con el producto, el carrusel no enseña lo enlazado.
        prod = next((d for d in salida if d["rol"] == "producto"), salida[min(1, len(salida) - 1)])
        prod["usa_foto_producto"] = True
    hashtags = resultado.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = hashtags.split()
    hashtags = [h if h.startswith("#") else f"#{h}" for h in (str(x).strip() for x in hashtags) if h]
    return {
        "original": resultado.get("original") if isinstance(resultado.get("original"), dict) else {},
        "apto": bool(resultado.get("apto", True)),
        "motivo_no_apto": str(resultado.get("motivo_no_apto") or ""),
        "diapositivas": salida,
        "caption": sin_cupones_afirmados(str(resultado.get("caption") or "").strip()),
        "hashtags": hashtags[:8],
    }


# ---------------------------------------------------------------------------
# Analizar + adaptar
# ---------------------------------------------------------------------------
def replicar(usuario: str, *, source: str, folder: str, producto: str, url: str,
             replica_de: str = "") -> dict:
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.api.gemini import generate_text

    usuario = usuario or "ness"
    if not url:
        raise ErrorReplica("Falta el enlace del carrusel de TikTok.")
    meta = datos_carrusel(url)
    urls = meta.pop("imagenes")
    cancion = meta.pop("musica", {})
    recortado = len(urls) > MAX_DIAPOS
    urls = urls[:MAX_DIAPOS]

    id_ = uuid.uuid4().hex[:12]
    carpeta = dir_replica(usuario, id_)
    tmp = Path(tempfile.mkdtemp(prefix="replica_carrusel_"))
    try:
        textos, foto = servicio._producto(source, folder, producto, usuario, tmp)
        origs = [_a_jpeg(_bajar(u), carpeta / "orig" / f"{i:02d}.jpg", LADO_GEMINI)
                 for i, u in enumerate(urls, start=1)]
        formato = _formato(origs[0])

        sistema = servicio._sin_comentarios(PROMPT.read_text(encoding="utf-8")).replace("{{FORMATO}}", formato)
        mensaje = (
            f"CARRUSEL DE REFERENCIA: las {len(origs)} primeras imágenes adjuntas, en orden"
            f" (diapositiva 1 = la primera)"
            + (f", de @{meta['autor']} ({meta['vistas']} vistas)" if meta.get("autor") else "")
            + (f". Texto de la publicación: «{meta['titulo']}»" if meta.get("titulo") else "")
            + f".\nFormato de las diapositivas: {formato}."
            + "\n\nNUESTRO PRODUCTO (ficha):\n" + servicio._ficha(textos)
            + ("\n\nLa ÚLTIMA imagen adjunta es la foto limpia de NUESTRO producto (no es una diapositiva)."
               if foto else "\n\n(No hay foto del producto: guíate por la ficha.)")
        )
        start_job(
            job_id=f"replica_carrusel_{id_[:8]}", program="tiktok_shop_ai_pro",
            mode="replicar_carrusel", title=f"Replicar carrusel: {textos.get('titulo', '')[:60]}",
            user=usuario,
        )
        try:
            crudo = generate_text(
                sistema, mensaje, model=servicio.MODELO, expect_json=True,
                images=[str(p) for p in origs] + ([str(foto)] if foto else []),
                temperature=0.6, max_output_tokens=8192, max_retries_on_quota=1,
            )
        except Exception as e:  # noqa: BLE001
            if "429" in str(e) or "quota" in str(e).lower() or "exhausted" in str(e).lower():
                raise ErrorReplica(
                    "Gemini no tiene cuota ahora mismo (claves agotadas o sin saldo). "
                    "Recarga en AI Studio o prueba más tarde.", status=503,
                ) from e
            raise
        finally:
            try:
                finalize_and_persist()
            except Exception:  # noqa: BLE001
                pass
        texto = (crudo or "").strip()
        if texto.startswith("```"):
            texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            resultado = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ErrorReplica(f"La IA no devolvió un JSON válido: {e}", status=502) from e

        doc = {
            "id": id_,
            "tipo": "carrusel",
            "usuario": usuario,
            "creado_at": time.time(),
            "url": url,
            "referencia": {**meta, "diapositivas": len(origs), "recortado": recortado},
            "producto": {"source": source, "folder": folder, "producto": str(producto),
                         "titulo": textos.get("titulo", ""), "tienda": textos.get("tienda", "")},
            "formato": formato,
            **({"replica_de": replica_de} if replica_de else {}),
            **_normalizar(resultado if isinstance(resultado, dict) else {}, len(origs), formato),
        }
        doc["musica"] = musica.completa({**doc, "musica": {"tiktok": cancion}}, {})
        servicio.guardar(doc)
        if source == catalogo.SOURCE:
            # El producto se acuerda del viral: así otro usuario lo replica
            # desde el catálogo sin buscar el enlace otra vez.
            catalogo.guardar_carrusel_url(folder, producto, url)
        return con_estado(doc)
    except Exception:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Leer, subir las fotos de Flow, quemar el texto, ZIP
# ---------------------------------------------------------------------------
def ver(usuario: str, id_: str) -> dict:
    doc = servicio.ver(usuario, id_)
    if doc.get("tipo") != "carrusel":
        raise ErrorReplica("Esa réplica no es un carrusel.", status=404)
    if "musica" not in doc:  # réplicas de antes de guardar la música: una vez y se queda
        doc["musica"] = musica.completa(doc)
        if doc["musica"].get("tiktok"):  # si tikwm falló, se reintenta la próxima vez
            try:
                servicio.guardar(doc, indexar=False)
            except Exception:  # noqa: BLE001
                pass
    return doc


def con_estado(doc: dict) -> dict:
    """El documento + qué fotos hay ya en disco de cada diapositiva."""
    usuario, id_ = doc.get("usuario") or "ness", doc["id"]
    diapos = []
    for d in doc.get("diapositivas") or []:
        n = d["n"]
        base = ruta_foto(usuario, id_, n, "base")
        txt = ruta_foto(usuario, id_, n, "txt")
        final = txt or base
        diapos.append({**d, "tiene_original": bool(ruta_foto(usuario, id_, n, "orig")),
                       "tiene_imagen": bool(base), "tiene_texto": bool(txt),
                       "lista": bool(base) and (bool(txt) or not d.get("texto")),
                       "version": int(final.stat().st_mtime) if final else 0})
    hechas = sum(1 for d in diapos if d["lista"])
    return {**doc, "diapositivas": diapos, "hechas": hechas, "total": len(diapos),
            "completo": bool(diapos) and hechas == len(diapos)}


def _diapo(doc: dict, n: int) -> dict:
    d = next((x for x in doc.get("diapositivas") or [] if x.get("n") == int(n)), None)
    if not d:
        raise ErrorReplica(f"El carrusel no tiene diapositiva {n}.", status=404)
    return d


def _quemar(usuario: str, id_: str, n: int, texto: str) -> None:
    """Siempre desde la foto de Flow (`base`), nunca desde la ya quemada."""
    from src.nicho_carruseles.services import texto_foto

    base = ruta_foto(usuario, id_, n, "base")
    destino = dir_replica(usuario, id_) / "txt" / f"{int(n):02d}.jpg"
    if not base:
        return
    if texto.strip():
        texto_foto.quemar(base, texto, destino)
    elif destino.exists():
        destino.unlink()


def subir_imagen(usuario: str, id_: str, n: int, datos: bytes) -> dict:
    """Guarda la foto generada en Flow para la diapositiva `n` y le quema su texto."""
    usuario = usuario or "ness"
    doc = ver(usuario, id_)
    d = _diapo(doc, n)
    _a_jpeg(datos, dir_replica(usuario, id_) / "base" / f"{int(n):02d}.jpg")
    _quemar(usuario, id_, n, d.get("texto") or "")
    return con_estado(doc)


def cambiar_texto(usuario: str, id_: str, n: int, texto: str) -> dict:
    """Corrige el texto de una diapositiva y vuelve a quemarlo si ya hay foto."""
    usuario = usuario or "ness"
    doc = ver(usuario, id_)
    d = _diapo(doc, n)
    d["texto"] = sin_cupones_afirmados((texto or "").strip())
    servicio.guardar(doc, indexar=False)
    _quemar(usuario, id_, n, d["texto"])
    return con_estado(doc)


def marcar_subido(usuario: str, id_: str, subido: bool = True) -> dict:
    """«Subido» de un carrusel (lo marca «Mis tandas › Fotos»). Vive en el
    propio documento de la réplica: es de ESE usuario y de esa publicación."""
    usuario = usuario or "ness"
    doc = ver(usuario, id_)
    doc["subido"] = bool(subido)
    doc["subido_at"] = time.time() if subido else 0
    servicio.guardar(doc, indexar=False)
    return con_estado(doc)


def _slug(texto: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:40] or "carrusel"


def nombre_carrusel(doc: dict) -> str:
    return f"carrusel_{_slug((doc.get('producto') or {}).get('titulo', ''))}_{doc['id'][:6]}"


def meter_en_zip(z: zipfile.ZipFile, doc: dict, carpeta: str) -> int:
    """Mete en `z`, bajo `carpeta/`, las diapositivas listas (con su texto, o
    la de Flow tal cual si no lleva) en orden + `caption.txt`. Devuelve
    cuántas fotos entraron. Lo usa también «Mis tandas › Fotos»."""
    usuario, id_ = doc.get("usuario") or "ness", doc["id"]
    metidas = 0
    for d in doc.get("diapositivas") or []:
        p = ruta_foto(usuario, id_, d["n"], "txt") or ruta_foto(usuario, id_, d["n"], "base")
        if p:
            z.write(p, f"{carpeta}/{d['n']:02d}.jpg")
            metidas += 1
    if metidas:
        pie = (doc.get("caption") or "").strip()
        if doc.get("hashtags"):
            pie = f"{pie}\n\n{' '.join(doc['hashtags'])}".strip()
        z.writestr(f"{carpeta}/caption.txt", pie + "\n")
    return metidas


def zip_carrusel(usuario: str, id_: str) -> tuple[bytes, str]:
    """(bytes del ZIP, nombre): cada diapositiva con su texto (o la de Flow
    tal cual si no lleva texto), en orden, + `caption.txt`."""
    usuario = usuario or "ness"
    doc = ver(usuario, id_)
    nombre = nombre_carrusel(doc)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        metidas = meter_en_zip(z, doc, nombre)
    if not metidas:
        raise ErrorReplica("Aún no hay ninguna foto subida en este carrusel.", status=404)
    return buf.getvalue(), f"{nombre}.zip"


# ---------------------------------------------------------------------------
# Replicar otra vez (mismo producto + mismo viral) para otro usuario
# ---------------------------------------------------------------------------
def destino(usuario: str, para: str = "") -> str:
    """Para quién se replica: uno mismo, o otro usuario si quien lo pide es
    admin (ness prepara los carruseles de Ana y Mauro)."""
    from src.api import users

    usuario = usuario or "ness"
    para = (para or "").strip().lower()
    if not para or para == usuario:
        return usuario
    if not users.es_admin(usuario):
        raise ErrorReplica("Solo un administrador replica para otro usuario.", status=403)
    if not users.existe(para):
        raise ErrorReplica(f"No existe el usuario {para!r}.", status=404)
    return para


def replicar_otra_vez(usuario: str, id_: str, para: str = "") -> dict:
    """Vuelve a pasar el MISMO carrusel viral con el MISMO producto (una
    llamada nueva de Gemini: textos y prompts salen distintos, que es lo que
    se quiere en otra cuenta) para `para` o para uno mismo."""
    doc = ver(usuario or "ness", id_)
    prod = doc.get("producto") or {}
    if not doc.get("url") or not prod.get("source"):
        raise ErrorReplica("A esa réplica le falta el enlace o el producto.", status=409)
    return replicar(destino(usuario, para), source=prod["source"], folder=prod["folder"],
                    producto=str(prod["producto"]), url=doc["url"], replica_de=id_)
