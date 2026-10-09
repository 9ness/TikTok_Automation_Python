"""Modelos del publicador Multiplataforma (dataclasses serializables a JSON)."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field, fields

from src.multiplataforma import config


def _filtrar(cls, d: dict) -> dict:
    nombres = {f.name for f in fields(cls)}
    return {k: v for k, v in (d or {}).items() if k in nombres}


@dataclass
class CuentaDestino:
    """Una cuenta de publicación (una por marca/persona), con sus destinos.

    `tokens` es {plataforma: access_token}. Instagram usa el token de la
    página de Facebook si no tiene uno propio (Facebook Login for Business).
    NUNCA se devuelve por la API: ver `publico()`.
    """

    slug: str
    nombre: str = ""
    dueno: str = ""  # usuario de la app (ness, ana…)
    ig_user_id: str = ""
    fb_page_id: str = ""
    threads_user_id: str = ""
    pinterest_board_id: str = ""
    tokens: dict[str, str] = field(default_factory=dict)
    afiliado_amazon_tag: str = ""
    afiliado_shein: str = ""  # id/notas del panel de SHEIN (el enlace se pega tal cual)
    activa: bool = True
    # Ingesta desde el Drive: vídeos/día por tipo y horas («HH:MM», hora de
    # `config.ZONA_HORARIA`). Ritmo 0 = esa carpeta no se ingesta.
    ritmo: dict[str, int] = field(default_factory=lambda: dict(config.RITMO_DEFAULT))
    horas: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in config.HORAS_DEFAULT.items()})
    # Encolado automático de Mis tandas (`tandas.auto_encolar`): días de vídeos
    # de producto que el tick mantiene en cola. 0 = solo a mano.
    auto_tandas: int = 0
    creada_en: float = field(default_factory=time.time)

    def destino(self, plataforma: str) -> str:
        return {
            "instagram": self.ig_user_id,
            "facebook": self.fb_page_id,
            "threads": self.threads_user_id,
            "pinterest": self.pinterest_board_id,
        }.get(plataforma, "")

    def token(self, plataforma: str) -> str:
        t = (self.tokens or {}).get(plataforma, "")
        if not t and plataforma == "instagram":
            t = (self.tokens or {}).get("facebook", "")
        return t

    def lista_para(self, plataforma: str) -> bool:
        """Tiene destino y token: se puede publicar de verdad."""
        return bool(self.destino(plataforma) and self.token(plataforma))

    def to_dict(self) -> dict:
        return asdict(self)

    def publico(self) -> dict:
        d = asdict(self)
        d.pop("tokens", None)
        d["tokens_configurados"] = sorted(k for k, v in (self.tokens or {}).items() if v)
        d["listas"] = [p for p in config.PLATAFORMAS if self.lista_para(p)]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CuentaDestino":
        return cls(**_filtrar(cls, d))


@dataclass
class Publicacion:
    """Un vídeo a publicar en una o varias plataformas de una cuenta.

    `estado`, `resultados`, `errores` e `intentos` van por plataforma: así una
    plataforma ya publicada no se repite aunque otra falle.
    """

    cuenta: str
    video_path: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    tipo: str = "producto"  # producto | prueba_viral | carrusel
    producto_ref: str = ""  # ref opcional al producto del nicho de origen
    titulo: str = ""
    # Texto base (sin enlace) para poder rehacer `textos` si el enlace llega
    # después (producto_ref sin enlace → se rellena desde enlaces_repo).
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    textos: dict[str, str] = field(default_factory=dict)
    comentario: str = ""  # primer comentario de Facebook (lleva el enlace)
    enlace: str = ""
    cover_url: str = ""
    # Solo `carrusel`: las fotos en orden (`video_path` = la primera, para la
    # identidad) y su versión 4:5 para Instagram; `carrusel_id` = la réplica.
    imagenes: list[str] = field(default_factory=list)
    imagenes_ig: list[str] = field(default_factory=list)
    carrusel_id: str = ""
    plataformas: list[str] = field(default_factory=lambda: list(config.PLATAFORMAS))
    estado: dict[str, str] = field(default_factory=dict)
    programada_en: float = field(default_factory=time.time)
    trial_graduation: str = "MANUAL"  # solo IG prueba_viral: MANUAL | SS_PERFORMANCE
    origen: str = ""  # "ingesta" = vino de la carpeta del Drive (se mueve a publicados/); "tandas" = de Mis tandas
    resultados: dict[str, dict] = field(default_factory=dict)
    errores: dict[str, str] = field(default_factory=dict)
    intentos: dict[str, int] = field(default_factory=dict)
    creada_en: float = field(default_factory=time.time)
    actualizada_en: float = 0.0

    def __post_init__(self) -> None:
        for p in self.plataformas:
            self.estado.setdefault(p, config.ESTADO_PENDIENTE)

    @property
    def clave(self) -> str:
        """Identidad para no encolar dos veces el mismo vídeo en la misma cuenta."""
        base = f"{self.cuenta}|{self.video_path}|{self.tipo}"
        return hashlib.sha1(base.encode()).hexdigest()[:16]

    @property
    def terminada(self) -> bool:
        return all(self.estado.get(p) in config.ESTADOS_FINALES for p in self.plataformas)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["clave"] = self.clave
        d["terminada"] = self.terminada
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Publicacion":
        return cls(**_filtrar(cls, d))
