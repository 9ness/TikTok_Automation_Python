"""Tandas, orden fijo, fecha orientativa y los botones de «Mis tandas»."""

from __future__ import annotations

import datetime as dt
import shutil
import threading
import time
import zoneinfo
from pathlib import Path

from src.mis_tandas import config, fuentes

_TZ = zoneinfo.ZoneInfo("Europe/Madrid")

# Lista ya leída por usuario: (cuándo, filas en orden). Los botones la
# corrigen en el sitio para no volver a leer Redis entero en cada toque.
_cache: dict[str, tuple[float, list[dict]]] = {}
_cerrojo = threading.Lock()


def _redis():
    # El orden vive junto a las preferencias de menú (`ui:menu:<usuario>`):
    # las dos cosas son de la persona, no de un nicho.
    from src.viralizacion.repos.redis_base import get_viralizacion_redis

    return get_viralizacion_redis()


# ---------------------------------------------------------------------------
# Orden fijo
# ---------------------------------------------------------------------------
def _clave_orden(f: dict) -> tuple:
    # Lo subido primero (por cuándo se subió) y luego lo pendiente por cuándo
    # se montó: así las tandas cerradas quedan delante y no se mueven.
    if f["uploaded"]:
        return (0, f["uploaded_at"] or f["orden_at"])
    return (1, f["orden_at"])


def _mezclar(a: list[dict], b: list[dict]) -> list[dict]:
    """Une dos listas sin cambiar el orden INTERNO de ninguna (el multimodo
    trae el suyo, que intercala formatos y no es cronológico)."""
    i = j = 0
    salida: list[dict] = []
    while i < len(a) and j < len(b):
        if _clave_orden(b[j]) < _clave_orden(a[i]):
            salida.append(b[j])
            j += 1
        else:
            salida.append(a[i])
            i += 1
    return salida + a[i:] + b[j:]


def _ordenar(usuario: str, pov: list[dict], mm: list[dict]) -> list[dict]:
    por_id = {f["id"]: f for f in pov + mm}
    r = _redis()
    clave = config.ORDEN_KEY.format(usuario=usuario or "ness")
    guardado = (r.get_json(clave) or {}).get("claves") or [] if r.is_available() else []
    conocidos = set(guardado)
    nuevos_pov = sorted((f for f in pov if f["id"] not in conocidos), key=_clave_orden)
    nuevos_mm = [f for f in mm if f["id"] not in conocidos]
    nuevos = _mezclar(nuevos_pov, nuevos_mm)
    if nuevos and r.is_available():
        r.set_json(clave, {"claves": guardado + [f["id"] for f in nuevos],
                           "updated_at": time.time()})
    # Lo que ya no existe (vídeo borrado) no sale, pero conserva su puesto
    # guardado por si vuelve.
    return [por_id[i] for i in guardado if i in por_id] + nuevos


def filas(usuario: str, fresco: bool = False) -> list[dict]:
    usuario = usuario or "ness"
    ahora = time.time()
    with _cerrojo:
        c = _cache.get(usuario)
        if c and not fresco and ahora - c[0] < config.CACHE_S:
            return c[1]
    pov, mm = fuentes.todas(usuario)
    ordenadas = _ordenar(usuario, pov, mm)
    with _cerrojo:
        _cache[usuario] = (time.time(), ordenadas)
    return ordenadas


# ---------------------------------------------------------------------------
# Ocultos: vídeos que el usuario ya no quiere subir. Salen de la lista y su
# hueco lo ocupa el siguiente; no se borra nada del nicho.
# ---------------------------------------------------------------------------
def ocultos(usuario: str) -> set[str]:
    r = _redis()
    if not r.is_available():
        return set()
    return set((r.get_json(config.OCULTOS_KEY.format(usuario=usuario or "ness")) or {}).get("ids") or [])


def ocultar(usuario: str, id_: str, oculto: bool = True) -> dict:
    usuario = usuario or "ness"
    _fila_de(usuario, id_)
    r = _redis()
    if not r.is_available():
        raise ErrorTanda("Redis no está disponible.", status=503)
    clave = config.OCULTOS_KEY.format(usuario=usuario)
    ids = set((r.get_json(clave) or {}).get("ids") or [])
    (ids.add if oculto else ids.discard)(id_)
    r.set_json(clave, {"ids": sorted(ids), "updated_at": time.time()})
    return {"ok": True, "id": id_, "oculto": oculto, "ocultos": len(ids)}


