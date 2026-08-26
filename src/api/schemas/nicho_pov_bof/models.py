"""Schemas del Nicho POV BOF (Fase 1 — navegación de productos).

Espejo TS en `frontend/lib/types/nichoPovBof.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    slug: str
    label: str
    # Solo en "Top vendidos": productos del ranking que aún no se han copiado a
    # la carpeta. Va aquí para poder avisar sin entrar a la fuente.
    pendientes: int = 0


class SourcesListResponse(BaseModel):
    items: list[SourceInfo]


class ProductFolder(BaseModel):
    name: str
    id: str
    completed: bool
    #: Productos que han entrado DESPUÉS de darla por hecha. El catálogo de la
    #: web se actualiza, así que una carpeta terminada puede recibir más — y
    #: sin esto quedarían escondidos.
    nuevos_desde_completada: int = 0
    # El Drive del curso ya no tiene esta carpeta: sale de nuestra copia. Se
    # marca para que se vea de dónde viene lo que se está trabajando.
    desde_copia: bool = False
    # Cuántos de sus productos tienen ya enlazada la ficha de TikTok Shop. Es
    # lo que dice, desde el listado, en qué carpeta hay trabajo — sin abrirla.
    con_url: int = 0


class FoldersListResponse(BaseModel):
    source: str
    items: list[ProductFolder]
    total: int
    completed_count: int
    # Primera carpeta no completada — es lo que la UI muestra por defecto.
    # None si ya están todas hechas.
    current: str | None = None


class PhotoInfo(BaseModel):
    id: str
    name: str
    size: int
    mime: str


class PhotosListResponse(BaseModel):
    source: str
    folder: str
    items: list[PhotoInfo]


class MarkCompletedRequest(BaseModel):
    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    completed: bool = True


class BackupCheckResponse(BaseModel):
    """Diff del origen contra la última copia. No copia nada."""

    last_snapshot: str | None = None
    has_changes: bool
    would_be_full: bool
    full_copy_ratio: float
    n_added: int
    n_modified: int
    n_deleted: int
    n_total_source: int
    change_ratio: float


class BackupSyncRequest(BaseModel):
    force_full: bool = False


class BackupSyncResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int


class PaqueteRequest(BaseModel):
    """Monta UNA carpeta con todo el material, para poder devolvérselo a
    quien comparte el Drive si lo pierde."""


class CompartirPaqueteRequest(BaseModel):
    correo: str
    # Por defecto solo lectura: es un respaldo, no una carpeta de trabajo.
    rol: str = "reader"


class MarkCompletedResponse(BaseModel):
    source: str
    folder: str
    completed: bool
    completed_count: int
    total: int
    next_folder: str | None = None


# ---------------------------------------------------------------------------
# FASE 2 — automatización de vídeos
# ---------------------------------------------------------------------------
class PromptsResponse(BaseModel):
    """Los dos prompts fijos que copia el operador fuera de la app."""

    imagen: str
    video: str


class ProductoInfo(BaseModel):
    """Un producto de una carpeta: emparejado de fotos + textos + estado."""

    producto: str
    # De qué carpeta es. Solo se rellena en el listado de TODAS las carpetas
    # (Top vendidos ordenado por ventas), donde cada producto es de una y la
    # pantalla necesita saberlo para actuar sobre él.
    folder: str = ""
    # Sus fotos salen de NUESTRA COPIA porque el Drive del curso ya no las
    # tiene. El producto sigue siendo grabable; la pantalla solo lo avisa.
    desde_copia: bool = False
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    # Aviso cuando el emparejado limpia/captura NO es fiable (vacío si lo es).
    # `photo_pairing` ya lo sabía, pero no salía de la API y el operador veía
    # la foto dudosa sin marca — llegó a colarse la captura de la descripción
    # como si fuera la del producto.
    foto_aviso: str = ""
    # Cuándo se subió la foto al Drive del curso (ISO de rclone, vacío si no se
    # sabe). Es lo único que dice si un producto es NUEVO en una carpeta que ya
    # se había trabajado — pasa a menudo: el curso va añadiendo durante el día.
    subida_at: str = ""
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    # Dos emojis para el caption: una reacción + uno del producto. Los da
    # Gemini; si el producto se extrajo antes de que existiera el campo, se
    # deducen del título (`services/emojis.py`).
    emojis: str = ""
    # Promesa detectada en el caption ("perfecta", "elimina"…), vacío si es
    # seguro. Solo se AVISA: el caption lo copia el operador al publicar, no
    # se quema en el vídeo, así que no se sustituye por él.
    caption_riesgo: str = ""
    # Gancho y CTA son FIJOS por decisión de cumplimiento (los dicta el
    # mentor del curso): solo rota el emoji. Ya no hay `*_riesgo` para ellos
    # porque no pueden ser arriesgados.
    gancho: str = ""
    cta: str = ""
    # Voz que encaja con el producto ("mujer" en cosmética/pelo, "hombre" en
    # el resto). Es solo el valor por defecto de la ficha, se puede cambiar.
    sexo_sugerido: str = "hombre"
    # Ya está metido en el escaparate de TikTok. Es un paso ANTERIOR a subir el
    # vídeo y el que más tiempo cuesta (se busca el producto a mano en el
    # Marketplace, porque EchoTik solo encuentra la ficha 1 de cada 4 veces y
    # su cuota gratis no da para el volumen diario).
    en_escaparate: bool = False
    # Precio leído de la ficha. Decide el guion: por encima de
    # `config.PRECIO_MIN_PLAZOS` el vídeo lleva el guion de Klarna (voz de
    # Fish, dos clips); por debajo, el audio grabado de siempre.
    # Solo en "Top vendidos": cuántas veces vendió el producto de origen y
    # cuándo entró en el ranking. Sirven para ordenar y para marcar los nuevos.
    ventas: int = 0
    vendido_at: float = 0
    precio: float = 0
    # El precio de antes del descuento, solo para verlo. La decisión la manda
    # `precio` (lo que se paga hoy): con cupones por debajo de 30 € Klarna no
    # deja financiar, así que el guion de plazos mentiría.
    precio_lista: float = 0
    modo_plazos: bool = False
    # Solo en modo plazos: cuáles de los dos clips están ya subidos.
    clip1: bool = False
    clip2: bool = False
    # El guion de plazos que le ha tocado, para poder leerlo antes de montar.
    guion: str = ""
    guion_caracteres: int = 0
    uploaded: bool = False
    # Cuándo se marcó como subido (epoch). Sirve para comprobar que un
    # producto repetido quedó bien marcado: si la hora cambia, entró.
    uploaded_at: float = 0
    sold: bool = False
    video_path: str | None = None
    # Marca de versión del vídeo montado: cambia en cada montaje y sirve para
    # que el navegador no reutilice el anterior de su caché.
    video_listo_at: int = 0
    # Hay un montaje de este producto en cola o en curso. Sale de la COLA, no
    # del estado guardado: el runner escribe `uploaded`/`video_path` a la vez
    # al terminar, así que lo guardado no distingue "montándose" de "sin
    # empezar". La ficha lo usa para refrescarse sola hasta que aparezca.
    montando: bool = False
    # Herramientas de edición elegibles por separado. Todas activas = el
    # montaje completo; ninguna = vídeo limpio (solo voz, encuadre y quitado
    # de marca si es Veo3).
    con_gancho: bool = True
    con_titulo: bool = True
    con_cta: bool = True
    con_flecha: bool = True
    # Ficha del producto en TikTok Shop, si se llegó a averiguar (EchoTik).
    # Vacío = todavía no se ha buscado o la búsqueda no encontró nada fiable.
    product_id: str = ""
    product_url: str = ""
    url_match_name: str = ""
    url_match_score: float = 0.0
    # Ventas del listado encontrado. Con 0 la ficha suele estar RETIRADA y al
    # abrirla TikTok responde "producto no encontrado".
    url_ventas_30d: int = 0
    url_ventas_total: int = 0


class ProductosListResponse(BaseModel):
    source: str
    folder: str
    items: list[ProductoInfo]
    # True una vez que se pulsó "Obtener textos" con éxito para la carpeta.
    textos_extraidos: bool = False
    # Algún producto de la carpeta se está montando: la UI sondea mientras
    # sea True y para sola cuando deja de serlo.
    montando: bool = False


class GuardarUrlRequest(BaseModel):
    """Pegar a mano la ficha de TikTok Shop de un producto (vacía = quitarla)."""

    source: str
    folder: str
    producto: str
    url: str = ""


class ExtraerTextosRequest(BaseModel):
    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)


class VideoLoteItem(BaseModel):
    """Un vídeo de la tanda, con el producto que le ha tocado."""

    # Identificador del bruto ya subido (no es una ruta: se resuelve en el
    # servidor contra la carpeta de subidas).
    token: str
    archivo: str = ""
    producto: str = ""
    # Por qué lo ha emparejado ahí. Se enseña para que el operador pueda
    # descartarlo de un vistazo sin abrir el vídeo.
    por_que: str = ""


class VideoLoteResponse(BaseModel):
    source: str
    folder: str
    items: list[VideoLoteItem] = Field(default_factory=list)
    reconocidos: int = 0
    #: Entre cuántos productos ha podido elegir. Se enseña porque es lo que
    #: dice si el "solo los que tienen URL" surtió efecto: si sigue poniendo
    #: diez, el check no estaba puesto.
    candidatos: int = 0


class VideoLoteConfirmarRequest(BaseModel):
    """Lo que confirma el operador tras repasar el reparto."""

    source: str
    folder: str
    items: list[VideoLoteItem] = Field(default_factory=list)
    sexo: str = "auto"
    con_gancho: bool = True
    con_titulo: bool = True
    con_cta: bool = True
    con_flecha: bool = True


class VideoLoteConfirmarResponse(BaseModel):
    encolados: int = 0
    pendientes: int = 0
    mensajes: list[str] = Field(default_factory=list)


class GuionPlazosRequest(BaseModel):
    """Sortea (o vuelve a sortear) el guion de plazos de un producto."""

    source: str
    folder: str
    producto: str
    # Cambiarlo aunque ya tenga uno: al operador no le convence el que salió.
    rehacer: bool = False


class ProductoEstadoRequest(BaseModel):
    """Parche parcial: solo se tocan los campos que vengan poblados."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    producto: str = Field(..., min_length=1)
    en_escaparate: bool | None = None
    uploaded: bool | None = None
    sold: bool | None = None
    # A qué nicho se le apunta la venta. Lo elige el operador: el mismo
    # producto se graba con varios nichos y solo él sabe con cuál vendió.
    nicho: str = ""
    # Precio escrito A MANO. Hace falta cuando la captura de la ficha no está
    # o no se lee (queda "precio sin detectar"): sin precio el producto nunca
    # pasa a plazos, así que una silla de 150 € se montaría con el guion corto
    # de un producto barato. `0` lo deja como estaba; para borrarlo, -1.
    precio: float | None = None


