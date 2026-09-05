"""Esquemas del Nicho General · UGC."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpcionUGC(BaseModel):
    """Un gancho o una duración, para pintarlos en la pantalla."""

    clave: str
    label: str


class ConfigUGCResponse(BaseModel):
    ganchos: list[OpcionUGC] = Field(default_factory=list)
    duraciones: list[OpcionUGC] = Field(default_factory=list)
    # Los nichos de producto y los dos sexos: de cada combinación hay un
    # personaje, y es lo que se elige en la tarjeta.
    nichos: list[OpcionUGC] = Field(default_factory=list)
    sexos: list[OpcionUGC] = Field(default_factory=list)
    # Los personajes que existen de verdad, ya con su nicho y su número.
    personajes: list[OpcionUGC] = Field(default_factory=list)
    escenas: int = 3
    # El de crear el personaje. Va aquí y no por producto porque es el mismo
    # siempre: se usa una vez por persona, con una foto de Pinterest.
    prompt_personaje: str = ""


class EscenaUGC(BaseModel):
    n: int
    titulo: str = ""
    # Los dos que copia el operador: el de la imagen va a Flow con el personaje
    # y la foto del producto; el de vídeo, sobre la imagen que salga.
    prompt_imagen: str = ""
    prompt_video: str = ""
    # Lo que se dice en voz alta. Se guarda aparte para poder contarlo y, sobre
    # todo, para reconocer luego qué clip es cuál al montarlos.
    guion: str = ""
    caracteres: int = 0


class ProductoUGC(BaseModel):
    producto: str
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    precio: str = ""
    plazos: bool = False
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    product_url: str = ""
    en_escaparate: bool = False
    # Lo propio de este nicho, por gancho y duración.
    escenas: list[EscenaUGC] = Field(default_factory=list)
    voz: str = ""
    # De qué nicho es: lo decide Gemini al escribir las escenas y se puede
    # corregir a mano. Es lo que elige el personaje.
    nicho: str = ""
    # Con qué persona se graba. El sexo va al prompt para que la identidad
    # vocal no contradiga al personaje.
    personaje: str = ""
    personaje_sexo: str = ""
    # `belleza_mujer`, `tech_hombre`… El nombre de la foto que hay que
    # adjuntar en Flow. Lo calcula el backend para que la pantalla no tenga que
    # saberse qué sexo le toca a cada nicho.
    personaje_clave: str = ""
    clips: list[str] = Field(default_factory=list)
    video_path: str | None = None
    video_listo_at: int = 0
    montando: bool = False
    uploaded: bool = False
    sold: bool = False


class ProductosUGCResponse(BaseModel):
    items: list[ProductoUGC] = Field(default_factory=list)
    gancho: str = ""
    duracion: str = ""


class EstadoUGCRequest(BaseModel):
    source: str
    folder: str
    producto: str
    gancho: str = ""
    duracion: str = ""
    uploaded: bool | None = None
    sold: bool | None = None
    en_escaparate: bool | None = None
    nicho: str | None = None
    personaje: str | None = None
    personaje_sexo: str | None = None


class EscenasLoteRequest(BaseModel):
    source: str
    folder: str = ""
    gancho: str = ""
    duracion: str = ""
    rehacer: bool = False
    productos: list[str] = Field(default_factory=list)


class MontarUGCRequest(BaseModel):
    source: str
    folder: str
    producto: str
    gancho: str = ""
    duracion: str = ""
