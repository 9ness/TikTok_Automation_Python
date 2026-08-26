"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  ProductoPiloto,
  ProductoPilotoResponse,
  ProductosPilotoResponse,
} from "@/lib/types/cuentaPiloto";

const ROOT = "/api/v1/cuenta-piloto";

export const pilotoKeys = {
  all: ["cuenta-piloto"] as const,
  productos: () => [...pilotoKeys.all, "productos"] as const,
  promptLive: () => [...pilotoKeys.all, "prompt-live"] as const,
};

/** El prompt del LIVE, para copiarlo y pegarlo en el chat de IA. */
export function usePromptLive() {
  return useQuery<{ prompt: string }>({
    queryKey: pilotoKeys.promptLive(),
    queryFn: () => api.get<{ prompt: string }>(`${ROOT}/prompt-live`),
    // No cambia salvo que el curso publique otro documento.
    staleTime: Infinity,
  });
}

export function useProductosPiloto() {
  return useQuery<ProductoPiloto[]>({
    queryKey: pilotoKeys.productos(),
    queryFn: async () =>
      (await api.get<ProductosPilotoResponse>(`${ROOT}/productos`)).items ?? [],
    // Mientras haya un montaje en curso se refresca solo, para que el vídeo
    // nuevo aparezca en la lista sin recargar la página.
    // También mientras quede una tanda a medias: si los nueve montajes están
    // en cola sin arrancar todavía, `montando` puede ser falso y el contador
    // se quedaría congelado en 0/9.
    refetchInterval: (q) =>
      (q.state.data ?? []).some(
        (p) => p.montando || (p.lote_total > 1 && p.lote_listos < p.lote_total),
      )
        ? 5000
        : false,
  });
}

/** Alta subiendo las dos fotos. La de la ficha es opcional. */
export function useCrearProductoPiloto() {
  const qc = useQueryClient();
  return useMutation<
    ProductoPiloto,
    Error,
    { fotoLimpia: File; fotoFicha?: File | null }
  >({
    mutationFn: async ({ fotoLimpia, fotoFicha }) => {
      const fd = new FormData();
      fd.append("foto_limpia", fotoLimpia);
      if (fotoFicha) fd.append("foto_ficha", fotoFicha);
      return (await api.post<ProductoPilotoResponse>(`${ROOT}/productos`, fd)).producto;
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: pilotoKeys.productos() }),
  });
}

/** Relee las fichas con Gemini. Sin `producto`, todas las que falten. */
export function useExtraerTextosPiloto() {
  const qc = useQueryClient();
  return useMutation<ProductoPiloto[], Error, string | undefined>({
    mutationFn: async (producto) => {
      const qs = producto ? `?producto=${encodeURIComponent(producto)}` : "";
      const r = await api.post<ProductosPilotoResponse>(
        `${ROOT}/extraer-textos${qs}`,
        {},
      );
      return r.items ?? [];
    },
    onSuccess: (items) => qc.setQueryData(pilotoKeys.productos(), items),
  });
}

export function useEditarTextosPiloto() {
  const qc = useQueryClient();
  return useMutation<
    ProductoPiloto,
    Error,
    { producto: string; titulo?: string; tienda?: string; caption?: string }
  >({
    mutationFn: async (body) =>
      (await api.patch<ProductoPilotoResponse>(`${ROOT}/producto`, body)).producto,
    onSuccess: () => void qc.invalidateQueries({ queryKey: pilotoKeys.productos() }),
  });
}

export function useBorrarProductoPiloto() {
  const qc = useQueryClient();
  return useMutation<ProductoPiloto[], Error, string>({
    mutationFn: async (producto) =>
      (
        await api.del<ProductosPilotoResponse>(
          `${ROOT}/producto?producto=${encodeURIComponent(producto)}`,
        )
      ).items ?? [],
    onSuccess: (items) => qc.setQueryData(pilotoKeys.productos(), items),
  });
}

/** Mete o saca el producto del escaparate. El estado es ÚNICO por producto
 *  (tienda|nombre) y compartido con los demás nichos: si el mismo producto ya
 *  se metió desde el POV BOF, aquí ya sale hecho. */
export function useSetEstadoPiloto() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { producto: string; en_escaparate: boolean }
  >({
    mutationFn: (body) => api.post(`${ROOT}/producto/estado`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pilotoKeys.productos() }),
  });
}

