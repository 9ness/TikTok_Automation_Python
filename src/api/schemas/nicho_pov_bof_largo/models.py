"""Schemas del Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VozLargo(BaseModel):
    id: str
    label: str


class VocesLargoResponse(BaseModel):
    """Banco de voces de Fish, por sexo. El operador solo elige sexo; cuál
    suena se sortea. Se listan para que sepa qué hay detrás."""

    hombre: list[VozLargo] = Field(default_factory=list)
    mujer: list[VozLargo] = Field(default_factory=list)


class ProductoLargo(BaseModel):
    producto: str
    # De qué carpeta es. Solo se rellena en el listado de TODAS las carpetas
    # (Top vendidos ordenado por ventas): ahí cada producto viene de una.
    folder: str = ""
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    foto_aviso: str = ""
    # Textos y enlaces del producto — vienen del Nicho POV BOF (dato objetivo
    # del producto, compartido), no se extraen ni se buscan aquí.
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    gancho: str = ""
    cta: str = ""
    caption_riesgo: str = ""
    sexo_sugerido: str = ""
    product_url: str = ""
    url_match_name: str = ""
    url_match_score: float = 0.0
    # Solo en "Top vendidos": ventas del producto de origen y cuándo entró.
    ventas: int = 0
    vendido_at: float = 0
    # Precio y modo de guion — el dato lo extrae el POV BOF, aquí se lee.
    precio: float = 0
    precio_lista: float = 0
    modo_plazos: bool = False
    # Lo propio de este nicho (progreso INDIVIDUAL, aislado del POV BOF).
    guion: str = ""
    # En qué modo se escribió el guion guardado. Si no cuadra con
    # `modo_plazos`, se reescribe al montar.
    guion_plazos: bool = False
    subliminal: str = ""
    guion_caracteres: int = 0
    clip1: bool = False
    clip2: bool = False
    voz_label: str = ""
    voz_sexo: str = ""
    en_escaparate: bool = False
    uploaded: bool = False
    uploaded_at: float = 0
    sold: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    montando: bool = False


class ProductosLargoResponse(BaseModel):
    source: str
    folder: str
    items: list[ProductoLargo] = Field(default_factory=list)
    montando: bool = False


class ProductoEstadoLargoRequest(BaseModel):
    """Parche parcial de Escaparate/Subido/Vendió (progreso individual). Solo
    se aplican los campos no `None`."""

    source: str
    folder: str
    producto: str
    en_escaparate: bool | None = None
    uploaded: bool | None = None
    sold: bool | None = None
    # A qué nicho se atribuye la venta en el ranking compartido. Aquí siempre
    # es "pov_bof_largo"; se acepta por si la UI lo manda explícito.
    nicho: str | None = None


class FolderLargo(BaseModel):
    name: str
    id: str = ""
    completed: bool = False


class FoldersLargoResponse(BaseModel):
    source: str
    items: list[FolderLargo] = Field(default_factory=list)
    total: int = 0
    completed_count: int = 0
    current: str | None = None


class MarkCompletedLargoRequest(BaseModel):
    source: str
    folder: str
    completed: bool = True


class MarkCompletedLargoResponse(BaseModel):
    source: str
    folder: str
    completed: bool
    completed_count: int = 0
    total: int = 0
    next_folder: str | None = None


class GuionLargoRequest(BaseModel):
    source: str
    folder: str
    producto: str
    # Reescribir aunque ya haya uno guardado (el operador no lo ve claro).
    rehacer: bool = False


class GuionLargoResponse(BaseModel):
    producto: ProductoLargo


class LoteLargoItem(BaseModel):
    token: str
    archivo: str = ""
    producto: str = ""
    por_que: str = ""


class LoteLargoResponse(BaseModel):
    source: str
    folder: str
    items: list[LoteLargoItem] = Field(default_factory=list)
    reconocidos: int = 0


class LoteLargoConfirmarRequest(BaseModel):
    """Lo que confirma el operador tras repasar el reparto de la tanda."""

    source: str
    folder: str
    items: list[LoteLargoItem] = Field(default_factory=list)
    sexo: str = "auto"
    con_gancho: bool = True
    con_titulo: bool = True
    con_cta: bool = True
    con_flecha: bool = True


class LoteLargoConfirmarResponse(BaseModel):
    encolados: int = 0
    pendientes: int = 0
    mensajes: list[str] = Field(default_factory=list)


class ClipLargoUploadResponse(BaseModel):
    job_id: str = ""
    encolado: bool = False
    message: str = ""
