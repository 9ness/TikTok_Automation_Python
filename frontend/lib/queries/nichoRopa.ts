"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  CarpetasRopaResponse,
  PrendaItem,
  PrendasListResponse,
  PromptsRopaResponse,
  VideoRopaUploadResponse,
} from "@/lib/types/nichoRopa";

const ROOT = "/api/v1/nicho-ropa";

export const nichoRopaKeys = {
  all: ["nicho-ropa"] as const,
  carpetas: () => [...nichoRopaKeys.all, "carpetas"] as const,
  prendas: (carpeta: string) => [...nichoRopaKeys.all, "prendas", carpeta] as const,
  prompts: (carpeta: string) => [...nichoRopaKeys.all, "prompts", carpeta] as const,
};

/** Los prompts a copiar. La carpeta solo cambia el del espejo: es el único
 *  que lleva a una persona dentro, y en las de hombre debe ser un hombre.
 *
 *  Los prompts SÍ cambian (se afinan cada pocas semanas), así que no se
 *  cachean para siempre: con `Infinity` el móvil se quedaba con el viejo
 *  aunque estuviera desplegado el nuevo (ver `usePrompts` del POV BOF). */
export function usePromptsRopa(carpeta: string, plazos = false) {
  return useQuery<PromptsRopaResponse>({
    queryKey: [...nichoRopaKeys.prompts(carpeta), plazos],
    queryFn: () =>
      api.get<PromptsRopaResponse>(
        `${ROOT}/prompts?carpeta=${encodeURIComponent(carpeta)}` +
          (plazos ? "&plazos=1" : ""),
      ),
    staleTime: 60_000,
  });
}

/** Carpetas de producto. Las de mujer son las del nicho CON personas, pero la
 *  misma prenda vale aquí colgada en percha. */
/** Importa un ZIP de prendas de la web del curso (mujer u hombre). */
/** Alta de una prenda PROPIA en uno de los cuatro catálogos del operador
 *  (mujer/hombre × muestras/tareas). Mismo convenio de nombres que el resto
 *  del proyecto, así que a partir de ahí es una prenda más. */
export function useCrearMiPrenda() {
  const qc = useQueryClient();
  return useMutation<
    { slug: string; carpeta: string; prenda: string },
    Error,
    { genero: string; fotoLimpia: File; fotoFicha?: File | null }
  >({
    mutationFn: async ({ genero, fotoLimpia, fotoFicha }) => {
      const fd = new FormData();
      fd.append("foto_limpia", fotoLimpia);
      if (fotoFicha) fd.append("foto_ficha", fotoFicha);
      return api.post(`${ROOT}/mis-prendas?genero=${encodeURIComponent(genero)}`, fd);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoRopaKeys.all }),
  });
}

export function useImportarPrendasWeb() {
  const qc = useQueryClient();
  return useMutation<
    {
      carpeta: string;
      genero: string;
      slug: string;
      nuevos: string[];
      actualizados: string[];
      iguales: string[];
      incompletos: string[];
    },
    Error,
    { archivo: File; genero: string }
  >({
    mutationFn: async ({ archivo, genero }) => {
      const fd = new FormData();
      fd.append("archivo", archivo);
      return api.post(
        `${ROOT}/prendas-web/importar?genero=${encodeURIComponent(genero)}`,
        fd,
      );
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoRopaKeys.all }),
  });
}

/** Guardar de golpe las fichas copiadas del DOM de la web del curso. */
export function useImportarUrlsRopa() {
  const qc = useQueryClient();
  return useMutation<
    {
      carpetas: number;
      guardados: number;
      agotados: number;
      en_indice: number;
      sin_carpeta: string[];
      descartadas: string[];
    },
    Error,
    { genero: string; filas: unknown[] }
  >({
    mutationFn: (body) => api.post(`${ROOT}/urls/importar`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: nichoRopaKeys.all }),
  });
}

export function useCarpetasRopa() {
  return useQuery<CarpetasRopaResponse>({
    queryKey: nichoRopaKeys.carpetas(),
    queryFn: () => api.get<CarpetasRopaResponse>(`${ROOT}/carpetas`),
    staleTime: Infinity,
  });
}