class ProductoBuscado(BaseModel):
    """Un producto encontrado por el buscador, con su carpeta.

    No es un `ProductoInfo`: el buscador barre las 35 carpetas de las dos
    fuentes, así que hace falta saber DE DÓNDE es cada resultado, y sobra casi
    todo lo demás (caption, gancho, prompts…) que costaría resolver 124 veces.
    """

    source: str
    folder: str
    producto: str
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    clean_photo_id: str = ""
    product_url: str = ""
    en_escaparate: bool = False
    uploaded: bool = False
    sold: bool = False
    # Unidades si ya está en el ranking de vendidos, para poder sumar otra
    # venta desde el propio resultado sin ir a buscarlo a su carpeta.
    unidades: int = 0


class BuscarProductosResponse(BaseModel):
    items: list[ProductoBuscado]
    # Cuántos encajaban en total: los resultados vienen recortados para no
    # pagar el emparejado de fotos de veinte carpetas.
    total: int = 0


class ProductoRecuperado(BaseModel):
    """Un recuperado con su producto ENTERO, no solo una referencia.

    Se trabajan todos juntos como si fueran una carpeta más, así que la ficha
    necesita lo mismo que en su carpeta de origen (textos, prompts, vídeo). El
    `source`/`folder` viaja al lado porque cada uno es de una carpeta distinta
    y las acciones (extraer textos, montar, marcar) van contra la SUYA.
    """

    source: str
    folder: str
    producto: ProductoInfo


