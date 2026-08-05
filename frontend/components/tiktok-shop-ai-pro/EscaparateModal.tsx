"use client";

import { Check, ClipboardCopy, Loader2, Store, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  buildCleanPhotoDownloadUrl,
  buildPhotoUrl,
  useSetEstado,
} from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";
import { FotoModal } from "./FotoModal";

/** Checklist para meter los productos de la carpeta en el escaparate.
 *
 *  Es el paso que MÁS tiempo se lleva del día. No se puede automatizar: la
 *  única API que da la ficha del producto (EchoTik) acierta 1 de cada 4 y
 *  regala 100 llamadas al mes, cuando a 70 productos diarios harían falta
 *  4.200. Así que se optimiza el trabajo a mano, no la búsqueda.
 *
 *  Dos decisiones que son el motivo de que esto exista:
 *
 *  1. **Agrupado por TIENDA.** En el Marketplace se busca una vez el nombre
 *     de la tienda y salen todos sus productos juntos, listos para añadir de
 *     una pasada. Diez productos de cuatro tiendas son cuatro búsquedas, no
 *     diez. Las tiendas con más productos van primero, que es donde más se
 *     ahorra.
 *  2. **Los ya añadidos desaparecen de la lista.** Con 70 productos al día lo
 *     que de verdad cuesta es perder el sitio y repasar lo ya hecho. Se
 *     pueden volver a ver para corregir un error, pero estorbando lo mínimo.
 */
