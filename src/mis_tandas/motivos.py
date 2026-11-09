"""Por qué se van a rojo y a ámbar los vídeos: los motivos del semáforo, agrupados.

Cada vídeo revisado guarda una frase («La suela sale color caramelo y cambia
de tono entre clips»). Sueltas no enseñan nada; agrupadas dicen qué falla más
y en qué nicho, que es lo que hay que mirar ANTES de generar el siguiente.

Módulo puro: recibe el documento del semáforo y devuelve números. No toca
Redis ni guarda nada. Límite conocido: el semáforo guarda UNA entrada por
vídeo y se pisa al rehacerlo, así que un rojo ya rehecho y aprobado no cuenta.
"""

from __future__ import annotations

import re
import time
import unicodedata

# (clave, título, lo que hay que hacer, raíces que la delatan). Una frase
# puede caer en varias: «cambia entre clips y la luz se enciende sola».
CATEGORIAS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("producto_distinto", "El producto no es el de la ficha",
     "Compara foto limpia y ficha con cada imagen ANTES de animar: color, corte, piezas y tamaño.",
     ("en la foto", "de la foto", "la ficha", "no coincide", "no es el real", "otro corte", "otro modelo",
      "inventad", "sale color", "sale beige", "en vez de", "el real es", "no aparece en la foto",
      "distint", "incoherente", "inconsistente", "no tiene el", "la foto", " otro ", " otra ", " otros ",
      "no lleva", "falta", "sin gancho", "no se aprecia", "apenas se", "mas gris", "mas beige", "mas clar",
      "mas oscur", "mas alt", "mas cort")),
    ("cambia_entre_clips", "El producto cambia de un clip a otro",
     "Los clips 2+ salen de la imagen del clip 1 como referencia; mira los clips lado a lado.",
     ("entre clips", "entre escenas", "entre el plano", "cambia de", "cambia entre", "se transforma",
      "desaparece", "aparece un", "aparece papel", "de otro", "se deforma", "se recoloca", " cambia ",
      " cambian ", "pasa de", "solo aparece", "solo se ve", "al principio")),
    ("fisica_imposible", "Pasa algo que no puede pasar",
     "Nada se mueve solo, nada flota ni atraviesa nada, el agua sale por su sitio, la escala no cambia.",
     ("sin enchuf", "sin cable", "se enciende sol", "suspendid", "imposible", "de la nada", "escala",
      "atravies", "flota", "sin soporte", "se mueve sol", "sin estar en", "no salen de", "sin interruptor",
      " sola ", " solo al ", "cae por", "antes de añadir")),
    ("encendido", "Electrónica encendida (luces, LED, pantallas)",
     "Bombillas y aparatos, apagados salvo que encenderse sea su función y se vea igual en todos los clips.",
     ("encendid", " led", "iluminad", "pantalla", " luz ", "luces", "lucecita", "electronic", "apagad",
      "proyecta", "parpade", "linterna", "se enciende", "cable")),
    ("mano_toca", "Una mano toca o roza el producto",
     "Que la mano roce NO es ámbar: si el producto no cambia al tocarlo es verde. Mira esos segundos a 2 fps.",
     ("mano", "dedo", "roza", "toca", "se apoya", "agarr")),
    ("complejo", "Producto complejo: piezas, variantes o funciones",
     "Cuenta las piezas contra la ficha y comprueba la variante del enlace antes de subir.",
     ("kit", "pieza", "varias", "varios", "multifuncion", "funciones", "set ", "variante", "verificar",
      "confirmar", "unidades", "cabezal", "accesorio", "deposito")),
    ("texto", "Texto, subtítulos, etiquetas o logos",
     "Lee el subtítulo entero y el texto del envase fotograma a fotograma; los logos, idénticos a la ficha.",
     ("subtitul", "texto", "etiqueta", "rotulo", "letra", "logo", "escudo", "titulo", "portada")),
    ("movimiento", "Vídeo estático o al límite de movimiento",
     "`scripts/medir_movimiento.py`: media ≥ 2 y ninguna mitad por debajo de 1,5 antes del verde.",
     ("estatic", "movimiento", "quiet", "parad")),
    ("voz_guion", "La voz o el guion no cuadran con lo que se ve",
     "Cada clip enseña lo que dice la voz en su tramo; el guion nombra el producto de la ficha.",
     ("la voz", "guion", " dice ", "locuc", "audio", "musica", "dialogo")),
    ("ninos", "Niños o producto infantil",
     "En TikTok Shop no salen niños: cambia de producto o de plano.",
     ("niño", "niña", "infantil", "kids", "bebe")),
    ("formato", "Formato: bandas negras, marca de agua, encuadre",
     "`cropdetect` debe dar 1080:1920 y la esquina inferior derecha, sin la estrella de Gemini.",
     ("banda", "marca de agua", "estrella de gemini", "encuadre", "recort", "3:4", "horizontal")),
    ("descartado", "Descartado por decisión (política, época, famosos, sancionado)",
     "No es un fallo de generación: mira el motivo antes de elegir un producto o un viral parecido.",
     ("descartad", "no publicar", "navideñ", "famos", "politica", "sancionad", "no replicable")),
]

