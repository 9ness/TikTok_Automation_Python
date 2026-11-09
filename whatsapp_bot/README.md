# Bot de WhatsApp del Editor Auto

Servicio FastAPI pequeño (para **vps-webs**) que atiende por WhatsApp a los clientes del Editor Auto.
No importa nada de `src/`: habla con la API del editor por HTTP (Tailscale) y guarda sus
conversaciones en un SQLite propio.

## Qué hace

| El cliente… | El bot… |
|---|---|
| saluda o escribe «menú» | botones: Precios · Mis vídeos · Hablar con Néstor |
| pregunta precios / planes | los de `precios.py` (copia de `frontend/lib/pricing.ts`; un test avisa si se desfasan) |
| «quiero el plan X» / pagar | enlace o datos de pago (`WHATSAPP_ENLACE_PAGO` / `WHATSAPP_DATOS_PAGO`); si no hay, avisa a Néstor |
| pregunta por sus vídeos | busca su teléfono en la API del editor: cuota del día, estado de cada vídeo y el MP4 (vídeo ≤16 MB, documento ≤100 MB, o enlace) |
| aún no está vinculado | pide su email → el editor le manda un código de 6 cifras → lo escribe en WhatsApp |
| pide hablar con Néstor | pausa el bot en ese chat (`WHATSAPP_PAUSA_HUMANO_MIN`) y avisa al panel con notificación |
| pregunta otra cosa | Haiku (`MODELO_IA` en `config.py`) con `prompts/asistente.md` + `prompts/faq.md`; tope `WHATSAPP_IA_MAX_DIA` por chat |

Además: si Néstor contesta desde el móvil (eco de coexistencia) el bot se calla `WHATSAPP_SILENCIO_MIN`
en ese chat; fuera de `WHATSAPP_HORARIO` contesta una vez con el mensaje de fuera de horario; registra
todas las conversaciones (página «Conectar WhatsApp» → Conversaciones); cuenta los mensajes del mes y
frena en `WHATSAPP_TOPE_MES` (Meta regala 1.000 mensajes de servicio al mes desde el 1-oct-2026).

Avisos salientes: la API del editor llama a `POST /interno/aviso` cuando el lote del día queda listo.
Dentro de la ventana de 24 h va como mensaje normal (gratis). Fuera de ella haría falta una plantilla
(se cobra): está apagado salvo `WHATSAPP_PLANTILLAS_DE_PAGO=1`.

## Cómo se conecta (elige UNA vía)

Seguir usando la app del móvil a la vez que el bot («coexistencia») solo lo ofrece Meta a través de
un Solution Partner / Tech Provider: con una app propia no se puede.

| Vía | Qué supone | Coste | Pasos de Néstor |
|---|---|---|---|
| **A · 360dialog** (`WHATSAPP_PROVEEDOR=360dialog`) | Mismo número y la app del móvil sigue funcionando. Se conecta escaneando un QR | 49 EUR/mes por número + mensajes de Meta | Alta en 360dialog → «Connect existing WhatsApp Business App number» → QR → copiar la API key |
| **C · Número aparte con Cloud API** (`WHATSAPP_PROVEEDOR=meta`) | Gratis, pero ese número deja de poder usarse en la app del móvil | 0 EUR + mensajes de Meta | App en developers.facebook.com → producto WhatsApp → añadir número → token permanente |
| A' · YCloud | Como A; dicen que sin cuota mensual | sin confirmar | No está implementado (haría falta un tercer proveedor) |
| B · Ser Tech Provider | Embedded Signup propio | Revisión de Meta de semanas | No compensa para un solo número |

**Sin confirmar con una cuenta real** (se leyó en la documentación, nov 2026, y no se ha probado):
las rutas de 360dialog `GET/POST /v1/configs/webhook`, `/v1/configs/templates` y `health_status`;
que 360dialog reenvíe la cabecera `X-Webhook-Secreto` que le configuramos; el formato exacto de los
ecos `smb_message_echoes`. Si algo de eso difiere, el arreglo está en `meta.py` y `eventos.py`.

## Variables

Todas en `.env.example`. Las claves se ponen con `clave whatsapp-bot <VARIABLE>` (escribe en
`~/proyectos/whatsapp-bot/.env.local` de vps-trabajo; el despliegue lo copia a vps-webs). Nunca en el
código ni en un chat. La página «Conectar WhatsApp» enseña cuáles faltan (solo el nombre).

## Desplegar (lo hace el chat del Editor, con el sí de Néstor)

Todo desde vps-trabajo, con la rama ya fusionada:

```bash
whatsapp_bot/deploy/desplegar.sh --preparar   # crea ~/proyectos/whatsapp-bot/.env.local y genera los tokens
clave whatsapp-bot D360_API_KEY               # (o las de Meta) · ANTHROPIC_API_KEY · PANEL_TOKEN → Néstor, por SSH
whatsapp_bot/deploy/desplegar.sh --estado     # qué falta
whatsapp_bot/deploy/desplegar.sh              # sube a vps-webs:~/whatsapp-bot, venv, systemd, comprueba /salud
whatsapp_bot/deploy/desplegar.sh --enlazar    # 3 variables EDITOR_WHATSAPP_* en el .env de la fábrica
whatsapp_bot/deploy/desplegar.sh --volver     # si algo va mal
```

Lo que el script NO hace y hay que hacer a mano:

1. **Caddy de vps-webs**: publicar solo el webhook. El script imprime el bloque (`handle /wa/webhook`
   dentro de `factory.nebulabsmedia.com`, antes de `handle @grande`). El resto del bot escucha solo en
   la IP de Tailscale (`100.83.196.101:8093`), así `/admin` e `/interno` no son públicos.
2. **Recrear el contenedor `api`** de la fábrica tras `--enlazar` (lee `.env` al arrancar).
3. Comprobar que el contenedor llega al bot: `docker exec <api> curl -s http://100.83.196.101:8093/salud`,
   y que el bot llega al editor (`EDITOR_API_URL`; por defecto `http://100.96.125.108:8080`, por confirmar).
4. En Meta (vía C): pegar la URL `https://factory.nebulabsmedia.com/wa/webhook` y el `WHATSAPP_VERIFY_TOKEN`.
   Con 360dialog no hace falta: el botón «Suscribir» de la página se lo dice a 360dialog.
5. Plantillas: botón «Enviar a aprobar» de la página (las tres de `plantillas/*.json`).

## Tests

```bash
python -m pytest tests/bot_whatsapp tests/editor_auto/test_whatsapp_vinculo.py tests/api/test_editor_whatsapp.py -q
```

El webhook se prueba con cargas de ejemplo de Meta (`tests/bot_whatsapp/ejemplos.py`) firmadas con un
App Secret de prueba; Meta, el editor, la IA y el panel son dobles. **No se ha probado contra Meta,
360dialog ni Haiku reales, ni se ha desplegado.**
