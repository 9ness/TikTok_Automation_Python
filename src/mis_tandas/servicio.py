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


def _intercalar(ids: list[str], por_id: dict[str, dict], nuevos: list[str]) -> list[str]:
    """Mete `nuevos` (los de Aleatorios) repartidos entre lo PENDIENTE: uno
    cada `ALEA_CADA`, a partir de las primeras `ALEA_SIN_TOCAR` tandas
    abiertas (el operador puede tenerlas ya bajadas). Lo subido no cuenta ni
    se mueve. Si no hay sitio, al final."""
    if not nuevos:
        return ids
    salida: list[str] = []
    cola = list(nuevos)
    pendientes = 0
    saltar = config.ALEA_SIN_TOCAR * config.POR_TANDA
    for i in ids:
        salida.append(i)
        f = por_id.get(i)
        if not f or f["uploaded"]:
            continue
        pendientes += 1
        if cola and pendientes > saltar and (pendientes - saltar) % config.ALEA_CADA == 0:
            salida.append(cola.pop(0))
    return salida + cola


def _ordenar(usuario: str, pov: list[dict], mm: list[dict], alea: list[dict] | None = None) -> list[dict]:
    alea = alea or []
    por_id = {f["id"]: f for f in pov + mm + alea}
    r = _redis()
    clave = config.ORDEN_KEY.format(usuario=usuario or "ness")
    guardado = (r.get_json(clave) or {}).get("claves") or [] if r.is_available() else []
    conocidos = set(guardado)
    nuevos_pov = sorted((f for f in pov if f["id"] not in conocidos), key=_clave_orden)
    nuevos_mm = [f for f in mm if f["id"] not in conocidos]
    nuevos = _mezclar(nuevos_pov, nuevos_mm)
    # Los de Aleatorios ya subidos van con el resto (por fecha); los
    # pendientes se intercalan en lo que queda por publicar.
    nuevos_alea = [f for f in alea if f["id"] not in conocidos]
    alea_subidos = sorted((f for f in nuevos_alea if f["uploaded"]), key=_clave_orden)
    alea_pend = sorted((f for f in nuevos_alea if not f["uploaded"]), key=_clave_orden)
    nuevos = _mezclar(alea_subidos, nuevos) if alea_subidos else nuevos
    ids = _intercalar(guardado + [f["id"] for f in nuevos], por_id, [f["id"] for f in alea_pend])
    if (nuevos or alea_pend) and r.is_available():
        r.set_json(clave, {"claves": ids, "updated_at": time.time()})
    # Lo que ya no existe (vídeo borrado) no sale, pero conserva su puesto
    # guardado por si vuelve.
    return [por_id[i] for i in ids if i in por_id]


def filas(usuario: str, fresco: bool = False) -> list[dict]:
    usuario = usuario or "ness"
    ahora = time.time()
    with _cerrojo:
        c = _cache.get(usuario)
        if c and not fresco and ahora - c[0] < config.CACHE_S:
            return c[1]
    pov, mm, alea = fuentes.todas(usuario)
    ordenadas = _ordenar(usuario, pov, mm, alea)
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


# ---------------------------------------------------------------------------
# Época y destino: cuándo se publica cada vídeo y si habla (TikTok) o no (Meta)
# ---------------------------------------------------------------------------
def habla(f: dict) -> bool:
    """Si el vídeo lleva voz: POV/Largo y Aleatorios siempre; del multimodo,
    los hablados (`mm_habla_*`) y los de 20 s con Fish."""
    if f["nicho"] != "mm":
        return True
    from src.nicho_ropa import config as ropa_config

    modo = f.get("modo") or ""
    return modo.startswith("mm_habla_") or ropa_config.lleva_fish(modo)


def _epoca_defecto(f: dict) -> str:
    return "otono" if str(f.get("modo_label") or "").startswith("🍂") else "neutro"


def epocas(usuario: str) -> dict[str, str]:
    r = _redis()
    if not r.is_available():
        return {}
    return (r.get_json(config.EPOCA_KEY.format(usuario=usuario or "ness")) or {}).get("videos") or {}


