"""De dónde salen los vídeos: un lector por nicho.

Todo sale de Redis y nada del Drive: listar carpetas del Drive cuesta segundos
por carpeta y esto se abre varias veces al día desde el móvil. Los documentos
se encuentran con un KEYS (`folder:*`, unos doscientos) y se leen con MGET.

Cada lector devuelve filas con la MISMA forma (`_fila`), y el `id` de cada una
dice a qué documento escribir cuando se pulsa un botón:

- `pov|<fuente>|<carpeta>|<producto>`
- `largo|<fuente>|<carpeta>|<producto>|<modo>`   (modo vacío = el de siempre)
- `mm|<carpeta>|<producto>`
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.mis_tandas import config

SEP = "|"
_TROZO = 40  # claves por MGET: la URL de Upstash REST lleva todas las claves


def _keys(r, patron: str) -> list[str]:
    """KEYS sin prefijo. Los clientes de los nichos no lo traen."""
    res = r._get(f"keys/{r._enc(r._full_key(patron))}") or []
    return [k[len(r.prefix):] if k.startswith(r.prefix) else k for k in res]


def _mget(r, claves: list[str]) -> dict[str, dict]:
    """`{clave: doc}` leyendo en trozos y en paralelo."""
    trozos = [claves[i:i + _TROZO] for i in range(0, len(claves), _TROZO)]
    if not trozos:
        return {}
    with ThreadPoolExecutor(max_workers=min(6, len(trozos))) as ex:
        docs = list(ex.map(r.mget_json, trozos))
    salida: dict[str, dict] = {}
    for trozo, leidos in zip(trozos, docs):
        for k, d in zip(trozo, leidos):
            if isinstance(d, dict):
                salida[k] = d
    return salida


def _partes_folder(clave: str) -> tuple[str, str]:
    """`folder:<fuente>:<carpeta>` → (fuente, carpeta). La carpeta puede
    llevar espacios (y alguna, uno al final): se respeta tal cual."""
    resto = clave[len("folder:"):]
    fuente, _, carpeta = resto.partition(":")
    return fuente, carpeta


def _vigentes(doc: dict) -> list[str]:
    todos = doc.get("productos") or {}
    vig = doc.get("ids_vigentes")
    if isinstance(vig, list):
        return [str(i) for i in vig if str(i) in todos]
    return list(todos)


def _label_fuente(fuente: str) -> str:
    from src.nicho_pov_bof import config as pov_config

    return (pov_config.SOURCES.get(fuente) or {}).get("label") or fuente


def _fila(**kw) -> dict:
    base = {
        "id": "", "nicho": "", "modo": "", "modo_label": "",
        "source": "", "carpeta": "", "carpeta_label": "", "producto": "",
        "titulo": "", "titulo_tiktok_completo": "", "tienda": "",
        "caption": "", "emojis": "", "product_url": "",
        "uploaded": False, "uploaded_at": 0.0, "sin_stock": False,
        "rehacer": False, "rehacer_nota": "", "rehecho": False,
        "puede_rehacer": False, "video_path": "", "video_listo_at": 0.0,
        "orden_at": 0.0, "flecha": False, "musica": None,
        "formato": "",
    }
    base.update(kw)
    return base


def _num(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _limpio(x) -> str:
    """Una línea: los títulos extraídos de la ficha traen saltos de línea."""
    return " ".join(str(x or "").split())


def _textos(prod: dict) -> dict:
    return {
        "titulo": _limpio(prod.get("titulo")),
        "titulo_tiktok_completo": _limpio(prod.get("titulo_tiktok_completo")),
        "tienda": _limpio(prod.get("tienda")),
        "caption": str(prod.get("caption") or ""),
        "emojis": str(prod.get("emojis") or ""),
        "sin_stock": bool(prod.get("sin_stock")),
    }


# ---------------------------------------------------------------------------
# POV BOF y POV BOF Largo (comparten los textos del POV BOF)
# ---------------------------------------------------------------------------
def pov_y_largo(usuario: str) -> list[dict]:
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis
    from src.nicho_pov_bof_largo import config as largo_config
    from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis

    usuario = usuario or "ness"
    rp = get_nicho_pov_bof_redis()
    rl = get_nicho_pov_bof_largo_redis()
    if not rp.is_available():
        return []

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pov = ex.submit(_keys, rp, "folder:*")
        f_largo = ex.submit(_keys, rl, "folder:*")
        claves_pov, claves_largo = f_pov.result(), f_largo.result()

    compartidas = [k for k in claves_pov if ":u:" not in k]
    privadas_pov = [k for k in claves_pov if k.endswith(f":u:{usuario}")]

    # Largo: documento por usuario y por modo de guion.
    largo_mias: list[tuple[str, str]] = []  # (clave, modo)
    for k in claves_largo:
        izq, _, der = k.rpartition(":u:")
        if not izq:
            continue
        quien, _, modo = der.partition(":m:")
        if quien == usuario:
            largo_mias.append((k, modo))

    # Qué documentos compartidos hacen falta: los de las carpetas con algo
    # mío (para ness, todos: sus vídeos del POV BOF viven ahí).
    if usuario == "ness":
        necesarias = set(compartidas)
    else:
        necesarias = {k.rpartition(":u:")[0] for k in privadas_pov}
        necesarias |= {k.rpartition(":u:")[0] for k, _ in largo_mias}
        necesarias &= set(compartidas)

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_comp = ex.submit(_mget, rp, sorted(necesarias))
        f_priv = ex.submit(_mget, rp, privadas_pov)
        f_largo = ex.submit(_mget, rl, [k for k, _ in largo_mias])
        comp, priv, docs_largo = f_comp.result(), f_priv.result(), f_largo.result()

    try:
        indice = pov_repo.urls_index()
    except Exception:  # noqa: BLE001 — sin índice vale la url de la ficha
        indice = None

    def _url(prod: dict) -> str:
        try:
            return pov_repo.url_de(prod, indice) or ""
        except Exception:  # noqa: BLE001
            return str(prod.get("product_url") or "")

    filas: list[dict] = []

    # --- POV BOF ---
    for clave, doc in comp.items():
        fuente, carpeta = _partes_folder(clave)
        mios = {}
        if usuario != "ness":
            mios = (priv.get(f"{clave}:u:{usuario}") or {}).get("productos") or {}
            if not mios:
                continue
        todos = doc.get("productos") or {}
        for n in _vigentes(doc):
            base = dict(todos.get(n) or {})
            if usuario != "ness":
                # Lo privado de ness no es de este usuario (`load_folder_para`).
                for campo in pov_repo.CAMPOS_PRIVADOS:
                    base.pop(campo, None)
                base.update(mios.get(n) or {})
            if not base.get("video_path"):
                continue
            listo = _num(base.get("video_listo_at"))
            filas.append(_fila(
                id=SEP.join(("pov", fuente, carpeta, n)), nicho="pov",
                source=fuente, carpeta=carpeta,
                carpeta_label=f"{_label_fuente(fuente)} · {carpeta.strip()}",
                producto=n, **_textos(base), product_url=_url(base),
                uploaded=bool(base.get("uploaded")),
                uploaded_at=_num(base.get("uploaded_at")),
                video_path=str(base.get("video_path")), video_listo_at=listo,
                orden_at=listo,
            ))

    # --- POV BOF Largo ---
    for clave, modo in largo_mias:
        doc = docs_largo.get(clave) or {}
        izq = clave.rpartition(":u:")[0]
        fuente, carpeta = _partes_folder(izq)
        textos_doc = (comp.get(izq) or {}).get("productos") or {}
        modo_real = modo or largo_config.ESTILO_GUION_DEFECTO
        etiqueta = (largo_config.ESTILOS_GUION.get(modo_real) or {}).get("label", modo_real)
        for n, prod in (doc.get("productos") or {}).items():
            if not prod.get("video_path"):
                continue
            textos = dict(textos_doc.get(str(n)) or {})
            listo = _num(prod.get("video_listo_at"))
            filas.append(_fila(
                id=SEP.join(("largo", fuente, carpeta, str(n), modo)), nicho="largo",
                modo=modo_real, modo_label=etiqueta,
                source=fuente, carpeta=carpeta,
                carpeta_label=f"{_label_fuente(fuente)} · {carpeta.strip()}",
                producto=str(n), **_textos(textos), product_url=_url(textos),
                uploaded=bool(prod.get("uploaded")),
                uploaded_at=_num(prod.get("uploaded_at")),
                rehacer=bool(prod.get("rehacer")),
                rehacer_nota=str(prod.get("rehacer_nota") or ""),
                rehecho=bool(prod.get("rehecho")), puede_rehacer=True,
                video_path=str(prod.get("video_path")), video_listo_at=listo,
                orden_at=listo,
            ))
    return filas


# ---------------------------------------------------------------------------
# Moda Mujer · Multimodo (su orden propio se respeta tal cual)
# ---------------------------------------------------------------------------
def multimodo(usuario: str) -> list[dict]:
    """En el orden FIJO de sus tandas (`multimodo:orden:<usuario>`): así Ana
    ve aquí exactamente lo mismo que en la pantalla del multimodo."""
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_ropa import config as ropa_config
    from src.nicho_ropa.repos import product_repo as ropa_repo
    from src.nicho_ropa.repos.redis_base import get_nicho_ropa_redis

    # Las carpetas salen de las claves de Redis y no de listar el Drive (que
    # en frío son 30-100 s): una carpeta sin documento no tiene vídeos.
    rr = get_nicho_ropa_redis()
    if not rr.is_available():
        return []
    carpetas = sorted({
        k[len("productos:"):] for k in _keys(rr, "productos:*")
        if ":u:" not in k and ropa_config.sexo_de_carpeta(k[len("productos:"):]) == "mujer"
    })
    videos = ropa_repo.videos_multimodo(carpetas, usuario)
    if not videos:
        return []
    videos = ropa_repo.fijar_orden_multimodo(videos, usuario, ropa_config.orden_para_publicar)
    try:
        indice = pov_repo.urls_index()
    except Exception:  # noqa: BLE001
        indice = None
    filas: list[dict] = []
    for v in videos:
        formato = str(v.get("formato") or "")
        url = ""
        if indice is not None:
            try:
                url = pov_repo.url_de(v, indice) or ""
            except Exception:  # noqa: BLE001
                url = ""
        filas.append(_fila(
            id=SEP.join(("mm", v["carpeta"], str(v["producto"]))), nicho="mm",
            modo=formato,
            modo_label=ropa_config.MODOS.get(formato, {}).get("label", formato),
            carpeta=v["carpeta"], carpeta_label=ropa_config.carpeta_label(v["carpeta"]),
            producto=str(v["producto"]), **_textos(v), product_url=url or str(v.get("product_url") or ""),
            uploaded=bool(v.get("uploaded")), uploaded_at=_num(v.get("uploaded_at")),
            rehacer=bool(v.get("rehacer")), rehacer_nota=str(v.get("rehacer_nota") or ""),
            rehecho=bool(v.get("rehecho")), puede_rehacer=True,
            video_path=str(v.get("video_path") or ""),
            video_listo_at=_num(v.get("video_listo_at")),
            orden_at=_num(v.get("primer_listo_at") or v.get("video_listo_at")),
            flecha=bool(v.get("flecha")), formato=formato,
            musica=ropa_config.musica_de(formato, f"{v['carpeta']}/{v['producto']}"),
        ))
    return filas


def todas(usuario: str) -> tuple[list[dict], list[dict]]:
    """(POV + Largo, Multimodo). Los dos en paralelo: son Redis distintos."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(pov_y_largo, usuario)
        f2 = ex.submit(multimodo, usuario)
        return f1.result(), f2.result()