def _cerrado(f: dict) -> bool:
    return bool(f["uploaded"] or f["sin_stock"])


# ---------------------------------------------------------------------------
# Tandas
# ---------------------------------------------------------------------------
def _publica(f: dict) -> dict:
    """Lo que va al navegador (sin la ruta del disco)."""
    from src.mis_tandas.config import NICHOS

    meta = NICHOS.get(f["nicho"], {})
    salida = {k: v for k, v in f.items() if k not in ("video_path", "orden_at")}
    salida["nicho_label"] = meta.get("label", f["nicho"])
    salida["hashtags_nicho"] = meta.get("hashtags", "")
    salida["pantalla"] = meta.get("pantalla", "")
    return salida


def tandas(usuario: str, todas: bool = False, fresco: bool = False, ver_ocultos: bool = False) -> dict:
    """Las tandas ABIERTAS con sus vídeos y, de las cerradas, solo cuántas hay
    (con `todas`, también sus vídeos). Una tanda está cerrada cuando todo lo
    suyo está subido o sin stock."""
    usuario = usuario or "ness"
    escondidos = ocultos(usuario)
    completa = filas(usuario, fresco=fresco)
    lista = [f for f in completa if f["id"] not in escondidos]
    n = config.POR_TANDA
    grupos = [lista[i:i + n] for i in range(0, len(lista), n)]

    dia = dt.datetime.now(_TZ).date()
    hoy = sum(
        1 for f in lista
        if f["uploaded"] and f["uploaded_at"]
        and dt.datetime.fromtimestamp(f["uploaded_at"], _TZ).date() == dia
    )
    por_dia = max(1, config.TANDAS_DIA.get(usuario, 1))
    if hoy >= config.SUBIDAS_DIA_HECHO * por_dia:
        dia += dt.timedelta(days=1)

    from src.nicho_ropa import config as ropa_config

    salida: list[dict] = []
    abiertas_vistas = 0
    cerradas = 0
    precalentar: list[dict] = []
    for i, grupo in enumerate(grupos):
        abierta = not all(_cerrado(f) for f in grupo)
        t = {
            "numero": i + 1,
            "total": len(grupo),
            "subidos": sum(1 for f in grupo if f["uploaded"]),
            "sin_stock": sum(1 for f in grupo if f["sin_stock"] and not f["uploaded"]),
            "rehacer": sum(1 for f in grupo if f["rehacer"] and not f["uploaded"]),
            "abierta": abierta,
            "nichos": sorted({f["nicho"] for f in grupo}),
        }
        if abierta:
            # Fecha orientativa: `por_dia` tandas por día desde hoy (o mañana).
            dia_tanda = dia + dt.timedelta(days=abiertas_vistas // por_dia)
            t["fecha"] = dia_tanda.isoformat()
            t["temporada"] = ropa_config.etiqueta_temporada(dia_tanda)
            if abiertas_vistas < config.PRECALENTAR_TANDAS:
                precalentar += [f for f in grupo if not _cerrado(f)]
            abiertas_vistas += 1
        else:
            cerradas += 1
        if abierta or todas:
            t["items"] = [_publica(f) for f in grupo]
            salida.append(t)
    _precalentar(usuario, precalentar)
    return {
        "usuario": usuario,
        "por_tanda": n,
        "total": len(lista),
        "subidos": sum(1 for f in lista if f["uploaded"]),
        "sin_stock": sum(1 for f in lista if f["sin_stock"] and not f["uploaded"]),
        "subidos_hoy": hoy,
        "cerradas": cerradas,
        "abiertas": abiertas_vistas,
        "ocultos": sum(1 for f in completa if f["id"] in escondidos),
        "ocultos_items": [_publica(f) for f in completa if f["id"] in escondidos] if ver_ocultos else [],
        "tandas": salida,
    }


# ---------------------------------------------------------------------------
# Botones: escriben en el documento del nicho
# ---------------------------------------------------------------------------
class ErrorTanda(Exception):
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def _partes(id_: str) -> list[str]:
    p = (id_ or "").split(fuentes.SEP)
    if p[0] == "pov" and len(p) == 4:
        return p
    if p[0] == "largo" and len(p) == 5:
        return p
    if p[0] == "mm" and len(p) == 3:
        return p
    raise ErrorTanda(f"Vídeo desconocido: {id_!r}")


def _cuota(ref: str, usuario: str, subido: bool) -> None:
    try:
        from src.cuotas.repos import cuota_repo

        cuota_repo.marcar("videos", ref, usuario, subido)
    except Exception:  # noqa: BLE001 — el contador no tumba el botón
        pass


def marcar(
    usuario: str, id_: str, *, uploaded: bool | None = None,
    sin_stock: bool | None = None, rehacer: bool | None = None,
    rehacer_nota: str | None = None,
) -> dict:
    """Aplica UN cambio en el documento original y lo refleja en la caché."""
    usuario = usuario or "ness"
    p = _partes(id_)
    # Solo vídeos que estén en SUS tandas: un id inventado o de otro usuario
    # crearía un documento nuevo en el nicho (los repos hacen upsert).
    _fila_de(usuario, id_)
    cambios: dict = {}
    if p[0] == "pov":
        _, fuente, carpeta, prod = p
        from src.nicho_pov_bof.repos import product_repo as pov_repo

        if rehacer is not None:
            raise ErrorTanda("El POV BOF no tiene «rehacer»: se rehace desde su pantalla.")
        if sin_stock is not None:
            pov_repo.save_extracted_texts(fuente, carpeta, {prod: {"sin_stock": bool(sin_stock)}})
            cambios["sin_stock"] = bool(sin_stock)
        if uploaded is not None:
            hecho = pov_repo.update_product(fuente, carpeta, prod, usuario=usuario, uploaded=bool(uploaded))
            cambios["uploaded"] = bool(uploaded)
            cambios["uploaded_at"] = float(hecho.get("uploaded_at") or (time.time() if uploaded else 0))
            _cuota(f"pov_bof|{fuente}|{carpeta}|{prod}", usuario, bool(uploaded))
    elif p[0] == "largo":
        _, fuente, carpeta, prod, modo = p
        from src.nicho_pov_bof.repos import product_repo as pov_repo
        from src.nicho_pov_bof_largo import config as largo_config
        from src.nicho_pov_bof_largo.repos import product_repo as largo_repo

        # El modo SIEMPRE explícito: vacío haría que el repo mirara el modo
        # activo de la carpeta y escribiría en el documento de otro modo.
        modo = modo or largo_config.ESTILO_GUION_DEFECTO
        campos: dict = {}
        if uploaded is not None:
            campos["uploaded"] = bool(uploaded)
            campos["uploaded_at"] = time.time() if uploaded else 0
        if rehacer is not None:
            campos["rehacer"] = bool(rehacer)
            campos["rehacer_at"] = time.time() if rehacer else 0
            campos["rehacer_nota"] = (rehacer_nota or "").strip()[:300] if rehacer else ""
        if campos:
            largo_repo.update_product(fuente, carpeta, prod, usuario=usuario, estilo=modo, **campos)
            cambios.update(campos)
        if sin_stock is not None:
            pov_repo.save_extracted_texts(fuente, carpeta, {prod: {"sin_stock": bool(sin_stock)}})
            cambios["sin_stock"] = bool(sin_stock)
        if uploaded is not None:
            _cuota(f"pov_bof_largo|{fuente}|{carpeta}|{prod}", usuario, bool(uploaded))
    else:
        _, carpeta, prod = p
        from src.api.routers.nicho_ropa import prendas
        from src.api.schemas.nicho_ropa.models import PrendaEstadoRequest

        # Los mismos endpoints que usa la pantalla del multimodo, en proceso:
        # misma validación, mismo contador del día.
        if uploaded is not None:
            r = prendas.multimodo_subido(
                PrendaEstadoRequest(carpeta=carpeta, producto=prod, uploaded=bool(uploaded)), usuario=usuario,
            )
            cambios["uploaded"] = bool(uploaded)
            cambios["uploaded_at"] = float(r.get("uploaded_at") or 0)
        if sin_stock is not None:
            prendas.multimodo_sin_stock(
                PrendaEstadoRequest(carpeta=carpeta, producto=prod, sin_stock=bool(sin_stock)), usuario=usuario,
            )
            cambios["sin_stock"] = bool(sin_stock)
        if rehacer is not None:
            r = prendas.multimodo_rehacer(
                PrendaEstadoRequest(carpeta=carpeta, producto=prod, rehacer=bool(rehacer),
                                    rehacer_nota=rehacer_nota or ""),
                usuario=usuario,
            )
            cambios.update({k: r[k] for k in ("rehacer", "rehacer_nota") if k in r})
    if not cambios:
        raise ErrorTanda("No hay nada que cambiar.")

    # Reflejo en la caché. El sin stock es del PRODUCTO: si el mismo producto
    # sale con otro vídeo (POV y Largo), se marcan los dos.
    with _cerrojo:
        c = _cache.get(usuario)
        if c:
            for f in c[1]:
                if f["id"] == id_:
                    f.update({k: v for k, v in cambios.items() if k in f})
                elif "sin_stock" in cambios and p[0] in ("pov", "largo") and f["nicho"] in ("pov", "largo") \
                        and f["source"] == p[1] and f["carpeta"] == p[2] and f["producto"] == p[3]:
                    f["sin_stock"] = cambios["sin_stock"]
    return {"ok": True, "id": id_, **cambios}


# ---------------------------------------------------------------------------
# Vídeo y foto
# ---------------------------------------------------------------------------
def _fila_de(usuario: str, id_: str) -> dict:
    _partes(id_)
    for f in filas(usuario):
        if f["id"] == id_:
            return f
    # Recién montado y aún no en la caché.
    for f in filas(usuario, fresco=True):
        if f["id"] == id_:
            return f
    raise ErrorTanda("Ese vídeo no es tuyo o ya no existe.", status=404)


def _cache_nicho(f: dict, usuario: str) -> Path | None:
    """La copia local que deja el MONTAJE (la misma que sirve la pantalla del
    nicho): es instantánea, el Drive tarda 20-50 s en frío."""
    from src.nicho_pov_bof import config as pov_config

    if f["nicho"] == "pov":
        return Path(pov_config.video_cache_path(f["carpeta"], f["producto"], usuario))
    if f["nicho"] == "largo":
        return Path(pov_config.video_cache_path(
            f["carpeta"], f["producto"], usuario, nicho="largo", estilo=f.get("modo") or "",
        ))
    return None


def _copia_local(f: dict, usuario: str) -> Path | None:
    """Copia en disco del vídeo. Primero la del nicho, si es ESTE vídeo (su
    nombre no lleva el modo del Largo ni la fuente: se comprueba que mide lo
    mismo que el del Drive). Si no, una propia con la versión en el nombre."""
    import re

    origen = Path(f["video_path"])
    try:
        tam_origen = origen.stat().st_size if origen.is_file() else -1
    except OSError:
        tam_origen = -1
    cand = _cache_nicho(f, usuario)
    if cand is not None and cand.is_file():
        try:
            if tam_origen < 0 or cand.stat().st_size == tam_origen:
                return cand
        except OSError:
            pass
    nombre = re.sub(
        r"[^A-Za-z0-9_.-]+", "_",
        f"{f['nicho']}__{usuario}__{f['source']}__{f['carpeta']}__{f['producto']}"
        f"__{f['modo']}__{int(f['video_listo_at'])}",
    )
    destino = Path(config.cache_dir()) / f"{nombre}.mp4"
    if destino.is_file():
        return destino
    if tam_origen < 0:
        return None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".part")
        shutil.copy2(origen, tmp)
        tmp.replace(destino)
        return destino
    except OSError:
        return origen


