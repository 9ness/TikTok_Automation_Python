"""Seed inicial de planes base. Idempotente — solo crea los planes que
faltan (busca por slug). Llamado desde el lifespan de FastAPI.

Los precios son referenciales. El admin puede editarlos desde la UI
después; el seeder NO sobrescribe planes existentes (excepto el backfill
de campos NUEVOS — features, support_level, queue_priority, queue_delay
— que sí se rellena en planes existentes si están con los valores default
del modelo, para que la UI muestre algo razonable sin tener que reeditar
todos los planes a mano tras un deploy).

Estrategia de precios:
- Competencia humana: 600-800€/mes por 5 vídeos/día.
- Nuestro objetivo: 50-60% del precio del editor humano para ganar
  los primeros clientes rápido.
- Coste por vídeo ~0.05$ → margen >95% en todos los tiers.

Ejes de diferenciación entre planes (ver `features` en cada uno):
- 🎬 Volumen diario
- 🕐 Ventana horaria (más amplia = más premium)
- ⚡ Prioridad en cola (top = más premium)
- ⏱ Espaciado entre vídeos (menos = más throughput, más premium)
- 🛠 Tools incluidas
- 💬 Soporte (email / Telegram / Telegram VIP / Dedicado)
- 🎨 Flujos custom / branding propio
- 📞 Onboarding 1-on-1 / llamada estratégica mensual
- 🚀 Early access a herramientas nuevas
"""

from __future__ import annotations

import logging

from src.editor_auto.models import Plan
from src.editor_auto.repos import PlanRepo

logger = logging.getLogger("editor_auto.plan_seeder")


