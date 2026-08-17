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
};

/** Las fotos que hay que ADJUNTAR en Flow: los dos prompts del curso son de
 *  imagen-a-imagen, sin referencia no generan nada. */
export interface ReferenciaEstado {
  hay: boolean;
  /** true si la puso el operador; false = la del Drive del curso. */
  propia: boolean;
  version: string;
}

export type Referencias = Record<"chica" | "producto", ReferenciaEstado>;

/** Dónde está la chica de la foto 1. Cada escenario tiene su prompt de Flow:
 *  la chica tiene que estar DONDE se usa el producto (en la cama si es un
 *  colchón, en el sofá si es un sofá). */
export interface EscenarioPrompt {
  clave: string;
  label: string;
  para: string;
  prompt: string;
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
  /** Cuántas faltan de cada escenario: es la cuenta que se lleva a Flow. */
  por_escenario: Record<string, number>;
  por_tanda: number;
  items: PendienteChica[];
}

export function usePromptsCarruseles() {
  return useQuery<PromptsCarruseles>({
    queryKey: carruselesKeys.prompts(),
    queryFn: () => api.get<PromptsCarruseles>(`${ROOT}/prompts`),
    staleTime: Infinity,
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
  return useMutation<RepartoChicas, Error, { escenario: string; files: File[] }>({
    mutationFn: ({ escenario, files }) => {
      const fd = new FormData();
      fd.append("escenario", escenario);
      files.forEach((f) => fd.append("archivos", f));
      return api.post<RepartoChicas>(`${ROOT}/chicas`, fd);
    },
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
    { producto?: string; tipo: "chica" | "producto" }
  >({
    mutationFn: (body) =>
      api.post<Quemado>(`${ROOT}/quemar`, { source, folder: folder ?? "", ...body }),
    onSuccess: (res) => guardar(res.estado),
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

export function useReferencias() {
  return useQuery<Referencias>({
    queryKey: carruselesKeys.referencias(),
    queryFn: async () =>
      (await api.get<{ items: Referencias }>(`${ROOT}/referencias`)).items,
  });
}

export function useSubirReferencia() {
  const qc = useQueryClient();
  return useMutation<
    { items: Referencias },
    Error,
    { tipo: "chica" | "producto"; file: File }
  >({
    mutationFn: ({ tipo, file }) => {
      const fd = new FormData();
      fd.append("tipo", tipo);
      fd.append("archivo", file);
      return api.post<{ items: Referencias }>(`${ROOT}/referencia`, fd);
    },
    onSuccess: (res) => qc.setQueryData(carruselesKeys.referencias(), res.items),
  });
}

/** Quita la propia y vuelve a la del curso. */
export function useBorrarReferencia() {
  const qc = useQueryClient();
  return useMutation<{ items: Referencias }, Error, "chica" | "producto">({
    mutationFn: (tipo) =>
      api.del<{ items: Referencias }>(`${ROOT}/referencia?tipo=${tipo}`),
    onSuccess: (res) => qc.setQueryData(carruselesKeys.referencias(), res.items),
  });
}

export function buildReferenciaUrl(
  tipo: "chica" | "producto",
  version: string,
  descargar = false,
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const dl = descargar ? "&descargar=1" : "";
  return `${base}${ROOT}/referencia?tipo=${tipo}&v=${encodeURIComponent(version)}${dl}${qs}`;
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
): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `&api_key=${encodeURIComponent(key)}` : "";
  const dl = descargar ? "&descargar=1" : "";
  return `${base}${ROOT}/foto?source=${encodeURIComponent(source)}&folder=${encodeURIComponent(
    folder,
  )}&producto=${encodeURIComponent(producto)}&tipo=${tipo}&v=${encodeURIComponent(
    version,
  )}${dl}${qs}`;
}
