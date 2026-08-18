"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** Nicho Carruseles (módulo 14).
 *
 *  El CATÁLOGO no está aquí: productos, fotos del Drive, textos, hashtags,
 *  escaparate y vendidos son los del Nicho POV BOF y se piden con sus hooks
 *  (`nichoPovBof.ts`), igual que hace Creativos Pro. Aquí solo vive lo del
 *  carrusel: si el producto vale, sus dos mensajes y sus dos fotos.
 */
const ROOT = "/api/v1/nicho-carruseles";

export const carruselesKeys = {
  all: ["nicho-carruseles"] as const,
  prompts: () => [...carruselesKeys.all, "prompts"] as const,
  folders: (source: string) => [...carruselesKeys.all, "folders", source] as const,
  estado: (source: string, folder: string) =>
    [...carruselesKeys.all, "estado", source, folder] as const,
  /** Las chicas que faltan son de TODOS los catálogos, no de uno. */
  pendientes: () => [...carruselesKeys.all, "pendientes"] as const,
  referencias: () => [...carruselesKeys.all, "referencias"] as const,
  aptos: () => [...carruselesKeys.all, "aptos"] as const,
  sinAsignar: () => [...carruselesKeys.all, "sin-asignar"] as const,
};

/** Un producto apto, mirando TODOS los catálogos a la vez. Es lo que deja
 *  bajar las fotos limpias en lote por categoría y generar la foto 2 de
 *  cincuenta productos en una sesión de Flow. */
export interface AptoCarrusel {
  source: string;
  folder: string;
  producto: string;
  ref: string;
  titulo: string;
  tienda: string;
  categoria: string;
  escenario: string;
  tiene_foto2: boolean;
}

export interface AptosCarrusel {
  items: AptoCarrusel[];
  por_categoria: Record<string, number>;
  /** Cuántos de cada categoría ya tienen foto 2 (para el "2/3"). */
  con_foto2_por_categoria: Record<string, number>;
  /** Cuántos productos del catálogo pasan el filtro. `total` son los que
   *  tienen textos extraídos: sin título no hay nada que clasificar. */
  resumen: {
    total: number;
    clasificados: number;
    aptos: number;
    filtros: number;
  };
}

export interface FotoSuelta {
  archivo: string;
  version: string;
}

/** Las fotos que hay que ADJUNTAR en Flow: los dos prompts del curso son de
 *  imagen-a-imagen, sin referencia no generan nada. */
export interface ReferenciaEstado {
  hay: boolean;
  /** true si la puso el operador; false = la del Drive del curso. */
  propia: boolean;
  version: string;
}

/** `chica`, `producto` y una por escenario (`chica_sofa`, `chica_playa`…). La
 *  del escenario es la que manda al generar esa tanda. */
export type Referencias = Record<string, ReferenciaEstado>;

/** Dónde está la chica de la foto 1. Cada escenario tiene su prompt de Flow:
 *  la chica tiene que estar DONDE se usa el producto (en la cama si es un
 *  colchón, en el sofá si es un sofá). */
export interface EscenarioPrompt {
  clave: string;
  label: string;
  para: string;
  prompt: string;
  /** El de la foto 2 en ESE sitio (cocina, dormitorio…). No necesita foto de
   *  composición: basta con la foto limpia del producto. */
  prompt_producto: string;
  prompt_producto_mano: string;
  /** Para CREAR la referencia de este escenario desde cero, sin adjuntar
   *  ninguna foto: es lo único que fija la edad. */
  prompt_referencia: string;
  /** Qué chica buscar (o pedirle a la IA) para este escenario. */
  busqueda: string;
}

export interface PromptsCarruseles {
  escenarios: EscenarioPrompt[];
  producto: string;
  formato: string;
  referencia_drive: string;
}

export interface CarpetaCarruseles {
  name: string;
  completed: boolean;
  /** Cuántos productos de la carpeta valen para carrusel. */
  aptos: number;
  clasificada: boolean;
}

