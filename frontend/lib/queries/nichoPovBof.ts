"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  HashtagsResponse,
  BackupCheckResponse,
  BackupSyncResponse,
  EchoTikCredsRequest,
  EchoTikCredsResponse,
  EchoTikCuenta,
  EchoTikCuentaRequest,
  EchoTikCuentasResponse,
  EstadoRequest,
  ExtraerTextosRequest,
  FoldersListResponse,
  MarkCompletedRequest,
  MarkCompletedResponse,
  PhotosListResponse,
  ProductoBuscado,
  ProductoItem,
  ProductoRecuperado,
  ProductoUrlRequest,
  ProductosUrlsRequest,
  ProductosUrlsResponse,
  PromptsResponse,
  SourcesListResponse,
  VendidoItem,
} from "@/lib/types/nichoPovBof";

const ROOT = "/api/v1/nicho-pov-bof";

export const nichoPovBofKeys = {
  all: ["nicho-pov-bof"] as const,
  sources: () => [...nichoPovBofKeys.all, "sources"] as const,
  folders: (source: string) => [...nichoPovBofKeys.all, "folders", source] as const,
  photos: (source: string, folder: string) =>
    [...nichoPovBofKeys.all, "photos", source, folder] as const,
  prompts: () => [...nichoPovBofKeys.all, "prompts"] as const,
  productos: (source: string, folder: string) =>
    [...nichoPovBofKeys.all, "productos", source, folder] as const,
  vendidos: (source: string) => [...nichoPovBofKeys.all, "vendidos", source] as const,
  buscar: (source: string, q: string) =>
    [...nichoPovBofKeys.all, "buscar", source, q] as const,
  recuperados: () => [...nichoPovBofKeys.all, "recuperados"] as const,
};

/** Busca un producto por nombre, tienda o carpeta en TODAS las carpetas.
 *
 *  Sirve para lo de siempre: llega el aviso de una venta y hay que dar con el
 *  producto sin acordarse de en cuál de las 35 carpetas estaba. Sin `q` (o con
 *  menos de 2 letras) no se llama: barrer todo por una sola letra devolvería
 *  media base de datos.
 */
export function useBuscarProductos(source: string, q: string) {
  const limpio = q.trim();
  return useQuery<{ items: ProductoBuscado[]; total: number }>({
    queryKey: nichoPovBofKeys.buscar(source, limpio),
    queryFn: () =>
      api.get<{ items: ProductoBuscado[]; total: number }>(
        `${ROOT}/buscar?q=${encodeURIComponent(limpio)}` +
          (source ? `&source=${encodeURIComponent(source)}` : ""),
      ),
    enabled: limpio.length >= 2,
    // Los resultados no cambian mientras escribes: evita repetir el barrido
    // al borrar una letra y volver a ponerla.
    staleTime: 30_000,
  });
}

/** Productos que aparecieron tarde en carpetas ya trabajadas.
 *
 *  Recorre las 35 carpetas emparejando fotos (unos segundos), así que solo se
 *  pide cuando el operador abre la lista, nunca al cargar la página. */
