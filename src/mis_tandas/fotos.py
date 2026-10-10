"""«Mis tandas › Fotos»: los carruseles de «Replicar carrusel» del usuario, en
tandas de diez para publicar, con su PROPIO contador (no se mezclan con los
vídeos ni cuentan para su cuota del día).

Solo lee las réplicas (`replicar_viral:<id>` con `tipo="carrusel"`) y «Subido»
se escribe en el documento de la réplica (`carrusel.marcar_subido`). Entra un
carrusel en cuanto tiene al menos una foto subida; el orden es el de creación
(lo nuevo al final), así una tanda no cambia de contenido al crear otro.
"""

from __future__ import annotations

import datetime as dt
import io
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
    salida = []
    for d in docs:
        if not isinstance(d, dict) or d.get("tipo") != "carrusel":
            continue
        e = carrusel.con_estado(d)
        if e["hechas"] > 0:
            salida.append(e)
    salida.sort(key=lambda d: d.get("creado_at") or 0)
    return salida


def _publica(d: dict) -> dict:
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
        "caption": d.get("caption", ""),
        "hashtags": d.get("hashtags") or [],
        "musica": d.get("musica") or {},
    }


def _grupos(lista: list[dict]) -> list[list[dict]]:
    n = config.POR_TANDA
    return [lista[i:i + n] for i in range(0, len(lista), n)]


def tandas(usuario: str, todas: bool = False) -> dict:
    """Tandas de diez carruseles. Abierta = le queda alguno sin subir; cada
    abierta lleva su día (hoy, mañana…). Las cerradas solo se cuentan, salvo
    con `todas`."""
    usuario = usuario or "ness"
    lista = [_publica(d) for d in _carruseles(usuario)]
    dia = dt.datetime.now(_TZ).date()
    salida, cerradas, abiertas = [], 0, 0
    for i, grupo in enumerate(_grupos(lista)):
        abierta = not all(c["subido"] for c in grupo)
        t = {
            "numero": i + 1,
            "total": len(grupo),
            "subidos": sum(1 for c in grupo if c["subido"]),
            "completos": sum(1 for c in grupo if c["completo"]),
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
        "completos": sum(1 for c in lista if c["completo"]),
        "abiertas": abiertas,
        "cerradas": cerradas,
        "tandas": salida,
    }


def marcar(usuario: str, id_: str, subido: bool) -> dict:
    from src.replicar_viral import carrusel

    return _publica(carrusel.marcar_subido(usuario, id_, subido))


def zip_tanda(usuario: str, numero: int, pendientes: bool = False) -> tuple[bytes, str]:
    """Todos los carruseles de la tanda `numero` en un ZIP, una carpeta por
    carrusel (`01_<producto>/01.jpg…` + caption.txt). `pendientes`: solo los
    que faltan por subir."""
    from src.replicar_viral import carrusel

    usuario = usuario or "ness"
    grupos = _grupos(_carruseles(usuario))
    if not 1 <= int(numero) <= len(grupos):
        raise carrusel.ErrorReplica(f"No existe la tanda {numero} de fotos.", status=404)
    buf = io.BytesIO()
    metidos = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i, doc in enumerate(grupos[int(numero) - 1], start=1):
            if pendientes and doc.get("subido"):
                continue
            if carrusel.meter_en_zip(z, doc, f"{i:02d}_{carrusel.nombre_carrusel(doc)}"):
                metidos += 1
    if not metidos:
        raise carrusel.ErrorReplica("No hay carruseles que bajar en esa tanda.", status=404)
    return buf.getvalue(), f"fotos_tanda_{int(numero):03d}.zip"