export interface FoldersCarruseles {
  source: string;
  items: CarpetaCarruseles[];
  current: string | null;
  done: number;
  total: number;
  aptos: number;
}

/** Qué fotos tiene el producto. El valor es el `mtime` (o "" si no está): se
 *  mete en la URL para poder cachear la imagen y aun así ver la nueva al
 *  sustituirla. */
export interface FotosCarrusel {
  chica: string;
  chica_txt: string;
  producto: string;
  producto_txt: string;
}

export interface ProductoCarrusel {
  categoria: string;
  apto: boolean;
  /** `true`/`false` si el operador lo forzó a mano; `null` = manda la IA. */
  apto_manual: boolean | null;
  /** Dónde va la chica de este producto (sale de su categoría). */
  escenario: string;
  /** No vacío si el operador lo cambió a mano. */
  escenario_manual: string;
  mensaje1: string;
  mensaje2: string;
  fotos: FotosCarrusel;
  subido_at: number;
}

export interface EstadoCarruseles {
  source: string;
  folder: string;
  clasificada: boolean;
  productos: Record<string, ProductoCarrusel>;
}

export interface PendienteChica {
  source: string;
  folder: string;
  producto: string;
  escenario: string;
}

export interface ChicasPendientes {
  faltan: number;
  total: number;
  /** Cuántas faltan de cada escenario: es la cuenta que se lleva a Flow. */
  por_escenario: Record<string, number>;
  /** Y cuántas hay en total, para poder decir "8/20". */
  total_por_escenario: Record<string, number>;
  /** Chicas de sobra esperando por escenario: se colocan solas en cuanto el
   *  curso añade un producto de ese sitio. */
  repuesto_por_escenario: Record<string, number>;
  por_tanda: number;
  items: PendienteChica[];
}


// ---------------------------------------------------------------------------
// Subida de tandas con porcentaje
// ---------------------------------------------------------------------------
// `fetch` no sabe decir cuánto lleva subido, así que las tandas van por
// XMLHttpRequest — igual que la subida de vídeos del POV BOF. Y en TROZOS de
// ocho ficheros: una tanda de 78 fotos son ~150 MB y mandarlos en una sola
// petición es pedir un timeout; así además el porcentaje avanza de verdad y no
// se queda clavado al 0 mientras sube todo.
const POR_TROZO = 8;

export interface ProgresoTanda {
  /** 0-100 del total de bytes de la tanda. */
  pct: number;
  hechos: number;
  total: number;
}

