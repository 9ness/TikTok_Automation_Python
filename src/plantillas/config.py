"""Configuración del módulo de plantillas de mensajes."""

from __future__ import annotations

import os


def redis_prefix() -> str:
    return os.getenv("PLANTILLAS_REDIS_PREFIX", "plantillas:")


# Las plantillas de fábrica. Se copian al documento del usuario la primera vez
# que entra, y a partir de ahí son SUYAS: editarlas no toca esto, y borrarlas
# no las resucita. Así el operador puede reescribirlas enteras sin miedo.
#
# `{{CUENTA}}` y `{{WECHAT}}` los rellena la pantalla antes de copiar.
# `{{PRODUCTO}}` existe como hueco pero la plantilla de fábrica NO lo usa: al
# vendedor se le escribe DESDE la ficha del producto, así que el chat ya dice de
# cuál se habla y repetir el nombre solo alarga el mensaje. Queda disponible por
# si algún día hace falta un mensaje que se mande fuera de ese contexto.
#
# El WeChat va al final y como oferta, no como condición: casi todos los
# vendedores son chinos y ahí negocian cómodos (comisión, muestras, exclusivas),
# pero pedirlo ANTES de decir qué quieres parece spam. Lo que se pega es el ID
# de WeChat PERSONALIZADO, no el `wxid_...` que sale por defecto: ese es interno
# y nadie te encuentra buscándolo.
PLANTILLAS_INICIALES: list[dict] = [
    {
        "id": "muestra-gratuita",
        "titulo": "🎁 Muestra gratuita a vendedores",
        "nota": (
            "Escríbelo DESDE la ficha del producto: así el chat ya dice de cuál "
            "hablas y no hace falta nombrarlo. Pon tu @ y tu ID de WeChat."
        ),
        "texto": (
            "Hola,\n\n"
            "Soy creador afiliado de TikTok Shop en España, Nivel 6. Os escribo "
            "por este producto: encaja con lo que estoy publicando ahora mismo.\n\n"
            "Datos de agosto:\n"
            "• +11.500 € de GMV generado\n"
            "• Crecimiento sostenido en un mes que suele ser bajo en ventas\n\n"
            "Propuesta: si me enviáis una muestra gratuita, subo un mínimo de 3 "
            "vídeos en las 2 semanas siguientes a recibirla, con enlace de "
            "afiliado activo. Cada uno con un ángulo distinto —punto de dolor, "
            "urgencia de precio y uso real— para ver cuál convierte mejor. Si el "
            "producto funciona, sigo publicando sin límite por mi parte.\n\n"
            "Mi cuenta es {{CUENTA}}, ahí podéis ver el contenido y el estilo.\n\n"
            "¿Me la podéis enviar? Os paso la dirección por aquí mismo.\n\n"
            "Si os va mejor, hablamos por WeChat: {{WECHAT}}. Ahí puedo "
            "responderos rápido y coordinar el envío y los vídeos.\n\n"
            "Gracias."
        ),
    },
    {
        "id": "campana-halloween",
        "titulo": "🎃 Campaña Halloween — qué tenéis",
        "nota": (
            "Este NO se escribe desde un producto: es para abrir tienda y que "
            "te digan qué catálogo de temporada tienen. Mándalo con semanas de "
            "margen — en octubre ya no da tiempo a enviar la muestra y grabar."
        ),
        # A diferencia del de muestra gratuita, aquí NO se pide un producto
        # concreto: se pregunta qué tienen. El gancho es el calendario — un
        # vendedor de temporada sabe que en octubre ya llega tarde, y quien te
        # trae creadores en septiembre le resuelve la campaña entera.
        "texto": (
            "Hola,\n\n"
            "Soy creador afiliado de TikTok Shop en España, Nivel 6. Os escribo "
            "por la campaña de Halloween: estoy montando ya el calendario de "
            "vídeos para poder publicar desde principios de octubre, que es "
            "cuando arranca la búsqueda en España.\n\n"
            "Mis datos de agosto:\n"
            "• +11.500 € de GMV generado\n"
            "• Crecimiento sostenido en un mes que suele ser bajo en ventas\n\n"
            "¿Qué productos de Halloween tenéis en catálogo? Disfraces, "
            "decoración, maquillaje, luces, accesorios… lo que tengáis para la "
            "temporada. Si me pasáis la lista, elijo los que mejor encajen con "
            "mi audiencia y os digo cuáles cojo.\n\n"
            "Lo que propongo: me enviáis muestra gratuita de los que "
            "seleccionemos y subo un mínimo de 3 vídeos por producto durante "
            "octubre, con enlace de afiliado activo y ángulos distintos para "
            "ver cuál convierte. Halloween es una ventana corta: por eso lo "
            "preparo ahora y no en octubre, cuando ya no da tiempo a enviar, "
            "recibir y grabar.\n\n"
            "Mi cuenta es {{CUENTA}}, ahí podéis ver el contenido y el estilo.\n\n"
            "Si os va mejor, hablamos por WeChat: {{WECHAT}}. Ahí puedo "
            "responderos rápido y cerrar la selección y el envío.\n\n"
            "Gracias."
        ),
    },
]