def poner_epoca(usuario: str, id_: str, epoca: str) -> dict:
    """Pone (o quita, con "") la época de un vídeo."""
    usuario = usuario or "ness"
    epoca = (epoca or "").strip().lower().replace("ñ", "n").replace(" ", "_")
    if epoca and epoca not in config.EPOCAS:
        raise ErrorTanda(f"Época «{epoca}» no vale: {', '.join(config.EPOCAS)} o vacío para quitarla.")
    f = _fila_de(usuario, id_)
    r = _redis()
    if not r.is_available():
        raise ErrorTanda("Redis no está disponible.", status=503)
    clave = config.EPOCA_KEY.format(usuario=usuario)
    videos = (r.get_json(clave) or {}).get("videos") or {}
    if epoca:
        videos[id_] = epoca
    else:
        videos.pop(id_, None)
    r.set_json(clave, {"videos": videos, "updated_at": time.time()})
    return {"ok": True, "id": id_, "epoca": videos.get(id_) or _epoca_defecto(f)}


# ---------------------------------------------------------------------------
# Semáforo de revisión: verde / ámbar / rojo por vídeo (ver config).
# ---------------------------------------------------------------------------
def semaforos(usuario: str) -> dict[str, dict]:
    r = _redis()
    if not r.is_available():
        return {}
    return (r.get_json(config.SEMAFORO_KEY.format(usuario=usuario or "ness")) or {}).get("videos") or {}


def _semaforo_vigente(s: dict | None, f: dict) -> dict | None:
    """El color solo vale para el montaje que se revisó."""
    if not s or abs(float(s.get("listo_at") or 0) - float(f.get("video_listo_at") or 0)) > 1:
        return None
    return s


def poner_semaforo(usuario: str, id_: str, color: str, motivo: str = "", por: str = "") -> dict:
    """Pone (o quita, con color "") el semáforo de un vídeo. Rojo marca además
    «rehacer» con el motivo en los nichos que lo tienen."""
    usuario = usuario or "ness"
    color = (color or "").strip().lower().replace("á", "a")
    if color and color not in config.SEMAFORO_COLORES:
        raise ErrorTanda(f"Color «{color}» no vale: verde, ambar, rojo o vacío para quitarlo.")
    f = _fila_de(usuario, id_)
    r = _redis()
    if not r.is_available():
        raise ErrorTanda("Redis no está disponible.", status=503)
    clave = config.SEMAFORO_KEY.format(usuario=usuario)
    doc = r.get_json(clave) or {}
    videos = doc.get("videos") or {}
    if color:
        videos[id_] = {"color": color, "motivo": (motivo or "").strip()[:300], "por": (por or "").strip()[:40],
                       "listo_at": float(f.get("video_listo_at") or 0), "at": time.time()}
    else:
        videos.pop(id_, None)
    r.set_json(clave, {"videos": videos, "updated_at": time.time()})
    rehacer = None
    if color == "rojo" and f.get("puede_rehacer") and not f.get("rehacer"):
        rehacer = marcar(usuario, id_, rehacer=True, rehacer_nota=f"🔴 {motivo}".strip())
    return {"ok": True, "id": id_, "semaforo": videos.get(id_), "rehacer": bool(rehacer)}


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
    d = _desde(f)
    salida["desde"] = d.isoformat() if d else ""
    return salida


def _desde(f: dict) -> dt.date | None:
    """Primer día en que se puede publicar: el `desde` de su carpeta especial
    del Largo (Q4 no antes del 28 oct, Venta Inversa del 6 oct…)."""
    if f["nicho"] not in ("pov", "largo"):
        return None
    try:
        from src.nicho_pov_bof import config as pov_config

        valor = (pov_config.CARPETAS_ESPECIALES.get(f["carpeta"]) or {}).get("desde")
        return dt.date.fromisoformat(str(valor)) if valor else None
    except (ValueError, TypeError, AttributeError):
        return None


def _clave_producto(f: dict) -> str:
    """Mismo producto aunque sea otro vídeo (otro modo del Largo, la copia de
    Q4…): por tienda + título; sin título, por su sitio en el catálogo."""
    titulo = " ".join(f.get("titulo", "").lower().split())
    if titulo:
        return f"{' '.join(f.get('tienda', '').lower().split())}|{titulo}"
    return f"{f['nicho']}|{f['source']}|{f['carpeta']}|{f['producto']}"


