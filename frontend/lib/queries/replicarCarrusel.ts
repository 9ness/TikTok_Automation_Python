"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

/** «Replicar carrusel» (`src/replicar_viral/carrusel.py`): un carrusel viral
 *  de TikTok + un producto del POV BOF → texto y prompt de Flow por
 *  diapositiva; las fotos se suben y la app les quema el texto. */

const ROOT = "/api/v1/replicar-viral";

export type RolDiapositiva = "gancho" | "problema" | "producto" | "prueba" | "cta";

export interface Diapositiva {
  n: number;
  rol: RolDiapositiva;
  texto_original: string;
  sale_producto: boolean;
  ambiente: string;
  texto: string;
  usa_foto_producto: boolean;
  prompt_imagen: string;
  tiene_original: boolean;
  tiene_imagen: boolean;
  tiene_texto: boolean;
  /** Tiene foto y, si lleva texto, ya quemado. */
  lista: boolean;
  /** mtime de la foto final, para romper la caché del <img>. */
  version: number;
}

/** La música del carrusel (`src/replicar_viral/musica.py`): la del viral,
 *  para ponerla a mano en TikTok, y una Mixkit sin copyright para Meta. */
export interface MusicaCarrusel {
  tiktok?: { titulo: string; autor: string; original: boolean; id: string; enlace: string };
  meta?: { estilo: string; pista?: string; autor?: string; fichero?: string; url?: string };
}

export interface CarruselReplica {
  id: string;
  tipo: "carrusel";
  creado_at: number;
  url: string;
  referencia: { titulo: string; autor: string; vistas: number; diapositivas: number; recortado: boolean };
  producto: { source: string; folder: string; producto: string; titulo: string; tienda: string; product_url?: string };
  formato: "3:4" | "9:16";
  original: { tema?: string; por_que_funciona?: string };
  apto: boolean;
  motivo_no_apto: string;
  diapositivas: Diapositiva[];
  caption: string;
  hashtags: string[];
  hechas: number;
  total: number;
  completo: boolean;
  usuario?: string;
  subido?: boolean;
  /** id de la réplica de la que se copió (replicar para otro usuario). */
  replica_de?: string;
  musica?: MusicaCarrusel;
}

export interface CarruselResumen {
  id: string;
  tipo: "carrusel";
  creado_at: number;
  url: string;
  referencia: CarruselReplica["referencia"];
  producto: CarruselReplica["producto"];
  apto: boolean;
  idea: string;
  diapositivas: number;
  /** Diapositivas con su foto de Flow ya subida. */
  hechas: number;
  subido?: boolean;
  replica_de?: string;
}

/** Producto del catálogo compartido «🖼️ Carruseles virales». */
export interface ProductoCarrusel {
  source: string;
  folder: string;
  producto: string;
  titulo: string;
  tienda: string;
  precio: string;
  product_url: string;
  /** El carrusel viral con el que se dio de alta o se replicó por última vez. */
  carrusel_url: string;
  creado_por: string;
  aviso?: string;
}

export const replicarCarruselKeys = {
  all: ["replicar-carrusel"] as const,
  lista: () => [...replicarCarruselKeys.all, "lista"] as const,
  uno: (id: string) => [...replicarCarruselKeys.all, "uno", id] as const,
  catalogo: () => [...replicarCarruselKeys.all, "catalogo"] as const,
};

/** URL de una foto (o del ZIP): va en <img src> / <a href>, así que lleva la
 *  API key en la query como `buildPhotoUrl` (la cookie dice quién es). */
function conClave(ruta: string): string {
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const sep = ruta.includes("?") ? "&" : "?";
  return `${api.baseUrl}${ruta}${key ? `${sep}api_key=${encodeURIComponent(key)}` : ""}`;
}

export function urlFotoCarrusel(
  id: string, n: number, tipo: "orig" | "final" = "final", version = 0, descargar = false,
): string {
  return conClave(
    `${ROOT}/carrusel/${id}/imagen/${n}?tipo=${tipo}&v=${version}` + (descargar ? "&descargar=true" : ""),
  );
}

export { conClave };

/** Baja las fotos listas de un carrusel UNA A UNA y en orden (sin ZIP), para
 *  tenerlas ya en la galería en el orden de publicación. Va por la URL con
 *  `descargar=true` (no por blob), que es lo que sabe bajar la APK. Pausa
 *  entre una y otra: el navegador bloquea o desordena descargas seguidas.
 *  Devuelve cuántas bajó. */
