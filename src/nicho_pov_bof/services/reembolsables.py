"""Muestras REEMBOLSABLES del catálogo «Muestras productos» (`mis_productos`).

Una muestra normal se pide gratis y basta con publicar un vídeo. Una
reembolsable la paga el operador y la tienda se la devuelve si el producto
llega a X ventas antes de una fecha: hay que tenerla a la vista y revisar
cada pocos días si ha vendido para, si no, hacer más versiones o buscar un
viral que replicar.

El dato va en el propio producto (campo `reembolso` del documento COMPARTIDO
de la carpeta, el mismo que guarda `product_url` o `sin_stock`):

    {"activo": bool, "ventas_objetivo": int>=1, "ventas": int>=0,
     "fecha_limite": "AAAA-MM-DD", "marcado_at": ts, "revisado_at": ts,
     "notas": str}

Se guarda la FECHA límite y no los días: así la cuenta atrás está siempre al
día sin tener que reescribir nada. Lo que se deriva (días restantes, estado,
si toca revisar) se calcula al leer, nunca se guarda.
"""

from __future__ import annotations

import time
import zoneinfo
from datetime import date, datetime, timedelta

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos import product_repo

SOURCE = "mis_productos"
_TZ = zoneinfo.ZoneInfo("Europe/Madrid")


def hoy() -> date:
    """Hoy en España (la fecha límite se cuenta en días de aquí)."""
    return datetime.now(_TZ).date()


def _ahora() -> float:
    return time.time()


def _exige_fuente(source: str) -> None:
    if source != SOURCE:
        raise ValueError(
            "Las muestras reembolsables solo existen en «Muestras productos» "
            f"(mis_productos), no en {source!r}."
        )


