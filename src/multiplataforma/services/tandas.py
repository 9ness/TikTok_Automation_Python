"""Resubir a IG/FB/Threads/Pinterest los vídeos de «Mis tandas» del dueño de
una cuenta, cada uno con el enlace de afiliado de SU producto.

- `productos(slug)`: lo montado por el dueño (`mis_tandas.fuentes.todas`),
  agrupado por producto, con su enlace guardado (o no) y cuántos vídeos ya
  están en la cola del publicador.
- `guardar_enlace(...)`: SHEIN tal cual (validado) o ASIN → Amazon con el tag
  de la cuenta; `sin_equivalente` si no hay nada parecido.
- `encolar(slug)`: encola (idempotente por `video_path`) los vídeos de los
  productos CON enlace, con el ritmo/horas `producto` de la cuenta.
- `links_publicos(slug)` / `foto_publica(...)`: la página pública /links.

Identidad del producto (`producto_key`): hash de `clave_producto`, que es
`norm(tienda)|norm(título)` (minúsculas, sin acentos ni espacios dobles; la misma idea
que `mis_tandas.servicio._clave_producto`). Es lo único que comparten el POV
BOF, todos los modos del Largo y las copias de Productos Q4 de un mismo
producto: el id de fila lleva fuente/carpeta/modo y cambia en cada copia. Sin
título (textos sin extraer) cae al sitio en el catálogo.
"""

from __future__ import annotations

import hashlib
import time
import unicodedata
from pathlib import Path

from src.multiplataforma import config
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, enlaces_repo, publicaciones_repo, redis_base
from src.multiplataforma.services import enlaces, ingesta, textos, video_url

ORIGEN = "tandas"
MAX_LINKS = 60
TIPO = "producto"


class ErrorTandas(ValueError):
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def _key_encoladas(slug: str) -> str:
    return f"tandas_encoladas:{slug}"


