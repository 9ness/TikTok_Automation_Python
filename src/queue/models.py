"""Modelos del sistema de cola: Job dataclass + enums.

`Job` se serializa/deserializa a JSON para persistencia (estado de cola
sobrevive reinicios de la app local). Los `params` son libres por modo
— cada runner sabe interpretar los suyos.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class JobMode(str, Enum):
    PRESIDENTS = "presidents"
    PRONOSTICOS = "pronosticos"
    SUBS_AUTO = "subs_auto"
    COPYRIGHT = "copyright"
    CONSTRUCCION_POV = "construccion_pov"
    TIKTOK_SHOP = "tiktok_shop"
    TIKTOK_SHOP_WATERMARK = "tiktok_shop_watermark"
    TIKTOK_SHOP_PACK = "tiktok_shop_pack"      # Radar: pack de 1 producto
    TIKTOK_SHOP_PLAN = "tiktok_shop_plan"      # Radar: plan N/día (varios packs)
    TIKTOK_SHOP_READY_VIDEO = "tiktok_shop_ready_video"  # subir vídeo → listo TikTok
    TIKTOK_SHOP_AUTO_DAY = "tiktok_shop_auto_day"  # Radar v2: llenar 1 día solo
    EDITOR_AUTO = "editor_auto"
    VIRALIZACION_BATCH = "viralizacion_batch"
    VIRALIZACION_CLIPS = "viralizacion_clips"  # trocear audio largo en clips
    NICHO_POV_BOF_BACKUP = "nicho_pov_bof_backup"  # copia/diff del Drive compartido
    # Textos de TODAS las carpetas de un catálogo, de una tacada. Va por la
    # cola porque son ~1 min de Gemini por carpeta y hay 35 por fuente.
    NICHO_POV_BOF_TEXTOS = "nicho_pov_bof_textos"
    # Importar por ZIP el catálogo de la web del curso. Va a la cola porque son
    # 31 ficheros de varios MB: en una petición HTTP se agotaría el tiempo, y
    # así además se ve el avance.
    NICHO_POV_BOF_WEB_IMPORT = "nicho_pov_bof_web_import"
    NICHO_POV_BOF_REVISAR = "nicho_pov_bof_revisar"
    NICHO_POV_BOF_VIDEO = "nicho_pov_bof_video"  # montaje final por producto
    NICHO_ROPA_VIDEO = "nicho_ropa_video"  # ropa sin personas: encuadre + mudo
    # Ropa CON personas: título centrado sobre la prenda + flecha + voz de mujer.
    NICHO_ROPA_PERSONAS_VIDEO = "nicho_ropa_personas_video"
    # BOF cinematográfico: DOS clips de 5s pegados + ajuste por velocidad.
    NICHO_BOF_CINE_VIDEO = "nicho_bof_cine_video"
    # Cuenta Piloto: vídeo orgánico subido + la edición del POV BOF.
    CUENTA_PILOTO_VIDEO = "cuenta_piloto_video"
    # POV BOF Largo: DOS clips de 10s + guion locutado por IA (Fish).
    NICHO_POV_BOF_LARGO_VIDEO = "nicho_pov_bof_largo_video"
    # POV BOF Largo: los guiones de TODA una carpeta, de una tacada.
    NICHO_POV_BOF_LARGO_GUIONES = "nicho_pov_bof_largo_guiones"
    # POV BOF: los guiones de 10s de TODA una carpeta, de una tacada.
    NICHO_POV_BOF_GUIONES = "nicho_pov_bof_guiones"
    # Cerrar los huecos de numeración de "Mis productos" tras borrar uno.
    NICHO_POV_BOF_RENUMERAR = "nicho_pov_bof_renumerar"
    # Carruseles: clasificar + escribir los dos mensajes de todo un catálogo.
    NICHO_CARRUSELES_PREPARAR = "nicho_carruseles_preparar"
    # Carruseles: reconocer con IA de qué producto es cada foto 2 de la tanda.
    NICHO_CARRUSELES_REPARTO = "nicho_carruseles_reparto"
    # Carruseles: quemar los mensajes en las fotos de todo un catálogo.
    NICHO_CARRUSELES_QUEMAR = "nicho_carruseles_quemar"
    # POV BOF con el guion de plazos (Klarna): voz de Fish y DOS clips.
    NICHO_POV_BOF_PLAZOS_VIDEO = "nicho_pov_bof_plazos_video"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Etiqueta legible por modo (para mostrar en UI)
MODE_LABELS = {
    JobMode.PRESIDENTS: "🏛️ Presidentes",
    JobMode.PRONOSTICOS: "📊 Pronósticos",
    JobMode.SUBS_AUTO: "🎬 Subs sobre Vídeo",
    JobMode.COPYRIGHT: "🛡️ Quitar Copy",
    JobMode.CONSTRUCCION_POV: "🏗️ Construcción POV",
    JobMode.TIKTOK_SHOP: "🛒 TikTok Shop",
    JobMode.TIKTOK_SHOP_WATERMARK: "🚿 Sin marca (TikTok Shop)",
    JobMode.TIKTOK_SHOP_READY_VIDEO: "🎬 Vídeo listo (TikTok Shop)",
    JobMode.TIKTOK_SHOP_AUTO_DAY: "🎯 Día automático (ADS frescos)",
    JobMode.EDITOR_AUTO: "✂️ Editor Auto",
    JobMode.VIRALIZACION_BATCH: "🚀 Viralización 1K",
    JobMode.VIRALIZACION_CLIPS: "✂️ Cortar audio largo",
    JobMode.NICHO_POV_BOF_BACKUP: "💾 Backup Productos España",
    JobMode.NICHO_POV_BOF_TEXTOS: "🔤 Textos de todo el catálogo",
    JobMode.NICHO_POV_BOF_WEB_IMPORT: "🌐 Importar ZIPs de la web",
    JobMode.NICHO_POV_BOF_REVISAR: "🔍 Revisar que cada texto es de su producto",
    JobMode.NICHO_POV_BOF_VIDEO: "🎬 Vídeo Nicho POV BOF",
    JobMode.NICHO_ROPA_VIDEO: "👕 Vídeo Nicho Ropa",
    JobMode.NICHO_ROPA_PERSONAS_VIDEO: "👗 Vídeo Ropa Con Personas",
    JobMode.NICHO_BOF_CINE_VIDEO: "🎬 Vídeo BOF Cinematográfico",
    JobMode.CUENTA_PILOTO_VIDEO: "🧪 Vídeo Cuenta Piloto",
    JobMode.NICHO_POV_BOF_LARGO_VIDEO: "🎙️ Vídeo POV BOF Largo",
    JobMode.NICHO_POV_BOF_LARGO_GUIONES: "✍️ Guiones POV BOF Largo",
    JobMode.NICHO_POV_BOF_GUIONES: "✍️ Guiones POV BOF",
    JobMode.NICHO_POV_BOF_RENUMERAR: "🔢 Renumerar productos propios",
    JobMode.NICHO_CARRUSELES_PREPARAR: "🖼️ Preparar carruseles",
    JobMode.NICHO_CARRUSELES_REPARTO: "🧩 Repartir fotos de carrusel",
    JobMode.NICHO_CARRUSELES_QUEMAR: "🔥 Escribir los textos del carrusel",
    JobMode.NICHO_POV_BOF_PLAZOS_VIDEO: "💳 Vídeo POV BOF (plazos)",
}


@dataclass
class Job:
    """Trabajo de generación de vídeo. Vive en la cola hasta que termine."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    mode: JobMode = JobMode.PRESIDENTS
    title: str = ""                      # Texto corto que el usuario verá ("Top 5 worst…")
    params: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0                # 0.0 → 1.0
    progress_label: str = "En espera"
    logs: list[str] = field(default_factory=list)
    result_path: str | None = None       # MP4 final si completó
    error: str | None = None
    enqueued_by: str | None = None       # username del operador que encoló (ness, buga, ...)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    duration_seconds: float | None = None  # duración del MP4 final (ffprobe)
    # Si está poblado y es > now, el worker IGNORA el job hasta esa hora.
    # Útil para programar a horas valle (madrugada) donde los providers
    # AI suelen tener cola libre. Se mantiene el job en estado PENDING.
    scheduled_for: float | None = None

    # ---- helpers ----
    @property
    def elapsed_s(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    @property
    def eta_s(self) -> float | None:
        """Tiempo restante estimado en segundos. None si aún no es fiable.

        Usamos threshold 15% de progreso (no 5%) porque antes de eso el
        ratio elapsed/progress es muy ruidoso y da estimaciones absurdas
        (ej: "ETA 45m" cuando realmente quedan 5m). A partir de 15% ya
        es razonablemente estable."""
        if self.status != JobStatus.RUNNING:
            return None
        if self.progress < 0.15:
            return None
        elapsed = self.elapsed_s
        if elapsed <= 0:
            return None
        total_est = elapsed / self.progress
        return max(0.0, total_est - elapsed)

    def append_log(self, msg: str, max_lines: int = 200) -> None:
        self.logs.append(msg)
        if len(self.logs) > max_lines:
            del self.logs[: len(self.logs) - max_lines]

    # ---- serialización (JSON-safe) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        d["mode"] = JobMode(d["mode"])
        d["status"] = JobStatus(d["status"])
        return cls(**d)