def _repartir(lista: list[dict], dia: dt.date, por_dia: int,
              previos: dict[str, dt.date] | None = None,
              n: int = config.POR_TANDA) -> list[tuple[list[dict], dt.date | None]]:
    """Reparte en tandas de `POR_TANDA` respetando el ORDEN fijo, salvo dos
    cosas que obligan a esperar (sin bloquear a los demás):

    - la fecha mínima de su carpeta (`desde`);
    - que el mismo producto no se publique dos veces en menos de
      `SEPARACION_MISMO_PRODUCTO` días.

    Lo subido no espera nunca (ya está publicado) y una tanda solo con subidos
    no gasta día. `previos`: producto → día en que ya va en una tanda fija.
    Devuelve [(vídeos, fecha o None si está cerrada)].
    """
    sep = dt.timedelta(days=config.SEPARACION_MISMO_PRODUCTO)
    ultimo: dict[str, dt.date] = dict(previos or {})
    for f in lista:
        if f["uploaded"] and f["uploaded_at"]:
            d = dt.datetime.fromtimestamp(f["uploaded_at"], _TZ).date()
            c = _clave_producto(f)
            ultimo[c] = max(ultimo.get(c, d), d)

    hueco = {"fecha": dia, "usados": 0}

    def nuevo_dia(minimo: dt.date | None = None) -> dt.date:
        if hueco["usados"] >= por_dia:
            hueco["fecha"] += dt.timedelta(days=1)
            hueco["usados"] = 0
        if minimo and minimo > hueco["fecha"]:
            hueco["fecha"], hueco["usados"] = minimo, 0
        hueco["usados"] += 1
        return hueco["fecha"]

    def cabe(f: dict, fecha: dt.date) -> bool:
        d = _desde(f)
        if d and fecha < d:
            return False
        previo = ultimo.get(_clave_producto(f))
        return not (previo and fecha < previo + sep)

    def requisito(f: dict) -> dt.date:
        """El primer día en que `f` podría entrar."""
        cands = [hueco["fecha"]]
        d = _desde(f)
        if d:
            cands.append(d)
        previo = ultimo.get(_clave_producto(f))
        if previo:
            cands.append(previo + sep)
        return max(cands)

    def poner(f: dict, fecha: dt.date, tanda: list[dict]) -> None:
        tanda.append(f)
        c = _clave_producto(f)
        ultimo[c] = max(ultimo.get(c, fecha), fecha)

    salida: list[tuple[list[dict], dt.date | None]] = []
    esperan: list[dict] = []
    cur: list[dict] = []
    fecha: dt.date | None = None

    def cerrar() -> None:
        nonlocal cur, fecha
        if cur:
            salida.append((cur, fecha))
        cur, fecha = [], None

    hecho: set[str] = set()  # colocado o apartado a esperar

    def llenar_prioritarios(desde_i: int) -> None:
        """Al abrir una tanda entra primero lo que esperaba y ya puede, y
        después lo que tiene fecha propia (carpetas especiales) y ya está en su
        ventana: es lo que caduca, lo normal puede ir otro día."""
        for e in list(esperan):
            if len(cur) < n and cabe(e, fecha):
                esperan.remove(e)
                poner(e, fecha, cur)
        for e in lista[desde_i:]:
            if len(cur) >= n:
                break
            if e["id"] in hecho or e["uploaded"] or not _desde(e):
                continue
            if cabe(e, fecha):
                hecho.add(e["id"])
                poner(e, fecha, cur)

    for i, f in enumerate(lista):
        if f["id"] in hecho:
            continue
        hecho.add(f["id"])
        if f["uploaded"]:
            cur.append(f)
        else:
            if fecha is None:
                fecha = nuevo_dia()
                llenar_prioritarios(i)
            if len(cur) < n and cabe(f, fecha):
                poner(f, fecha, cur)
            else:
                esperan.append(f)
        if len(cur) >= n:
            cerrar()
    cerrar()

    # Lo que sigue esperando: tandas nuevas en cuanto llegue su fecha.
    while esperan:
        minimo = min(requisito(e) for e in esperan)
        fecha = nuevo_dia(minimo)
        cur = []
        for e in list(esperan):
            if len(cur) < n and cabe(e, fecha):
                esperan.remove(e)
                poner(e, fecha, cur)
        if not cur:  # no debería pasar; evita un bucle infinito
            hueco["fecha"] += dt.timedelta(days=1)
            hueco["usados"] = 0
            continue
        salida.append((cur, fecha))
    return salida


def _fijas(usuario: str) -> list[dict]:
    r = _redis()
    if not r.is_available():
        return []
    return list((r.get_json(config.FIJAS_KEY.format(usuario=usuario)) or {}).get("tandas") or [])


