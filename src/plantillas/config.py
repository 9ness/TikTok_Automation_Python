"""Configuración del módulo de plantillas de mensajes."""

from __future__ import annotations

import os


def redis_prefix() -> str:
    return os.getenv("PLANTILLAS_REDIS_PREFIX", "plantillas:")


# Las plantillas de fábrica. Se copian al documento del usuario la primera vez
# que entra, y a partir de ahí son SUYAS: editarlas no toca esto, y borrarlas
# no las resucita. Así el operador puede reescribirlas enteras sin miedo.
#
# `{{CUENTA}}` lo rellena la pantalla antes de copiar. `{{PRODUCTO}}` existe
# como hueco pero la plantilla de fábrica NO lo usa: al vendedor se le escribe
# DESDE la ficha del producto, así que el chat ya dice de cuál se habla y
# repetir el nombre solo alarga el mensaje. Queda disponible por si algún día
# hace falta un mensaje que se mande fuera de ese contexto.
PLANTILLAS_INICIALES: list[dict] = [
    {
        "id": "muestra-gratuita",
        "titulo": "🎁 Muestra gratuita a vendedores",
        "nota": (
            "Escríbelo DESDE la ficha del producto: así el chat ya dice de cuál "
            "hablas y no hace falta nombrarlo. Solo tienes que poner tu @."
        ),
        "texto": (
            "Hola,\n\n"
            "Soy creador afiliado de TikTok Shop en España, Nivel 6. Os escribo "
            "por este producto: encaja con lo que estoy publicando ahora mismo.\n\n"
            "Datos de agosto:\n"
            "• +13.500 € de GMV generado\n"
            "• Crecimiento sostenido en un mes que suele ser bajo en ventas\n\n"
            "Propuesta: si me enviáis una muestra gratuita, subo un mínimo de 3 "
            "vídeos en las 2 semanas siguientes a recibirla, con enlace de "
            "afiliado activo. Cada uno con un ángulo distinto —punto de dolor, "
            "urgencia de precio y uso real— para ver cuál convierte mejor. Si el "
            "producto funciona, sigo publicando sin límite por mi parte.\n\n"
            "Mi cuenta es {{CUENTA}}, ahí podéis ver el contenido y el estilo.\n\n"
            "¿Me la podéis enviar? Os paso la dirección por aquí mismo.\n\n"
            "Gracias."
        ),
    },
]
