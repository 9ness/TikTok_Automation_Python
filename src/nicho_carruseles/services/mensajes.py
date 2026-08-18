"""Los dos mensajes que van quemados en el carrusel.

Se piden en UNA llamada para toda la carpeta, no una por producto: es lo único
que hace que el mensaje 1 salga DISTINTO en cada uno. El mensaje 1 no habla del
producto (es la chica sorprendida), así que diez llamadas aisladas escribirían
diez veces la misma frase — que es exactamente lo que hunde este formato
cuando la cuenta publica veinte carruseles seguidos.

Del prompt del curso ("Pront para Mensajes"), con una diferencia: allí se pedían
20 variantes a mano para copiarlas una a una; aquí se pide una por producto.
"""

from __future__ import annotations

import json
from typing import Callable

from src.nicho_carruseles import config
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None

# Palabras que convierten el mensaje 1 en una promesa de salud. El prompt ya lo
# prohíbe, pero se coló ("Mis articulaciones nunca estuvieron mejor") porque el
# modelo ve el título del producto y le tira escribir sobre él. Con suplementos
# y cosmética eso es lo que tumba una cuenta, así que se comprueba también aquí:
# el mensaje 1 va sobre la foto de una chica, donde no se ve ningún producto.
# Estas se buscan por el PRINCIPIO de la palabra, para cazar sus variantes
# ("articulacion" → articulaciones).
_PROMESAS_RAIZ = (
    "articulacion", "inmun", "defensa", "energia", "digest", "dolor", "duerm",
    "dormir", "descans", "arruga", "mancha", "adelgaz", "recupera", "colagen",
    "vitamin", "musculo", "estres", "ansiedad", "memoria", "concentracion",
    "alivi", "cicatriz", "inflama",
)
# Y estas SOLO como palabra entera: por raíz se comían frases inocentes
# ("locura" no promete nada, y "pelotas" tampoco).
_PROMESAS_EXACTAS = (
    "cura", "curar", "curo", "curan", "sana", "sano", "salud", "piel", "peso",
    "grasa", "pelo", "cabello", "sueno", "suenos",
)
# "uñas" se mira CON tilde: sin ella es "unas", que es un artículo y se llevaba
# por delante frases inocentes ("me han regalado unas...").
_CON_TILDE = ("uñas",)


def promete_algo(mensaje: str) -> str:
    """La palabra que convierte el mensaje en una promesa, o "" si está limpio."""
    import re
    import unicodedata

    original = str(mensaje or "").lower()
    for palabra in _CON_TILDE:
        if re.search(rf"\b{palabra}\b", original):
            return palabra
    plano = unicodedata.normalize("NFKD", original)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    for raiz in _PROMESAS_RAIZ:
        if re.search(rf"\b{raiz}", plano):
            return raiz
    for palabra in _PROMESAS_EXACTAS:
        if re.search(rf"\b{palabra}\b", plano):
            return palabra
    return ""


def escribir(
    productos: dict[str, dict], *, evitar: list[str] | None = None,
    frase: str = "", on_log: OnLog = _noop,
) -> dict[str, dict]:
    """`{producto: {titulo}}` → `{producto: {mensaje1, mensaje2}}`.

    `evitar` son mensajes 1 que ya se han usado en otras carpetas: el modelo no
    los ve de otra forma y acabaría repitiéndolos entre carpeta y carpeta.
    """
    con_titulo = {
        pid: prod for pid, prod in productos.items()
        if str(prod.get("titulo") or "").strip()
    }
    if not con_titulo:
        on_log("[carruseles] ningún producto con título: extrae los textos primero")
        return {}

    lista = [
        {
            "id": pid,
            "titulo": str(prod.get("titulo") or "").strip(),
            "tienda": str(prod.get("tienda") or "").strip(),
        }
        for pid, prod in sorted(con_titulo.items(), key=lambda kv: kv[0])
    ]
    peticion = {"productos": lista}
    if frase:
        # La frase de un carrusel que YA funciona: los mensajes 2 son variantes
        # suyas adaptadas a cada producto. Es el método del curso.
        peticion["frase_referencia"] = frase
    if evitar:
        # Solo los últimos: la lista entera crecería sin fin y se comería el
        # prompt según se van haciendo carpetas.
        peticion["mensajes_ya_usados"] = evitar[-60:]

    on_log(f"[carruseles] escribiendo mensajes de {len(lista)} productos…")
    try:
        raw = generate_json(
            config.leer_prompt("mensajes"),
            json.dumps(peticion, ensure_ascii=False),
            # Alta a propósito: aquí lo que se pide es variedad.
            temperature=1.0,
        )
    except Exception as e:  # noqa: BLE001
        on_log(f"[carruseles] Gemini falló al escribir los mensajes: {e}")
        return {}

    if not isinstance(raw, dict):
        on_log(f"[carruseles] respuesta inesperada: {type(raw).__name__}")
        return {}

    salida: dict[str, dict] = {}
    vistos = {m.strip().lower() for m in (evitar or [])}
    for pid in con_titulo:
        entrada = raw.get(pid)
        if not isinstance(entrada, dict):
            continue
        m1 = str(entrada.get("mensaje1") or "").strip()
        m2 = str(entrada.get("mensaje2") or "").strip()
        if not m1 or not m2:
            continue
        # El mensaje 1 se cae si repite (TikTok lo lee como contenido duplicado)
        # o si promete algo. Pero el 2 es de ESE producto y no tiene la culpa:
        # antes se descartaba la pareja entera y el producto se quedaba con los
        # dos mensajes viejos — así se quedaron once con el párrafo largo del
        # carrito naranja después de acortarlos todos.
        motivo = ""
        if m1.lower() in vistos:
            motivo = "estaba repetido"
        elif promete_algo(m1):
            motivo = f"promete algo («{promete_algo(m1)}»)"
        if motivo:
            on_log(f"[carruseles] el mensaje 1 del producto {pid} {motivo}, se queda el de antes")
            salida[pid] = {"mensaje2": m2}
            continue
        vistos.add(m1.lower())
        salida[pid] = {"mensaje1": m1, "mensaje2": m2}

    faltan = [pid for pid in con_titulo if pid not in salida]
    if faltan:
        on_log(f"[carruseles] sin mensajes utilizables: {faltan}")
    on_log(f"[carruseles] {len(salida)}/{len(con_titulo)} productos con mensajes")
    return salida