function subirTrozo(
  path: string,
  files: File[],
  extra: Record<string, string>,
  onBytes: (subidos: number) => void,
): Promise<unknown> {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const fd = new FormData();
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  files.forEach((f) => fd.append("archivos", f));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${base}${path}`);
    if (key) xhr.setRequestHeader("X-API-Key", key);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onBytes(e.loaded);
    };
    xhr.onload = () => {
      let d: { detail?: string; error?: string } = {};
      try {
        d = JSON.parse(xhr.responseText || "{}");
      } catch {
        d = {};
      }
      if (xhr.status >= 400) {
        reject(new Error(d.detail || d.error || `Error ${xhr.status} subiendo`));
        return;
      }
      resolve(d);
    };
    xhr.onerror = () => reject(new Error("Error de red subiendo la tanda"));
    xhr.send(fd);
  });
}

export interface ResultadoTanda {
  subidas: number;
  fallidas: number;
  total: number;
  /** El primer error, para poder enseñarlo. */
  error?: string;
  /** Cómo se ha guardado cada foto en el servidor (solo fotos de producto).
   *  Es lo que deja repartir SOLO esta tanda y no las sueltas de antes. */
  archivos: string[];
}

/** Sube todos los ficheros en trozos, avisando del porcentaje del TOTAL.
 *
 *  Un trozo que falla NO aborta la tanda: se cuenta y se sigue con el resto.
 *  Antes, si se caía el segundo trozo de veinte fotos, entraban ocho y no había
 *  forma de saber cuáles — y volver a subirlas todas las duplicaba a medias. */
async function subirTanda(
  path: string,
  files: File[],
  extra: Record<string, string>,
  onProgreso?: (p: ProgresoTanda) => void,
): Promise<ResultadoTanda> {
  const bytesTotal = files.reduce((n, f) => n + f.size, 0) || 1;
  let yaSubidos = 0;
  let subidas = 0;
  let error = "";
  const archivos: string[] = [];
  for (let i = 0; i < files.length; i += POR_TROZO) {
    const trozo = files.slice(i, i + POR_TROZO);
    const bytesTrozo = trozo.reduce((n, f) => n + f.size, 0);
    try {
      const res = await subirTrozo(path, trozo, extra, (bytes) => {
        onProgreso?.({
          pct: Math.min(100, Math.round(((yaSubidos + bytes) / bytesTotal) * 100)),
          hechos: i,
          total: files.length,
        });
      });
      const nombres = (res as { archivos?: string[] })?.archivos;
      if (Array.isArray(nombres)) archivos.push(...nombres);
      subidas += trozo.length;
    } catch (e) {
      if (!error) error = e instanceof Error ? e.message : String(e);
    }
    yaSubidos += bytesTrozo;
    onProgreso?.({
      pct: Math.min(100, Math.round((yaSubidos / bytesTotal) * 100)),
      hechos: Math.min(files.length, i + trozo.length),
      total: files.length,
    });
  }
  return {
    subidas, fallidas: files.length - subidas, total: files.length, error, archivos,
  };
}

export function usePromptsCarruseles() {
  return useQuery<PromptsCarruseles>({
    queryKey: carruselesKeys.prompts(),
    queryFn: () => api.get<PromptsCarruseles>(`${ROOT}/prompts`),
  });
}

export function useFoldersCarruseles(source: string) {
  return useQuery<FoldersCarruseles>({
    queryKey: carruselesKeys.folders(source),
    queryFn: () =>
      api.get<FoldersCarruseles>(`${ROOT}/folders?source=${encodeURIComponent(source)}`),
    enabled: Boolean(source),
  });
}

export function useEstadoCarruseles(source: string, folder: string | null) {
  return useQuery<EstadoCarruseles>({
    queryKey: carruselesKeys.estado(source, folder ?? ""),
    queryFn: () =>
      api.get<EstadoCarruseles>(
        `${ROOT}/estado?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}`,
      ),
    enabled: Boolean(source && folder),
  });
}

export function useCompletarCarpetaCarrusel() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean },
    Error,
    { source: string; folder: string; completed: boolean }
  >({
    mutationFn: (body) => api.post(`${ROOT}/complete`, body),
    onSuccess: (_r, v) =>
      void qc.invalidateQueries({ queryKey: carruselesKeys.folders(v.source) }),
  });
}

/** Guarda el estado que devuelven casi todos los endpoints de escritura: así
 *  la pantalla se actualiza sin una segunda vuelta a la API. */
function useGuardarEstado(source: string, folder: string | null) {
  const qc = useQueryClient();
  return (estado: EstadoCarruseles) => {
    qc.setQueryData(carruselesKeys.estado(source, folder ?? ""), estado);
    void qc.invalidateQueries({ queryKey: carruselesKeys.folders(source) });
    void qc.invalidateQueries({ queryKey: carruselesKeys.pendientes() });
  };
}

export function useClasificarCarpeta(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<EstadoCarruseles, Error, void>({
    mutationFn: () =>
      api.post<EstadoCarruseles>(`${ROOT}/clasificar`, { source, folder: folder ?? "" }),
    onSuccess: guardar,
  });
}

export function useMarcarApto(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<
    EstadoCarruseles,
    Error,
    { producto: string; apto: boolean | null }
  >({
    mutationFn: (body) =>
      api.post<EstadoCarruseles>(`${ROOT}/apto`, {
        source,
        folder: folder ?? "",
        ...body,
      }),
    onSuccess: guardar,
  });
}

export function useEscribirMensajes(source: string, folder: string | null) {
  const qc = useQueryClient();
  return useMutation<{ escritos: number }, Error, void>({
    mutationFn: () =>
      api.post<{ escritos: number }>(`${ROOT}/mensajes`, {
        source,
        folder: folder ?? "",
      }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: carruselesKeys.estado(source, folder ?? "") }),
  });
}

export function useEditarMensaje(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<
    EstadoCarruseles,
    Error,
    { producto: string; mensaje1?: string; mensaje2?: string }
  >({
    mutationFn: (body) =>
      api.post<EstadoCarruseles>(`${ROOT}/mensaje`, {
        source,
        folder: folder ?? "",
        ...body,
      }),
    onSuccess: guardar,
  });
}

/** Cuántas fotos de chica hay que generar en Flow, de TODOS los catálogos y
 *  repartidas por escenario. */
export function useChicasPendientes() {
  return useQuery<ChicasPendientes>({
    queryKey: carruselesKeys.pendientes(),
    queryFn: () => api.get<ChicasPendientes>(`${ROOT}/chicas/pendientes`),
    staleTime: 5 * 60_000,
  });
}

export interface RepartoChicas {
  escenario: string;
  asignadas: number;
  items: (PendienteChica & { archivo: string; mtime: number })[];
  sobran_fotos: number;
  faltan: number;
}

/** Sube la tanda entera de chicas de un escenario: se reparten solas entre los
 *  productos de ESE escenario que no tienen, de todos los catálogos. */
export function useSubirChicas() {
  const qc = useQueryClient();
  return useMutation<
    ResultadoTanda,
    Error,
    { escenario: string; files: File[]; onProgreso?: (p: ProgresoTanda) => void }
  >({
    mutationFn: ({ escenario, files, onProgreso }) =>
      subirTanda(`${ROOT}/chicas`, files, { escenario }, onProgreso),
    onSuccess: () => void qc.invalidateQueries({ queryKey: carruselesKeys.all }),
  });
}

/** Cambia dónde va la chica de un producto (cuando la categoría se queda
 *  corta). Vacío = el que le toca por su categoría. */
export function useCambiarEscenario(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<EstadoCarruseles, Error, { producto: string; escenario: string }>({
    mutationFn: (body) =>
      api.post<EstadoCarruseles>(`${ROOT}/escenario`, {
        source,
        folder: folder ?? "",
        ...body,
      }),
    onSuccess: guardar,
  });
}

/** Borra las fotos de chica de un escenario entero, para repetir la tanda. */
export function useBorrarChicas() {
  const qc = useQueryClient();
  return useMutation<{ borradas: number }, Error, string>({
    mutationFn: (escenario) =>
      api.del(`${ROOT}/chicas?escenario=${encodeURIComponent(escenario)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: carruselesKeys.all }),
  });
}