class RecuperadosResponse(BaseModel):
    items: list[ProductoRecuperado] = Field(default_factory=list)
    # Carpetas implicadas, para poder relanzar la extracción de textos de
    # todas de una vez sin ir carpeta por carpeta.
    carpetas: list[str] = Field(default_factory=list)


class ProductoUrlRequest(BaseModel):
    """Pide averiguar la ficha de TikTok Shop de UN producto.

    Una petición = UNA llamada del plan de EchoTik (trial de 100), por eso no
    hay endpoint que lo haga de carpeta entera sin que el operador lo pida
    producto a producto."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    producto: str = Field(..., min_length=1)


class ProductosUrlsRequest(BaseModel):
    """Busca la ficha de TODOS los productos de la carpeta que aún no la
    tengan. Gasta UNA llamada de EchoTik por producto sin URL — los que ya
    la tienen no se vuelven a buscar."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)


class ProductosUrlsResponse(BaseModel):
    """Lista ya actualizada + cuánto costó, para poder avisar al operador."""

    source: str
    folder: str
    items: list[ProductoInfo]
    textos_extraidos: bool = False
    llamadas: int = 0        # llamadas de EchoTik consumidas
    encontrados: int = 0     # cuántas fichas se resolvieron
    sin_resultado: int = 0   # buscados pero EchoTik no los indexa
    aviso: str = ""          # p. ej. cuota agotada a mitad


