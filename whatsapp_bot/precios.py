"""Precios y planes del Editor Auto.

COPIA de ``nebulabs-media/lib/pricing.ts`` (la única fuente de verdad). El bot
no inventa ofertas: dice lo que hay aquí y nada más. Si cambian los precios en
la web, se cambian aquí también; ``tests/bot_whatsapp/test_precios.py`` compara
los dos ficheros y falla si no coinciden.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .horario import ZONA


@dataclass(frozen=True)
class Plan:
    id: str
    nombre: str
    videos_dia: int
    precio: int  # €/mes sin oferta
    precio_fundador: int  # €/mes con la oferta fundador
    incluye: tuple[str, ...]
    popular: bool = False
    a_medida: bool = False  # VIP: se contrata hablando con Néstor


PLANES: tuple[Plan, ...] = (
    Plan(
        "starter", "Básico", 3, 59, 29,
        ("3 vídeos/día (≈90 al mes)", "Cortes, subtítulos y flecha CTA", "Entrega en 24 h",
         "Soporte por email y WhatsApp"),
    ),
    Plan(
        "pro", "Pro", 5, 99, 49,
        ("5 vídeos/día (≈150 al mes)", "Todo lo del Básico", "Fotos de apoyo (B-roll) incluidas",
         "Prioridad en la cola: pasa antes que el Básico", "Soporte prioritario por WhatsApp"),
        popular=True,
    ),
    Plan(
        "studio", "Studio", 10, 179, 89,
        ("10 vídeos/día (≈300 al mes)", "Todo lo del Pro",
         "Más prioridad en la cola: pasa antes que el Pro",
         "Para publicar más de un vídeo al día por producto"),
    ),
    Plan(
        "agencia", "Escala", 15, 249, 129,
        ("15 vídeos/día (≈450 al mes)", "El triple de vídeos que el Pro", "Todo lo del Studio",
         "Prioridad alta en la cola", "Trato directo por WhatsApp"),
    ),
    Plan(
        "vip", "VIP a medida", 5, 299, 149,
        ("Tu estilo de edición fijo: el que elijas o el de la cuenta que nos enseñes",
         "Puedes cambiar de estilo una vez al mes", "Gancho de texto en los primeros segundos",
         "Fotos de apoyo de lo que nombras, en el momento justo",
         "Cada vídeo revisado antes de entregártelo", "Una ronda de cambios por vídeo",
         "Máxima prioridad en la cola: tus vídeos van primero",
         "Hasta 5 vídeos/día y WhatsApp directo"),
        a_medida=True,
    ),
)

# Oferta fundador (Black Friday 2026). Pasada la fecha, el bot deja de ofrecerla.
FUNDADOR_PLAZAS = 25
FUNDADOR_FIN = "2026-11-23T23:59:00+01:00"
FUNDADOR_FIN_TEXTO = "domingo 23 de noviembre"
VIP_PLAZAS = 5
PRUEBA_VIDEOS = 3  # vídeos gratis al registrarse
DESCUENTO_ANUAL = 2 / 12  # paga 10 meses, usa 12


def fundador_vigente(ahora: datetime | None = None) -> bool:
    ahora = ahora or datetime.now(ZONA)
    return ahora < datetime.fromisoformat(FUNDADOR_FIN)


def precio_mes(plan: Plan, ahora: datetime | None = None) -> int:
    return plan.precio_fundador if fundador_vigente(ahora) else plan.precio


def precio_anual_al_mes(plan: Plan, ahora: datetime | None = None) -> int:
    """Lo que sale al mes pagando el año (mismo redondeo que la web)."""
    return math.floor(precio_mes(plan, ahora) * (1 - DESCUENTO_ANUAL) + 0.5)


def plan_por_nombre(texto: str) -> Plan | None:
    """Busca un plan por su id o su nombre dentro de un texto."""
    bajo = _plano(texto)
    for plan in sorted(PLANES, key=lambda p: -len(p.nombre)):
        if _plano(plan.nombre) in bajo or plan.id in bajo.split():
            return plan
    if "vip" in bajo.split():
        return PLANES[-1]
    return None


def _plano(texto: str) -> str:
    cambios = str.maketrans("áéíóúü", "aeiouu")
    return (texto or "").lower().translate(cambios)


def linea_plan(plan: Plan, ahora: datetime | None = None) -> str:
    if fundador_vigente(ahora):
        precio = f"{plan.precio_fundador} €/mes (antes {plan.precio} €)"
    else:
        precio = f"{plan.precio} €/mes"
    marca = " ⭐ el más elegido" if plan.popular else ""
    return f"*{plan.nombre}* · {plan.videos_dia} vídeos/día · {precio}{marca}"


def texto_precios(ahora: datetime | None = None) -> str:
    """Resumen de planes para mandar por WhatsApp."""
    lineas = ["Estos son los planes de edición de vídeo:", ""]
    lineas += [linea_plan(p, ahora) for p in PLANES if not p.a_medida]
    vip = PLANES[-1]
    lineas += ["", f"{linea_plan(vip, ahora)} · edición a tu estilo y revisada a mano ({VIP_PLAZAS} plazas)"]
    lineas += ["", "Todos incluyen cortes automáticos, subtítulos y flecha CTA."]
    if fundador_vigente(ahora):
        lineas.append(
            f"Precio fundador para las {FUNDADOR_PLAZAS} primeras plazas, hasta el {FUNDADOR_FIN_TEXTO}."
        )
    else:
        lineas.append("Si en la web ves otro precio, vale el de la web.")
    lineas.append("Pagando el año salen 2 meses gratis.")
    lineas.append(f"Y puedes probarlo gratis: tus {PRUEBA_VIDEOS} primeros vídeos no se pagan.")
    return "\n".join(lineas)


def texto_plan(plan: Plan, ahora: datetime | None = None) -> str:
    """Ficha de un plan concreto."""
    lineas = [linea_plan(plan, ahora), ""]
    lineas += [f"• {punto}" for punto in plan.incluye]
    lineas += ["", f"Pagando el año: {precio_anual_al_mes(plan, ahora)} €/mes (2 meses gratis)."]
    return "\n".join(lineas)
