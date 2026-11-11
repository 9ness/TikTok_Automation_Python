"""Hashtags del Black Friday de la agencia (Miture), para todas las cuentas (11/11/2026).

Se AÑADEN a los de siempre en la descripción de vídeos y carruseles (Mis tandas y la subida del móvil):
  - #TikTokShopBlackFriday del 11 al 30/11 (calentamiento 11-22; ~/relevos/black-friday-agencia-2026.md),
  - el de la categoría del PRODUCTO del 11 al 17/11 (#BlackFridayBeauty/Fashion/Home/Tech/Essentials).
La categoría sale del título del producto por palabras clave; lo que no encaja va a Essentials.
#OfertasenLIVE (solo directos) y #blackfriday2026 (fuera de la lista) NO van en vídeos.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

# Desde el 11/11 para TODAS las cuentas (Néstor), no solo Viva Shop.
PRINCIPAL = ("#TikTokShopBlackFriday", dt.date(2026, 11, 11), dt.date(2026, 11, 30))
CATEGORIA = (dt.date(2026, 11, 11), dt.date(2026, 11, 17))

# Orden = prioridad (una crema «para manos» es Beauty, no Fashion).
_PALABRAS = [
    ("#BlackFridayBeauty", "crema serum tonico facial piel antimanchas antiedad spf protector solar maquillaje "
                           "labial pintalabios rimel mascara pestanas cejas perfume colonia fragancia unas "
                           "manicura esmalte champu acondicionador cabello pelo capilar secador plancha rizador "
                           "depiladora afeitadora recortadora cosmetic belleza skincare exfoliante limpiador "
                           "contorno ojeras parches hidratante colageno retinol niacinamida azelaico"),
    ("#BlackFridayTech", "consola auricular auriculares cascos power bank bateria externa cargador cable usb "
                         "movil smartphone tablet smartwatch reloj inteligente altavoz bluetooth proyector camara "
                         "carplay android auto teclado raton gaming retro mando drone dron oukitel ordenador "
                         "portatil monitor microfono tracker gps"),
    ("#BlackFridayFashion", "pantalon chaqueta abrigo sudadera vestido falda camiseta camisa jersey bomber "
                            "botas botines zapatillas zapatos calzado sujetador bragas boxer calcetines medias "
                            "leggings jogger chandal pijama gorro bufanda guantes bolso mochila cartera cinturon "
                            "body reductor faja pasamontanas bailarina sombrero gafas joya joyas collar pendientes "
                            "pulsera anillo ropa prenda polar plumifero"),
    ("#BlackFridayHome", "mopa fregona cubo cocina sarten olla cazo cuchillo tabla picador freidora microondas "
                         "nevera frigorifico manta sabanas edredon almohada cojin cortina alfombra lampara luz "
                         "luces guirnalda organizador estante estanteria armario percha cajon colgador ducha "
                         "grifo bano lavabo inodoro calefactor estufa ventilador humidificador aspiradora "
                         "limpieza escurreplatos vaso taza termo botella decoracion mesa silla sofa colchon "
                         "toalla jardin planta mascota perro gato arenero"),
]
_INDICE = [(tag, set(p.split())) for tag, p in _PALABRAS]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def categoria(titulo: str) -> str:
    palabras = set(_norm(titulo).split())
    for tag, claves in _INDICE:
        if palabras & claves:
            return tag
    return "#BlackFridayEssentials"


def hashtags(usuario: str, pieza: dict, hoy: dt.date | None = None) -> list[str]:
    """Los hashtags de campaña que tocan hoy para esta pieza (vídeo o carrusel); [] fuera de fechas."""
    hoy = hoy or dt.date.today()
    tag, ini, fin = PRINCIPAL
    if not ini <= hoy <= fin:
        return []
    salida = [tag]
    if CATEGORIA[0] <= hoy <= CATEGORIA[1]:
        salida.append(categoria(pieza.get("titulo") or pieza.get("producto_titulo") or ""))
    return salida
