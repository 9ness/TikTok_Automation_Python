"""Parámetros de «Mis tandas»."""

from __future__ import annotations

# Vídeos por tanda: una tanda es lo que se publica en un día.
POR_TANDA = 10

# Si hoy ya se han marcado tantos subidos, la tanda abierta es para MAÑANA
# (mismo criterio que el multimodo: algún día faltan enlaces y se queda en 8).
SUBIDAS_DIA_HECHO = 8

# Tandas al día por usuario, para la fecha orientativa. ness publica entre 10 y
# 20 según el día; se deja en una y abre la siguiente si le da tiempo.
TANDAS_DIA: dict[str, int] = {"ness": 1, "ana": 1, "mauro": 1}

# El mismo producto (otro modo del Largo, la copia de Q4…) no se publica dos
# veces en menos de estos días: el segundo espera.
SEPARACION_MISMO_PRODUCTO = 2  # 8 oct 2026: 2 días (Q4: hasta 5 vídeos por producto; con 5 días eran ~3 semanas)

# Cuánto vale la lista ya leída (por usuario y proceso). Los botones la
# corrigen en el sitio, así que esto solo decide cada cuánto se ven los vídeos
# NUEVOS que montan los agentes.
CACHE_S = 45

# Cuántas tandas abiertas se precalientan (vídeo copiado a disco local).
PRECALENTAR_TANDAS = 2

# Nichos que entran, con su etiqueta y el slug de hashtags del frontend.
NICHOS: dict[str, dict[str, str]] = {
    "pov": {"label": "POV BOF", "hashtags": "nicho-pov-bof", "pantalla": "/tiktok-shop-ai-pro/nicho-pov-bof"},
    "largo": {"label": "POV BOF Largo", "hashtags": "pov-bof-largo", "pantalla": "/tiktok-shop-ai-pro/pov-bof-largo"},
    "mm": {"label": "Multimodo", "hashtags": "nicho-ropa-mujer", "pantalla": "/tiktok-shop-ai-pro/moda-mujer-multimodo"},
    "alea": {"label": "Moda Mujer · Aleatorios", "hashtags": "nicho-ropa-mujer", "pantalla": "/tiktok-shop-ai-pro/nicho-ropa-mujer"},
}

# Los de Moda Mujer · Aleatorios (hablan: Tienda Colores, Calle Dividido) se
# INTERCALAN con el resto en vez de ir todos al final: uno cada tantos
# pendientes (5 → dos por tanda de diez). Las primeras tandas abiertas no se
# tocan: el operador puede haberlas bajado ya.
ALEA_CADA = 5
ALEA_SIN_TOCAR = 2  # tandas abiertas que se dejan como están

ORDEN_KEY = "mis_tandas:orden:{usuario}"
FOTO_KEY = "mis_tandas:fotos"
OCULTOS_KEY = "mis_tandas:ocultos:{usuario}"
# Tandas FIJADAS: en cuanto una tanda se enseña (de las primeras abiertas, o
# llena) se guardan sus vídeos y ya no cambia: marcar subido o sin stock no
# mete otro vídeo de la siguiente (el operador ya la ha bajado). Solo sale de
# ella un vídeo rehecho, y solo «Tanda completada» la cierra.
# Semáforo de revisión antes de subir (oct 2026, con la cuenta en CRH crítico):
# verde = producto sencillo y vídeo sin dudas; ámbar = está bien pero el
# producto es complejo y no compensa el riesgo; rojo = hay que rehacerlo (marca
# además «rehacer» con el motivo). Va atado a `video_listo_at`: si el vídeo se
# vuelve a montar, el color viejo deja de valer y hay que revisarlo otra vez.
SEMAFORO_KEY = "mis_tandas:semaforo:{usuario}"
SEMAFORO_COLORES = ("verde", "ambar", "rojo")
FIJAS_KEY = "mis_tandas:fijas:{usuario}"

# ÉPOCA de cada vídeo (oct 2026): para saber CUÁNDO publicarlo (TikTok y Meta,
# que va a uno al día y reparte por época). La pone el agente al montarlo
# (`epoca_video` del MCP); sin poner, los Vintage 🍂 son «otono» y el resto
# «neutro». Va por id de vídeo y no caduca al rehacer: la escena la pidió así.
EPOCA_KEY = "mis_tandas:epoca:{usuario}"
EPOCAS = ("neutro", "otono", "halloween", "black_friday", "invierno", "navidad")

# Cuentas que en TikTok SOLO publican vídeos con voz (oct 2026: la de Ana se
# sancionó por «muchos vídeos cortos de baja calidad o parecidos» — mudos de
# 10 s con música). Sus tandas son solo de hablados; los mudos salen aparte en
# `solo_meta` (van a Meta), sin ocultarse ni borrarse.
SOLO_HABLADOS: set[str] = {"ana"}

# Vídeos por tanda por usuario (si no, `POR_TANDA`): Ana, 6 al día desde el
# 18/10/2026 (del 10 al 17, uno al día: sube solo el mejor de la tanda).
POR_TANDA_USUARIO: dict[str, int] = {"ana": 6}


def por_tanda(usuario: str) -> int:
    return POR_TANDA_USUARIO.get(usuario or "ness", POR_TANDA)
FIJAR_ABIERTAS = 2   # tandas abiertas que se fijan (la de hoy y la siguiente)
FIJAS_GUARDAR = 60   # completadas que se recuerdan


def cache_dir() -> str:
    """Copias locales de los vídeos del Largo de modos que no son el de por
    defecto: su caché del nicho no lleva el modo en el nombre y dos modos del
    mismo producto se pisarían."""
    import os

    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "mis_tandas_videos")
