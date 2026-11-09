"""Servicio FastAPI del bot de WhatsApp del Editor.

Rutas:
- ``GET  /salud``            para el despliegue.
- ``GET  /webhook``          verificación de Meta (hub.challenge).
- ``POST /webhook``          mensajes. Meta: firma X-Hub-Signature-256.
                             360dialog: cabecera secreta que le dimos nosotros.
- ``POST /interno/aviso``    lo llama la API del editor («tus vídeos están listos»).
- ``/admin/*``               lo usa la página «Conectar WhatsApp» del panel.

Arranque (vps-webs, solo en la IP de Tailscale; Caddy publica únicamente /webhook):
``uvicorn --factory whatsapp_bot.app:crear_app --host 100.83.196.101 --port 8093``.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .almacen import Almacen
from .bot import Bot
from .config import CABECERA_SECRETO, CLAVES_360, CLAVES_META, MODELO_IA, Ajustes
from .editor import ClienteEditor
from .eventos import extraer_eventos
from .firma import firma_valida
from .ia import Asistente
from .meta import ClienteMeta, ErrorMeta
from .panel import Panel

log = logging.getLogger("whatsapp_bot.app")
_PLANTILLAS = Path(__file__).resolve().parent / "plantillas"


def plantillas_propuestas() -> list[dict[str, Any]]:
    """Las plantillas que traemos escritas (``plantillas/*.json``)."""
    salida = []
    for fichero in sorted(_PLANTILLAS.glob("*.json")):
        try:
            salida.append(json.loads(fichero.read_text(encoding="utf-8")))
        except ValueError:
            log.warning("plantilla mal escrita: %s", fichero.name)
    return salida


def _texto_plantilla(definicion: dict[str, Any]) -> str:
    for comp in definicion.get("components") or []:
        if str(comp.get("type", "")).upper() == "BODY":
            return str(comp.get("text", ""))
    return ""


def crear_app(
    ajustes: Ajustes | None = None,
    *,
    almacen: Almacen | None = None,
    meta: ClienteMeta | None = None,
    editor: ClienteEditor | None = None,
    ia: Asistente | None = None,
    panel: Panel | None = None,
) -> FastAPI:
    aj = ajustes or Ajustes.desde_entorno()
    db = almacen or Almacen(aj.db_path)
    cli_meta = meta or ClienteMeta(aj)
    cli_editor = editor or ClienteEditor(aj)
    bot = Bot(aj, db, cli_meta, cli_editor, ia or Asistente(aj), panel or Panel(aj))

    app = FastAPI(title="Bot de WhatsApp del Editor", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.bot = bot
    app.state.ajustes = aj

    # ── seguridad ───────────────────────────────────────────────────────────
    def con_token(request: Request) -> None:
        """Bearer del panel o de la API del editor (vale cualquiera de los dos)."""
        validos = [t for t in (aj.admin_token, aj.interno_token) if t]
        if not validos:
            raise HTTPException(503, "falta WHATSAPP_ADMIN_TOKEN")
        cabecera = request.headers.get("authorization", "")
        dado = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
        if not dado or not any(hmac.compare_digest(dado.encode(), t.encode()) for t in validos):
            raise HTTPException(401, "token incorrecto")

    def procesar(payload: dict[str, Any]) -> None:
        for evento in extraer_eventos(payload):
            try:
                bot.procesar(evento)
            except Exception:  # un mensaje raro no puede tumbar los demás
                log.exception("fallo al atender un evento de WhatsApp")

    # ── públicas ────────────────────────────────────────────────────────────
    @app.get("/salud")
    def salud() -> dict[str, Any]:
        return {"ok": True, "proveedor": aj.proveedor, "listo": aj.listo}

    @app.get("/webhook")
    def verificar(request: Request) -> PlainTextResponse:
        q = request.query_params
        token = q.get("hub.verify_token", "")
        if (
            q.get("hub.mode") == "subscribe"
            and aj.verify_token
            and hmac.compare_digest(token.encode(), aj.verify_token.encode())
        ):
            db.poner_dato("webhook_verificado", int(time.time()))
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "token de verificación incorrecto")

    @app.post("/webhook")
    async def recibir(request: Request, tareas: BackgroundTasks) -> dict[str, bool]:
        cuerpo = await request.body()
        if aj.es_360:
            if not aj.webhook_secreto:
                raise HTTPException(503, "falta WHATSAPP_WEBHOOK_SECRETO")
            dado = request.headers.get(CABECERA_SECRETO, "")
            if not hmac.compare_digest(dado.encode(), aj.webhook_secreto.encode()):
                raise HTTPException(401, "secreto incorrecto")
        else:
            if not aj.app_secret:
                raise HTTPException(503, "falta WHATSAPP_APP_SECRET")
            if not firma_valida(cuerpo, request.headers.get("x-hub-signature-256"), aj.app_secret):
                raise HTTPException(401, "firma incorrecta")
        try:
            payload = json.loads(cuerpo)
        except ValueError:
            raise HTTPException(400, "JSON incorrecto") from None
        db.poner_dato("webhook_ultimo", int(time.time()))
        if isinstance(payload, dict):
            tareas.add_task(procesar, payload)  # contestar 200 ya; Meta reintenta si tardamos
        return {"ok": True}

    # ── lo llama la API del editor ──────────────────────────────────────────
    @app.post("/interno/aviso", dependencies=[Depends(con_token)])
    async def aviso(request: Request) -> dict[str, Any]:
        datos = await _json(request)
        if datos.get("evento") != "videos_listos":
            raise HTTPException(400, "evento desconocido")
        try:
            listos = int(datos.get("listos") or 0)
        except (TypeError, ValueError):
            listos = 0
        return bot.aviso_videos_listos(
            str(datos.get("telefono") or ""), str(datos.get("nombre") or ""),
            str(datos.get("dia") or ""), listos, str(datos.get("caduca") or ""),
        )

    # ── panel «Conectar WhatsApp» ───────────────────────────────────────────
    @app.get("/admin/diagnostico", dependencies=[Depends(con_token)])
    def diagnostico() -> dict[str, Any]:
        return _diagnostico(aj, db, cli_meta, cli_editor, bot)

    @app.get("/admin/conversaciones", dependencies=[Depends(con_token)])
    def conversaciones(limite: int = 50) -> dict[str, Any]:
        return {"conversaciones": db.conversaciones(max(1, min(limite, 200)))}

    @app.get("/admin/conversacion", dependencies=[Depends(con_token)])
    def conversacion(wa_id: str) -> dict[str, Any]:
        return {"mensajes": db.mensajes_chat(wa_id)}

    @app.post("/admin/plantillas", dependencies=[Depends(con_token)])
    def enviar_plantillas() -> dict[str, Any]:
        resultado: dict[str, Any] = {"enviadas": [], "ya_estaban": [], "errores": []}
        try:
            existentes = {str(p.get("name")) for p in cli_meta.plantillas()}
        except ErrorMeta as exc:
            return {**resultado, "errores": [{"nombre": "*", "error": exc.mensaje}]}
        for definicion in plantillas_propuestas():
            nombre = str(definicion.get("name"))
            if nombre in existentes:
                resultado["ya_estaban"].append(nombre)
                continue
            try:
                cli_meta.crear_plantilla(definicion)
                resultado["enviadas"].append(nombre)
            except ErrorMeta as exc:
                resultado["errores"].append({"nombre": nombre, "error": exc.mensaje})
        return resultado

    @app.post("/admin/suscribir", dependencies=[Depends(con_token)])
    def suscribir() -> dict[str, Any]:
        try:
            return {"ok": bool(cli_meta.suscribir_app())}
        except ErrorMeta as exc:
            return {"ok": False, "error": exc.mensaje}

    @app.post("/admin/prueba", dependencies=[Depends(con_token)])
    async def prueba(request: Request) -> dict[str, Any]:
        datos = await _json(request)
        wa_id = re.sub(r"\D", "", str(datos.get("telefono") or ""))
        if len(wa_id) < 8:
            return {"ok": False, "error": "teléfono incorrecto (con prefijo, p. ej. 34600111222)"}
        texto = str(datos.get("texto") or "") or f"Prueba del bot de {aj.nombre_negocio} ✅"
        try:
            wamid = cli_meta.enviar_texto(wa_id, texto)
        except ErrorMeta as exc:
            return {"ok": False, "error": exc.mensaje}
        db.registrar(wa_id, "sale", "prueba", texto, wamid=wamid or None)
        return {"ok": True}

    @app.post("/admin/pausa", dependencies=[Depends(con_token)])
    async def pausa(request: Request) -> dict[str, Any]:
        datos = await _json(request)
        wa_id = str(datos.get("wa_id") or "")
        try:
            minutos = int(datos.get("minutos") or aj.pausa_humano_min)
        except (TypeError, ValueError):
            minutos = aj.pausa_humano_min
        if not wa_id:
            return {"ok": False, "error": "falta wa_id"}
        db.pausar(wa_id, max(1, minutos) * 60, "panel")
        return {"ok": True}

    @app.post("/admin/reanudar", dependencies=[Depends(con_token)])
    async def reanudar(request: Request) -> dict[str, Any]:
        datos = await _json(request)
        wa_id = str(datos.get("wa_id") or "")
        if not wa_id:
            return {"ok": False, "error": "falta wa_id"}
        db.reanudar(wa_id)
        return {"ok": True}

    return app


async def _json(request: Request) -> dict[str, Any]:
    try:
        datos = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON incorrecto") from None
    if not isinstance(datos, dict):
        raise HTTPException(400, "JSON incorrecto")
    return datos


def _diagnostico(aj: Ajustes, db: Almacen, meta: ClienteMeta, editor: ClienteEditor,
                 bot: Bot) -> dict[str, Any]:
    """Comprueba sola cada pieza de la conexión. Nunca devuelve valores de claves."""
    pasos: list[dict[str, Any]] = []

    def paso(pid: str, titulo: str, ok: bool | None, detalle: str) -> bool | None:
        pasos.append({"id": pid, "titulo": titulo, "ok": ok, "detalle": detalle})
        return ok

    nombres = CLAVES_360 if aj.es_360 else CLAVES_META
    faltan = list(aj.faltan) if aj.faltan or aj.listo else list(nombres)
    claves_ok = bool(paso(
        "claves", "Claves puestas", aj.listo,
        "todas puestas" if aj.listo else "faltan: " + ", ".join(faltan or nombres),
    ))

    numero = None
    numero_ok: bool | None = None
    webhook_ok: bool | None = None
    remotas: list[dict[str, Any]] = []
    plantillas_ok: bool | None = None
    detalle_plantillas = "se comprueba cuando estén las claves"
    if claves_ok:
        try:
            n = meta.numero()
            numero = {
                "telefono": str(n.get("display_phone_number") or ""),
                "nombre": str(n.get("verified_name") or ""),
                "calidad": str(n.get("quality_rating") or ""),
                "en_app": n.get("is_on_biz_app") if isinstance(n.get("is_on_biz_app"), bool) else None,
            }
            numero_ok = True
            paso("numero", "Número conectado", True, numero["telefono"] or "responde")
        except ErrorMeta as exc:
            numero_ok = False
            paso("numero", "Número conectado", False, exc.mensaje)
        try:
            webhook_ok, detalle = meta.webhook_suscrito()
        except ErrorMeta as exc:
            webhook_ok, detalle = False, exc.mensaje
        paso("webhook", "Webhook suscrito", webhook_ok, detalle)
        try:
            remotas = meta.plantillas()
            aprobadas = sum(1 for p in remotas if str(p.get("status", "")).upper() == "APPROVED")
            plantillas_ok = aprobadas > 0
            detalle_plantillas = f"{aprobadas} aprobadas de {len(remotas)}"
        except ErrorMeta as exc:
            plantillas_ok, detalle_plantillas = False, exc.mensaje
    else:
        paso("numero", "Número conectado", None, "se comprueba cuando estén las claves")
        paso("webhook", "Webhook suscrito", None, "se comprueba cuando estén las claves")

    ultimo = int(db.dato("webhook_ultimo", "0") or 0)
    paso(
        "webhook_recibido", "Llegan mensajes", bool(ultimo) or None,
        time.strftime("último: %d/%m %H:%M", time.localtime(ultimo)) if ultimo
        else "aún no ha llegado ninguno: escribe al número desde otro móvil",
    )
    paso("plantillas", "Plantillas aprobadas", plantillas_ok, detalle_plantillas)

    if editor.configurado:
        editor_ok, detalle = editor.alcanzable()
    else:
        editor_ok, detalle = False, "faltan EDITOR_API_URL o EDITOR_API_KEY"
    paso("editor", "API del editor", editor_ok, detalle)
    paso("ia", "IA para preguntas libres", bot.ia.activo or None,
         MODELO_IA if bot.ia.activo else "sin ANTHROPIC_API_KEY: solo menús")
    paso("panel", "Avisos a Néstor", bot.panel.configurado or None,
         "puestos" if bot.panel.configurado else "faltan PANEL_URL o PANEL_TOKEN")

    estados = {str(p.get("name")): str(p.get("status") or "").upper() for p in remotas}
    return {
        "proveedor": aj.proveedor,
        "listo": bool(claves_ok and numero_ok and webhook_ok and editor_ok),
        "faltan": [] if aj.listo else faltan,
        "pasos": pasos,
        "numero": numero,
        "webhook": {
            "url": f"{aj.url_publica}/webhook" if aj.url_publica else "",
            "verificado": int(db.dato("webhook_verificado", "0") or 0),
            "ultimo_recibido": ultimo,
        },
        "plantillas": [
            {
                "nombre": str(p.get("name") or ""),
                "estado": str(p.get("status") or "").upper(),
                "categoria": str(p.get("category") or ""),
                "idioma": str(p.get("language") or ""),
                "motivo": str(p.get("rejected_reason") or ""),
            }
            for p in remotas
        ],
        "plantillas_propuestas": [
            {
                "nombre": str(d.get("name") or ""),
                "categoria": str(d.get("category") or ""),
                "texto": _texto_plantilla(d),
                "estado": estados.get(str(d.get("name")), "") or "sin_enviar",
            }
            for d in plantillas_propuestas()
        ],
        "mes": {"enviados": db.salientes_del_mes(), "tope": aj.tope_mes},
        "horario": aj.horario,
        "abierto_ahora": bot.abierto_ahora(),
        "ia": {"activa": bot.ia.activo, "modelo": MODELO_IA, **db.gasto_ia()},
    }


def __getattr__(nombre: str) -> Any:
    # ``uvicorn whatsapp_bot.app:app`` crea la app al pedirla, no al importar
    # el módulo (así los tests no leen el entorno ni abren la base de datos).
    if nombre == "app":
        global _app
        try:
            return _app
        except NameError:
            _app = crear_app()
            return _app
    raise AttributeError(nombre)
