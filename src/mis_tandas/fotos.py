"""«Mis tandas › Fotos»: los carruseles de «Replicar carrusel» del usuario, en
tandas de diez para publicar, con su PROPIO contador (no se mezclan con los
vídeos ni cuentan para su cuota del día).

Solo lee las réplicas (`replicar_viral:<id>` con `tipo="carrusel"`). Los botones
hacen lo mismo que en «Vídeos»: «Subido» se escribe en el documento de la
réplica (`carrusel.marcar_subido`) y cuenta para el tope diario de carruseles
(`cuotas`); «Sin stock» es del PRODUCTO (los textos del POV BOF, como en los
vídeos), así que lo ven también sus vídeos y al revés. Un carrusel sin stock se
queda en su tanda con la marca y no entra en el ZIP. Entra un
carrusel en cuanto tiene al menos una foto subida; el orden es el de creación
(lo nuevo al final), así una tanda no cambia de contenido al crear otro.
"""

from __future__ import annotations

import datetime as dt
import io
import time
import zipfile
import zoneinfo

from src.mis_tandas import config

_TZ = zoneinfo.ZoneInfo("Europe/Madrid")


def _carruseles(usuario: str) -> list[dict]:
    """Los documentos de carrusel del usuario con alguna foto, del más viejo
    al más nuevo, con su estado de disco (`hechas`/`total`)."""
    from src.replicar_viral import carrusel, servicio

    r = servicio._redis()
    if not r.is_available():
        return []
    ids = (r.get_json(servicio.INDICE.format(usuario=usuario)) or {}).get("ids") or []
    if not ids:
        return []
    claves = [servicio.CLAVE.format(id=i) for i in ids]
    docs = r.mget_json(claves) if hasattr(r, "mget_json") else [r.get_json(k) for k in claves]
    from concurrent.futures import ThreadPoolExecutor

    validos = [d for d in docs if isinstance(d, dict) and d.get("tipo") == "carrusel"]
    # Cada uno lee sus carpetas del Drive montado: en paralelo, no uno tras otro.
    with ThreadPoolExecutor(max_workers=8) as pool:
        estados = list(pool.map(carrusel.con_estado, validos))
    salida = [e for e in estados if e["hechas"] > 0]
    salida.sort(key=lambda d: d.get("creado_at") or 0)
    return salida


def _sin_stock(lista: list[dict]) -> set[tuple[str, str, str]]:
    """(source, folder, producto) marcados sin stock en los textos del POV BOF,
    leyendo una vez cada carpeta."""
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    carpetas = {
        (str(p.get("source") or ""), str(p.get("folder") or ""))
        for p in ((d.get("producto") or {}) for d in lista)
        if p.get("source") and p.get("folder")
    }
    marcados: set[tuple[str, str, str]] = set()
    for fuente, carpeta in carpetas:
        try:
            prods = (pov_repo.load_folder(fuente, carpeta) or {}).get("productos") or {}
        except Exception:  # noqa: BLE001 — sin Redis del POV BOF, nada sin stock
            continue
        marcados |= {(fuente, carpeta, str(k)) for k, v in prods.items()
                     if isinstance(v, dict) and v.get("sin_stock")}
    return marcados


def _clave(d: dict) -> tuple[str, str, str]:
    p = d.get("producto") or {}
    return str(p.get("source") or ""), str(p.get("folder") or ""), str(p.get("producto") or "")


def _cerrado(c: dict) -> bool:
    return bool(c["subido"] or c["sin_stock"])


def _listo_at(d: dict) -> float:
    """La última foto que se subió o se quemó (`version` = mtime). Si cambia,
    el semáforo que se puso deja de valer, como al rehacer un vídeo."""
    return float(max((x.get("version") or 0 for x in d.get("diapositivas") or []), default=0))


def listo_at(usuario: str, id_: str) -> float:
    """Para poner el semáforo: comprueba además que el carrusel es de ESE usuario."""
    from src.replicar_viral import carrusel

    return _listo_at(carrusel.con_estado(carrusel.ver(usuario or "ness", id_)))


def _semaforo(d: dict, sem: dict) -> dict | None:
    from src.mis_tandas import servicio

    return servicio._semaforo_vigente(sem.get(servicio.CARRUSEL + d["id"]), {"video_listo_at": _listo_at(d)})