def _guardar_fijas(usuario: str, fijas: list[dict]) -> None:
    r = _redis()
    if not r.is_available():
        return
    # Las completadas viejas sobran: se recuerdan las últimas, las abiertas todas.
    cerradas = [i for i, t in enumerate(fijas) if t.get("completada_at")]
    quitar = set(cerradas[:-config.FIJAS_GUARDAR]) if len(cerradas) > config.FIJAS_GUARDAR else set()
    fijas = [t for i, t in enumerate(fijas) if i not in quitar]
    r.set_json(config.FIJAS_KEY.format(usuario=usuario), {"tandas": fijas, "updated_at": time.time()})


def tandas(usuario: str, todas: bool = False, fresco: bool = False, ver_ocultos: bool = False) -> dict:
    """Las tandas ABIERTAS con sus vídeos y, de las cerradas, solo cuántas hay
    (con `todas`, también sus vídeos).

    Las tandas que se enseñan quedan FIJADAS (`FIJAS_KEY`): las primeras
    `FIJAR_ABIERTAS` abiertas y toda tanda llena. Un vídeo no sale nunca de su
    tanda (subido y sin stock se quedan con su marca) salvo si se rehace, y
    una tanda solo se cierra con «Tanda completada». Lo que aún no está en
    ninguna se reparte con `_repartir`; ahí lo pendiente sin stock no ocupa
    sitio: sale aparte en `esperando_stock` hasta que vuelva."""
    usuario = usuario or "ness"
    escondidos = ocultos(usuario)
    completa = filas(usuario, fresco=fresco)
    lista = [f for f in completa if f["id"] not in escondidos]
    n_tanda = config.por_tanda(usuario)
    # Cuenta que en TikTok solo publica hablados: los mudos sin subir salen
    # de las tandas y van aparte (Meta). Lo ya subido se queda donde estaba.
    solo_meta: list[dict] = []
    if usuario in config.SOLO_HABLADOS:
        solo_meta = [f for f in lista if not habla(f) and not f["uploaded"]]
        fuera_tiktok = {f["id"] for f in solo_meta}
        lista = [f for f in lista if f["id"] not in fuera_tiktok]
    por_id = {f["id"]: f for f in lista}

    dia = dt.datetime.now(_TZ).date()
    hoy = sum(
        1 for f in lista
        if f["uploaded"] and f["uploaded_at"]
        and dt.datetime.fromtimestamp(f["uploaded_at"], _TZ).date() == dia
    )
    por_dia = max(1, config.TANDAS_DIA.get(usuario, 1))
    if hoy >= config.SUBIDAS_DIA_HECHO * por_dia:
        dia += dt.timedelta(days=1)
    hueco = {"fecha": dia, "usados": 0}

    def siguiente_dia(minimo: dt.date | None = None) -> dt.date:
        if hueco["usados"] >= por_dia:
            hueco["fecha"] += dt.timedelta(days=1)
            hueco["usados"] = 0
        if minimo and minimo > hueco["fecha"]:
            hueco["fecha"], hueco["usados"] = minimo, 0
        hueco["usados"] += 1
        return hueco["fecha"]

    # 1) Las fijas, tal cual se guardaron. Un vídeo NUNCA sale de su tanda
    #    (subido y sin stock se quedan con su marca), salvo uno marcado para
    #    rehacer que ya se ha vuelto a montar: ese va a una tanda nueva.
    todos = {f["id"]: f for f in completa}
    fijas = _fijas(usuario)
    cambio = False
    for t in fijas:
        listo = t.setdefault("listo", {})
        marcados = set(t.get("rehacer") or [])
        if t.get("completada_at"):
            # Cerrar la tanda no puede atrapar un rehacer: en cuanto se vuelve
            # a montar sale y se reparte de nuevo, como en una abierta.
            fuera = {
                i for i in marcados
                if (f := todos.get(i)) and not f["rehacer"] and not f["uploaded"]
                and i in listo and f["video_listo_at"] > listo[i] + 1
            }
            if fuera:
                t["ids"] = [i for i in t.get("ids", []) if i not in fuera]
                t["rehacer"] = sorted(marcados - fuera)
                for i in fuera:
                    listo.pop(i, None)
                cambio = True
            continue
        quedan = []
        for i in t.get("ids", []):
            f = todos.get(i)
            if f is None:  # ya no se lee (borrado en el nicho): se guarda igual
                quedan.append(i)
                continue
            if f["rehacer"] and i not in marcados:
                marcados.add(i)
                cambio = True
            if i not in listo:
                listo[i] = f["video_listo_at"]
                cambio = True
            elif i in marcados and not f["rehacer"] and f["video_listo_at"] > listo[i] + 1:
                marcados.discard(i)
                listo.pop(i, None)
                cambio = True
                continue  # rehecho: fuera, se reparte de nuevo
            quedan.append(i)
        if quedan != t.get("ids"):
            t["ids"] = quedan
        t["rehacer"] = sorted(marcados)

    grupos: list[tuple[list[dict], dt.date | None, bool]] = []  # (vídeos, fecha, cerrada)
    previos: dict[str, dt.date] = {}
    for t in fijas:
        items = [por_id[i] for i in t.get("ids", []) if i in por_id]
        if not items:
            continue
        # Solo «Tanda completada» cierra una tanda fija: toda subida sigue a la vista.
        cerrada = bool(t.get("completada_at"))
        fecha = None
        if not cerrada:
            desde = [d for d in (_desde(f) for f in items if not _cerrado(f)) if d]
            fecha = siguiente_dia(max(desde) if desde else None)
            for f in items:
                if not _cerrado(f):
                    c = _clave_producto(f)
                    previos[c] = max(previos.get(c, fecha), fecha)
        grupos.append((items, fecha, cerrada))

    # 2) El resto se reparte detrás de las fijas. Se fijan las primeras
    #    abiertas y toda tanda llena; una a medio llenar al final se sigue
    #    llenando con lo que se monte.
    en_fijas = {i for t in fijas for i in t.get("ids", [])}
    resto = [f for f in lista if f["id"] not in en_fijas]
    sin_stock = [f for f in resto if f["sin_stock"] and not f["uploaded"]]
    publicables = [f for f in resto if not (f["sin_stock"] and not f["uploaded"])]
    if hueco["usados"] >= por_dia:
        hueco["fecha"] += dt.timedelta(days=1)
    abiertas_fijas = sum(1 for _, _, c in grupos if not c)
    historicas: list[tuple[list[dict], dt.date | None, bool]] = []
    nuevas: list[tuple[list[dict], dt.date | None, bool]] = []
    for grupo, fecha in _repartir(publicables, hueco["fecha"], por_dia, previos, n_tanda):
        if all(f["uploaded"] for f in grupo):
            historicas.append((grupo, None, True))
            continue
        if abiertas_fijas < config.FIJAR_ABIERTAS or len(grupo) >= n_tanda:
            fijas.append({"ids": [f["id"] for f in grupo], "creada": time.time(),
                          "listo": {f["id"]: f["video_listo_at"] for f in grupo}})
            abiertas_fijas += 1
            cambio = True
        nuevas.append((grupo, fecha, False))
    if cambio:
        _guardar_fijas(usuario, fijas)

    from src.nicho_ropa import config as ropa_config

    salida: list[dict] = []
    abiertas_vistas = 0
    cerradas = 0
    precalentar: list[dict] = []
    for i, (grupo, fecha, cerrada) in enumerate(historicas + grupos + nuevas):
        abierta = not cerrada
        t = {
            "numero": i + 1,
            "total": len(grupo),
            "subidos": sum(1 for f in grupo if f["uploaded"]),
            "sin_stock": sum(1 for f in grupo if f["sin_stock"] and not f["uploaded"]),
            "rehacer": sum(1 for f in grupo if f["rehacer"] and not f["uploaded"]),
            "abierta": abierta,
            "nichos": sorted({f["nicho"] for f in grupo}),
        }
        if abierta and fecha:
            t["fecha"] = fecha.isoformat()
            t["temporada"] = ropa_config.etiqueta_temporada(fecha)
            if abiertas_vistas < config.PRECALENTAR_TANDAS:
                precalentar += [f for f in grupo if not _cerrado(f)]
            abiertas_vistas += 1
        else:
            cerradas += 1
        if abierta or todas:
            t["items"] = [_publica(f) for f in grupo]
            salida.append(t)
    _precalentar(usuario, precalentar)
    sem = semaforos(usuario)
    epo = epocas(usuario)
    meta_items = [_publica(f) for f in solo_meta]
    for v in meta_items:
        v["semaforo"] = _semaforo_vigente(sem.get(v["id"]), v)
    for v in meta_items + [v for t in salida for v in t.get("items", [])]:
        v["epoca"] = epo.get(v["id"]) or _epoca_defecto(v)
        v["habla"] = habla(v)
    for t in salida:
        for v in t.get("items", []):
            v["semaforo"] = _semaforo_vigente(sem.get(v["id"]), v)
        items = t.get("items", [])
        t["semaforo"] = {c: sum(1 for v in items if (v.get("semaforo") or {}).get("color") == c and not v["uploaded"])
                         for c in config.SEMAFORO_COLORES}
    return {
        "usuario": usuario,
        "por_tanda": n_tanda,
        "total": len(lista),
        "subidos": sum(1 for f in lista if f["uploaded"]),
        "sin_stock": sum(1 for f in lista if f["sin_stock"] and not f["uploaded"]),
        "subidos_hoy": hoy,
        "cerradas": cerradas,
        "abiertas": abiertas_vistas,
        "ocultos": sum(1 for f in completa if f["id"] in escondidos),
        "ocultos_items": [_publica(f) for f in completa if f["id"] in escondidos] if ver_ocultos else [],
        "esperando_stock": [_publica(f) for f in sin_stock],
        # Mudos sin subir de una cuenta `SOLO_HABLADOS`: no van a TikTok (Meta).
        "solo_meta": meta_items,
        "tandas": salida,
    }


