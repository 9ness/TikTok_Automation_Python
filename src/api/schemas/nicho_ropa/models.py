"""Schemas del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

Espejo TS en `frontend/lib/types/nichoRopa.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PromptsRopaResponse(BaseModel):
    """Los prompts que el operador copia fuera de la app.

    El de vídeo va en DOS versiones: la diferencia es una única frase (la mano
    acariciando la ropa), así que se derivan de un mismo texto.
    """

    imagen: str
    video_con_manos: str
    video_sin_manos: str
    # Segundo escenario del nicho: la prenda colgada en una percha, sin nadie.
    video_percha: str = ""
    # El de la web: la prenda PUESTA, frente al espejo. Ya viene con las
    # palabras del sexo que toque según la carpeta pedida.
    video_espejo: str = ""
    sexo: str = ""


class CarpetaRopa(BaseModel):
    slug: str
    label: str
    # Importada por ZIP del catálogo de la web (la prenda va puesta), frente a
    # las cuatro planas del Drive del curso. Cada pantalla enseña solo las
    # suyas, así que el filtro lo decide el backend y no un `slug.includes()`.
    web: bool = False


class CarpetasRopaResponse(BaseModel):
    items: list[CarpetaRopa] = Field(default_factory=list)


class PrendaInfo(BaseModel):
    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    # Aviso cuando no se puede distinguir cuál es la foto de la prenda.
    foto_aviso: str = ""
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    # Promesa detectada en el caption; vacío si es seguro publicarlo.
    caption_riesgo: str = ""
    # Escaparate: sale del índice ÚNICO por (tienda|nombre), compartido con
    # los demás nichos — al Marketplace el producto se sube una sola vez.
    en_escaparate: bool = False
    uploaded: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    # Hay un montaje de esta prenda en cola o en curso.
    montando: bool = False


class PrendasListResponse(BaseModel):
    carpeta: str = ""
    items: list[PrendaInfo] = Field(default_factory=list)
    textos_extraidos: bool = False
    montando: bool = False


class PrendaEstadoRequest(BaseModel):
    """Marcar/desmarcar la prenda en el escaparate.

    El escaparate es único por producto (tienda|nombre) y compartido con los
    demás nichos: al Marketplace se sube una sola vez.
    """

    carpeta: str
    producto: str
    en_escaparate: bool


class VideoRopaUploadResponse(BaseModel):
    ok: bool = True
    job_id: str | None = None
    message: str = ""