/** Mientras haya un montaje en curso se sondea solo, y para al terminar. */
export function usePrendas(carpeta: string, modo = "espejo") {
  return useQuery<PrendasListResponse>({
    queryKey: [...nichoRopaKeys.prendas(carpeta), modo],
    queryFn: () =>
      api.get<PrendasListResponse>(
        `${ROOT}/prendas?carpeta=${encodeURIComponent(carpeta)}` +
          `&modo=${encodeURIComponent(modo)}`,
      ),
    refetchInterval: (query) => (query.state.data?.montando ? 5000 : false),
    enabled: Boolean(carpeta),
  });
}

/** Tarda ~1 min: lee todas las capturas con Gemini en una sola llamada. */
export function useExtraerTextosRopa() {
  const qc = useQueryClient();
  return useMutation<PrendasListResponse, Error, string>({
    mutationFn: (carpeta) =>
      api.post<PrendasListResponse>(
        `${ROOT}/extraer-textos?carpeta=${encodeURIComponent(carpeta)}`,
      ),
    onSuccess: (res, carpeta) =>
      qc.setQueryData(nichoRopaKeys.prendas(carpeta), res),
  });
}

export function useSubirVideoRopa() {
  const qc = useQueryClient();
  return useMutation<
    VideoRopaUploadResponse,
    Error,
    {
      producto: string;
      carpeta: string;
      file: File;
      sexo: string;
      /** "0" para silenciar un clip de la web; vacío = lo decide la carpeta. */
      conservar_audio?: string;
    }
  >({
    mutationFn: ({ producto, carpeta, file, sexo, conservar_audio }) => {
      const fd = new FormData();
      fd.append("producto", producto);
      fd.append("carpeta", carpeta);
      fd.append("sexo", sexo);
      if (conservar_audio) fd.append("conservar_audio", conservar_audio);
      fd.append("file", file);
      return api.post<VideoRopaUploadResponse>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: (_res, vars) => {
      void qc.invalidateQueries({ queryKey: nichoRopaKeys.prendas(vars.carpeta) });
    },
  });
}

/** Mete o saca la prenda del escaparate. El estado es ÚNICO por producto
 *  (tienda|nombre) y compartido con los demás nichos: si ya se metió desde el
 *  POV BOF o desde otra carpeta, aquí ya sale hecho. */
export function useSetEstadoRopa(carpeta: string) {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    // Solo se manda lo que cambia: el escaparate necesita textos y el flag de
    // plazos no, así que van por separado.
    {
      producto: string;
      en_escaparate?: boolean;
      plazos?: boolean;
      /** Devuelve el control a lo que diga la ficha. */
      plazos_auto?: boolean;
    }
  >({
    mutationFn: (body) => api.post(`${ROOT}/producto/estado`, { carpeta, ...body }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: nichoRopaKeys.prendas(carpeta) }),
  });
}

function conApiKey(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  return `${base}${path}${key ? `&api_key=${encodeURIComponent(key)}` : ""}`;
}

/** Un <img> no manda headers, así que la api_key va por query. */
export function buildFotoRopaUrl(fileId: string): string {
  return conApiKey(`${ROOT}/foto?file_id=${encodeURIComponent(fileId)}`);
}

export function buildFotoLimpiaRopaUrl(producto: string, carpeta: string): string {
  return conApiKey(
    `${ROOT}/foto-limpia?producto=${encodeURIComponent(producto)}` +
      `&carpeta=${encodeURIComponent(carpeta)}`,
  );
}

/** `v` es la marca de versión: sin ella el navegador reutiliza el vídeo viejo. */
export function buildVideoRopaUrl(
  producto: string, carpeta: string, v: number, descargar = false, modo = "espejo",
): string {
  return conApiKey(
    `${ROOT}/video?producto=${encodeURIComponent(producto)}` +
      `&carpeta=${encodeURIComponent(carpeta)}&v=${v}` +
      `&modo=${encodeURIComponent(modo)}` +
      (descargar ? "&descargar=true" : ""),
  );
}

export type { PrendaItem };