export function useSubirFotoCarrusel(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<
    EstadoCarruseles,
    Error,
    { producto: string; tipo: "chica" | "producto"; file: File }
  >({
    mutationFn: ({ producto, tipo, file }) => {
      const fd = new FormData();
      fd.append("source", source);
      fd.append("folder", folder ?? "");
      fd.append("producto", producto);
      fd.append("tipo", tipo);
      fd.append("archivo", file);
      return api.post<EstadoCarruseles>(`${ROOT}/foto`, fd);
    },
    onSuccess: guardar,
  });
}

export function useBorrarFotoCarrusel(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<
    EstadoCarruseles,
    Error,
    { producto: string; tipo: "chica" | "producto" }
  >({
    mutationFn: ({ producto, tipo }) =>
      api.del<EstadoCarruseles>(
        `${ROOT}/foto?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
          folder ?? "",
        )}&producto=${encodeURIComponent(producto)}&tipo=${tipo}`,
      ),
    onSuccess: guardar,
  });
}

export interface Quemado {
  quemadas: number;
  saltados: string[];
  estado: EstadoCarruseles;
}

/** Quema el mensaje sobre la foto. Sin `producto` va toda la carpeta — que es
 *  como se usa con las chicas. */
export function useQuemarTexto(source: string, folder: string | null) {
  const guardar = useGuardarEstado(source, folder);
  return useMutation<
    Quemado,
    Error,
    { producto?: string; tipo: "chica" | "producto" | "ambas" }
  >({
    mutationFn: (body) =>
      api.post<Quemado>(`${ROOT}/quemar`, { source, folder: folder ?? "", ...body }),
    onSuccess: (res) => guardar(res.estado),
  });
}