def _publica(d: dict, sin_stock: bool = False, sem: dict | None = None) -> dict:
    prod = d.get("producto") or {}
    return {
        "id": d["id"],
        "creado_at": d.get("creado_at") or 0,
        "titulo": prod.get("titulo") or f"Producto {prod.get('producto', '')}",
        "tienda": prod.get("tienda", ""),
        "source": prod.get("source", ""),
        "folder": prod.get("folder", ""),
        "producto": str(prod.get("producto", "")),
        "url": d.get("url", ""),
        "product_url": prod.get("product_url", ""),
        "hechas": d["hechas"],
        "diapositivas": d["total"],
        "completo": d["completo"],
        "subido": bool(d.get("subido")),
        "subido_at": d.get("subido_at") or 0,
        "sin_stock": bool(sin_stock),
        "caption": d.get("caption", ""),
        "hashtags": d.get("hashtags") or [],
        "musica": d.get("musica") or {},
        "semaforo": _semaforo(d, sem or {}),
    }


def _grupos(lista: list[dict]) -> list[list[dict]]:
    n = config.POR_TANDA
    return [lista[i:i + n] for i in range(0, len(lista), n)]


COMPLETADAS_KEY = "mis_tandas:fotos_completadas:{usuario}"


def _completadas(usuario: str) -> list[list[str]]:
    """Las tandas cerradas con «Tanda completada», cada una con SUS ids (fijas:
    lo que se cree después no se les mete dentro)."""
    from src.mis_tandas import servicio

    r = servicio._redis()
    if not r.is_available():
        return []
    doc = r.get_json(COMPLETADAS_KEY.format(usuario=usuario)) or {}
    return [list(map(str, t)) for t in doc.get("tandas") or [] if t]


def completar(usuario: str, ids: list[str]) -> dict:
    """«Tanda completada» de fotos, como en los vídeos: cierra la tanda con
    esos carruseles aunque quede alguno sin subir (no marca nada como subido)."""
    from src.mis_tandas import servicio

    usuario = usuario or "ness"
    ids = [str(i) for i in ids if i][: config.POR_TANDA * 2]
    if not ids:
        raise RuntimeError("No hay carruseles que cerrar.")
    previas = _completadas(usuario)
    ya = {i for t in previas for i in t}
    nuevos = [i for i in ids if i not in ya]
    if nuevos:
        previas.append(nuevos)
        servicio._redis().set_json(COMPLETADAS_KEY.format(usuario=usuario), {"tandas": previas})
    return {"ok": True, "cerradas": len(previas)}


def _repartir(lista: list[dict], usuario: str) -> list[tuple[list[dict], bool]]:
    """(carruseles, cerrada). Primero las completadas, con su contenido fijo;
    luego el resto en grupos de diez. Una tanda solo se cierra con «Tanda
    completada»: subirlo todo no la quita de la vista."""
    por_id = {c["id"]: c for c in lista}
    salida, usados = [], set()
    for t in _completadas(usuario):
        grupo = [por_id[i] for i in t if i in por_id]
        if grupo:
            salida.append((grupo, True))
            usados |= {c["id"] for c in grupo}
    resto = [c for c in lista if c["id"] not in usados]
    return salida + [(g, False) for g in _grupos(resto)]


def tandas(usuario: str, todas: bool = False) -> dict:
    """Tandas de diez carruseles. Abierta = le queda alguno sin subir (sin
    stock no cuenta: no se puede publicar); cada abierta lleva su día (hoy,
    mañana…). Como en los vídeos, si hoy ya se subió casi una tanda entera
    (`SUBIDAS_DIA_HECHO`), la primera abierta pasa a mañana. Las cerradas solo
    se cuentan, salvo con `todas`."""
    usuario = usuario or "ness"
    docs = _carruseles(usuario)
    agotados = _sin_stock(docs)
    from src.mis_tandas import servicio

    sem = servicio.semaforos(usuario)
    lista = [_publica(d, _clave(d) in agotados, sem) for d in docs]
    dia = dt.datetime.now(_TZ).date()
    hoy = sum(
        1 for c in lista
        if c["subido"] and c["subido_at"]
        and dt.datetime.fromtimestamp(c["subido_at"], _TZ).date() == dia
    )
    if hoy >= config.SUBIDAS_DIA_HECHO:
        dia += dt.timedelta(days=1)
    salida, cerradas, abiertas = [], 0, 0
    for i, (grupo, cerrada) in enumerate(_repartir(lista, usuario)):
        abierta = not cerrada
        t = {
            "numero": i + 1,
            "total": len(grupo),
            "subidos": sum(1 for c in grupo if c["subido"]),
            "sin_stock": sum(1 for c in grupo if c["sin_stock"] and not c["subido"]),
            "completos": sum(1 for c in grupo if c["completo"]),
            "semaforo": {col: sum(1 for c in grupo if (c["semaforo"] or {}).get("color") == col and not c["subido"])
                         for col in config.SEMAFORO_COLORES},
            "sin_revisar": sum(1 for c in grupo if not c["subido"] and not c["sin_stock"]
                               and servicio.sin_revisar(c)),
            "abierta": abierta,
            "desde": min(c["creado_at"] for c in grupo),
            "hasta": max(c["creado_at"] for c in grupo),
        }
        if abierta:
            t["fecha"] = (dia + dt.timedelta(days=abiertas)).isoformat()
            abiertas += 1
        else:
            cerradas += 1
        if abierta or todas:
            t["items"] = grupo
            salida.append(t)
    return {
        "usuario": usuario,
        "por_tanda": config.POR_TANDA,
        "total": len(lista),
        "subidos": sum(1 for c in lista if c["subido"]),
        "sin_stock": sum(1 for c in lista if c["sin_stock"] and not c["subido"]),
        "subidos_hoy": hoy,
        "completos": sum(1 for c in lista if c["completo"]),
        "abiertas": abiertas,
        "cerradas": cerradas,
        "tandas": salida,
    }


