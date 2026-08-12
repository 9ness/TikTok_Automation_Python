"""Topes diarios de publicación en TikTok (transversal a todos los nichos).

No es un nicho ni un programa: es el límite de la CUENTA. Da igual con qué
nicho se haya grabado el vídeo — al final se publica en el mismo perfil, así
que el contador es uno solo por usuario y por día.
"""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

REDIS_PREFIX = os.getenv("CUOTAS_REDIS_PREFIX", "cuotas:")

# Lo que TikTok deja subir al día.
TOPE_VIDEOS = int(os.getenv("CUOTA_TOPE_VIDEOS", "25"))
TOPE_CARRUSELES = int(os.getenv("CUOTA_TOPE_CARRUSELES", "50"))

# Cuándo avisar. NO es el tope: el operador quiere frenar antes de rozarlo,
# porque lo que TikTok cuenta y lo que contamos aquí puede bailar en uno o dos
# (una subida que falla, un borrado…) y pasarse tiene coste de cuenta.
AVISO_VIDEOS = int(os.getenv("CUOTA_AVISO_VIDEOS", "20"))
AVISO_CARRUSELES = int(os.getenv("CUOTA_AVISO_CARRUSELES", "45"))

# El día se corta a medianoche EN ESPAÑA, no en UTC: el servidor va en UTC y en
# verano son dos horas de diferencia, así que a las 00:30 de aquí el contador
# habría seguido contando en el día anterior.
ZONA = ZoneInfo(os.getenv("CUOTAS_TZ", "Europe/Madrid"))


def hoy() -> str:
    """Fecha de hoy (`YYYY-MM-DD`) en la zona del operador."""
    return datetime.now(ZONA).strftime("%Y-%m-%d")