/** Quema los mensajes de TODO el catálogo, por la cola. */
export function useQuemarTodo() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string },
    Error,
    { tipo: "chica" | "producto" | "ambas"; rehacer?: boolean }
  >({
    mutationFn: (body) => api.post(`${ROOT}/quemar/todo`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["queue"] }),
  });
}

export function useSubidosCarruseles(source: string, folder: string | null) {
  return useQuery<Record<string, number>>({
    queryKey: [...carruselesKeys.all, "subidos", source, folder ?? ""],
    queryFn: async () =>
      (
        await api.get<{ items: string[]; horas: Record<string, number> }>(
          `${ROOT}/subidos?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
            folder ?? "",
          )}`,
        )
      ).horas ?? {},
    enabled: Boolean(source && folder),
  });
}

export function useMarcarSubidoCarrusel(source: string, folder: string | null) {
  const qc = useQueryClient();
  return useMutation<
    { items: string[]; horas: Record<string, number> },
    Error,
    { producto: string; uploaded: boolean }
  >({
    mutationFn: (body) =>
      api.post<{ items: string[]; horas: Record<string, number> }>(`${ROOT}/subido`, {
        source,
        folder: folder ?? "",
        ...body,
      }),
    onSuccess: (res) => {
      qc.setQueryData([...carruselesKeys.all, "subidos", source, folder ?? ""], res.horas ?? {});
      void qc.invalidateQueries({ queryKey: ["cuotas", "hoy"] });
    },
  });
}

/** Todos los aptos de todos los catálogos, con su categoría. */
export function useAptos() {
  return useQuery<AptosCarrusel>({
    queryKey: carruselesKeys.aptos(),
    queryFn: () => api.get<AptosCarrusel>(`${ROOT}/aptos`),
    // El barrido de los cuatro catálogos es lo más caro de esta pantalla y solo
    // cambia cuando el propio operador sube o clasifica algo (que ya invalida).
    staleTime: 5 * 60_000,
  });
}

export interface RepartoFotos2 {
  pendientes: number;
  job_id: string;
}

/** Sube la tanda de fotos de PRODUCTO. El reconocimiento va por la COLA: es
 *  una llamada de visión por cada 12 fotos y una tanda de 40 dejaba el
 *  navegador esperando minuto y medio.
 *
 *  Las fotos se guardan antes de encolar, así que aunque el reparto falle no se
 *  pierde ninguna: aparecen en "Sin reconocer" y se colocan a mano. */