export async function descargarFotosCarrusel(id: string): Promise<number> {
  const doc = await api.get<CarruselReplica>(`${ROOT}/carrusel/${id}`);
  const listas = doc.diapositivas.filter((d) => d.tiene_imagen).sort((a, b) => a.n - b.n);
  for (const [i, d] of listas.entries()) {
    if (i) await new Promise((r) => setTimeout(r, 1200));
    const a = document.createElement("a");
    a.href = urlFotoCarrusel(id, d.n, "final", d.version, true);
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  return listas.length;
}

export function urlZipCarrusel(id: string): string {
  return conClave(`${ROOT}/carrusel/${id}/zip`);
}

export function useCarruseles() {
  return useQuery<{ items: CarruselResumen[] }>({
    queryKey: replicarCarruselKeys.lista(),
    queryFn: () => api.get<{ items: CarruselResumen[] }>(`${ROOT}?tipo=carrusel`),
    staleTime: 30_000,
  });
}

export function useCarrusel(id: string | null) {
  return useQuery<CarruselReplica>({
    queryKey: replicarCarruselKeys.uno(id ?? ""),
    queryFn: () => api.get<CarruselReplica>(`${ROOT}/carrusel/${id}`),
    enabled: Boolean(id),
  });
}

export function useReplicarCarrusel() {
  const qc = useQueryClient();
  return useMutation<CarruselReplica, Error, { source: string; folder: string; producto: string; url: string; para?: string }>({
    mutationFn: (v) => {
      const fd = new FormData();
      fd.append("source", v.source);
      fd.append("folder", v.folder);
      fd.append("producto", v.producto);
      fd.append("url", v.url);
      if (v.para) fd.append("para", v.para);
      return api.post<CarruselReplica>(`${ROOT}/carrusel/analizar`, fd);
    },
    onSuccess: (doc) => {
      qc.setQueryData(replicarCarruselKeys.uno(doc.id), doc);
      qc.invalidateQueries({ queryKey: replicarCarruselKeys.lista() });
    },
  });
}

export function useSubirFotoCarrusel(id: string) {
  const qc = useQueryClient();
  return useMutation<CarruselReplica, Error, { n: number; file: File }>({
    mutationFn: ({ n, file }) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post<CarruselReplica>(`${ROOT}/carrusel/${id}/imagen/${n}`, fd);
    },
    onSuccess: (doc) => qc.setQueryData(replicarCarruselKeys.uno(id), doc),
  });
}

export function useTextoCarrusel(id: string) {
  const qc = useQueryClient();
  return useMutation<CarruselReplica, Error, { n: number; texto: string }>({
    mutationFn: ({ n, texto }) => api.post<CarruselReplica>(`${ROOT}/carrusel/${id}/texto/${n}`, { texto }),
    onSuccess: (doc) => qc.setQueryData(replicarCarruselKeys.uno(id), doc),
  });
}

export function useCatalogoCarrusel() {
  return useQuery<{ source: string; items: ProductoCarrusel[] }>({
    queryKey: replicarCarruselKeys.catalogo(),
    queryFn: () => api.get<{ source: string; items: ProductoCarrusel[] }>(`${ROOT}/carrusel/catalogo`),
    staleTime: 30_000,
  });
}

/** Alta en «Carruseles virales»: fotos + URL; la app lee los textos de la ficha. */
export function useCrearProductoCarrusel() {
  const qc = useQueryClient();
  return useMutation<
    ProductoCarrusel, Error,
    { limpia: File; ficha: File; product_url: string; carrusel_url?: string }
  >({
    mutationFn: (v) => {
      const fd = new FormData();
      fd.append("foto_limpia", v.limpia);
      fd.append("foto_ficha", v.ficha);
      fd.append("product_url", v.product_url);
      if (v.carrusel_url) fd.append("carrusel_url", v.carrusel_url);
      return api.post<ProductoCarrusel>(`${ROOT}/carrusel/producto`, fd);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: replicarCarruselKeys.catalogo() }),
  });
}

export function useReleerTextosCarrusel() {
  const qc = useQueryClient();
  return useMutation<ProductoCarrusel, Error, { folder: string; producto: string }>({
    mutationFn: (v) => api.post<ProductoCarrusel>(`${ROOT}/carrusel/producto/textos`, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: replicarCarruselKeys.catalogo() }),
  });
}

/** Vuelve a replicar el mismo carrusel viral + producto (para otro usuario si eres admin). */
export function useReplicarOtraVez() {
  const qc = useQueryClient();
  return useMutation<CarruselReplica, Error, { id: string; para?: string }>({
    mutationFn: ({ id, para }) => api.post<CarruselReplica>(`${ROOT}/carrusel/${id}/replicar`, { para: para ?? "" }),
    onSuccess: (doc) => {
      qc.setQueryData(replicarCarruselKeys.uno(doc.id), doc);
      qc.invalidateQueries({ queryKey: replicarCarruselKeys.lista() });
    },
  });
}
