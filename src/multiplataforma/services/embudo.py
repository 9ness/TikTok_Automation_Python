"""Embudo de la página de la bio (`/links/<cuenta>`).

En Instagram el pie de un reel no lleva enlace: quien quiere el producto pasa
por la bio. No se sabía cuánta gente llegaba a la página ni qué abría. Aquí se
cuenta, por día, las visitas a la página y los clics en cada producto.

- El enlace de la página sigue yendo DIRECTO a la tienda (Amazon no admite
  acortadores): el clic lo avisa el navegador aparte (`sendBeacon`).
- Solo contadores: ni IP, ni cookies, ni identificador de quien entra.
- Un hash de Redis por cuenta y mes, `embudo:<slug>:<AAAA-MM>`, con campos
  `v:<DD>` (visitas) y `c:<DD>:<producto>` (clics). Solo se cuentan productos
  que están en la página, así que el hash no crece con basura.
- Los rastreadores de vista previa no cuentan, y hay un tope por minuto para
  que una ráfaga no infle las cifras.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from zoneinfo import ZoneInfo

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo, enlaces_repo
from src.multiplataforma.repos.redis_base import get_redis
from src.multiplataforma.services import enlace_corto, tandas

logger = logging.getLogger(__name__)

VISITA, CLIC = "visita", "clic"


def _dia(ts: float) -> dt.date:
    return dt.datetime.fromtimestamp(ts, ZoneInfo(config.ZONA_HORARIA)).date()


def _clave(slug: str, dia: dt.date) -> str:
    return f"embudo:{slug}:{dia:%Y-%m}"


def registrar(slug: str, tipo: str, producto: str = "", *, user_agent: str = "", ahora: float | None = None) -> bool:
    """Suma una visita o un clic. Devuelve si contó; nunca lanza."""
    if tipo not in (VISITA, CLIC) or not cuentas_repo.slug_valido(slug) or enlace_corto.es_bot(user_agent):
        return False
    ahora = time.time() if ahora is None else ahora
    try:
        pagina = tandas.links_publicos(slug)  # cacheada: la página la acaba de pedir
        if tipo == CLIC and producto not in {p["id"] for p in pagina["productos"]}:
            return False
        r = get_redis()
        if r.incr_ttl(f"embudo:tope:{slug}:{int(ahora // 60)}", 120) > config.EMBUDO_TOPE_MINUTO:
            return False
        dia = _dia(ahora)
        campo = f"v:{dia:%d}" if tipo == VISITA else f"c:{dia:%d}:{producto}"
        r.hincrby(_clave(slug, dia), campo)
        return True
    except tandas.ErrorTandas:
        return False  # la cuenta no existe o está apagada
    except Exception as e:  # noqa: BLE001 — medir nunca debe romper la página
        logger.warning("embudo %s: %s", slug, type(e).__name__)
        return False


def leer(slug: str, desde: float, hasta: float) -> dict:
    """Visitas y clics de los días posteriores a `desde` hasta el de `hasta`."""
    primero, ultimo = _dia(desde) + dt.timedelta(days=1), _dia(hasta)
    por_dia: dict[str, dict[str, int]] = {}
    productos: dict[str, int] = {}
    dias = [primero + dt.timedelta(days=i) for i in range((ultimo - primero).days + 1)]
    for anio, mes in sorted({(d.year, d.month) for d in dias}):
        for campo, n in get_redis().hgetall(f"embudo:{slug}:{anio:04d}-{mes:02d}").items():
            partes = campo.split(":", 2)
            try:
                dia = dt.date(anio, mes, int(partes[1]))
            except (IndexError, ValueError):
                continue
            if not primero <= dia <= ultimo:
                continue
            fila = por_dia.setdefault(dia.isoformat(), {"visitas": 0, "clics": 0})
            if partes[0] == "v":
                fila["visitas"] += n
            elif partes[0] == "c" and len(partes) == 3:
                fila["clics"] += n
                productos[partes[2]] = productos.get(partes[2], 0) + n
    return {"visitas": sum(f["visitas"] for f in por_dia.values()),
            "clics": sum(f["clics"] for f in por_dia.values()),
            "por_dia": dict(sorted(por_dia.items())), "productos": productos}


def resumen(slug: str, desde: float, hasta: float, top: int = 15) -> dict:
    """`leer` con los productos más abiertos y su título (para el informe)."""
    datos = leer(slug, desde, hasta)
    titulos = enlaces_repo.todos(slug) if datos["productos"] else {}
    orden = sorted(datos["productos"].items(), key=lambda kv: -kv[1])[:top]
    datos["productos"] = [{"id": k, "titulo": str((titulos.get(k) or {}).get("titulo") or "")[:70], "clics": n}
                          for k, n in orden]
    return datos
