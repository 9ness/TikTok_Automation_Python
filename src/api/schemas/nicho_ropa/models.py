"""Schemas del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

Espejo TS en `frontend/lib/types/nichoRopa.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EstiloMof10(BaseModel):
    """Un estilo de vídeo de 10s: la imagen y el guion, ya en su sexo."""

    clave: str
    label: str
    imagen: str
    guion: str
    # El texto no es suyo: lo derivamos cambiando las palabras de la persona.
    derivado: bool = False


class ModoRopa(BaseModel):
    clave: str
    label: str


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
    # Lo que enseña el chip de la carpeta, como en el POV BOF: cuántas prendas
    # tiene, cuántas llevan ya la ficha de TikTok enlazada y cuántas tienen el
    # vídeo del modo en el que se está trabajando. Solo se calculan cuando se
    # pide un `sexo` concreto —una pantalla de trabajo—, porque cuesta una
    # lectura de Redis por carpeta.
    total: int = 0
    con_url: int = 0
    con_video: int = 0
    # "MOF 10 segundos": imagen en Flow + guion/vídeo en Omni. Un clip único
    # de 10s, en vez de generar el vídeo de una tirada. Van en lista porque
    # publica estilos nuevos cada poco.
    mof10: list[EstiloMof10] = Field(default_factory=list)
    # Los modos de grabación que existen PARA ESE SEXO: el curso no publica
    # los mismos formatos para hombre y mujer (el bolso es de mujer, las dos
    # situaciones de calle son de hombre). La lista la manda el backend para
    # que la pantalla no tenga que saberse los formatos.
    modos: list[ModoRopa] = Field(default_factory=list)


class CarpetaRopa(BaseModel):
    slug: str
    label: str
    # Importada por ZIP del catálogo de la web (la prenda va puesta), frente a
    # las cuatro planas del Drive del curso. Cada pantalla enseña solo las
    # suyas, así que el filtro lo decide el backend y no un `slug.includes()`.
    web: bool = False
    # Catálogo del OPERADOR (muestras/tareas, por género). Se comporta como
    # una carpeta de la web —la prenda va puesta— pero las prendas las sube
    # él, así que la pantalla enseña ahí el formulario de alta.
    propia: bool = False
    # `mujer_muestras`, `hombre_tareas`… Vacío en las cuatro del curso.
    genero: str = ""
    # "mujer" / "hombre". La pantalla de la web enseña UN inventario cada vez,
    # así que necesita saber de quién es cada carpeta; el género no vale porque
    # las del ZIP no lo llevan y las propias lo traen con el catálogo pegado
    # (`mujer_muestras`). Lo decide el backend, no un `slug.startsWith()`.
    sexo: str = ""


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
    # Ficha de TikTok Shop, pegada en lote desde la web del curso.
    product_url: str = ""
    # Su web marca "SIN STOCK" en vez del enlace.
    sin_stock: bool = False
    # ¿Su ficha ofrece pago a plazos? Sale de la propia ficha al extraer los
    # textos —mismo criterio que el POV BOF: lo que diga, y si no se ve, el
    # precio— y decide QUÉ PROMPT usar. Se puede corregir a mano.
    plazos: bool = False
    # `True`/`False` si el operador lo corrigió; `None` si manda la ficha.
    plazos_manual: bool | None = None
    # Lo que paga hoy el comprador, tal cual se leyó de la captura.
    precio: str = ""
    uploaded: bool = False
    # Vendió con esta prenda. El ranking es POR USUARIO y común a todos los
    # nichos (`nicho_pov_bof/repos/product_repo.py`): la venta es de la cuenta
    # de quien la hizo, no del catálogo de donde saliera la prenda.
    sold: bool = False
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
    # Solo se aplica lo que venga: la tarjeta manda el campo que cambia.
    en_escaparate: bool | None = None
    # Corrige a mano lo que dijo la ficha sobre el pago a plazos. Mandar
    # `null` no toca nada; para volver a lo que diga la ficha, `auto`.
    plazos: bool | None = None
    # `True` devuelve el control a la ficha (borra la corrección manual).
    plazos_auto: bool = False
    # Ya publicado en TikTok. Lo escribía solo el runner al montar, así que no
    # había forma de marcarlo (ni de desmarcarlo si te equivocabas) — y en el
    # resto de nichos es un botón de la tarjeta.
    uploaded: bool | None = None
    # Vendió. Va al ranking común por usuario, igual que en el POV BOF Largo.
    sold: bool | None = None


class VideoRopaUploadResponse(BaseModel):
    ok: bool = True
    job_id: str | None = None
    message: str = ""