# ---------------------------------------------------------------------------
# Identidad del producto
# ---------------------------------------------------------------------------
def _norm(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    return " ".join("".join(c for c in plano if not unicodedata.combining(c)).split())


def clave_producto(f: dict) -> str:
    """`tienda|título` en minúsculas, sin acentos ni espacios dobles. Se
    normaliza AQUÍ y no con `product_repo.clave_escaparate`: allí `_normaliza`
    está redefinida más abajo (la de hashtags) y no quita mayúsculas/acentos."""
    titulo = _norm(f.get("titulo", ""))
    if titulo:
        return f"{_norm(f.get('tienda', ''))}|{titulo}"
    return "|".join(str(f.get(k, "")) for k in ("nicho", "source", "carpeta", "producto"))


def producto_key(f: dict) -> str:
    return hashlib.sha1(clave_producto(f).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Lectura de Mis tandas
# ---------------------------------------------------------------------------
def cuenta_o_error(slug: str) -> CuentaDestino:
    c = cuentas_repo.get(slug)
    if not c:
        raise ErrorTandas(f"No existe la cuenta {slug}", status=404)
    if not c.dueno:
        raise ErrorTandas(f"La cuenta {slug} no tiene dueño (usuario de la app)", status=400)
    return c


def filas(dueno: str) -> list[dict]:
    """Vídeos montados del dueño (POV + Largo, Multimodo, Aleatorios), sin
    los que ha quitado de Mis tandas."""
    from src.mis_tandas import fuentes

    pov, mm, alea = fuentes.todas(dueno)
    try:
        from src.mis_tandas import servicio

        fuera = servicio.ocultos(dueno)
    except Exception:  # noqa: BLE001 — sin la lista de ocultos, salen todos
        fuera = set()
    return [f for f in pov + mm + alea if f.get("video_path") and f["id"] not in fuera]


def _cola_por_producto(slug: str) -> dict[str, list[Publicacion]]:
    out: dict[str, list[Publicacion]] = {}
    for p in publicaciones_repo.de_cuenta(slug):
        if p.producto_ref:
            out.setdefault(p.producto_ref, []).append(p)
    return out


def _ultima_publicacion(pubs: list[Publicacion]) -> float:
    marcas = [float((p.resultados.get(pl) or {}).get("publicado_en") or 0)
              for p in pubs for pl in p.plataformas]
    return max(marcas, default=0.0)


def _estado_enlace(e: dict | None) -> str:
    if not e:
        return "sin_enlace"
    if e.get("sin_equivalente"):
        return enlaces_repo.SIN_EQUIVALENTE
    return "con_enlace" if e.get("enlace") else "sin_enlace"


def productos(slug: str, *, sin_enlace: bool = False) -> dict:
    c = cuenta_o_error(slug)
    guardados = enlaces_repo.todos(slug)
    cola = _cola_por_producto(slug)
    grupos: dict[str, dict] = {}
    for f in filas(c.dueno):
        k = producto_key(f)
        g = grupos.get(k)
        if g is None:
            g = grupos[k] = {
                "producto_key": k, "titulo": f.get("titulo") or f"Producto {f.get('producto', '')}",
                "tienda": f.get("tienda", ""), "product_url": f.get("product_url", ""),
                "foto": f"/api/v1/multiplataforma/cuentas/{slug}/productos/{k}/foto",
                "videos": 0, "subidos_tiktok": 0, "ultimo_video_at": 0.0,
                "fila_id": f["id"], "ubicaciones": [],
            }
        g["videos"] += 1
        g["subidos_tiktok"] += 1 if f.get("uploaded") else 0
        g["ultimo_video_at"] = max(g["ultimo_video_at"], float(f.get("video_listo_at") or 0))
        sitio = f"{f.get('nicho')} · {f.get('carpeta_label') or f.get('carpeta')} · {f.get('producto')}"
        if sitio not in g["ubicaciones"]:
            g["ubicaciones"].append(sitio)
    # La foto pública sigue la fila vigente del producto.
    enlaces_repo.tocar_meta(slug, {k: {"fila_id": g["fila_id"]} for k, g in grupos.items()})
    lista = []
    for k, g in grupos.items():
        e = guardados.get(k)
        pubs = cola.get(k, [])
        g["enlace"] = (e or {}).get("enlace", "")
        g["estado_enlace"] = _estado_enlace(e)
        g["nota"] = (e or {}).get("nota", "")
        g["en_cola"] = sum(1 for p in pubs if not p.terminada)
        g["en_multiplataforma"] = len(pubs)
        if sin_enlace and g["estado_enlace"] != "sin_enlace":
            continue
        lista.append(g)
    lista.sort(key=lambda g: (-g["subidos_tiktok"], -g["ultimo_video_at"]))
    return {"cuenta": slug, "dueno": c.dueno, "total": len(lista), "productos": lista}


# ---------------------------------------------------------------------------
# Enlaces
# ---------------------------------------------------------------------------
def guardar_enlace(slug: str, producto_key_: str, *, shein: str = "", asin: str = "",
                   enlace: str = "", nota: str = "", titulo: str = "", foto_url: str = "",
                   precio: str = "") -> dict:
    """Guarda el enlace del producto. `shein`/`asin` = 'sin_equivalente' (o
    ambos vacíos con `nota`) marcan que no hay un producto parecido."""
    c = cuenta_o_error(slug)
    if not enlaces_repo.key_valida(producto_key_):
        raise ErrorTandas(f"producto_key no válida: {producto_key_!r}")
    shein, asin, enlace = (shein or "").strip(), (asin or "").strip(), (enlace or "").strip()
    sin = enlaces_repo.SIN_EQUIVALENTE in (shein.lower(), asin.lower(), enlace.lower())
    datos: dict = {"nota": nota.strip()}
    try:
        if sin:
            datos.update(sin_equivalente=True, enlace="", shein="", asin="", amazon="")
        elif asin:
            amazon = enlaces.enlace_amazon(asin, c.afiliado_amazon_tag)
            datos.update(sin_equivalente=False, asin=asin.upper(), amazon=amazon, shein="", enlace=amazon)
        elif shein or (enlace and enlaces.es_shein(enlace)):
            url = enlaces.enlace_shein(shein or enlace)
            datos.update(sin_equivalente=False, shein=url, asin="", amazon="", enlace=url)
        elif enlace and enlaces.es_amazon(enlace):
            url = enlaces.validar(enlace)
            datos.update(sin_equivalente=False, amazon=url, shein="", asin="", enlace=url)
        else:
            raise ErrorTandas("Falta `shein` (enlace del panel tal cual), `asin` o 'sin_equivalente'")
        if foto_url:
            foto_url = enlaces.validar(foto_url)
    except enlaces.EnlaceInvalido as e:
        raise ErrorTandas(str(e)) from e
    if titulo:
        datos["titulo"] = titulo.strip()[:120]
    if foto_url:
        datos["foto_url"] = foto_url
    if precio:
        datos["precio"] = str(precio).strip()[:20]
    # Título y fila de Mis tandas, si el producto está ahí (para /links).
    for f in filas(c.dueno):
        if producto_key(f) == producto_key_:
            datos.setdefault("titulo", f.get("titulo") or "")
            datos["tienda"] = f.get("tienda", "")
            datos["fila_id"] = f["id"]
            datos["clave"] = clave_producto(f)
            break
    return enlaces_repo.guardar(slug, producto_key_, datos)


# ---------------------------------------------------------------------------
# Encolar
# ---------------------------------------------------------------------------
def encolar(slug: str, *, incluir_no_subidos: bool = False, limite: int = 0,
            ahora: float | None = None) -> dict:
    """Encola los vídeos de productos CON enlace que aún no estén en la cola
    (por `video_path`). Por defecto solo los ya subidos a TikTok. Orden: el
    de TikTok (lo subido antes, antes)."""
    c = cuenta_o_error(slug)
    ahora = time.time() if ahora is None else ahora
    ritmo = int((c.ritmo or {}).get(TIPO, config.RITMO_DEFAULT.get(TIPO, 1)))
    if ritmo <= 0:
        raise ErrorTandas(f"La cuenta {slug} tiene ritmo 0 para «{TIPO}»: no se encola nada")
    horas = (c.horas or {}).get(TIPO) or config.HORAS_DEFAULT.get(TIPO, ["12:00"])
    r = redis_base.get_redis()
    ya = set(r.smembers(_key_encoladas(slug)))
    ya |= {p.video_path for p in publicaciones_repo.de_cuenta(slug)}
    guardados = enlaces_repo.todos(slug)

    informe: dict = {"cuenta": slug, "encoladas": [], "omitidas": {"sin_enlace": 0, "no_subidos": 0,
                                                                   "ya_encolados": 0, "ruta_no_valida": 0}}
    candidatas = []
    for f in filas(c.dueno):
        if f["video_path"] in ya:
            informe["omitidas"]["ya_encolados"] += 1
            continue
        if not incluir_no_subidos and not f.get("uploaded"):
            informe["omitidas"]["no_subidos"] += 1
            continue
        k = producto_key(f)
        e = guardados.get(k) or {}
        if e.get("sin_equivalente") or not e.get("enlace"):
            informe["omitidas"]["sin_enlace"] += 1
            continue
        if not video_url.servible(f["video_path"]) or not video_url.ruta_permitida(f["video_path"]):
            informe["omitidas"]["ruta_no_valida"] += 1
            continue
        candidatas.append((f, k, e))
    candidatas.sort(key=lambda t: (float(t[0].get("uploaded_at") or 0) or float(t[0].get("video_listo_at") or 0)))
    if limite > 0:
        candidatas = candidatas[:limite]

    reloj = ingesta.huecos(ritmo, horas, max(ahora, ingesta._ultima_programada(slug, TIPO)))
    for f, k, e in candidatas:
        titulo = e.get("titulo") or f.get("titulo") or ""
        caption = f.get("caption", "")
        t = textos.construir(titulo=titulo, caption=caption, enlace=e["enlace"], plataformas=config.PLATAFORMAS)
        pub = Publicacion(
            cuenta=slug, video_path=f["video_path"], tipo=TIPO, producto_ref=k,
            titulo=t["titulo_pin"], caption=caption, textos=t["textos"], comentario=t["comentario"],
            enlace=e["enlace"], plataformas=list(config.PLATAFORMAS), programada_en=next(reloj), origen=ORIGEN,
        )
        pub, creada = publicaciones_repo.encolar(pub)
        r.sadd(_key_encoladas(slug), f["video_path"])
        ya.add(f["video_path"])
        informe["encoladas"].append({"id": pub.id, "producto_key": k, "titulo": titulo,
                                     "programada_en": pub.programada_en, "creada": creada})
    informe["total"] = len(informe["encoladas"])
    return informe


def rellenar_enlace(pub: Publicacion) -> bool:
    """Si `pub` trae `producto_ref` y no `enlace`, lo toma de enlaces_repo y
    rehace los textos. True si ha cambiado algo."""
    if pub.enlace or not pub.producto_ref:
        return False
    enlace = enlaces_repo.enlace_de(pub.cuenta, pub.producto_ref)
    if not enlace:
        return False
    try:
        t = textos.construir(titulo=pub.titulo, caption=pub.caption, enlace=enlace,
                             hashtags=pub.hashtags, plataformas=pub.plataformas)
    except enlaces.EnlaceInvalido:
        return False
    pub.enlace = enlace
    pub.textos = t["textos"]
    pub.comentario = t["comentario"]
    return True


# ---------------------------------------------------------------------------
# Página pública /links
# ---------------------------------------------------------------------------
def _corto(titulo: str, n: int = 70) -> str:
    t = " ".join((titulo or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# La página pública la abre cualquiera desde la bio: se sirve de memoria unos
# segundos para no ir a Redis y al Drive en cada visita (un pico de la API
# dejaba la página en «cargando» en el móvil).
_LINKS_TTL_S = 60
_links_cache: dict[str, tuple[float, dict]] = {}


def links_publicos(slug: str) -> dict:
    """Solo lo publicable: nombre de la cuenta y productos con enlace. Nada
    interno (rutas, ids de Drive, filas). Cacheado `_LINKS_TTL_S`."""
    hit = _links_cache.get(slug)
    if hit and time.time() - hit[0] < _LINKS_TTL_S:
        return hit[1]
    datos = _links_publicos(slug)
    _links_cache[slug] = (time.time(), datos)
    return datos


def _links_publicos(slug: str) -> dict:
    c = cuentas_repo.get(slug)
    if not c or not c.activa:
        raise ErrorTandas("No existe", status=404)
    cola = _cola_por_producto(slug)
    items = []
    for k, e in enlaces_repo.todos(slug).items():
        if e.get("sin_equivalente") or not e.get("enlace"):
            continue
        pubs = cola.get(k, [])
        orden = _ultima_publicacion(pubs) or max((p.programada_en for p in pubs if p.programada_en <= time.time()),
                                                 default=0.0)
        items.append((orden, float(e.get("actualizado") or 0), {
            "id": k,
            "titulo": _corto(e.get("titulo") or "Producto"),
            "foto": f"/api/v1/multiplataforma/links/{slug}/foto/{k}",
            "enlace": e["enlace"],
            "tienda": "amazon" if enlaces.es_amazon(e["enlace"]) else ("shein" if enlaces.es_shein(e["enlace"]) else ""),
        }))
    items.sort(key=lambda t: (t[0], t[1]), reverse=True)
    productos_ = [i[2] for i in items[:MAX_LINKS]]
    hay_amazon = any(p["tienda"] == "amazon" for p in productos_)
    base = f"/api/v1/multiplataforma/links/{slug}/marca"
    return {
        "cuenta": c.nombre or c.slug,
        "tema": config.tema_links(slug),
        "banner": config.BANNER_LINKS,
        "logo": f"{base}/logo" if config.fichero_marca(slug, "logo") else "",
        "portada": f"{base}/portada" if config.fichero_marca(slug, "portada") else "",
        "fondo": f"{base}/fondo" if config.fichero_marca(slug, "fondo") else "",
        "productos": productos_,
        "aviso_amazon": textos.aviso_amazon() if hay_amazon else "",
    }


def foto_publica(slug: str, producto_key_: str, ancho: int = 400) -> Path | str:
    """Path de la miniatura, o la URL https externa (`foto_url`) a la que
    redirigir. Solo productos con enlace publicable de una cuenta activa."""
    c = cuentas_repo.get(slug)
    e = enlaces_repo.get(slug, producto_key_) if c and c.activa else None
    if not e or e.get("sin_equivalente") or not e.get("enlace"):
        raise ErrorTandas("No existe", status=404)
    if e.get("foto_url"):
        return str(e["foto_url"])
    return foto_interna(c, e.get("fila_id", ""), ancho)


def foto_interna(c: CuentaDestino, fila_id: str, ancho: int = 400) -> Path:
    if not fila_id:
        raise ErrorTandas("Sin foto", status=404)
    from src.mis_tandas import servicio

    try:
        return servicio.foto(c.dueno, fila_id, ancho)
    except servicio.ErrorTanda as err:
        raise ErrorTandas(str(err), status=err.status) from err
