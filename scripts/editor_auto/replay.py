"""Grabar y reproducir las llamadas de pago del cortador (banco de regresión).

El cortador llama a Deepgram (ASR) y a una IA (Claude, OpenAI o Gemini) por
`analyze_transcript_json`. Para medir cambios sin gastar, el banco las graba
una vez en disco y luego las reproduce: misma entrada → misma respuesta, 0 €.

Modos (`instalar(modo, carpeta)`):
  - "record": llama de verdad y guarda cada respuesta (gasta, una vez).
  - "replay": solo lee lo grabado. Si falta algo, NO llama: lanza
    `ReplayMiss`. Deepgram cae entonces a Whisper local (gratis) y una pasada
    de IA sin grabar falla como si la IA no respondiera.
  - "offline": como replay pero sin carpeta: nada de pago llega a salir.

Clave = sha256 de (función, argumentos). Las respuestas van a
`<carpeta>/<función>/<clave>.json`. Solo para scripts: NO se importa desde
el código de producción.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable

MODOS = ("record", "replay", "offline")


class ReplayMiss(RuntimeError):
    """Llamada de pago sin respuesta grabada (en replay nunca se llama)."""


class Grabadora:
    def __init__(self, modo: str, carpeta: str | None):
        if modo not in MODOS:
            raise ValueError(f"modo {modo!r} no válido ({MODOS})")
        if modo != "offline" and not carpeta:
            raise ValueError("record/replay necesitan carpeta")
        self.modo = modo
        self.carpeta = carpeta
        self.stats = {"hits": 0, "misses": 0, "grabadas": 0}
        self._originales: list[tuple[Any, str, Any]] = []

    # -- disco -------------------------------------------------------------
    @staticmethod
    def clave(nombre: str, args: Any) -> str:
        if isinstance(args, (bytes, bytearray)):
            blob = bytes(args)
        else:
            blob = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str).encode()
        return hashlib.sha256(nombre.encode() + b"\0" + blob).hexdigest()[:32]

    def _ruta(self, nombre: str, clave: str) -> str:
        return os.path.join(self.carpeta or "", nombre, f"{clave}.json")

    def llamar(self, nombre: str, clave: str, real: Callable[[], Any]) -> Any:
        ruta = self._ruta(nombre, clave)
        if self.modo != "offline" and os.path.exists(ruta):
            self.stats["hits"] += 1
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)["respuesta"]
        if self.modo != "record":
            self.stats["misses"] += 1
            raise ReplayMiss(f"{nombre} sin grabar ({clave})")
        resp = real()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"funcion": nombre, "respuesta": resp}, f, ensure_ascii=False)
        os.replace(tmp, ruta)
        self.stats["grabadas"] += 1
        return resp

    # -- parches -----------------------------------------------------------
    def _parchear(self, modulo: Any, attr: str, nuevo: Any) -> None:
        self._originales.append((modulo, attr, getattr(modulo, attr)))
        setattr(modulo, attr, nuevo)

    def instalar(self) -> "Grabadora":
        from src.editor_auto.api import claude_client, gemini_client, openai_client
        from src.editor_auto.tools import silence_cutter

        dg_real = silence_cutter._deepgram_words

        def deepgram(payload: bytes, *, language=None, model="nova-3", offset=0.0):
            k = self.clave("deepgram", hashlib.sha256(payload).hexdigest()
                           + f"|{language}|{model}")
            words = self.llamar("deepgram", k, lambda: dg_real(
                payload, language=language, model=model, offset=0.0))
            # Se graba con offset 0 y se aplica aquí: el mismo tramo vale
            # aunque el corte de audio se pida desde otro punto.
            return [{**w, "start": w["start"] + offset, "end": w["end"] + offset}
                    for w in words]

        self._parchear(silence_cutter, "_deepgram_words", deepgram)

        for nombre, mod in (("claude", claude_client), ("openai", openai_client),
                            ("gemini", gemini_client)):
            real = mod.analyze_transcript_json

            def envoltorio(*, _n=nombre, _real=real, **kw):
                return self.llamar(_n, self.clave(_n, kw), lambda: _real(**kw))

            self._parchear(mod, "analyze_transcript_json", envoltorio)
        return self

    def desinstalar(self) -> None:
        while self._originales:
            mod, attr, orig = self._originales.pop()
            setattr(mod, attr, orig)

    def __enter__(self) -> "Grabadora":
        return self.instalar()

    def __exit__(self, *_exc) -> None:
        self.desinstalar()