def completar(usuario: str, ids: list[str]) -> dict:
    """«Tanda completada»: CIERRA la tanda (la siguiente pasa a ser la primera)
    sin marcar nada. Lo que no se subió se queda sin subir, en esa tanda."""
    usuario = usuario or "ness"
    pedidos = {i for i in ids if i}
    if not pedidos:
        raise ErrorTanda("Sin vídeos.")
    for i in pedidos:
        _partes(i)
    r = _redis()
    if not r.is_available():
        raise ErrorTanda("Redis no está disponible.", status=503)
    fijas = _fijas(usuario)
    tanda = next((t for t in fijas if pedidos & set(t.get("ids", []))), None)
    if tanda is None:  # una tanda que aún no estaba fijada: se fija ya cerrada
        tanda = {"ids": sorted(pedidos), "creada": time.time()}
        fijas.append(tanda)
    tanda["completada_at"] = time.time()
    _guardar_fijas(usuario, fijas)
    por_id = {f["id"]: f for f in filas(usuario)}
    sin_subir = sum(1 for i in tanda["ids"] if i in por_id and not _cerrado(por_id[i]))
    return {"ok": True, "cerrada": len(tanda["ids"]), "sin_subir": sin_subir}


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
    if p[0] == "alea" and len(p) == 4:
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
        carpeta, prod = p[1], p[2]
        if p[0] == "alea" and rehacer is not None:
            # Del VÍDEO (producto + modo), no del producto como el del multimodo.
            from src.nicho_ropa.repos import product_repo as ropa_repo

            try:
                r = ropa_repo.marcar_rehacer_modo(carpeta, prod, p[3], usuario,
                                                  rehacer=bool(rehacer), nota=rehacer_nota or "")
            except (ValueError, RuntimeError) as e:
                raise ErrorTanda(str(e)) from e
            cambios.update({k: r[k] for k in ("rehacer", "rehacer_nota") if k in r})
            rehacer = None
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
                elif p[0] in ("mm", "alea") and f["nicho"] in ("mm", "alea") \
                        and f["carpeta"] == p[1] and f["producto"] == p[2]:
                    # Moda Mujer: subido y sin stock son del PRODUCTO (el
                    # mismo producto con vídeo de multimodo y de Aleatorios).
                    f.update({k: v for k, v in cambios.items() if k in ("uploaded", "uploaded_at", "sin_stock")})
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
    mm = [f["video_path"] for f in lista if f["nicho"] in ("mm", "alea") and f["video_path"]]
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
    if f["nicho"] in ("mm", "alea"):
        raise ErrorTanda("Los vídeos de Moda Mujer se sirven desde su nicho.")
    p = _copia_local(f, usuario)
    if not p or not p.is_file():
        raise ErrorTanda(f"El vídeo ya no está en {f['video_path']} (¿borrado de Drive?).", status=404)
    return p, Path(f["video_path"]).name or p.name


def _clave_foto(f: dict) -> str:
    if f["nicho"] in ("mm", "alea"):
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
            if f["nicho"] in ("mm", "alea"):
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