export function useProductosRecuperados(enabled: boolean) {
  return useQuery<{ items: ProductoRecuperado[]; carpetas: string[] }>({
    queryKey: nichoPovBofKeys.recuperados(),
    queryFn: () =>
      api.get<{ items: ProductoRecuperado[]; carpetas: string[] }>(`${ROOT}/recuperados`),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useSources() {
  return useQuery<SourcesListResponse>({
    queryKey: nichoPovBofKeys.sources(),
    queryFn: () => api.get<SourcesListResponse>(`${ROOT}/sources`),
  });
}

export function useFolders(source: string) {
  return useQuery<FoldersListResponse>({
    queryKey: nichoPovBofKeys.folders(source),
    queryFn: () =>
      api.get<FoldersListResponse>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function usePhotos(source: string, folder: string | null) {
  return useQuery<PhotosListResponse>({
    queryKey: nichoPovBofKeys.photos(source, folder ?? ""),
    queryFn: () =>
      api.get<PhotosListResponse>(
        `${ROOT}/photos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      ),
    enabled: Boolean(source && folder),
  });
}

export function useMarkCompleted(source: string) {
  const qc = useQueryClient();
  return useMutation<MarkCompletedResponse, Error, MarkCompletedRequest>({
    mutationFn: (body) => api.post<MarkCompletedResponse>(`${ROOT}/complete`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.folders(source) });
    },
  });
}

export interface UltimaCopia {
  ts?: number;
  mode?: string;
  n_added?: number;
  n_modified?: number;
  n_deleted?: number;
  copied?: number;
  failed?: number;
}

/** Qué hizo la última copia (la diaria incluida).
 *
 *  Es una lectura de Redis, no toca Drive, así que se pide al abrir la
 *  pantalla: lo que interesa es enterarse el mismo día de que el curso ha
 *  BORRADO ficheros, y eso antes solo salía en el log del job. */
export function useUltimaCopia() {
  return useQuery<UltimaCopia>({
    queryKey: [...nichoPovBofKeys.all, "backup-ultima"],
    queryFn: () => api.get<UltimaCopia>(`${ROOT}/backup/ultima`),
    staleTime: 60_000,
  });
}

/** Comprobar cambios en el Drive de origen. Bajo demanda: el listado
 *  recursivo tarda ~1 min, así que no se dispara solo al abrir la página. */
export function useBackupCheck() {
  return useMutation<BackupCheckResponse, Error, void>({
    mutationFn: () => api.get<BackupCheckResponse>(`${ROOT}/backup/check`),
  });
}

export function useBackupSync() {
  return useMutation<BackupSyncResponse, Error, { force_full: boolean }>({
    mutationFn: (body) => api.post<BackupSyncResponse>(`${ROOT}/backup/sync`, body),
  });
}

/** El paquete: UNA carpeta con todo el material, con el árbol original.
 *
 *  El archivo de copias (completa + un delta por día) sirve para trabajar,
 *  pero para DEVOLVERLE el material a quien comparte el Drive —le hackearon
 *  el correo y se quedó sin acceso— hace falta una sola carpeta. */
export type PaqueteEstado = { carpeta?: string; ficheros?: number; bytes?: number };

export function usePaquete() {
  return useQuery<PaqueteEstado>({
    queryKey: [...nichoPovBofKeys.all, "backup-paquete"],
    queryFn: () => api.get<PaqueteEstado>(`${ROOT}/backup/paquete`),
    staleTime: 60_000,
  });
}

export function useMontarPaquete() {
  const qc = useQueryClient();
  return useMutation<BackupSyncResponse, Error, void>({
    mutationFn: () => api.post<BackupSyncResponse>(`${ROOT}/backup/paquete`, {}),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...nichoPovBofKeys.all, "backup-paquete"] }),
  });
}

export function useCompartirPaquete() {
  return useMutation<
    { carpeta: string; correo: string; rol: string; enlace: string },
    Error,
    { correo: string; rol?: string }
  >({
    mutationFn: (body) => api.post(`${ROOT}/backup/paquete/compartir`, body),
  });
}

/** Textos de TODAS las carpetas de un catálogo, de una tacada.
 *
 *  Vive aquí y no en cada nicho porque los textos son del catálogo COMPARTIDO:
 *  extraerlos vale igual para POV BOF, POV BOF Largo, Creativos Pro y
 *  Carruseles. Va por la cola — son ~1 min de Gemini por carpeta y hay 35. */
export function useTextosLote() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; title: string; position_in_queue: number },
    Error,
    { source: string; rehacer?: boolean; unoAUno?: boolean }
  >({
    mutationFn: ({ source, rehacer, unoAUno }) =>
      api.post(
        `${ROOT}/textos/lote?source=${encodeURIComponent(source)}` +
          (rehacer ? "&rehacer=1" : "") +
          (unoAUno ? "&uno_a_uno=1" : ""),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["queue"] }),
  });
}

/** URL de la foto (api_key por query — un <img> no manda headers). */
/** Alta de un producto PROPIO: se suben las dos fotos y el backend las guarda
 *  con el convenio de nombres del Drive del curso, así que a partir de ahí es
 *  un producto más. Devuelve en qué carpeta cayó (se llenan de 10 en 10). */
export function useCrearMiProducto() {
  const qc = useQueryClient();
  return useMutation<
    { source: string; carpeta: string; producto: string },
    Error,
    { fotoLimpia: File; fotoFicha?: File | null }
  >({
    mutationFn: async ({ fotoLimpia, fotoFicha }) => {
      const fd = new FormData();
      fd.append("foto_limpia", fotoLimpia);
      if (fotoFicha) fd.append("foto_ficha", fotoFicha);
      return api.post(`${ROOT}/mis-productos`, fd);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

/** Importa un ZIP de la web del curso a "🌐 Productos Web".
 *
 *  Se puede resubir el mismo ZIP: el catálogo se actualiza y la respuesta dice
 *  qué productos son nuevos, cuáles cambiaron y cuáles estaban igual. */
export function useImportarProductosWeb() {
  const qc = useQueryClient();
  return useMutation<
    {
      carpeta: string;
      nuevos: string[];
      actualizados: string[];
      iguales: string[];
      incompletos: string[];
    },
    Error,
    { archivo: File }
  >({
    mutationFn: async ({ archivo }) => {
      const fd = new FormData();
      fd.append("archivo", archivo);
      return api.post(`${ROOT}/productos-web/importar`, fd);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

/** Encola la importación de VARIOS ZIP de golpe.
 *
 *  Van a la cola porque son 31 ficheros de varios MB: en la propia petición se
 *  agotaría el tiempo y no se vería el avance. */
export function useImportarProductosWebLote() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; title: string; zips: number },
    Error,
    { archivos: File[] }
  >({
    mutationFn: async ({ archivos }) => {
      const fd = new FormData();
      for (const f of archivos) fd.append("archivos", f);
      return api.post(`${ROOT}/productos-web/importar-lote`, fd);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

export function useBorrarMiProducto() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, { carpeta: string; producto: string }>({
    mutationFn: ({ carpeta, producto }) =>
      api.del(
        `${ROOT}/mis-productos?carpeta=${encodeURIComponent(carpeta)}` +
          `&producto=${encodeURIComponent(producto)}`,
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

/** Ancho por defecto de las fotos que se PINTAN.
 *
 *  Es lo que impedía que la APK se cerrara sola: el móvil guarda cada foto
 *  descodificada (ancho × alto × 4 bytes), así que una ficha de 1320×2868 son
 *  15 MB de RAM y una carpeta de diez productos se plantaba en ~300 MB. Chrome
 *  mata la pestaña por memoria y en la APK eso se ve como la app cerrándose.
 *  A 400 px la misma foto ocupa 1,4 MB y en una tarjeta no se nota.
 *
 *  El original NO se toca donde importa: las descargas van por `/foto-limpia`
 *  y el vídeo se monta en el servidor leyendo el fichero de Drive.
 */
export const ANCHO_MINIATURA = 400;
/** Para el visor: se ve a ~384 px de ancho, pero con pantallas 2-3x conviene
 *  el doble largo. Es UNA foto a la vez, no veinte. */
export const ANCHO_VISOR = 900;
/** Para los sellos de 44-64 px (ficha de producto, vendidos, escaparate).
 *
 *  Ahí `ANCHO_MINIATURA` era 6 veces más grande de lo que se pinta, y lo que
 *  ocupa en el móvil es el bitmap DESCODIFICADO, no el fichero: 400 px de ancho
 *  son ~1,4 MB por foto, y una carpeta de diez productos ~28 MB de nada. A 160
 *  px (2,5× para pantallas densas) la misma foto son ~0,22 MB. Cuanto menos
 *  ocupa el proceso, menos papeletas tiene de que Android lo mate al dejarlo
 *  de fondo — que es lo que sale en el chivato. */
export const ANCHO_CHIP = 160;

export function buildPhotoUrl(
  source: string, folder: string, fileId: string, ancho: number | null = ANCHO_MINIATURA,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const w = ancho ? `&w=${ancho}` : "";
  return `${base}${ROOT}/photo?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&file_id=${encodeURIComponent(fileId)}${w}${qs}`;
}

// --- Fase 2: automatización de vídeos ----------------------------------

/** Prompts (imagen/vídeo) — no dependen de carpeta ni fuente.
 *
 *  `staleTime` finito A PROPÓSITO: con `Infinity` el prompt se quedaba
 *  congelado para siempre en el móvil —la clave empieza por `nicho-pov-bof`,
 *  así que `cache-persistente` lo guarda en localStorage y al arrancar se
 *  rehidrataba el viejo sin volver a pedirlo—. Se cambió el prompt de vídeo
 *  al inglés, se desplegó, y el botón de copiar seguía dando el de antes.
 *  Son dos ficheros pequeños: pedirlos cada minuto no cuesta nada. */
export function usePrompts() {
  return useQuery<PromptsResponse>({
    queryKey: nichoPovBofKeys.prompts(),
    queryFn: () => api.get<PromptsResponse>(`${ROOT}/prompts`),
    staleTime: 60_000,
  });
}

export function useProductos(source: string, folder: string | null) {
  // El backend devuelve {source, folder, items, textos_extraidos}; se
  // desenvuelve aquí a la lista para que los componentes no tengan que
  // conocer la envoltura.
  //
  // Mientras haya un montaje en cola o en curso se sondea solo, y para en
  // cuanto deja de haberlo. La señal (`montando`) sale de la COLA: antes se
  // intentaba deducir con `uploaded && !video_path`, pero el runner escribe
  // esos dos campos A LA VEZ al terminar, así que la condición nunca era
  // cierta y el sondeo no arrancaba nunca — había que recargar a mano.
  return useQuery<ProductoItem[]>({
    // 12 s: lo inmediato lo cubre el aviso de la cola al terminar el montaje
    // (`useAlTerminarJob`); esto es solo la red de seguridad.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.montando) ? 12000 : false,
    queryKey: nichoPovBofKeys.productos(source, folder ?? ""),
    queryFn: async () =>
      (await api.get<{ items: ProductoItem[] }>(
        `${ROOT}/productos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      )).items ?? [],
    enabled: Boolean(source && folder),
  });
}

/** Relee del Drive saltándose la caché de listados del servidor.
 *
 *  El backend cachea qué fotos tiene cada carpeta, así que una carpeta que se
 *  listó vacía (Drive lento, o las fotos aún sin subir) seguía saliendo vacía
 *  aunque se recargara la app. Esto es lo que hace de verdad el botón
 *  "Actualizar productos y ventas".
 */
export async function refrescarDesdeDrive(source: string, folder: string | null) {
  await api.get(`${ROOT}/folders?source=${encodeURIComponent(source)}&refresh=true`);
  if (folder) {
    await api.get(
      `${ROOT}/productos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
        folder,
      )}&refresh=true`,
    );
  }
}

/** TODOS los productos de la fuente, de más a menos ventas.
 *
 *  Solo tiene sentido en "Top vendidos": ahí cada producto se queda de por
 *  vida en la carpeta de diez donde entró, así que ordenar dentro de una
 *  carpeta no da el ranking. Cada item trae su `folder`.
 */
export function useProductosTodos(source: string, activo: boolean) {
  return useQuery<ProductoItem[]>({
    queryKey: [...nichoPovBofKeys.productos(source, "*todos*")],
    queryFn: async () =>
      (await api.get<{ items: ProductoItem[] }>(
        `${ROOT}/productos-todos?source=${encodeURIComponent(source)}`,
      )).items ?? [],
    enabled: Boolean(source && activo),
    // 12 s: lo inmediato lo cubre el aviso de la cola al terminar el montaje
    // (`useAlTerminarJob`); esto es solo la red de seguridad.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.montando) ? 12000 : false,
  });
}

/** Tarda ~1 min (lee las capturas con Gemini) — el caller muestra spinner. */
export function useExtraerTextos() {
  const qc = useQueryClient();
  return useMutation<ProductoItem[], Error, ExtraerTextosRequest>({
    mutationFn: async (body) =>
      (await api.post<{ items: ProductoItem[] }>(`${ROOT}/extraer-textos`, body)).items ?? [],
    onSuccess: (items, vars) => {
      qc.setQueryData(nichoPovBofKeys.productos(vars.source, vars.folder), items);
    },
  });
}

/** Quita un clip subido por error (productos de plazos, que llevan dos). */
export function useQuitarClip() {
  const qc = useQueryClient();
  return useMutation<
    ProductoItem,
    Error,
    { source: string; folder: string; producto: string; slot: 1 | 2 }
  >({
    mutationFn: ({ source, folder, producto, slot }) =>
      api.post<ProductoItem>(
        `${ROOT}/clip/quitar?source=${encodeURIComponent(source)}` +
          `&folder=${encodeURIComponent(folder)}` +
          `&producto=${encodeURIComponent(producto)}&slot=${slot}`,
        {},
      ),
    onSuccess: (updated, v) => {
      const mete = (p: ProductoItem) =>
        p.producto === updated.producto
          ? { ...p, clip1: updated.clip1, clip2: updated.clip2 }
          : p;
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(v.source, v.folder),
        (old) => old?.map(mete),
      );
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(v.source, "*todos*"),
        (old) =>
          old?.map((p) =>
            p.producto === updated.producto && (p.folder ?? "") === v.folder ? mete(p) : p,
          ),
      );
    },
  });
}

export function useSetEstado() {
  const qc = useQueryClient();
  return useMutation<ProductoItem, Error, EstadoRequest>({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/estado`, body),
    onSuccess: (updated, vars) => {
      // Solo los campos de ESTADO, no el producto entero: la respuesta viene
      // sin fotos (rellenarlas costaba 10-15s por toque) y sustituyendo la
      // ficha completa desaparecía la miniatura hasta recargar.
      const soloEstado = (p: ProductoItem): ProductoItem => ({
        ...p,
        en_escaparate: updated.en_escaparate,
        uploaded: updated.uploaded,
        uploaded_at: updated.uploaded_at,
        sold: updated.sold,
      });
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? soloEstado(p) : p)),
      );
      // La lista global (ranking de Top vendidos) es otra query. Se PARCHEA
      // en sitio, no se invalida: invalidándola, cada toque a Escaparate o
      // Subido volvía a listar las cuatro carpetas enteras del ranking y el
      // botón tardaba segundos en responder.
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, "*todos*"),
        (old) =>
          old?.map((p) =>
            p.producto === updated.producto && (p.folder ?? "") === vars.folder
              ? soloEstado(p)
              : p,
          ),
      );
      // El ranking de vendidos solo cambia si se tocó "Vendió": recargarlo al
      // marcar Escaparate o Subido era trabajo de más en la acción que más se
      // repite del día.
      if (vars.sold !== undefined) {
        void qc.invalidateQueries({ queryKey: nichoPovBofKeys.vendidos(vars.source) });
      }
      // Y si lo que cambió fue "Subido", el tope diario ya no es el mismo.
      if (vars.uploaded !== undefined) {
        void qc.invalidateQueries({ queryKey: ["cuotas", "hoy"] });
      }
      // El precio decide si el vídeo va con guion de plazos (dos clips) y lo
      // lee también el POV BOF Largo, que es otro nicho con sus propias
      // queries: se invalida TODO, que es lo único que garantiza que el
      // cambio se vea donde se está mirando.
      if (vars.precio !== undefined) {
        void qc.invalidateQueries();
      }
    },
  });
}

/** Copia a "Top vendidos" los productos del ranking que aún no estén.
 *
 *  No gasta Gemini (los textos se copian de la carpeta de origen) y solo
 *  añade: un producto ya copiado no se mueve de sitio aunque venda más. */
export interface SincronizarTopResponse {
  añadidos: number;
  total: number;
  carpetas: number;
  /** Vendidos que NO se pudieron copiar (y por qué). Sin esto, el botón
   *  seguía diciendo "traer 1 producto nuevo" para siempre. */
  omitidos?: { producto: string; motivo: string }[];
}

/** Rehace fotos y textos de una carpeta de Top vendidos desde el original. */
export function useRepararTopVendidos() {
  const qc = useQueryClient();
  return useMutation<
    { fotos: number; textos: number; avisos: string[] },
    Error,
    { folder: string }
  >({
    mutationFn: ({ folder }) =>
      api.post<{ fotos: number; textos: number; avisos: string[] }>(
        `${ROOT}/top-vendidos/reparar?folder=${encodeURIComponent(folder)}`,
        {},
      ),
    // Cambian fotos Y textos de toda la carpeta, y los leen todos los nichos.
    onSuccess: () => void qc.invalidateQueries(),
  });
}

export function useSincronizarTopVendidos() {
  const qc = useQueryClient();
  return useMutation<SincronizarTopResponse, Error, void>({
    mutationFn: () =>
      api.post<SincronizarTopResponse>(`${ROOT}/top-vendidos/sincronizar`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all });
    },
  });
}

/** Sortea el guion de plazos del producto (o pide otro distinto).
 *
 *  No gasta ninguna llamada de API: son cinco textos fijos del curso. Sirve
 *  para leer lo que va a decir la voz ANTES de montar. */
export function useSortearGuionPlazos() {
  const qc = useQueryClient();
  return useMutation<
    ProductoItem,
    Error,
    { source: string; folder: string; producto: string; rehacer?: boolean }
  >({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/guion-plazos`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? updated : p)),
      );
    },
  });
}

