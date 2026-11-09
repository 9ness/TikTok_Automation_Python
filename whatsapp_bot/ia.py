"""Respuestas con IA (Claude Haiku) para lo que no cubren los menús.

Poco y barato: un tope de respuestas por chat y día, prompt cacheado y, ante
cualquier fallo, se vuelve al menú. El prompt y la FAQ están en ``prompts/``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import MODELO_IA, Ajustes
from .precios import texto_precios

log = logging.getLogger("whatsapp_bot.ia")

MARCA_NESTOR = "[[NESTOR]]"
ESFUERZO = "low"
MAX_TOKENS = 1500  # el pensamiento cuenta dentro; la respuesta son 2-3 frases
MAX_TURNOS = 10
# USD por millón de tokens (entrada, salida). Oct 2026.
TARIFAS = {"claude-haiku-5-5": (0.10, 0.50)}

_PROMPTS = Path(__file__).resolve().parent / "prompts"


@dataclass
class RespuestaIA:
    texto: str = ""
    derivar: bool = False  # la IA no sabe: que lo coja Néstor
    entrada: int = 0
    salida: int = 0
    cache_lectura: int = 0
    cache_escritura: int = 0
    usd: float = 0.0


def coste_usd(modelo: str, entrada: int, salida: int, cache_lectura: int = 0,
              cache_escritura: int = 0) -> float:
    p_in, p_out = TARIFAS.get(modelo, TARIFAS[MODELO_IA])
    total = entrada * p_in + cache_lectura * p_in * 0.1 + cache_escritura * p_in * 1.25 + salida * p_out
    return round(total / 1_000_000, 6)


def prompt_sistema(ajustes: Ajustes) -> str:
    faq = (_PROMPTS / "faq.md").read_text(encoding="utf-8")
    faq = faq.replace("{web}", ajustes.web_publica).replace("{horario}", ajustes.horario)
    base = (_PROMPTS / "asistente.md").read_text(encoding="utf-8")
    return (
        base.replace("{negocio}", ajustes.nombre_negocio)
        .replace("{faq}", faq.strip())
        .replace("{precios}", texto_precios())
    )


def turnos(historial: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Pasa el historial del chat a turnos user/assistant alternos."""
    salida: list[dict[str, str]] = []
    for msg in historial[-MAX_TURNOS * 2:]:
        texto = (msg.get("texto") or "").strip()
        if not texto:
            continue
        rol = "user" if msg.get("direccion") == "entra" else "assistant"
        if salida and salida[-1]["role"] == rol:
            salida[-1]["content"] += "\n" + texto
        else:
            salida.append({"role": rol, "content": texto})
    while salida and salida[0]["role"] != "user":
        salida.pop(0)
    while salida and salida[-1]["role"] != "user":
        salida.pop()
    return salida


class Asistente:
    def __init__(self, ajustes: Ajustes, cliente: Any | None = None) -> None:
        self._aj = ajustes
        self._cliente = cliente
        self._sistema: str | None = None

    @property
    def activo(self) -> bool:
        return self._cliente is not None or bool(self._aj.anthropic_api_key)

    def _anthropic(self) -> Any:
        if self._cliente is None:
            import anthropic  # se importa tarde: sin clave no hace falta el SDK

            self._cliente = anthropic.Anthropic(
                api_key=self._aj.anthropic_api_key, max_retries=2, timeout=30.0
            )
        return self._cliente

    def responder(self, historial: list[dict[str, Any]], contexto_cliente: str = "") -> RespuestaIA | None:
        """Respuesta de la IA, o None si no se pudo (el bot enseña el menú)."""
        if not self.activo:
            return None
        mensajes = turnos(historial)
        if not mensajes:
            return None
        if self._sistema is None:
            self._sistema = prompt_sistema(self._aj)
        sistema: list[dict[str, Any]] = [
            {"type": "text", "text": self._sistema, "cache_control": {"type": "ephemeral"}}
        ]
        if contexto_cliente:
            sistema.append({"type": "text", "text": "# Este cliente\n\n" + contexto_cliente})
        try:
            resp = self._anthropic().messages.create(
                model=MODELO_IA,
                max_tokens=MAX_TOKENS,
                output_config={"effort": ESFUERZO},
                system=sistema,
                messages=mensajes,
            )
        except Exception as exc:  # red, cuota, clave… nunca tumba el webhook
            log.warning("la IA no contestó (%s)", type(exc).__name__)
            return None

        uso = getattr(resp, "usage", None)
        entrada = int(getattr(uso, "input_tokens", 0) or 0)
        salida = int(getattr(uso, "output_tokens", 0) or 0)
        c_lee = int(getattr(uso, "cache_read_input_tokens", 0) or 0)
        c_escribe = int(getattr(uso, "cache_creation_input_tokens", 0) or 0)
        r = RespuestaIA(
            entrada=entrada, salida=salida, cache_lectura=c_lee, cache_escritura=c_escribe,
            usd=coste_usd(MODELO_IA, entrada, salida, c_lee, c_escribe),
        )
        if getattr(resp, "stop_reason", "") == "refusal":
            r.derivar = True
            return r
        texto = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", None) or [])
            if getattr(b, "type", "") == "text"
        ).strip()
        if not texto or MARCA_NESTOR in texto:
            r.derivar = True
            return r
        r.texto = texto
        return r