_calentando: set[str] = set()


def _limpiar_cache(dias: int = 10) -> None:
    import os

    d = Path(config.cache_dir())
    if not d.is_dir():
        return
    limite = time.time() - dias * 86400
    for p in d.iterdir():
        try:
            if p.is_file() and p.stat().st_mtime < limite:
                os.remove(p)
        except OSError:
            pass


def _precalentar(usuario: str, lista: list[dict]) -> None:
    """Deja preparados, en segundo plano, los vídeos y las fotos de las
    próximas tandas: al abrirlas ya salen del disco."""
    sin_foto = [f for f in lista if ("foto|" + f["id"]) not in _calentando]
    if sin_foto:
        _calentando.update("foto|" + f["id"] for f in sin_foto)

        def _fotos() -> None:
            try:
                ids = _resolver_fotos(sin_foto)
                from src.nicho_pov_bof.services import drive_client

                for fid in ids.values():
                    try:
                        drive_client.fetch_photo(fid)
                    except Exception:  # noqa: BLE001
                        pass
            finally:
                for f in sin_foto:
                    _calentando.discard("foto|" + f["id"])

        threading.Thread(target=_fotos, daemon=True).start()
    pendientes = [f for f in lista if f["nicho"] in ("pov", "largo") and f["id"] not in _calentando]
    mm = [f["video_path"] for f in lista if f["nicho"] == "mm" and f["video_path"]]
    if mm:
        try:
            from src.api.routers.nicho_ropa import prendas

            prendas._precalentar(mm)
        except Exception:  # noqa: BLE001
            pass
    if not pendientes:
        return
    _calentando.update(f["id"] for f in pendientes)

    def _leer() -> None:
        _limpiar_cache()
        for f in pendientes:
            try:
                _copia_local(f, usuario)
            except Exception:  # noqa: BLE001
                pass
            finally:
                _calentando.discard(f["id"])

    threading.Thread(target=_leer, daemon=True).start()


