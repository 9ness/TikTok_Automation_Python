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
};

export function useProductosPiloto() {
  return useQuery<ProductoPiloto[]>({
    queryKey: pilotoKeys.productos(),
    queryFn: async () =>
      (await api.get<ProductosPilotoResponse>(`${ROOT}/productos`)).items ?? [],
    // Mientras haya un montaje en curso se refresca solo, para que el vídeo
    // nuevo aparezca en la lista sin recargar la página.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((p) => p.montando) ? 5000 : false,
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