def marcar(usuario: str, id_: str, subido: bool | None = None,
           sin_stock: bool | None = None) -> dict:
    """Los botones de un carrusel, como los de un vídeo: «Subido» en la réplica
    + tope diario de carruseles; «Sin stock» en el producto."""
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.replicar_viral import carrusel

    usuario = usuario or "ness"
    if subido is None and sin_stock is None:
        raise carrusel.ErrorReplica("No hay nada que cambiar.")
    doc = carrusel.ver(usuario, id_)  # solo carruseles de ESE usuario
    fuente, carpeta, prod = _clave(doc)
    if subido is not None:
        doc = carrusel.marcar_subido(usuario, id_, subido)
        try:
            from src.cuotas.repos import cuota_repo

            cuota_repo.marcar("carruseles", f"replica_carrusel|{id_}", usuario, bool(subido))
        except Exception:  # noqa: BLE001 — el tope es un aviso, no un bloqueo
            pass
    else:
        doc = carrusel.con_estado(doc)
    if sin_stock is not None:
        if not (fuente and carpeta and prod):
            raise carrusel.ErrorReplica("Este carrusel no tiene producto del catálogo: no se puede marcar sin stock.")
        pov_repo.save_extracted_texts(fuente, carpeta, {prod: {"sin_stock": bool(sin_stock)}})
        agotado = bool(sin_stock)
    else:
        agotado = _clave(doc) in _sin_stock([doc])
    from src.mis_tandas import servicio

    return _publica(doc, agotado, servicio.semaforos(usuario))


def zip_tanda(usuario: str, numero: int, pendientes: bool = False) -> tuple[bytes, str]:
    """Todos los carruseles de la tanda `numero` en un ZIP, una carpeta por
    carrusel (`01_<producto>/01.jpg…` + caption.txt). `pendientes`: solo los
    que faltan por subir."""
    from src.replicar_viral import carrusel

    usuario = usuario or "ness"
    docs = _carruseles(usuario)
    agotados = _sin_stock(docs)
    # Las mismas tandas que se ven en pantalla (con las completadas primero).
    grupos = [g for g, _ in _repartir(docs, usuario)]
    if not 1 <= int(numero) <= len(grupos):
        raise carrusel.ErrorReplica(f"No existe la tanda {numero} de fotos.", status=404)
    from src.mis_tandas import servicio

    sem = servicio.semaforos(usuario)
    saltados = 0
    buf = io.BytesIO()
    metidos = 0
    # Fecha de captura DEcreciente (01 del primer carrusel = la más nueva): la
    # galería pone lo más nuevo arriba y así sale en el orden de la tanda.
    epoca = time.time()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, doc in enumerate(grupos[int(numero) - 1], start=1):
            if pendientes and doc.get("subido"):
                continue
            if _clave(doc) in agotados and not doc.get("subido"):
                continue  # sin stock no se publica (como en los vídeos)
            if not doc.get("subido") and servicio.sin_revisar({"semaforo": _semaforo(doc, sem)}):
                saltados += 1
                continue  # sin semáforo o en rojo no se baja para publicar
            n = carrusel.meter_en_zip(z, doc, f"{i:02d}_{carrusel.nombre_carrusel(doc)}", epoca)
            if n:
                metidos += 1
                epoca -= 2 * n
    if not metidos:
        if saltados:
            raise carrusel.ErrorReplica(
                f"{saltados} carrusel(es) SIN REVISAR o en rojo: un carrusel no está terminado hasta que se "
                "comprueba. Ponles el semáforo antes de bajarlos para publicar.", status=409)
        raise carrusel.ErrorReplica("No hay carruseles que bajar en esa tanda.", status=404)
    return buf.getvalue(), f"fotos_tanda_{int(numero):03d}.zip"