BASE_PLANS: list[dict] = [
    {
        "slug": "trial",
        "name": "Trial · 5 vídeos",
        "description": (
            "Prueba sin compromiso. 5 vídeos en total para que el cliente "
            "valide la calidad antes de pagar el plan mensual."
        ),
        "daily_video_limit": 2,
        "monthly_video_limit": 5,
        "allowed_tools": [],  # todas
        "processing_window_start_hour": 9,
        "processing_window_end_hour": 18,
        "spacing_minutes": 30,
        "queue_priority": 0,
        "queue_delay_minutes": 10,
        "support_level": "email",
        "features": [
            "🎬 Hasta 5 vídeos en total (no diarios)",
            "🕐 Procesado lun-vie 9:00-18:00",
            "⏱ Espaciado ~30 min entre vídeos",
            "🛠 Acceso a todas las herramientas",
            "💬 Soporte por email (respuesta 48 h)",
            "⚠️ Cola estándar (lo último en procesarse)",
        ],
        "price_eur_monthly": 0.0,
        "price_eur_setup_once": 0.0,
        "is_promo": True,
        "promo_slots_total": 50,
        "sort_order": 10,
    },
    {
        "slug": "starter",
        "name": "Starter · 3 vídeos/día",
        "description": (
            "Para creadores que arrancan. 3 vídeos/día (≈90/mes), tools "
            "esenciales (subs auto + corte de silencios). Procesado en "
            "horario laboral 9:00-19:00 para que llegue ordenado."
        ),
        "daily_video_limit": 3,
        "monthly_video_limit": None,
        "allowed_tools": ["subs_auto", "silence_cutter"],
        "processing_window_start_hour": 9,
        "processing_window_end_hour": 19,
        "spacing_minutes": 25,
        "queue_priority": 10,
        "queue_delay_minutes": 5,
        "support_level": "email",
        "features": [
            "🎬 3 vídeos/día (≈90/mes)",
            "🕐 Horario 9:00-19:00 (10 h al día)",
            "⏱ Espaciado 25 min entre vídeos",
            "🛠 Subtítulos auto + corte de silencios",
            "💬 Soporte por email (respuesta 24 h)",
            "⚡ Prioridad baja en cola",
        ],
        "price_eur_monthly": 149.0,
        "price_eur_setup_once": 0.0,
        "sort_order": 20,
    },
    {
        "slug": "pro",
        "name": "Pro · 5 vídeos/día ★ OFERTA",
        "description": (
            "El plan estrella. 5 vídeos/día (≈150/mes) — la misma "
            "capacidad que un editor freelance a 600-800€/mes. "
            "Todas las tools (incluye silence_cutter_scripted con guión "
            "y sticker CTA). Precio especial para los primeros 20 clientes."
        ),
        "daily_video_limit": 5,
        "monthly_video_limit": None,
        "allowed_tools": [],  # todas
        "processing_window_start_hour": 8,
        "processing_window_end_hour": 19,
        "spacing_minutes": 20,
        "queue_priority": 50,
        "queue_delay_minutes": 0,
        "support_level": "telegram",
        "features": [
            "🎬 5 vídeos/día (≈150/mes) — vs editor humano a 600-800€",
            "🕐 Horario 8:00-19:00 (11 h al día)",
            "⏱ Espaciado 20 min entre vídeos",
            "🛠 TODAS las herramientas (subs, silencios, sticker CTA, guión)",
            "💬 Soporte por Telegram (respuesta <8 h en horario)",
            "⚡ Prioridad normal en cola (delante de Starter)",
            "★ Precio promo para los primeros 20 clientes (después 349€)",
        ],
        "price_eur_monthly": 249.0,
        "price_eur_setup_once": 0.0,
        "is_promo": True,
        "promo_slots_total": 20,
        "sort_order": 30,
    },
    {
        "slug": "studio",
        "name": "Studio · 10 vídeos/día",
        "description": (
            "Para agencias o creadores con varias cuentas. 10 vídeos/día "
            "(~300/mes). Ventana ampliada 8:00-21:00 para reaccionar a "
            "tendencias. Soporte prioritario."
        ),
        "daily_video_limit": 10,
        "monthly_video_limit": None,
        "allowed_tools": [],
        "processing_window_start_hour": 8,
        "processing_window_end_hour": 21,
        "spacing_minutes": 15,
        "queue_priority": 100,
        "queue_delay_minutes": 0,
        "support_level": "telegram_vip",
        "features": [
            "🎬 10 vídeos/día (≈300/mes) — apto para 2-3 cuentas",
            "🕐 Horario 8:00-21:00 (13 h al día — reacción a tendencias)",
            "⏱ Espaciado 15 min entre vídeos (entrega ágil)",
            "🛠 TODAS las herramientas",
            "💬 Soporte VIP por Telegram (respuesta <2 h en horario)",
            "⚡ Prioridad ALTA en cola (siempre delante de Starter/Pro)",
            "🚀 Early access a herramientas nuevas (beta)",
        ],
        "price_eur_monthly": 549.0,
        "price_eur_setup_once": 0.0,
        "sort_order": 40,
    },
    {
        "slug": "agencia",
        "name": "Agencia · 24/7 ilimitado",
        "description": (
            "Sin límite diario, ventana 24h, flujos personalizados, "
            "soporte dedicado. Para agencias y creadores serios de "
            "TikTok Shop que necesitan reaccionar en cualquier momento."
        ),
        "daily_video_limit": 0,  # 0 = ilimitado
        "monthly_video_limit": None,
        "allowed_tools": [],
        "processing_window_start_hour": 0,
        "processing_window_end_hour": 23,
        "spacing_minutes": 0,
        "queue_priority": 200,
        "queue_delay_minutes": 0,
        "support_level": "dedicado",
        "features": [
            "🎬 Vídeos ILIMITADOS al día",
            "🕐 Procesado 24/7 (sin ventana horaria)",
            "⏱ Sin espaciado entre vídeos (entrega inmediata)",
            "🛠 TODAS las herramientas + flujos personalizados",
            "💬 Soporte dedicado WhatsApp/Telegram (respuesta <30 min)",
            "⚡ Prioridad MÁXIMA en cola (siempre el primero)",
            "🎨 Branding propio (white-label opcional)",
            "🚀 Early access total a todo lo nuevo",
        ],
        "price_eur_monthly": 999.0,
        "price_eur_setup_once": 0.0,
        "sort_order": 50,
    },
    {
        "slug": "enterprise",
        "name": "Enterprise · multi-cuenta + estrategia",
        "description": (
            "Para creadores top de TikTok Shop con varias cuentas y "
            "ticket alto. Incluye llamada estratégica mensual con el "
            "equipo, configuración multi-cuenta con flujos diferentes "
            "por cuenta, y onboarding 1-on-1."
        ),
        "daily_video_limit": 0,  # ilimitado
        "monthly_video_limit": None,
        "allowed_tools": [],
        "processing_window_start_hour": 0,
        "processing_window_end_hour": 23,
        "spacing_minutes": 0,
        "queue_priority": 500,
        "queue_delay_minutes": 0,
        "support_level": "dedicado_24_7",
        "features": [
            "🎬 Vídeos ILIMITADOS · multi-cuenta (hasta 5 cuentas separadas)",
            "🕐 Procesado 24/7 sin restricciones",
            "⏱ Sin espaciado · entrega instantánea",
            "🛠 Flujos custom por cuenta (cada cuenta su estilo)",
            "💬 Soporte 24/7 con responsable de cuenta asignado",
            "⚡ Prioridad MÁXIMA — siempre por delante del resto",
            "📞 Llamada estratégica MENSUAL (revisión KPIs + ideas)",
            "🎯 Onboarding 1-on-1 personalizado (2 h)",
            "🎨 Branding completo white-label",
            "📊 Dashboard avanzado con métricas por cuenta",
        ],
        "price_eur_monthly": 1499.0,
        "price_eur_setup_once": 299.0,
        "sort_order": 60,
    },
]