export function EscaparateModal({
  source,
  folder,
  productos,
  onClose,
}: {
  source: string;
  folder: string;
  productos: ProductoItem[];
  onClose: () => void;
}) {
  const setEstado = useSetEstado();
  const [verHechos, setVerHechos] = useState(false);
  // Cuál se está guardando: sin esto, con la lista entera deshabilitada por
  // `isPending` no se sabe a qué producto le diste.
  const [guardando, setGuardando] = useState<string | null>(null);
  // Producto cuya foto se está mirando en grande. Hace falta porque dos
  // productos de la misma tienda pueden ser casi idénticos (dos colchones,
  // la misma plataforma vibratoria dos veces) y con la miniatura de 44px no
  // hay quien los distinga: la ficha grande es lo que evita meter el que no
  // era en el escaparate.
  const [fotoDe, setFotoDe] = useState<ProductoItem | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hechos = productos.filter((p) => p.en_escaparate);
  const visibles = verHechos ? productos : productos.filter((p) => !p.en_escaparate);

  /** Productos por tienda, las tiendas con más productos delante. */
  const grupos = useMemo(() => {
    const mapa = new Map<string, ProductoItem[]>();
    for (const p of visibles) {
      // Sin título de TikTok no hay nada que buscar en el Marketplace: se
      // separan para que se vea que les falta pasar "Textos" antes.
      const clave = p.titulo_tiktok_completo
        ? (p.tienda || "").trim() || "Sin tienda"
        : "__sin_textos__";
      const lista = mapa.get(clave);
      if (lista) lista.push(p);
      else mapa.set(clave, [p]);
    }
    return [...mapa.entries()].sort((a, b) => {
      // El grupo sin textos siempre al final: ahí no se puede trabajar.
      if (a[0] === "__sin_textos__") return 1;
      if (b[0] === "__sin_textos__") return -1;
      return b[1].length - a[1].length;
    });
  }, [visibles]);

  function copiar(label: string, texto: string) {
    navigator.clipboard.writeText(texto);
    toast.success(`${label} copiado`);
  }

  function marcar(p: ProductoItem, valor: boolean) {
    setGuardando(p.producto);
    setEstado.mutate(
      { source, folder, producto: p.producto, en_escaparate: valor },
      {
        onSettled: () => setGuardando(null),
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <button
        type="button"
        aria-label="Cerrar"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <div className="relative flex max-h-[85vh] w-full flex-col rounded-t-2xl border border-border/60 bg-card shadow-xl sm:max-h-[80vh] sm:w-[min(32rem,calc(100vw-2rem))] sm:rounded-2xl">
        <div className="flex items-center gap-2 border-b border-border/60 p-3">
          <Store className="h-4 w-4 shrink-0 text-sky-500" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Meter en el escaparate</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {hechos.length}/{productos.length} hechos · {folder}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-md p-1 text-muted-foreground transition hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {grupos.length === 0 && (
            <p className="py-6 text-center text-xs text-muted-foreground">
              Todos metidos en el escaparate. 🎉
            </p>
          )}

          {grupos.map(([tienda, items]) => {
            const sinTextos = tienda === "__sin_textos__";
            return (
              <div key={tienda} className="space-y-1.5">
                {/* Cabecera de tienda: se busca UNA vez en el Marketplace y
                    salen todos sus productos de golpe. */}
                <div className="flex items-center gap-1.5">
                  {sinTextos ? (
                    <p className="min-w-0 flex-1 truncate text-[11px] font-semibold text-amber-500">
                      Sin título todavía — pasa “Textos” antes
                    </p>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => copiar("Tienda", tienda)}
                        className="flex min-w-0 flex-1 items-center gap-1 rounded-md bg-sky-500/10 px-2 py-1 text-left text-[11px] font-semibold text-sky-500 transition hover:bg-sky-500/20"
                        title="Copiar el nombre de la tienda para buscarla en el Marketplace"
                      >
                        <Store className="h-3 w-3 shrink-0" />
                        <span className="truncate">{tienda}</span>
                        <ClipboardCopy className="h-3 w-3 shrink-0 opacity-60" />
                      </button>
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        {items.length}
                      </span>
                    </>
                  )}
                </div>

                {items.map((p) => (
                  <div
                    key={p.producto}
                    className={`flex items-center gap-2 rounded-lg border p-2 transition ${
                      p.en_escaparate
                        ? "border-emerald-500/40 bg-emerald-500/5 opacity-60"
                        : "border-border/60"
                    }`}
                  >
                    {p.clean_photo_id ? (
                      <button
                        type="button"
                        onClick={() => setFotoDe(p)}
                        title="Ver la foto del producto y la de la ficha"
                        className="shrink-0 rounded-md transition hover:ring-2 hover:ring-sky-500"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={buildPhotoUrl(source, folder, p.clean_photo_id)}
                          alt={p.titulo || p.producto}
                          loading="lazy"
                          className="h-11 w-11 rounded-md object-cover"
                        />
                      </button>
                    ) : (
                      <div className="h-11 w-11 shrink-0 rounded-md bg-muted" />
                    )}

                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-[11px] font-medium leading-snug">
                        {p.titulo || `Producto ${p.producto}`}
                      </p>
                      {!sinTextos && (
                        <button
                          type="button"
                          onClick={() =>
                            copiar("Título", p.titulo_tiktok_completo || "")
                          }
                          className="mt-0.5 flex max-w-full items-center gap-1 text-[10px] text-muted-foreground transition hover:text-foreground"
                        >
                          <ClipboardCopy className="h-3 w-3 shrink-0" />
                          <span className="truncate">Copiar título exacto</span>
                        </button>
                      )}
                    </div>

                    <button
                      type="button"
                      disabled={guardando === p.producto}
                      onClick={() => marcar(p, !p.en_escaparate)}
                      aria-label={
                        p.en_escaparate ? "Quitar del escaparate" : "Marcar como añadido"
                      }
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition disabled:opacity-50 ${
                        p.en_escaparate
                          ? "bg-emerald-500 text-white"
                          : "border border-border/60 text-muted-foreground hover:border-emerald-500 hover:text-emerald-500"
                      }`}
                    >
                      {guardando === p.producto ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {fotoDe && (
          <FotoModal
            open
            onOpenChange={(v) => !v && setFotoDe(null)}
            titulo={fotoDe.titulo || `Producto ${fotoDe.producto}`}
            urlLimpia={
              fotoDe.clean_photo_id
                ? buildPhotoUrl(source, folder, fotoDe.clean_photo_id)
                : null
            }
            urlTitulo={
              fotoDe.titled_photo_id
                ? buildPhotoUrl(source, folder, fotoDe.titled_photo_id)
                : null
            }
            urlDescarga={buildCleanPhotoDownloadUrl(source, folder, fotoDe.producto)}
          />
        )}

        {hechos.length > 0 && (
          <button
            type="button"
            onClick={() => setVerHechos((v) => !v)}
            className="border-t border-border/60 p-2.5 text-[11px] text-muted-foreground transition hover:text-foreground"
          >
            {verHechos
              ? "Ocultar los ya añadidos"
              : `Ver los ${hechos.length} ya añadidos`}
          </button>
        )}
      </div>
    </div>
  );
}