/** Sube un vídeo orgánico. Se puede repetir: cada montaje se AÑADE. */
export function useSubirVideoPiloto() {
  const qc = useQueryClient();
  return useMutation<
    { job_id: string; message: string },
    Error,
    {
      producto: string;
      file: File;
      sexo: string;
      conGancho: boolean;
      conTitulo: boolean;
      conCta: boolean;
      conFlecha: boolean;
      /** Tamaño de la tanda. Solo lo manda el primero de la serie. */
      lote?: number;
      /** Con qué guion se locuta: el de siempre o el de plazos. */
      tipoGuion?: string;
    }
  >({
    mutationFn: async (v) => {
      const fd = new FormData();
      fd.append("file", v.file);
      fd.append("producto", v.producto);
      fd.append("sexo", v.sexo);
      fd.append("con_gancho", String(v.conGancho));
      fd.append("con_titulo", String(v.conTitulo));
      fd.append("con_cta", String(v.conCta));
      fd.append("con_flecha", String(v.conFlecha));
      if (v.lote && v.lote > 1) fd.append("lote", String(v.lote));
      if (v.tipoGuion) fd.append("tipo_guion", v.tipoGuion);
      return api.post<{ job_id: string; message: string }>(`${ROOT}/video/upload`, fd);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: pilotoKeys.productos() }),
  });
}

// --- URLs directas ----------------------------------------------------------

function base(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

function keyQs(): string {
  const k = process.env.NEXT_PUBLIC_API_KEY;
  return k ? `&api_key=${encodeURIComponent(k)}` : "";
}

export function fotoPilotoUrl(
  producto: string, cual: "limpia" | "ficha" = "limpia", descargar = false,
): string {
  return `${base()}${ROOT}/foto?producto=${encodeURIComponent(
    producto,
  )}&cual=${cual}&descargar=${descargar}${keyQs()}`;
}

export function videoPilotoUrl(
  producto: string, n: number, descargar = false,
): string {
  return `${base()}${ROOT}/video?producto=${encodeURIComponent(
    producto,
  )}&n=${n}&descargar=${descargar}${keyQs()}`;
}

// --- Mis audios -------------------------------------------------------------

export interface GuionAudio {
  tipo: "normal" | "plazos";
  n: number;
  texto: string;
  grabado: boolean;
  grabado_at: number;
  segundos: number;
}

const audiosKey = (sexo: string) => [...pilotoKeys.all, "audios", sexo] as const;

/** Los diez guiones a grabar con el texto para leer y cuáles ya están. */
export function useAudiosPiloto(sexo: string) {
  return useQuery<GuionAudio[]>({
    queryKey: audiosKey(sexo),
    queryFn: async () =>
      (await api.get<{ items: GuionAudio[] }>(`${ROOT}/audios?sexo=${sexo}`)).items ?? [],
  });
}

/** Guarda la grabación de un guion. Sirve tanto para lo grabado en la propia
 *  pantalla como para un fichero de la grabadora del móvil. */
export function useSubirAudioPiloto() {
  const qc = useQueryClient();
  return useMutation<
    { items: GuionAudio[] },
    Error,
    { sexo: string; tipo: string; n: number; blob: Blob; nombre?: string }
  >({
    mutationFn: (v) => {
      const fd = new FormData();
      fd.append("file", v.blob, v.nombre ?? `${v.tipo}${v.n}.webm`);
      fd.append("sexo", v.sexo);
      fd.append("tipo", v.tipo);
      fd.append("n", String(v.n));
      return api.post<{ items: GuionAudio[] }>(`${ROOT}/audios`, fd);
    },
    onSuccess: (r, v) => qc.setQueryData(audiosKey(v.sexo), r.items),
  });
}

export function useBorrarAudioPiloto() {
  const qc = useQueryClient();
  return useMutation<
    { items: GuionAudio[] },
    Error,
    { sexo: string; tipo: string; n: number }
  >({
    mutationFn: (v) =>
      api.del<{ items: GuionAudio[] }>(
        `${ROOT}/audios?sexo=${v.sexo}&tipo=${v.tipo}&n=${v.n}`,
      ),
    onSuccess: (r, v) => qc.setQueryData(audiosKey(v.sexo), r.items),
  });
}

/** URL para escuchar lo grabado. Lleva `t` para saltarse la caché al regrabar:
 *  el fichero se llama igual y si no sonaría el anterior. */
export function audioPilotoUrl(
  sexo: string, tipo: string, n: number, version = 0,
): string {
  const k = process.env.NEXT_PUBLIC_API_KEY ?? "";
  return `${base()}/api/v1/cuenta-piloto/audios/file?sexo=${sexo}&tipo=${tipo}&n=${n}&t=${version}${
    k ? `&api_key=${encodeURIComponent(k)}` : ""
  }`;
}