def _entero(valor, nombre: str, minimo: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{nombre} tiene que ser un número entero.") from e
    if isinstance(valor, float) and valor != n:
        raise ValueError(f"{nombre} tiene que ser un número entero.")
    if n < minimo:
        raise ValueError(f"{nombre} tiene que ser {minimo} o más.")
    return n


def _fecha_limite(dias: int) -> str:
    return (hoy() + timedelta(days=dias)).isoformat()


def info(reembolso: dict | None, *, ahora: float | None = None) -> dict | None:
    """Lo guardado + los derivados. `None` si no es (o ya no es) reembolsable."""
    if not isinstance(reembolso, dict) or not reembolso.get("activo"):
        return None
    ahora = _ahora() if ahora is None else ahora
    objetivo = max(1, int(reembolso.get("ventas_objetivo") or 1))
    ventas = max(0, int(reembolso.get("ventas") or 0))
    fecha = str(reembolso.get("fecha_limite") or "")
    try:
        dias = (date.fromisoformat(fecha) - hoy()).days
    except ValueError:
        dias = 0
    if ventas >= objetivo:
        estado = "cumplido"
    elif dias < 0:
        estado = "vencido"
    else:
        estado = "en_curso"
    revisado = float(reembolso.get("revisado_at") or 0)
    toca = estado == "en_curso" and (
        ahora - revisado >= config.REVISAR_CADA_DIAS * 86400
    )
    return {
        "activo": True,
        "ventas_objetivo": objetivo,
        "ventas": ventas,
        "fecha_limite": fecha,
        "marcado_at": float(reembolso.get("marcado_at") or 0),
        "revisado_at": revisado,
        "notas": str(reembolso.get("notas") or ""),
        "dias_restantes": dias,
        "estado": estado,
        "toca_revisar": toca,
    }


def _existe(folder: str, producto: str) -> bool:
    """El producto está en la carpeta (listado cacheado del Drive montado)."""
    from src.nicho_pov_bof.services import mis_productos

    if folder not in mis_productos.carpetas(SOURCE):
        return False
    return str(producto) in mis_productos._productos_en(folder, SOURCE)


def _leer(folder: str, producto: str) -> dict:
    return (
        (product_repo.load_folder(SOURCE, folder).get("productos") or {})
        .get(str(producto)) or {}
    )


def _guardar(folder: str, producto: str, reembolso: dict) -> dict:
    prod = product_repo._update_product_sin_cerrojo(
        SOURCE, folder, str(producto), reembolso=reembolso,
    )
    return _item(folder, str(producto), prod)


def _item(folder: str, producto: str, prod: dict) -> dict:
    return {
        "source": SOURCE,
        "folder": folder,
        "producto": producto,
        "titulo": str(prod.get("titulo") or ""),
        "tienda": str(prod.get("tienda") or ""),
        "reembolso": info(prod.get("reembolso")),
    }


def marcar(
    folder: str, producto: str, ventas_objetivo, dias, ventas=0, notas: str = "",
    *, source: str = SOURCE, comprobar: bool = True,
) -> dict:
    """Marca (o vuelve a marcar desde cero) un producto como reembolsable."""
    _exige_fuente(source)
    objetivo = _entero(ventas_objetivo, "Las ventas necesarias", 1)
    n_dias = _entero(dias, "Los días", 0)
    n_ventas = _entero(ventas, "Las ventas actuales", 0)
    if comprobar and not _existe(folder, producto):
        raise ValueError(f"No hay producto {producto} en la carpeta {folder!r}.")
    ahora = _ahora()
    with product_repo._cerrojo_carpeta(SOURCE, folder):
        return _guardar(folder, producto, {
            "activo": True,
            "ventas_objetivo": objetivo,
            "ventas": n_ventas,
            "fecha_limite": _fecha_limite(n_dias),
            "marcado_at": ahora,
            "revisado_at": ahora,
            "notas": str(notas or "").strip()[:500],
        })


def actualizar(
    folder: str, producto: str, ventas=None, dias=None, ventas_objetivo=None,
    notas: str | None = None, revisado: bool = True, sumar_ventas: int = 0,
    *, source: str = SOURCE,
) -> dict:
    """Cambia ventas / días / objetivo / notas de uno ya marcado.

    `ventas` es el total (no lo que se suma); `sumar_ventas` suma encima (el
    «+1 venta» de la tarjeta). Con `revisado=True` (por defecto) se sella la
    revisión: llamarla sin cambiar nada es «revisado, sin ventas nuevas».
    """
    _exige_fuente(source)
    with product_repo._cerrojo_carpeta(SOURCE, folder):
        actual = _leer(folder, producto).get("reembolso")
        if not isinstance(actual, dict) or not actual.get("activo"):
            raise ValueError(
                f"El producto {producto} de {folder!r} no está marcado como "
                "reembolsable: márcalo primero."
            )
        nuevo = dict(actual)
        if ventas is not None:
            nuevo["ventas"] = _entero(ventas, "Las ventas actuales", 0)
        if sumar_ventas:
            nuevo["ventas"] = max(
                0, int(nuevo.get("ventas") or 0)
                + _entero(sumar_ventas, "Las ventas a sumar", -1000),
            )
        if ventas_objetivo is not None:
            nuevo["ventas_objetivo"] = _entero(ventas_objetivo, "Las ventas necesarias", 1)
        if dias is not None:
            nuevo["fecha_limite"] = _fecha_limite(_entero(dias, "Los días", 0))
        if notas is not None:
            nuevo["notas"] = str(notas).strip()[:500]
        if revisado:
            nuevo["revisado_at"] = _ahora()
        return _guardar(folder, producto, nuevo)


def desmarcar(folder: str, producto: str, *, source: str = SOURCE) -> dict:
    """Vuelve a muestra normal. Se conserva lo que había con `activo=False`."""
    _exige_fuente(source)
    with product_repo._cerrojo_carpeta(SOURCE, folder):
        actual = _leer(folder, producto).get("reembolso")
        if not isinstance(actual, dict) or not actual.get("activo"):
            return _item(folder, str(producto), _leer(folder, producto))
        return _guardar(folder, producto, {
            **actual, "activo": False, "desmarcado_at": _ahora(),
        })


def _orden(item: dict) -> tuple:
    r = item["reembolso"]
    return (not r["toca_revisar"], r["estado"] != "en_curso", r["dias_restantes"])


def listar(carpetas: list[str] | None = None) -> dict:
    """Todos los reembolsables del catálogo: primero los que toca revisar,
    luego los en curso por días restantes, y al final cumplidos y vencidos."""
    if carpetas is None:
        from src.nicho_pov_bof.services import mis_productos

        carpetas = mis_productos.carpetas(SOURCE)
    docs = product_repo.load_folders([(SOURCE, c) for c in carpetas])
    items: list[dict] = []
    for carpeta, doc in zip(carpetas, docs):
        for pid, prod in (doc.get("productos") or {}).items():
            if info(prod.get("reembolso")):
                items.append(_item(carpeta, str(pid), prod))
    items.sort(key=_orden)
    estados = [i["reembolso"]["estado"] for i in items]
    return {
        "items": items,
        "total": len(items),
        "en_curso": estados.count("en_curso"),
        "cumplidos": estados.count("cumplido"),
        "vencidos": estados.count("vencido"),
        "toca_revisar": sum(1 for i in items if i["reembolso"]["toca_revisar"]),
        "revisar_cada_dias": config.REVISAR_CADA_DIAS,
    }
