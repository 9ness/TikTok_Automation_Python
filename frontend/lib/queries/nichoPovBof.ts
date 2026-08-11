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

/** Prompts fijos (imagen/vídeo) — no dependen de carpeta ni fuente. */
export function usePrompts() {
  return useQuery<PromptsResponse>({
    queryKey: nichoPovBofKeys.prompts(),
    queryFn: () => api.get<PromptsResponse>(`${ROOT}/prompts`),
    staleTime: Infinity,
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
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.montando) ? 5000 : false,
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

export function useSetEstado() {
  const qc = useQueryClient();
  return useMutation<ProductoItem, Error, EstadoRequest>({
    mutationFn: (body) => api.post<ProductoItem>(`${ROOT}/producto/estado`, body),
    onSuccess: (updated, vars) => {
      qc.setQueryData<ProductoItem[]>(
        nichoPovBofKeys.productos(vars.source, vars.folder),
        (old) => old?.map((p) => (p.producto === updated.producto ? updated : p)),
      );
      // Puede haber entrado o salido de "vendidos".
      void qc.invalidateQueries({ queryKey: nichoPovBofKeys.vendidos(vars.source) });
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
export function buildCleanPhotoDownloadUrl(
  source: string, folder: string, producto: string,
  variante: "limpia" | "ficha" = "limpia",
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/foto-limpia?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&variante=${variante}${qs}`;
}