SIN_MOTIVO = "sin_motivo"
OTROS = "otros"
# Frases que no dicen nada: cuentan como «sin motivo».
_VACIOS = {"", "marcado a mano", "rehacer", "rojo", "ambar", "ok", "bien", "mal"}

TITULOS = {c: t for c, t, _, _ in CATEGORIAS} | {
    SIN_MOTIVO: "Sin motivo escrito", OTROS: "Otros motivos"}
CONSEJOS = {c: a for c, _, a, _ in CATEGORIAS} | {
    SIN_MOTIVO: "Pon SIEMPRE el motivo en una frase: es lo que permite aprender de los rojos.",
    OTROS: "Léelos: si se repiten, falta una categoría."}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower().replace("ñ", "\0"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").replace("\0", "ñ")
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def clasificar(motivo: str) -> list[str]:
    """Las categorías de una frase (una o varias). Vacía → `sin_motivo`."""
    p = re.sub(r"[^a-z0-9ñ:,.%/ ]", " ", _plano(motivo))
    p = " " + re.sub(r"\s+", " ", p).strip() + " "
    if p.strip(" .:,") in _VACIOS:
        return [SIN_MOTIVO]
    cats = [c for c, _, _, raices in CATEGORIAS if any(r in p for r in raices)]
    return cats or [OTROS]


def nicho_de(id_: str) -> str:
    """`largo|…` → largo, `car|…` → car (el prefijo del id de Mis tandas)."""
    return id_.split("|", 1)[0] if "|" in id_ else "otro"


def resumen(semaforos: dict[str, dict], dias: int = 0, ahora: float | None = None,
            ejemplos: int = 3) -> dict:
    """Totales por color y, para rojo y ámbar, las categorías de más a menos
    con ejemplos (los más recientes). `dias` > 0: solo lo revisado en ese plazo."""
    ahora = ahora or time.time()
    desde = ahora - dias * 86400 if dias and dias > 0 else 0
    filas = [(i, s) for i, s in (semaforos or {}).items()
             if isinstance(s, dict) and float(s.get("at") or 0) >= desde]
    colores = {"verde": 0, "ambar": 0, "rojo": 0}
    por_nicho: dict[str, dict[str, int]] = {}
    grupos: dict[str, dict[str, list]] = {"rojo": {}, "ambar": {}}
    for id_, s in filas:
        color = s.get("color")
        if color not in colores:
            continue
        colores[color] += 1
        n = por_nicho.setdefault(nicho_de(id_), {"verde": 0, "ambar": 0, "rojo": 0})
        n[color] += 1
        if color in grupos:
            for cat in clasificar(s.get("motivo") or ""):
                grupos[color].setdefault(cat, []).append((float(s.get("at") or 0), id_, s.get("motivo") or ""))
    total = sum(colores.values())

    def _lista(color: str) -> list[dict]:
        out = []
        for cat, items in grupos[color].items():
            items.sort(reverse=True)
            out.append({
                "categoria": cat, "titulo": TITULOS[cat], "videos": len(items),
                "pct": round(100 * len(items) / max(colores[color], 1)),
                "que_hacer": CONSEJOS[cat],
                "ejemplos": [{"id": i, "motivo": m} for _, i, m in items[:ejemplos] if m],
            })
        out.sort(key=lambda x: (x["categoria"] in (SIN_MOTIVO, OTROS), -x["videos"], x["categoria"]))
        return out

    return {
        "dias": int(dias or 0),
        "revisados": total,
        "colores": colores,
        "pct_rojo": round(100 * colores["rojo"] / total, 1) if total else 0.0,
        "pct_ambar": round(100 * colores["ambar"] / total, 1) if total else 0.0,
        "rojo": _lista("rojo"),
        "ambar": _lista("ambar"),
        "por_nicho": [
            {"nicho": k, **v, "pct_rojo": round(100 * v["rojo"] / max(sum(v.values()), 1), 1)}
            for k, v in sorted(por_nicho.items(), key=lambda kv: -sum(kv[1].values()))
        ],
        "nota": "Un rojo ya rehecho y aprobado no cuenta: el semáforo guarda solo el último color de cada vídeo.",
    }
