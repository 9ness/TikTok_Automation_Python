"""Calendario de campañas de TikTok Shop (Black Friday y Navidad).

Transversal a todos los nichos, igual que el tope diario: la campaña es de la
tienda y de la cuenta, no de un formato de vídeo. De aquí beben la franja de la
web (debajo del contador) y el MCP de agentes (`campanas`), para que las dos
cosas digan lo mismo.

Fuentes: el calendario «BFCM + Christmas Deals» de TikTok Shop EU (11 nov – 16
dic 2026) y el «Calendario de campañas de España Q4» que pasó la agencia
(Miture, 8 oct 2026), que les pone NIVEL de prioridad: SS > S > A > B. El año que viene se cambia la lista `CAMPANAS` y ya está: el resto
se calcula.

Por qué hay AVISOS y no solo fechas: un vídeo tarda días en coger tracción, así
que el contenido de una campaña tiene que estar publicado ANTES de que empiece.
Cada hito avisa `AVISO_DIAS` antes.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.cuotas import config

# Días de antelación con los que se avisa de que toca preparar contenido.
AVISO_DIAS = 14
# Antes de esto la franja ni sale: a dos meses vista solo estorba.
VISIBLE_DIAS = 60

_DIAS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

# Prioridad de la campaña según TikTok (calendario Q4 de la agencia).
NIVELES = {"SS": "máxima", "S": "alta", "A": "media", "B": "baja"}

CAMPANAS: list[dict] = [
    {
        "id": "oct_mensual",
        "nombre": "Campaña mensual de octubre",
        "corto": "Campaña de octubre",
        "emoji": "🎃",
        "color": "amber",
        "nivel": "S",
        "inicio": "2026-10-27",
        "fin": "2026-10-31",
        "tema": "Campaña mensual de fin de mes (coincide con Halloween)",
        "consejo": "Campaña de nivel S. Octubre es para ACUMULAR vídeos para Black Friday: "
                   "5 vídeos distintos por producto prioritario y 10+ si pasa de 200 €.",
        "guion": "Ángulo de campaña de fin de mes: buen precio y producto top de la semana.",
    },
    {
        "id": "bf_front",
        "nombre": "Black Friday · Front Run Week",
        "corto": "Black Friday",
        "emoji": "🛒",
        "color": "rose",
        "nivel": "SS",
        "inicio": "2026-11-11",
        "fin": "2026-11-17",
        "tema": "Semana de categorías y ranking de directos",
        "consejo": "Empiezan las ofertas de Black Friday (TikTok compite contra Amazon). "
                   "Sube producto con descuento o buen precio y vídeos de «chollo».",
        "guion": "Ángulo de oferta adelantada de Black Friday: precio, chollo, «antes de que se agote».",
    },
    {
        "id": "bf_mid",
        "nombre": "Black Friday · Mid Week",
        "corto": "Black Friday",
        "emoji": "🎁",
        "color": "violet",
        "nivel": "SS",
        "inicio": "2026-11-18",
        "fin": "2026-11-24",
        "tema": "Festival de marcas y ranking de directos (23-24: Live All-Star)",
        "consejo": "Semana de marcas: mejor productos con marca conocida y reseñas.",
        "guion": "Ángulo de marca y confianza: «el que todo el mundo está comprando esta semana».",
    },
    {
        "id": "bf_peak",
        "nombre": "Black Friday Peak",
        "corto": "Black Friday Peak",
        "emoji": "🔥",
        "color": "red",
        "nivel": "SS",
        "inicio": "2026-11-25",
        "fin": "2026-11-29",
        "tema": "Live All-Star (creador + marca + subasta). Día fuerte: viernes 27",
        "consejo": "El pico de ventas. Lo preparado tiene que estar YA publicado; "
                   "estos días, volumen al tope diario.",
        "guion": "Urgencia máxima de Black Friday: «solo este fin de semana», «el precio más bajo del año».",
    },
    {
        "id": "cyber",
        "nombre": "Cyber Monday",
        "corto": "Cyber Monday",
        "emoji": "🛍️",
        "color": "sky",
        "nivel": "SS",
        "inicio": "2026-11-30",
        "fin": "2026-11-30",
        "tema": "Último día de ofertas del Black Friday",
        "consejo": "Última oportunidad: vídeos de «hoy es el último día».",
        "guion": "Última oportunidad: «hoy acaba», «si no lo pillaste el viernes».",
    },
    {
        "id": "xmas",
        "nombre": "Navidad · Ofertas festivas",
        "corto": "Navidad",
        "emoji": "🎄",
        "color": "emerald",
        "nivel": "S",
        "inicio": "2026-12-01",
        "fin": "2026-12-16",
        "tema": "Campaña de Navidad (hasta el 16: llega antes de Nochebuena)",
        "consejo": "Ángulo REGALO: para quién es, «llega antes de Navidad». "
                   "La última semana, prisa por el envío.",
        "guion": "Ángulo regalo: para quién es el regalo perfecto y que llega a tiempo para Navidad.",
    },
]

# Días sueltos del calendario Q4 que NO son campaña de varios días: ofertas
# semanales (nivel A) y días de subastas, los miércoles (nivel B). Solo en
# octubre; en noviembre y diciembre la agencia no da fechas.
EVENTOS: list[dict] = (
    [{"fecha": f, "tipo": "ofertas_semanales", "nombre": "Ofertas semanales", "emoji": "🏷️",
      "nivel": "A", "consejo": "Día de ofertas semanales: sube los productos que tengan descuento."}
     for f in ("2026-10-11", "2026-10-18", "2026-10-25")]
    + [{"fecha": f, "tipo": "subastas", "nombre": "Día de subastas", "emoji": "🔨",
        "nivel": "B", "consejo": "Día de subastas (directos): prioridad baja para vídeos."}
       for f in ("2026-10-07", "2026-10-14", "2026-10-21")]
)

# Días que el calendario oficial resalta en color (el gran día y los cambios).
DESTACADOS = {"2026-11-19", "2026-11-27", "2026-11-30"}

# Hitos de los que se avisa con antelación (el primero de cada bloque).
HITOS = ("oct_mensual", "bf_front", "bf_peak", "cyber", "xmas")

# Regla fija para agentes y guiones: sale en el estado y en la guía.
REGLA_PROMOCION = (
    "Nunca prometas un descuento, precio de Black Friday o regalo que la ficha "
    "del producto NO tenga: es «promoción incoherente» y sanciona la cuenta. "
    "Sin oferta real, usa el ángulo que sí es cierto (regalo, llega a tiempo, "
    "producto top de la semana)."
)


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _hoy() -> date:
    return _d(config.hoy())


def _publica(c: dict, hoy: date) -> dict:
    ini, fin = _d(c["inicio"]), _d(c["fin"])
    return {**c, "dias_para": (ini - hoy).days, "dias_restantes": (fin - hoy).days}


def campana_de(dia: date) -> dict | None:
    for c in CAMPANAS:
        if _d(c["inicio"]) <= dia <= _d(c["fin"]):
            return c
    return None


def _semanas() -> list[dict]:
    """El calendario en semanas de miércoles a martes, como el oficial.

    Arranca en Black Friday: la campaña de octubre va suelta en la lista.
    """
    ini = _d(next(c for c in CAMPANAS if c["id"] == "bf_front")["inicio"])
    fin = _d(CAMPANAS[-1]["fin"])
    semanas: list[dict] = []
    dia = ini
    n = 1
    while dia <= fin:
        dias = []
        for _ in range(7):
            if dia > fin:
                break
            c = campana_de(dia)
            dias.append({
                "fecha": dia.isoformat(),
                "dia": _DIAS[dia.weekday()],
                "campana": c["id"] if c else None,
                "destacado": dia.isoformat() in DESTACADOS,
            })
            dia += timedelta(days=1)
        semanas.append({"n": n, "dias": dias})
        n += 1
    # El oficial mete el día suelto del final (mié 16 dic) en la semana 5.
    if len(semanas) > 1 and len(semanas[-1]["dias"]) == 1:
        semanas[-2]["dias"] += semanas.pop()["dias"]
    return semanas


def estado(hoy: date | None = None) -> dict:
    """Dónde estamos del calendario: campaña en curso, la próxima y los avisos."""
    hoy = hoy or _hoy()
    ini, fin = _d(CAMPANAS[0]["inicio"]), _d(CAMPANAS[-1]["fin"])
    activa = campana_de(hoy)
    proximas = [c for c in CAMPANAS if _d(c["inicio"]) > hoy]
    # La siguiente que CAMBIA algo: dentro de Black Friday las semanas se
    # suceden sin hueco, así que la próxima es la inmediata.
    proxima = proximas[0] if proximas else None

    avisos: list[str] = []
    for c in CAMPANAS:
        if c["id"] not in HITOS:
            continue
        falta = (_d(c["inicio"]) - hoy).days
        if 0 < falta <= AVISO_DIAS:
            avisos.append(
                f"{c['emoji']} {c['corto']} empieza en {falta} día{'s' if falta != 1 else ''} "
                f"({_d(c['inicio']).strftime('%d/%m')}): {c['consejo']}"
            )
    for ev in EVENTOS:
        falta = (_d(ev["fecha"]) - hoy).days
        if 0 <= falta <= 1:
            cuando = "hoy" if falta == 0 else "mañana"
            avisos.append(f"{ev['emoji']} {ev['nombre']} {cuando} (nivel {ev['nivel']}): {ev['consejo']}")
    if activa and activa["id"] == "xmas":
        quedan = (_d(activa["fin"]) - hoy).days
        if quedan <= 5:
            avisos.append(
                f"🎄 Quedan {quedan} días de campaña de Navidad: vídeos de «llega antes de Nochebuena»."
            )

    return {
        "hoy": hoy.isoformat(),
        "inicio": ini.isoformat(),
        "fin": fin.isoformat(),
        "visible": (ini - hoy).days <= VISIBLE_DIAS and hoy <= fin,
        "terminado": hoy > fin,
        "activa": _publica(activa, hoy) if activa else None,
        "proxima": _publica(proxima, hoy) if proxima else None,
        "avisos": avisos,
        "aviso_dias": AVISO_DIAS,
        "campanas": [_publica(c, hoy) for c in CAMPANAS],
        "eventos": [{**ev, "dias_para": (_d(ev["fecha"]) - hoy).days}
                    for ev in sorted(EVENTOS, key=lambda x: x["fecha"]) if _d(ev["fecha"]) >= hoy],
        "niveles": NIVELES,
        "semanas": _semanas(),
        "regla_promocion": REGLA_PROMOCION,
    }


def contexto_guion(hoy: date | None = None) -> str:
    """Una frase para orientar un guion a la campaña del momento ("" si no toca).

    Toca si hay campaña en curso o empieza dentro del aviso. Lleva siempre la
    regla de no prometer lo que la ficha no tiene.
    """
    e = estado(hoy)
    c = e["activa"] or (
        e["proxima"] if e["proxima"] and e["proxima"]["dias_para"] <= AVISO_DIAS else None
    )
    if not c:
        return ""
    return f"Campaña de TikTok Shop: {c['nombre']} ({c['inicio']} a {c['fin']}). {c['guion']} {REGLA_PROMOCION}"