export function useSubirFotos2() {
  const qc = useQueryClient();
  return useMutation<
    RepartoFotos2,
    Error,
    { files: File[]; categoria?: string; onProgreso?: (p: ProgresoTanda) => void }
  >({
    mutationFn: async ({ files, categoria, onProgreso }) => {
      const subida = await subirTanda(`${ROOT}/fotos2`, files, {}, onProgreso);
      // Con todo subido, un solo trabajo para reconocerlas: encolar uno por
      // trozo dejaría ocho jobs peleándose por los mismos productos. Con
      // `categoria`, el reconocimiento solo mira los productos de esa; y con
      // los nombres, SOLO estas fotos —si quedaban sueltas de otra tanda que
      // no se reconoció, no se mezclan con las nuevas.
      const qs = new URLSearchParams();
      if (categoria) qs.set("categoria", categoria);
      subida.archivos.forEach((a) => qs.append("archivos", a));
      return api.post<RepartoFotos2>(`${ROOT}/fotos2/repartir?${qs.toString()}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: carruselesKeys.all });
      void qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}

/** Filtrar (y escribir los mensajes de) TODO un catálogo, por la cola. */
export function usePrepararCatalogo() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; title: string; position_in_queue: number },
    Error,
    {
      source: string;
      rehacer?: boolean;
      solo_filtrar?: boolean;
      solo_mensajes?: boolean;
      carpetas?: string[];
    }
  >({
    mutationFn: (body) => api.post(`${ROOT}/preparar`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["queue"] }),
  });
}

export function useSinAsignar() {
  return useQuery<FotoSuelta[]>({
    queryKey: carruselesKeys.sinAsignar(),
    queryFn: async () =>
      (await api.get<{ items: FotoSuelta[] }>(`${ROOT}/sin-asignar`)).items,
    // El reparto corre en la cola: mientras queden fotas sueltas se vuelve a
    // mirar, y así la lista se vacía sola según las va colocando.
    refetchInterval: (q) => ((q.state.data?.length ?? 0) > 0 ? 15000 : false),
  });
}

export function useAsignarSuelta() {
  const qc = useQueryClient();
  return useMutation<
    { items: FotoSuelta[] },
    Error,
    { archivo: string; source: string; folder: string; producto: string }
  >({
    mutationFn: (body) => api.post(`${ROOT}/sin-asignar/asignar`, body),
    onSuccess: (res) => {
      qc.setQueryData(carruselesKeys.sinAsignar(), res.items);
      void qc.invalidateQueries({ queryKey: carruselesKeys.all });
    },
  });
}

export function useBorrarSuelta() {
  const qc = useQueryClient();
  return useMutation<{ items: FotoSuelta[] }, Error, string>({
    mutationFn: (archivo) =>
      api.del(`${ROOT}/sin-asignar?archivo=${encodeURIComponent(archivo)}`),
    onSuccess: (res) => qc.setQueryData(carruselesKeys.sinAsignar(), res.items),
  });
}

export function buildSueltaUrl(archivo: string, version: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  return `${base}${ROOT}/sin-asignar/foto?archivo=${encodeURIComponent(
    archivo,
  )}&v=${encodeURIComponent(version)}${qs}`;
}

/** La chica de la casa: una ficha JSON con su cara, sacada de una foto.
 *
 *  Sirve para CREAR las referencias de cada escenario: un párrafo no clava a
 *  una persona y la referencia es lo que manda en la foto final. Mismo paso que
 *  "crear la chica" del Nicho Ropa Con Personas. */
export interface ChicaFicha {
  hay: boolean;
  resumen: string;
  creada_at?: number;
  /** true si es la ficha de ESE escenario; false = se está usando la general. */
  propia?: boolean;
}

/** `escenario` vacío = la ficha general (la que vale para los que no tengan
 *  la suya). */
export function useChicaCarrusel(escenario = "") {
  return useQuery<ChicaFicha>({
    queryKey: [...carruselesKeys.all, "chica", escenario],
    queryFn: () =>
      api.get<ChicaFicha>(
        `${ROOT}/chica` + (escenario ? `?escenario=${encodeURIComponent(escenario)}` : ""),
      ),
  });
}

export function useCrearChicaCarrusel() {
  const qc = useQueryClient();
  return useMutation<ChicaFicha, Error, { file: File; escenario?: string }>({
    mutationFn: ({ file, escenario }) => {
      const fd = new FormData();
      if (escenario) fd.append("escenario", escenario);
      fd.append("archivo", file);
      return api.post<ChicaFicha>(`${ROOT}/chica`, fd);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...carruselesKeys.all, "chica"] });
      // Los prompts de referencia cambian: ahora llevan su ficha dentro.
      void qc.invalidateQueries({ queryKey: carruselesKeys.prompts() });
    },
  });
}

export function useBorrarChicaCarrusel() {
  const qc = useQueryClient();
  return useMutation<ChicaFicha, Error, string | void>({
    mutationFn: (escenario) =>
      api.del<ChicaFicha>(
        `${ROOT}/chica` + (escenario ? `?escenario=${encodeURIComponent(escenario)}` : ""),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...carruselesKeys.all, "chica"] });
      void qc.invalidateQueries({ queryKey: carruselesKeys.prompts() });
    },
  });
}

export function useReferencias() {
  return useQuery<Referencias>({
    queryKey: carruselesKeys.referencias(),
    queryFn: async () =>
      (await api.get<{ items: Referencias }>(`${ROOT}/referencias`)).items,
    staleTime: 5 * 60_000,
  });
}

export function useSubirReferencia() {
  const qc = useQueryClient();
  return useMutation<
    { items: Referencias },
    Error,
    { tipo: "chica" | "producto"; file: File; escenario?: string }
  >({
    mutationFn: ({ tipo, file, escenario }) => {
      const fd = new FormData();
      fd.append("tipo", tipo);
      if (escenario) fd.append("escenario", escenario);
      fd.append("archivo", file);
      return api.post<{ items: Referencias }>(`${ROOT}/referencia`, fd);
    },
    onSuccess: (res) => qc.setQueryData(carruselesKeys.referencias(), res.items),
  });
}

/** Quita la propia y vuelve a la del curso. */
export function useBorrarReferencia() {
  const qc = useQueryClient();
  return useMutation<
    { items: Referencias },
    Error,
    { tipo: "chica" | "producto"; escenario?: string }
  >({
    mutationFn: ({ tipo, escenario }) =>
      api.del<{ items: Referencias }>(
        `${ROOT}/referencia?tipo=${tipo}` +
          (escenario ? `&escenario=${encodeURIComponent(escenario)}` : ""),
      ),
    onSuccess: (res) => qc.setQueryData(carruselesKeys.referencias(), res.items),
  });
}

/** URL de la foto de referencia. Con `ancho` la pide encogida: los sellos de
 *  44 px de los escenarios se bajaban enteros (medio mega por carga). Al
 *  descargarla nunca se encoge — esa es la que se sube a Flow. */
export function buildReferenciaUrl(
  tipo: "chica" | "producto",
  version: string,
  descargar = false,
  escenario = "",
  ancho = 0,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const dl = descargar ? "&descargar=1" : "";
  const esc = escenario ? `&escenario=${encodeURIComponent(escenario)}` : "";
  const w = ancho && !descargar ? `&w=${ancho}` : "";
  return `${base}${ROOT}/referencia?tipo=${tipo}&v=${encodeURIComponent(
    version,
  )}${esc}${dl}${w}${qs}`;
}

/** URL de una foto del banco. Lleva el `mtime` (`v`) para que el móvil pueda
 *  cachearla y aun así ver la nueva cuando se sustituye. */
export function buildFotoCarruselUrl(
  source: string,
  folder: string,
  producto: string,
  tipo: keyof FotosCarrusel,
  version: string,
  descargar = false,
  ancho = 0,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const dl = descargar ? "&descargar=1" : "";
  const w = ancho && !descargar ? `&w=${ancho}` : "";
  return `${base}${ROOT}/foto?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&tipo=${tipo}&v=${encodeURIComponent(
    version,
  )}${dl}${w}${qs}`;
}
