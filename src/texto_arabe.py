"""Texto en árabe mezclado con español y números (cuenta árabe, 29/10/2026).

Lo usan los dos pintores de texto: el bloque del POV
(`nicho_pov_bof.pipeline.video_editor`) y el de las fotos de los carruseles
(`nicho_carruseles.services.texto_foto`). Ver `docs/CUENTA_ARABE.md`.

- Ninguna de las fuentes de siempre trae letras árabes: con árabe se usa
  Tajawal, que también trae latinas.
- La unión de letras y el orden derecha→izquierda los hace PIL con raqm.
- En una línea que se lee de derecha a izquierda, lo latino y los números se
  AÍSLAN (LRI…PDI): sin eso el algoritmo bidi daba la vuelta a «24-48h»
  («48h-24») y sacaba el euro al otro lado («€ 39,90»).
"""

from __future__ import annotations

import re

FUENTE_ARABE = "Tajawal-ExtraBold.ttf"
ARABE_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
# Un tramo latino/numérico: empieza y acaba en letra latina, cifra o símbolo de
# precio; por dentro admite espacios y la puntuación de precios y plazos.
_LTR_RE = re.compile(r"[A-Za-zÀ-ÿ0-9](?:[A-Za-zÀ-ÿ0-9.,:%€$+\-/ ]*[A-Za-zÀ-ÿ0-9%€$])?")
_LRI, _PDI = "⁦", "⁩"


def es_arabe(texto: str) -> bool:
    return bool(ARABE_RE.search(texto or ""))


def fuente_para(texto: str, fuente: str) -> str:
    return FUENTE_ARABE if es_arabe(texto) else fuente


def rtl(texto: str) -> bool:
    """Se lee de derecha a izquierda si su PRIMERA letra es árabe (regla de
    Unicode): «Tocador LED 🔥 بثمن همزة» va de izquierda a derecha y
    «بثمن همزة 39,90 €», al revés. Las cifras no deciden."""
    for ch in texto or "":
        if ARABE_RE.match(ch):
            return True
        if ch.isalpha():
            return False
    return False


def aislar(tramo: str) -> str:
    """Envuelve lo latino y los números de un tramo con árabe para que el bidi
    no los desordene. Sin árabe, el tramo sale tal cual."""
    if not es_arabe(tramo):
        return tramo
    return _LTR_RE.sub(lambda m: f"{_LRI}{m.group(0)}{_PDI}", tramo)
