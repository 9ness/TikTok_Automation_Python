"""Schemas Pydantic del Programa 4 — Viralización."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PonenteInfo(BaseModel):
    slug: str
    label: str
    n_audios: int
    hooks_available: int
    hooks_total: int
    paisajes_available: int
    paisajes_total: int


class PonentesListResponse(BaseModel):
    items: list[PonenteInfo]


class CarpetasListResponse(BaseModel):
    """Carpetas ya creadas bajo VIRALIZACION, para elegir dónde guardar."""

    items: list[str]


class StyleChoice(BaseModel):
    key: str
    label: str


class StylesListResponse(BaseModel):
    items: list[StyleChoice]


class RoundPlan(BaseModel):
    """Cuántos vídeos caen en cada ronda con el reparto actual."""

    ronda: int
    n_videos: int
    default_style: str


class RoundPlanResponse(BaseModel):
    total_videos: int
    rounds: list[RoundPlan]


class ViralizacionGenerateRequest(BaseModel):
    ponentes: list[str] = Field(..., min_length=1)
    cantidad: dict[str, int]
    nombre_cuenta: str = Field(..., min_length=1)
    # 0 = sin música de fondo (default). >0 = nº de rondas que la llevan.
    music_rounds: int = 0
    # Estilo por ronda: `round_styles[i]` es la ronda i+1. Vacío = rotación
    # automática. Lo que falte también cae en la rotación.
    round_styles: list[str] = Field(default_factory=list)
    # Estilos elegidos: los vídeos se reparten entre ellos a partes iguales,
    # sin depender de cuántas rondas salgan del reparto de audios. Vacío = los 6.
    styles_pool: list[str] = Field(default_factory=list)
    # Audios elegidos por ponente: {"pablo": ["pablo1_largo.mp3", ...]}.
    # Vacío = todos los del banco. Sirve para tirar solo de los largos, que
    # retienen más.
    audios: dict[str, list[str]] = Field(default_factory=dict)
    # CTA final hablado ("no te olvides de seguirme…"): "no" | "todos" |
    # "mitad". Solo se aplica a Pablo Motos — Víctor Küppers ya lo trae dentro
    # de sus propios audios. Va SIN subtítulos.
    cta_final: str = "no"


class ViralizacionGenerateResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    total_videos: int


class CuentaEjemplo(BaseModel):
    handle: str = ""
    nota: str = ""


class CuentasEjemploResponse(BaseModel):
    ok: bool = True
    cuentas: list[CuentaEjemplo] = Field(default_factory=list)


class CuentasEjemploRequest(BaseModel):
    cuentas: list[CuentaEjemplo] = Field(default_factory=list)


class AudioItem(BaseModel):
    nombre: str
    duracion_s: float
    # "base"  = recortado a mano por el operador.
    # "clip"  = sacado de una charla larga por el cortador automático.
    # Se eligen igual; la distinción es para saber qué está probando.
    origen: str = "base"
    # Cuándo entró al banco (epoch). Con 20 audios hace falta saber cuáles son
    # los recién llegados para probar SOLO esos en la siguiente tanda.
    creado_at: float = 0.0


class AudiosListResponse(BaseModel):
    items: list[AudioItem] = Field(default_factory=list)


class ClipPropuesto(BaseModel):
    """Un corte que Gemini propone, todavía SIN cortar."""

    inicio: float
    fin: float
    duracion: float
    # Con qué frase arranca — es lo que decide si el vídeo retiene.
    gancho: str = ""
    tema: str = ""
    porque: str = ""


class PropuestaClips(BaseModel):
    ponente: str
    fichero: str
    clips: list[ClipPropuesto] = []
    at: float | None = None


class PropuestasListResponse(BaseModel):
    items: list[PropuestaClips] = []


class SubirAudioLargoResponse(BaseModel):
    ok: bool = True
    job_id: str | None = None
    ponente: str = ""
    fichero: str = ""
    mensaje: str = ""


class CortarClipsRequest(BaseModel):
    """Qué clips de la propuesta se convierten en MP3.

    Van por índice y no por tiempos: si el operador tuviera que mandarlos,
    cualquier redondeo del navegador movería el corte que ya se validó.
    """

    ponente: str = Field(..., min_length=1)
    fichero: str = Field(..., min_length=1)
    indices: list[int] = Field(..., min_length=1)


class CortarClipsResponse(BaseModel):
    ok: bool = True
    creados: list[str] = []
    mensaje: str = ""