class EchoTikCredsRequest(BaseModel):
    """Credenciales del plan de EchoTik. Cambian cada pocos días (cuenta de
    pruebas), así que se guardan en Redis y se aplican EN CALIENTE."""

    usuario: str = Field(..., min_length=4)
    password: str = Field(..., min_length=8)
    # Gasta UNA llamada comprobando que funcionan antes de guardarlas.
    probar: bool = True


class EchoTikCredsResponse(BaseModel):
    ok: bool
    configurado: bool
    # Usuario enmascarado, para saber cuál está puesto sin exponerlo.
    usuario_mascara: str = ""
    origen: str = ""          # "guardadas" | "env" | "ninguna"
    mensaje: str = ""


class EchoTikCuenta(BaseModel):
    """Una cuenta del banco. La contraseña NUNCA sale de aquí."""

    usuario: str              # completo: hace falta para activarla o borrarla
    usuario_mascara: str = ""
    nota: str = ""
    activa: bool = False      # es la que está en uso ahora mismo
    llamadas: int = 0         # gastadas en el ciclo actual
    primer_uso_at: float | None = None
    ultimo_uso_at: float | None = None
    # Cuándo se estima que le vuelven las 100 llamadas (primer uso + 30 días).
    renueva_at: float | None = None
    disponible: bool = True   # se puede usar ya
    sin_cuota: bool = False   # dio "Usage Limit Exceeded" en este ciclo


class EchoTikCuentasResponse(BaseModel):
    ok: bool = True
    items: list[EchoTikCuenta] = []
    mensaje: str = ""


class EchoTikCuentaRequest(BaseModel):
    """Alta de una cuenta en el banco, sin ponerla en uso."""

    usuario: str = Field(..., min_length=4)
    password: str = Field(..., min_length=8)
    nota: str = ""


class VideoUploadResponse(BaseModel):
    ok: bool
    job_id: str | None = None
    message: str


class UnidadesRequest(BaseModel):
    """Suma `delta` unidades vendidas (puede ser negativo). Nunca baja de 1."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    producto: str = Field(..., min_length=1)
    delta: int = 1


class SoldProductsResponse(BaseModel):
    # Cada item trae source/folder/producto + los campos guardados
    # (titulo, video_path, gancho, cta...) — el schema exacto por producto
    # ya lo valida `ProductoInfo`, aquí basta un dict de paso.
    items: list[dict]


class HashtagsResponse(BaseModel):
    ok: bool = True
    # Hashtags que se pegan al final de TODOS los captions. Son de cuenta, no
    # de producto: el operador los cambia por campaña.
    tags: list[str] = Field(default_factory=list)


class HashtagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