def video(usuario: str, id_: str) -> tuple[Path, str]:
    """(fichero, nombre). Para el multimodo se usa su propio endpoint."""
    f = _fila_de(usuario, id_)
    if f["nicho"] == "mm":
        raise ErrorTanda("Los vídeos del multimodo se sirven desde su nicho.")
    p = _copia_local(f, usuario)
    if not p or not p.is_file():
        raise ErrorTanda(f"El vídeo ya no está en {f['video_path']} (¿borrado de Drive?).", status=404)
    return p, Path(f["video_path"]).name or p.name


def _clave_foto(f: dict) -> str:
    if f["nicho"] == "mm":
        return f"mm|{f['carpeta']}|{f['producto']}"
    return f"pov|{f['source']}|{f['carpeta']}|{f['producto']}"


def _resolver_fotos(lista: list[dict]) -> dict[str, str]:
    """`{clave_foto: file_id}` de las filas dadas.

    Encontrar la foto es lo caro (listar la carpeta del Drive y emparejar:
    30-50 s en frío), así que el id se guarda en Redis para siempre —un id de
    Drive no cambia— y se busca POR CARPETA: sus diez productos suelen ir
    juntos en la misma tanda.
    """
    from src.nicho_pov_bof.services import drive_client

    r = _redis()
    guardadas = (r.get_json(config.FOTO_KEY) or {}) if r.is_available() else {}
    salida = {c: guardadas[c] for c in (_clave_foto(f) for f in lista) if guardadas.get(c)}
    faltan = [f for f in lista if _clave_foto(f) not in salida]
    nuevas: dict[str, str] = {}
    vistas: set[tuple] = set()
    for f in faltan:
        try:
            if f["nicho"] == "mm":
                from src.nicho_ropa.services import prendas_web

                fid = prendas_web.foto_limpia_id(f["carpeta"], f["producto"]) or ""
                if fid:
                    nuevas[_clave_foto(f)] = fid
                continue
            carpeta = (f["source"], f["carpeta"])
            if carpeta in vistas:
                continue
            vistas.add(carpeta)
            from src.nicho_pov_bof.services import photo_pairing

            fotos = [drive_client.probe_dimensions(x) for x in drive_client.list_photos(*carpeta)]
            for par in photo_pairing.pair_folder(fotos):
                limpia = (par.get("clean") or {}).get("id") or ""
                if limpia:
                    nuevas[f"pov|{carpeta[0]}|{carpeta[1]}|{par['producto']}"] = limpia
        except Exception:  # noqa: BLE001 — sin foto, la fila sale igual
            continue
    if nuevas and r.is_available():
        # Releer justo antes de escribir: otra petición puede haber guardado
        # las suyas mientras se listaba el Drive.
        actual = r.get_json(config.FOTO_KEY) or {}
        actual.update(nuevas)
        r.set_json(config.FOTO_KEY, actual)
    salida.update(nuevas)
    return salida


def foto(usuario: str, id_: str, ancho: int = 96) -> Path:
    """Miniatura de la foto limpia del producto. Se pide foto a foto desde la
    página, no al listar: la lista sale en un segundo y las miniaturas van
    llegando (y al listar ya se dejan buscando las de las próximas tandas)."""
    from src.nicho_pov_bof.services import drive_client

    f = _fila_de(usuario, id_)
    file_id = _resolver_fotos([f]).get(_clave_foto(f), "")
    if not file_id:
        raise ErrorTanda("Este producto no tiene foto limpia.", status=404)
    path = drive_client.fetch_photo(file_id)
    try:
        from src.nicho_pov_bof.services import thumbs

        return thumbs.miniatura(path, ancho) or path
    except Exception:  # noqa: BLE001
        return path