def _backfill_new_fields(existing: Plan, template: dict) -> bool:
    """Si el plan existente tiene los campos nuevos en su default vacío,
    los rellena desde el template. Devuelve True si tocó algo.

    Solo backfilla campos que están vacíos para NO sobrescribir lo que
    el admin pudo haber editado a mano. Útil al desplegar la nueva
    versión sobre planes ya creados.
    """
    touched = False
    # features list vacía → backfill
    if not existing.features and template.get("features"):
        existing.features = list(template["features"])
        touched = True
    # support_level "email" (default) y el template tiene otro → backfill
    if existing.support_level == "email" and template.get("support_level", "email") != "email":
        existing.support_level = template["support_level"]
        touched = True
    # queue_priority 0 (default) y template lo distingue → backfill
    if existing.queue_priority == 0 and template.get("queue_priority", 0) != 0:
        existing.queue_priority = template["queue_priority"]
        touched = True
    # queue_delay_minutes 0 (default) y template > 0 → backfill
    if existing.queue_delay_minutes == 0 and template.get("queue_delay_minutes", 0) > 0:
        existing.queue_delay_minutes = template["queue_delay_minutes"]
        touched = True
    return touched


def seed_base_plans() -> int:
    """Crea los planes que faltan + backfilla campos nuevos en los
    existentes. Devuelve cuántos creó o modificó.

    Idempotente.
    """
    repo = PlanRepo()
    created = 0
    backfilled = 0
    for data in BASE_PLANS:
        slug = data["slug"]
        existing = repo.get_by_slug(slug)
        if existing is None:
            plan = Plan(**data)
            repo.save(plan)
            created += 1
            logger.info(
                "[plan_seeder] creado plan '%s' (%s) · %.0f€/mes",
                plan.slug, plan.name, plan.price_eur_monthly,
            )
            continue
        # Existe — solo backfill de campos nuevos vacíos.
        if _backfill_new_fields(existing, data):
            repo.save(existing)
            backfilled += 1
            logger.info(
                "[plan_seeder] backfill features/soporte en plan '%s'", slug,
            )
    if created == 0 and backfilled == 0:
        logger.info("[plan_seeder] planes ya inicializados (skip)")
    return created + backfilled
