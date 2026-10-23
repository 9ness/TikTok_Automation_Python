"""Resubir a IG/FB/Threads/Pinterest los vídeos de «Mis tandas» del dueño de
una cuenta, cada uno con el enlace de afiliado de SU producto.

- `productos(slug)`: lo montado por el dueño (`mis_tandas.fuentes.todas`),
  agrupado por producto, con su enlace guardado (o no) y cuántos vídeos ya
  están en la cola del publicador.
- `guardar_enlace(...)`: SHEIN tal cual (validado) o ASIN → Amazon con el tag
  de la cuenta; `sin_equivalente` si no hay nada parecido.
- `encolar(slug)`: encola (idempotente por `video_path`) los vídeos de los
  productos CON enlace, con el ritmo/horas `producto` de la cuenta. Los MUDOS
  van con música del banco (`services/musica.py`); el SET guarda el original.
- `links_publicos(slug)` / `foto_publica(...)`: la página pública /links.

Identidad del producto (`producto_key`): hash de `clave_producto`, que es
`norm(tienda)|norm(título)` (minúsculas, sin acentos ni espacios dobles; la misma idea
que `mis_tandas.servicio._clave_producto`). Es lo único que comparten el POV
BOF, todos los modos del Largo y las copias de Productos Q4 de un mismo
producto: el id de fila lleva fuente/carpeta/modo y cambia en cada copia. Sin
título (textos sin extraer) cae al sitio en el catálogo.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
import unicodedata
import zoneinfo
from pathlib import Path

from src.multiplataforma import config
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, enlaces_repo, publicaciones_repo, redis_base
from src.multiplataforma.services import enlaces, ingesta, musica, textos, video_url

logger = logging.getLogger(__name__)

ORIGEN = "tandas"
MAX_LINKS = 300
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
    """Vídeos montados del dueño (POV + Largo, Multimodo, Aleatorios y réplicas
    virales ya montadas), sin los que ha quitado de Mis tandas."""
    from src.mis_tandas import fuentes

    pov, mm, alea = fuentes.todas(dueno)
    try:
        rv = fuentes.replicas_video(dueno)
    except Exception:  # noqa: BLE001 — sin réplicas, el resto sigue
        rv = []
    from src.mis_tandas import servicio

    try:
        fuera = servicio.ocultos(dueno)
    except Exception:  # noqa: BLE001 — sin la lista de ocultos, salen todos
        fuera = set()
    try:
        epo, sem = servicio.epocas(dueno), servicio.semaforos(dueno)
    except Exception:  # noqa: BLE001 — sin época ni semáforo: neutro y sin revisar
        epo, sem = {}, {}
    from src.mis_tandas import config as tandas_config

    out = []
    for f in pov + mm + alea + rv:
        if not f.get("video_path") or f["id"] in fuera:
            continue
        f["epoca"] = epo.get(f["id"]) or servicio._epoca_defecto(f)
        f["semaforo"] = (servicio._semaforo_vigente(sem.get(f["id"]), f) or {}).get("color", "")
        # Cuentas que en TikTok solo suben hablados: sus mudos van solo a Meta.
        f["solo_meta"] = dueno in tandas_config.SOLO_HABLADOS and not servicio.habla(f)
        out.append(f)
    return out


SEP_DUENO = "::"


def filas_cuenta(c: CuentaDestino) -> list[dict]:
    """Las filas de TODOS los dueños de la cuenta. Las de un dueño extra llevan
    el usuario delante del id (`nestor2::pov|…`) para sacar luego su foto."""
    out = []
    for u in c.duenos():
        for f in filas(u):
            if u != c.dueno:
                f = {**f, "id": f"{u}{SEP_DUENO}{f['id']}"}
            out.append(f)
    return out


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
    for f in filas_cuenta(c):
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
                   precio: str = "", temporada: str | None = None) -> dict:
    """Guarda el enlace del producto. `shein`/`asin` = 'sin_equivalente' (o
    ambos vacíos con `nota`) marcan que no hay un producto parecido."""
    c = cuenta_o_error(slug)
    if not enlaces_repo.key_valida(producto_key_):
        raise ErrorTandas(f"producto_key no válida: {producto_key_!r}")
    shein, asin, enlace = (shein or "").strip(), (asin or "").strip(), (enlace or "").strip()
    sin = enlaces_repo.SIN_EQUIVALENTE in (shein.lower(), asin.lower(), enlace.lower())
    datos: dict = {"nota": nota.strip()}
    if temporada is not None:  # None = no tocar la que tuviera; "" = todo el año
        temporada = temporada.strip().lower()
        if temporada and temporada not in config.TEMPORADAS:
            raise ErrorTandas(f"temporada no válida: {temporada!r} (vale {sorted(config.TEMPORADAS)} o vacío)")
        datos["temporada"] = temporada
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
    for f in filas_cuenta(c):
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
                                                                   "ya_encolados": 0, "ruta_no_valida": 0,
                                                                   "fuera_temporada": 0, "rojo": 0}}
    mes = time.localtime(ahora).tm_mon
    candidatas = []
    for f in filas_cuenta(c):
        if f["video_path"] in ya:
            informe["omitidas"]["ya_encolados"] += 1
            continue
        if f.get("semaforo") == "rojo":
            informe["omitidas"]["rojo"] += 1
            continue
        # Los mudos de «Solo Meta» no se suben a TikTok: basta con que estén revisados.
        meta_ok = f.get("solo_meta") and f.get("semaforo") in ("verde", "ambar")
        if not incluir_no_subidos and not f.get("uploaded") and not meta_ok:
            informe["omitidas"]["no_subidos"] += 1
            continue
        if prioridad(f, dt.datetime.fromtimestamp(ahora, _zona()).date())[0] == config.PRIORIDAD_FUERA:
            informe["omitidas"]["fuera_temporada"] += 1
            continue
        k = producto_key(f)
        e = guardados.get(k) or {}
        if e.get("sin_equivalente") or not e.get("enlace"):
            informe["omitidas"]["sin_enlace"] += 1
            continue
        temp = e.get("temporada") or ""
        if temp and mes not in config.TEMPORADAS.get(temp, ()):
            informe["omitidas"]["fuera_temporada"] += 1
            continue
        if not video_url.servible(f["video_path"]) or not video_url.ruta_permitida(f["video_path"]):
            informe["omitidas"]["ruta_no_valida"] += 1
            continue
        candidatas.append((f, k, e))
    hoy = dt.datetime.fromtimestamp(ahora, _zona()).date()
    candidatas.sort(key=lambda t: (prioridad(t[0], hoy),
                                   float(t[0].get("uploaded_at") or 0) or float(t[0].get("video_listo_at") or 0)))
    if limite > 0:
        candidatas = candidatas[:limite]

    reloj = ingesta.huecos(ritmo, horas, max(ahora, ingesta._ultima_programada(slug, TIPO)), semilla=slug)
    for f, k, e in candidatas:
        # El título de la ficha de la tienda (SHEIN/Amazon) es largo y a veces
        # en inglés: el texto sale del caption + emojis de la fila, en español.
        titulo = f.get("titulo") or e.get("titulo") or ""
        caption = " ".join(x for x in ((f.get("caption") or titulo).strip(), (f.get("emojis") or "").strip()) if x)
        tags = _hashtags(titulo, e["enlace"], slug)
        t = textos.construir(titulo="", caption=caption, enlace=e["enlace"], hashtags=tags,
                             plataformas=config.PLATAFORMAS)
        # Mudos (multimodo de 10 s): copia con música del banco según su
        # sugerencia; con voz, o si algo falla, el original tal cual.
        mus = musica.con_musica(f["video_path"], f.get("musica"), slug, log=logger.info)
        pub = Publicacion(
            cuenta=slug, video_path=mus["path"] if mus else f["video_path"], tipo=TIPO, producto_ref=k,
            titulo=titulo[: config.MAX_TITULO_PINTEREST], caption=caption, hashtags=tags, textos=t["textos"], comentario=t["comentario"],
            enlace=e["enlace"], plataformas=list(config.PLATAFORMAS), programada_en=next(reloj), origen=ORIGEN,
        )
        pub, creada = publicaciones_repo.encolar(pub)
        r.sadd(_key_encoladas(slug), f["video_path"])
        ya.add(f["video_path"])
        informe["encoladas"].append({"id": pub.id, "producto_key": k, "titulo": titulo,
                                     "programada_en": pub.programada_en, "creada": creada,
                                     "musica": f"{mus['estilo']}/{mus['pista']}" if mus else ""})
    informe["total"] = len(informe["encoladas"])
    return informe


# ---------------------------------------------------------------------------
# Prioridad por época y replanificación de la cola
# ---------------------------------------------------------------------------
def _zona() -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo(config.ZONA_HORARIA)


def en_ventana(epoca: str, hoy: dt.date) -> bool:
    v = config.VENTANA_EPOCA.get(epoca)
    if not v:
        return True
    (d1, m1), (d2, m2) = v
    a, b, x = (m1, d1), (m2, d2), (hoy.month, hoy.day)
    return a <= x <= b if a <= b else (x >= a or x <= b)


def prioridad(f: dict, hoy: dt.date) -> tuple[int, int]:
    """(época, semáforo): menor sale antes. Réplicas virales primero; luego la
    época que se acaba antes; fuera de su ventana, al final."""
    sem = config.PRIORIDAD_SEMAFORO.get(f.get("semaforo") or "", 1)
    if f.get("nicho") == "rv":
        return config.PRIORIDAD_REPLICA, sem
    ep = f.get("epoca") or "neutro"
    if not en_ventana(ep, hoy):
        return config.PRIORIDAD_FUERA, sem
    return config.PRIORIDAD_EPOCA.get(ep, config.PRIORIDAD_EPOCA["neutro"]), sem


def _original(path: str) -> str:
    """La copia con música guarda al lado un .json con el vídeo original."""
    try:
        meta = Path(path).with_suffix(".json")
        if meta.is_file():
            return str(json.loads(meta.read_text("utf-8")).get("original") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _empezada(p: Publicacion) -> bool:
    return any(p.estado.get(pl) == config.ESTADO_PUBLICADO
               or ((p.resultados.get(pl) or {}) and not (p.resultados.get(pl) or {}).get("dry_run"))
               for pl in p.plataformas)


def replanificar(slug: str, *, ahora: float | None = None, margen_s: int = 2700) -> dict:
    """Vuelve a repartir la cola de la cuenta desde ahora, sin huecos, con su
    ritmo y sus horas. En `producto`, por prioridad (`prioridad`); en el resto,
    en el orden que ya tenían. No toca lo que ya ha empezado a publicarse ni lo
    que sale en los próximos `margen_s` (el tick puede estar con ello)."""
    c = cuenta_o_error(slug)
    ahora = time.time() if ahora is None else ahora
    hoy = dt.datetime.fromtimestamp(ahora, _zona()).date()
    info: dict[str, dict] = {}
    if c.dueno:
        info = {f["video_path"]: f for f in filas_cuenta(c)}
    pendientes = [p for p in publicaciones_repo.de_cuenta(slug) if not p.terminada and not _empezada(p)]
    out: dict = {"cuenta": slug, "movidas": 0}
    for tipo in config.TIPOS:
        pubs = [p for p in pendientes if p.tipo == tipo]
        if not pubs:
            continue
        fijas = [p for p in pubs if p.programada_en <= ahora + margen_s]
        mover = [p for p in pubs if p.programada_en > ahora + margen_s]
        if tipo == TIPO:
            mover.sort(key=lambda p: (prioridad(info.get(p.video_path) or info.get(_original(p.video_path)) or {}, hoy),
                                      p.programada_en))
        else:
            mover.sort(key=lambda p: p.programada_en)
        ritmo = int((c.ritmo or {}).get(tipo, config.RITMO_DEFAULT.get(tipo, 1))) or 1
        horas = (c.horas or {}).get(tipo) or config.HORAS_DEFAULT.get(tipo, ["12:00"])
        reloj = ingesta.huecos(ritmo, horas, max([ahora] + [p.programada_en for p in fijas]), semilla=slug)
        for p in mover:
            t = next(reloj)
            if abs(t - p.programada_en) > 1:
                p.programada_en = t
                publicaciones_repo.guardar(p)
                out["movidas"] += 1
        out[tipo] = len(pubs)
    return out


def replanificar_todas(*, ahora: float | None = None, cada_s: int = 3600, log=lambda _: None) -> list[dict]:
    """Lo llama el tick: como mucho una vez por hora, solo cuentas con `priorizar_epocas`."""
    ahora = time.time() if ahora is None else ahora
    r = redis_base.get_redis()
    if ahora - float((r.get_json("replanificar") or {}).get("at") or 0) < cada_s:
        return [{"motivo": "reciente"}]
    r.set_json("replanificar", {"at": ahora})
    out = []
    for c in cuentas_repo.listar():
        if not (c.activa and c.priorizar_epocas):
            continue
        try:
            inf = replanificar(c.slug, ahora=ahora)
        except Exception as e:  # noqa: BLE001 — una cuenta rota no para el tick
            inf = {"cuenta": c.slug, "error": str(e)}
        if inf.get("movidas") or inf.get("error"):
            log(f"[replanificar] {c.slug}: {inf.get('movidas', 0)} movidas {inf.get('error', '')}")
        out.append(inf)
    return out


def _hashtags(titulo: str, enlace: str, slug: str = "") -> list[str]:
    """Hashtags por categoría del producto (`config.HASHTAGS_CATEGORIA`) + los de la tienda.
    Sin categoría, los de la cuenta (`HASHTAGS_DEFECTO_CUENTA`) o los genéricos de hogar."""
    t = f" {_norm(titulo)} "
    tags = next((h for palabras, h in config.HASHTAGS_CATEGORIA if any(p in t for p in palabras)),
                config.HASHTAGS_DEFECTO_CUENTA.get(slug, config.HASHTAGS_DEFECTO))
    tienda = "shein" if enlaces.es_shein(enlace) else "amazon" if enlaces.es_amazon(enlace) else ""
    return list(tags) + config.HASHTAGS_TIENDA.get(tienda, [])


def auto_encolar(slug: str, *, ahora: float | None = None, cada_s: int = 3600) -> dict:
    """Mantiene en cola `auto_tandas` días de vídeos de producto: cuando un
    vídeo de un producto CON enlace se marca subido a TikTok, entra solo. Lo
    llama el tick; como mucho una vez por hora y cuenta (leer Mis tandas cuesta)."""
    c = cuenta_o_error(slug)
    dias = int(c.auto_tandas or 0)
    if dias <= 0:
        return {"cuenta": slug, "total": 0, "motivo": "apagado"}
    ahora = time.time() if ahora is None else ahora
    r = redis_base.get_redis()
    marca = f"auto_tandas:{slug}"
    ultima = float((r.get_json(marca) or {}).get("at") or 0)
    if ahora - ultima < cada_s:
        return {"cuenta": slug, "total": 0, "motivo": "reciente"}
    r.set_json(marca, {"at": ahora})
    ritmo = int((c.ritmo or {}).get(TIPO, config.RITMO_DEFAULT.get(TIPO, 1))) or 1
    en_cola = sum(1 for p in publicaciones_repo.de_cuenta(slug)
                  if p.tipo == TIPO and p.origen == ORIGEN and not p.terminada)
    hueco = dias * ritmo - en_cola
    if hueco <= 0:
        return {"cuenta": slug, "total": 0, "motivo": "cola llena", "en_cola": en_cola}
    return encolar(slug, limite=hueco, ahora=ahora)


def auto_encolar_todas(*, ahora: float | None = None, log=lambda _: None) -> list[dict]:
    out = []
    for c in cuentas_repo.listar():
        if not (c.activa and c.dueno and c.auto_tandas):
            continue
        try:
            inf = auto_encolar(c.slug, ahora=ahora)
        except Exception as e:  # noqa: BLE001 — una cuenta rota no para el tick
            inf = {"cuenta": c.slug, "error": str(e)}
        if inf.get("total") or inf.get("error"):
            log(f"[auto_tandas] {c.slug}: {inf.get('total', 0)} encoladas {inf.get('error', '')}")
        out.append({k: inf.get(k) for k in ("cuenta", "total", "motivo", "error") if inf.get(k) is not None})
    return out


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
    import threading

    threading.Thread(target=_precalentar_fotos, args=(slug, [p["id"] for p in datos["productos"]]),
                     daemon=True, name=f"links-fotos-{slug}").start()
    return datos


def categoria_link(titulo: str) -> str:
    """Categoría del producto por palabras del título (`config.CATEGORIAS_LINKS`)."""
    t = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode().lower()
    palabras = set(t.replace("/", " ").replace(",", " ").replace("-", " ").split()) | set(t.split())
    # Plurales sin listar: «sandals» → «sandal», «chaquetas» → «chaqueta».
    palabras |= {w[:-1] for w in palabras if w.endswith("s")} | {w[:-2] for w in palabras if w.endswith("es")}
    for nombre, claves in config.CATEGORIAS_LINKS:
        if palabras & set(claves):
            return nombre
    return config.CATEGORIA_OTROS


def _links_publicos(slug: str) -> dict:
    c = cuentas_repo.get(slug)
    if not c or not c.activa:
        raise ErrorTandas("No existe", status=404)
    cola = _cola_por_producto(slug)
    items = []
    for k, e in enlaces_repo.todos(slug).items():
        if e.get("sin_equivalente") or not e.get("enlace"):
            continue
        # Solo lo que YA salió en un vídeo/carrusel: los enlaces se preparan
        # en lote para la cola (cientos) y quien llega de la bio busca lo que
        # ha visto, no lo que se publicará dentro de tres semanas.
        publicado = _ultima_publicacion(cola.get(k, []))
        if not publicado:
            continue
        titulo = _corto(e.get("titulo") or "Producto")
        items.append((publicado, {
            "id": k,
            "titulo": titulo,
            "foto": f"/api/v1/multiplataforma/links/{slug}/foto/{k}",
            "enlace": e["enlace"],
            "tienda": "amazon" if enlaces.es_amazon(e["enlace"]) else ("shein" if enlaces.es_shein(e["enlace"]) else ""),
            "categoria": categoria_link(e.get("titulo") or ""),
            "publicado_en": int(publicado),
        }))
    items.sort(key=lambda t: t[0], reverse=True)
    productos_ = [i[1] for i in items[:MAX_LINKS]]
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


# Lo que ya se resolvió por (cuenta, producto, ancho): buscar la fila o la
# publicación lee TODA la cola de la cuenta (~1-4 s) y la miniatura ya está.
_FOTOS_TTL_S = 6 * 3600
_fotos_cache: dict[tuple[str, str, str, int], tuple[float, Path]] = {}


def foto_publica(slug: str, producto_key_: str, ancho: int = 400) -> Path | str:
    """Path de la miniatura, o la URL https externa (`foto_url`) a la que
    redirigir. Solo productos con enlace publicable de una cuenta activa."""
    c = cuentas_repo.get(slug)
    e = enlaces_repo.get(slug, producto_key_) if c and c.activa else None
    if not e or e.get("sin_equivalente") or not e.get("enlace"):
        raise ErrorTandas("No existe", status=404)
    if e.get("foto_url"):
        return str(e["foto_url"])
    # La comprobación de arriba va siempre (un enlace borrado deja de tener
    # foto al momento); lo caro, buscar la fila o la publicación, se recuerda.
    clave = (slug, producto_key_, str(e.get("fila_id") or ""), ancho)
    hit = _fotos_cache.get(clave)
    if hit and time.time() - hit[0] < _FOTOS_TTL_S and hit[1].is_file():
        return hit[1]
    res: Path | None = None
    if e.get("fila_id"):
        try:
            res = foto_interna(c, e["fila_id"], ancho)
        except ErrorTandas:
            pass  # la fila ya no existe: se prueba con lo publicado
    if res is None:
        res = _foto_de_lo_publicado(slug, producto_key_, ancho)
    _fotos_cache[clave] = (time.time(), res)
    return res


def _foto_de_lo_publicado(slug: str, producto_key_: str, ancho: int) -> Path:
    """Sin fila de Mis tandas (carruseles, ingesta del Drive): la 1.ª foto del
    carrusel o un fotograma del vídeo que se publicó. Antes salía un hueco
    blanco en /links para casi la mitad de los productos."""
    import subprocess

    from src.nicho_pov_bof.services import thumbs

    pubs = sorted(_cola_por_producto(slug).get(producto_key_, []),
                  key=lambda p: _ultima_publicacion([p]), reverse=True)
    for p in pubs:
        origen = next((Path(i) for i in p.imagenes if Path(i).is_file()), None)
        if origen is None and Path(p.video_path or "").is_file():
            v = Path(p.video_path)
            if v.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                origen = v
            else:
                origen = Path(config.links_cache_dir()) / f"pub_{p.id}.jpg"
                if not (origen.is_file() and origen.stat().st_size > 0):
                    origen.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(v),
                                        "-frames:v", "1", "-vf", "scale=720:-2", str(origen)],
                                       check=True, timeout=60)
                    except Exception:  # noqa: BLE001 — se prueba la siguiente
                        continue
        if origen is not None and origen.is_file():
            try:
                return thumbs.miniatura(origen, ancho) or origen
            except Exception:  # noqa: BLE001
                return origen
    raise ErrorTandas("Sin foto", status=404)


# Anchos que pide la página (/links): 640 el último vídeo, 192 la lista.
_ANCHOS_LINKS = (640, 192)


def _precalentar_fotos(slug: str, claves: list[str]) -> None:
    """Deja hechas las miniaturas para que la primera visita no espere a
    bajarlas del Drive y recortarlas una a una."""
    for k in claves:
        for w in _ANCHOS_LINKS:
            try:
                foto_publica(slug, k, w)
            except Exception:  # noqa: BLE001 — sin foto: la página pone el hueco
                break


def foto_interna(c: CuentaDestino, fila_id: str, ancho: int = 400) -> Path:
    if not fila_id:
        raise ErrorTandas("Sin foto", status=404)
    from src.mis_tandas import servicio

    try:
        usuario, _, id_ = fila_id.rpartition(SEP_DUENO)
        return servicio.foto(usuario or c.dueno, id_, ancho)
    except servicio.ErrorTanda as err:
        raise ErrorTandas(str(err), status=err.status) from err