/** Averigua la ficha de TikTok Shop del producto. GASTA UNA LLAMADA del plan
 *  de EchoTik (trial de 100), por eso va producto a producto y no de carpeta
 *  entera. Si no encuentra nada fiable devuelve el producto sin `product_url`
 *  (no es un error). */
export function useBuscarProductoUrl() {
  const qc = useQueryClient();
  return useMutation<ProductoItem, Error, ProductoUrlRequest>({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/url`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? updated : p)),
      );
    },
  });
}

/** Busca la ficha de TODOS los productos de la carpeta sin URL. Gasta UNA
 *  llamada de EchoTik por producto buscado — la respuesta trae el recuento
 *  (`llamadas`) para poder decírselo al operador. */
export function useBuscarUrlsCarpeta() {
  const qc = useQueryClient();
  return useMutation<ProductosUrlsResponse, Error, ProductosUrlsRequest>({
    mutationFn: (body) => api.post<ProductosUrlsResponse>(`${ROOT}/productos/urls`, body),
    onSuccess: (res, vars) => {
      qc.setQueryData(nichoPovBofKeys.productos(vars.source, vars.folder), res.items);
    },
  });
}

/** Credenciales de EchoTik. Se aplican en caliente: el cliente las lee de
 *  Redis, así que no hace falta redespliegue ni tocar el .env del VPS. */
export function useEchoTikEstado() {
  return useQuery<EchoTikCredsResponse>({
    queryKey: [...nichoPovBofKeys.all, "echotik"] as const,
    queryFn: () => api.get<EchoTikCredsResponse>(`${ROOT}/echotik`),
  });
}

export function useGuardarEchoTik() {
  const qc = useQueryClient();
  return useMutation<EchoTikCredsResponse, Error, EchoTikCredsRequest>({
    mutationFn: (body) => api.post<EchoTikCredsResponse>(`${ROOT}/echotik`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...nichoPovBofKeys.all, "echotik"] });
    },
  });
}

/** Banco de cuentas de EchoTik. Guardar y activar van por separado: se apuntan
 *  cuentas de respaldo sin tocar la que está en uso, y al mes se vuelve a la
 *  que ya tenga la cuota renovada. */
const cuentasKey = [...nichoPovBofKeys.all, "echotik", "cuentas"] as const;

export function useEchoTikCuentas() {
  return useQuery<EchoTikCuenta[]>({
    queryKey: cuentasKey,
    queryFn: async () =>
      (await api.get<EchoTikCuentasResponse>(`${ROOT}/echotik/cuentas`)).items ?? [],
  });
}

function useCuentasMutation<V>(fn: (v: V) => Promise<EchoTikCuentasResponse>) {
  const qc = useQueryClient();
  return useMutation<EchoTikCuentasResponse, Error, V>({
    mutationFn: fn,
    onSuccess: (res) => {
      qc.setQueryData(cuentasKey, res.items ?? []);
      // La cuenta activa cambia → el panel de credenciales tiene que refrescar.
      void qc.invalidateQueries({ queryKey: [...nichoPovBofKeys.all, "echotik"] });
    },
  });
}

export function useGuardarCuentaEchoTik() {
  return useCuentasMutation<EchoTikCuentaRequest>((body) =>
    api.post<EchoTikCuentasResponse>(`${ROOT}/echotik/cuentas`, body),
  );
}

export function useActivarCuentaEchoTik() {
  return useCuentasMutation<string>((usuario) =>
    api.post<EchoTikCuentasResponse>(
      `${ROOT}/echotik/cuentas/activar?usuario=${encodeURIComponent(usuario)}`,
    ),
  );
}

export function useBorrarCuentaEchoTik() {
  return useCuentasMutation<string>((usuario) =>
    api.del<EchoTikCuentasResponse>(
      `${ROOT}/echotik/cuentas?usuario=${encodeURIComponent(usuario)}`,
    ),
  );
}

/** Hashtags de cuenta (los mismos para todos los captions). */
export function useHashtags() {
  return useQuery<string[]>({
    queryKey: [...nichoPovBofKeys.all, "hashtags"] as const,
    queryFn: async () => (await api.get<HashtagsResponse>(`${ROOT}/hashtags`)).tags ?? [],
  });
}

export function useGuardarHashtags() {
  const qc = useQueryClient();
  return useMutation<HashtagsResponse, Error, string[]>({
    mutationFn: (tags) => api.post<HashtagsResponse>(`${ROOT}/hashtags`, { tags }),
    onSuccess: (res) => {
      qc.setQueryData([...nichoPovBofKeys.all, "hashtags"], res.tags ?? []);
    },
  });
}

/** Ranking de vendidos. Sin `source` salen TODOS, que es lo que piden los
 *  nichos con catálogo propio (gorras, ropa, cuenta piloto): el índice es único
 *  y global, así que el ranking es el mismo se mire desde donde se mire. */
export function useVendidos(source: string) {
  return useQuery<VendidoItem[]>({
    queryKey: nichoPovBofKeys.vendidos(source),
    queryFn: async () =>
      (await api.get<{ items: VendidoItem[] }>(
        `${ROOT}/vendidos${source ? `?source=${encodeURIComponent(source)}` : ""}`,
      )).items ?? [],
  });
}

/** Suma (o resta) unidades vendidas. El ranking vuelve ya reordenado. */
export function useSumarUnidades() {
  const qc = useQueryClient();
  return useMutation<
    { items: VendidoItem[] },
    Error,
    { source: string; folder: string; producto: string; delta: number }
  >({
    mutationFn: (body) =>
      api.post<{ items: VendidoItem[] }>(`${ROOT}/vendidos/unidades`, body),
    onSuccess: (res, vars) => {
      qc.setQueryData(nichoPovBofKeys.vendidos(vars.source), res.items ?? []);
    },
  });
}

/** URL del vídeo YA montado. `v` es la marca de versión: sin ella el
 *  navegador reutilizaría el vídeo anterior de su caché al remontar. */
export function buildVideoUrl(
  source: string, folder: string, producto: string,
  version = 0, descargar = false,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/video?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&v=${version}${descargar ? "&descargar=true" : ""}${qs}`;
}

/** URL de descarga de una foto por nombre de producto (no por file id; el
 *  backend resuelve el par limpia/titulada dentro de la carpeta).
 *
 *  Hay que pasar por ESTE endpoint y no por `buildPhotoUrl`: el atributo
 *  `download` de un `<a>` se ignora cuando la URL es de otro origen —y la API
 *  lo es—, así que lo que fuerza la descarga es el `Content-Disposition:
 *  attachment` que pone este endpoint. Con la URL de ver, el móvil abre la
 *  imagen en una pestaña y no baja nada.
 *
 *  `variante`: "limpia" (default, la que anima el POV BOF) o "ficha" (la
 *  captura con la descripción, que es la que pide Creativos Pro).
 */
export interface ProductoConUrl {
  clave: string;
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  titulo_tiktok_completo: string;
  tienda: string;
  /** Precio de la ficha (0 si no se pudo leer): ordena la lista de la tienda. */
  precio: number;
  /** El de antes del descuento, para enseñarlo tachado. */
  precio_lista: number;
  url: string;
  /** En qué carpetas sale el mismo producto (la ficha vale para todas). */
  carpetas: string[];
}

export interface UrlsCatalogo {
  source: string;
  tiendas: { tienda: string; items: ProductoConUrl[]; con_url: number; total: number }[];
  con_url: number;
  total: number;
}

/** Los productos de un catálogo agrupados por tienda, con su ficha de TikTok. */
export function useUrlsCatalogo(source: string) {
  return useQuery<UrlsCatalogo>({
    queryKey: [...nichoPovBofKeys.all, "urls", source],
    queryFn: () =>
      api.get<UrlsCatalogo>(`${ROOT}/urls-catalogo?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
    staleTime: 60_000,
  });
}

/** Guardar de golpe las fichas copiadas del DOM de la web del curso. */
export function useImportarUrls() {
  const qc = useQueryClient();
  return useMutation<
    {
      carpetas: number;
      guardados: number;
      en_indice: number;
      /** Carpetas del pegote que no casan con ninguna del catálogo. */
      sin_carpeta: string[];
      /** Enlaces que no son de TikTok (su web tiene alguno suelto). */
      descartadas: string[];
    },
    Error,
    { source: string; filas: unknown[] }
  >({
    mutationFn: (body) => api.post(`${ROOT}/urls/importar`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

/** Pegar (o quitar) la ficha de un producto. Vale para todas sus carpetas. */
export function useGuardarUrlProducto() {
  const qc = useQueryClient();
  return useMutation<
    { url: string },
    Error,
    { source: string; folder: string; producto: string; url: string }
  >({
    mutationFn: (body) => api.post(`${ROOT}/url-producto`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoPovBofKeys.all }),
  });
}

/** Revisar que el texto de cada producto es el de SU ficha (por la cola). */
export function useRevisarTextos() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; title: string },
    Error,
    { source: string; arreglar?: boolean }
  >({
    mutationFn: ({ source, arreglar }) =>
      api.post(
        `${ROOT}/textos/revisar?source=${encodeURIComponent(source)}` +
          (arreglar ? "&arreglar=true" : ""),
        {},
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["queue"] }),
  });
}

export function buildCleanPhotoDownloadUrl(
  source: string, folder: string, producto: string,
  variante: "limpia" | "ficha" = "limpia",
  /** Con ancho sale encogida y se PINTA (no se descarga): para miniaturas
   *  donde solo hace falta reconocer el producto. */
  ancho = 0,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const w = ancho ? `&w=${ancho}` : "";
  return `${base}${ROOT}/foto-limpia?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&variante=${variante}${w}${qs}`;
}

// --- Subida en tanda -------------------------------------------------------

export interface LoteItem {
  token: string;
  archivo: string;
  producto: string;
  por_que: string;
}

export interface LoteResponse {
  source: string;
  folder: string;
  items: LoteItem[];
  reconocidos: number;
  /** Entre cuántos productos ha podido elegir. */
  candidatos?: number;
}

/** Sube varios vídeos de golpe y devuelve de qué producto cree que es cada uno.
 *  NO encola nada: el operador repasa y confirma después. */
/** Sube UN vídeo de la tanda y devuelve su identificador.
 *
 *  Con XHR y no con fetch para tener porcentaje de verdad: son ficheros de
 *  10-30 MB y sin progreso el botón se queda minutos sin decir nada. Van de
 *  uno en uno a propósito — varios a la vez desde el móvil se atragantan.
 */
export function baseApi(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

export function claveApi(): string {
  return process.env.NEXT_PUBLIC_API_KEY ?? "";
}

/** Endpoint de subida de un vídeo del lote. Lo necesita también la subida en
 *  segundo plano, que arma las peticiones a mano. */
export function urlSubidaLote(root: string): string {
  return `${baseApi()}${root}/video/lote/subir`;
}

export function subirUno(v: {
  source: string;
  folder: string;
  /** El fichero, o el blob recuperado de IndexedDB al retomar una tanda. */
  file: File | Blob;
  nombre?: string;
  root: string;
  onProgreso?: (pct: number) => void;
  /** Para poder cortar la subida al desmontar la pantalla. */
  senal?: AbortSignal;
}): Promise<string> {
  const base = baseApi();
  const key = claveApi();
  const nombre = v.nombre ?? (v.file instanceof File ? v.file.name : "video.mp4");
  const fd = new FormData();
  fd.append("file", v.file, nombre);
  fd.append("source", v.source);
  fd.append("folder", v.folder);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${base}${v.root}/video/lote/subir`);
    if (key) xhr.setRequestHeader("X-API-Key", key);
    xhr.withCredentials = true;
    if (v.senal) {
      if (v.senal.aborted) {
        reject(new Error("Subida cancelada"));
        return;
      }
      v.senal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) v.onProgreso?.(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      try {
        const d = JSON.parse(xhr.responseText) as { token?: string; error?: string };
        if (xhr.status >= 400 || !d.token) {
          reject(new Error(d.error || `No se pudo subir ${nombre}`));
          return;
        }
        resolve(d.token);
      } catch {
        reject(new Error(`Respuesta inválida al subir ${nombre}`));
      }
    };
    xhr.onabort = () => reject(new Error("Subida cancelada"));
    xhr.onerror = () => reject(new Error(`Error de red subiendo ${nombre}`));
    xhr.send(fd);
  });
}

/** Con los vídeos ya subidos, dice de qué producto es cada uno. */
export function useRepartirLote(root: string = ROOT) {
  return useMutation<
    LoteResponse,
    Error,
    {
      source: string;
      folder: string;
      tokens: string[];
      /** Repartir SOLO entre los productos con la ficha enlazada. */
      solo_con_url?: boolean;
    }
  >({
    mutationFn: (body) => api.post<LoteResponse>(`${root}/video/lote/repartir`, body),
  });
}

export function useConfirmarLote(root: string = ROOT) {
  const qc = useQueryClient();
  return useMutation<
    { encolados: number; pendientes: number; mensajes: string[] },
    Error,
    {
      source: string;
      folder: string;
      items: { token: string; producto: string }[];
      sexo: string;
      con_gancho: boolean;
      con_titulo: boolean;
      con_cta: boolean;
      con_flecha: boolean;
    }
  >({
    mutationFn: (body) =>
      api.post<{ encolados: number; pendientes: number; mensajes: string[] }>(
        `${root}/video/lote/confirmar`,
        body,
      ),
    // Se invalida TODO el nicho, no solo esta carpeta: la pantalla la usan los
    // dos y cada uno guarda su progreso en su sitio.
    onSuccess: () => void qc.invalidateQueries(),
  });
}

/** URL para ver un bruto de la tanda que aún no se ha asignado.
 *
 *  Lleva la api_key en la URL porque va en un `<video src>` y ahí no se pueden
 *  poner cabeceras. */
export function archivoLoteUrl(root: string, token: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const k = process.env.NEXT_PUBLIC_API_KEY ?? "";
  return (
    `${base}${root}/video/lote/archivo?token=${encodeURIComponent(token)}` +
    (k ? `&api_key=${encodeURIComponent(k)}` : "")
  );
}
