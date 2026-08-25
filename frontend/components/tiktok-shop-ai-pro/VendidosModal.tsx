"use client";

import { Loader2, Search, ShoppingBag, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  buildPhotoUrl,
  useBuscarProductos,
  useSetEstado,
  useSumarUnidades,
  useVendidos,
  ANCHO_CHIP,
} from "@/lib/queries/nichoPovBof";
import type { ProductoBuscado } from "@/lib/types/nichoPovBof";
import { Portal } from "@/components/ui/portal";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

/** Ranking de lo que ya ha vendido. Es el dato más valioso del flujo — dice qué
 *  tipo de producto buscar — y por eso está en TODOS los nichos, no solo en el
 *  POV BOF: el índice de vendidos es ÚNICO y global (la cuenta de TikTok es la
 *  misma), así que se ve lo mismo desde cualquier pantalla.
 *
 *  Sale de su propio índice en Redis (dos llamadas), no de recorrer las 35
 *  carpetas: eso tardaba ocho segundos y encima venía sin fotos.
 *
 *  Lo importante es poder sumar unidades: un producto que REPITE venta vale
 *  mucho más que uno que vendió una vez.
 */
export function VendidosModal({
  source,
  onClose,
  conBuscador = true,
}: {
  /** Filtra el ranking a una fuente. Sin él salen TODOS, que es lo que quieren
   *  los nichos con catálogo propio (gorras, ropa, cuenta piloto). */
  source?: string;
  onClose: () => void;
  /** El buscador solo tiene sentido donde el catálogo es el del POV BOF: es
   *  ahí donde se busca el producto que vendió para marcarlo. */
  conBuscador?: boolean;
}) {
  const vendidos = useVendidos(source ?? "");
  const sumar = useSumarUnidades();
  const items = vendidos.data ?? [];
  const total = items.reduce((n, v) => n + (v.unidades || 1), 0);
  // El buscador vive AQUÍ y no en su propio botón porque se usa para una cosa:
  // llega el aviso de una venta con el nombre del producto y hay que dar con él
  // para marcarlo. Esta es la pantalla de las ventas.
  const [busca, setBusca] = useState("");
  const buscando = conBuscador && busca.trim().length >= 2;
  const resultados = useBuscarProductos(source ?? "", busca);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <Portal>
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <button
        type="button"
        aria-label="Cerrar"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <div className="relative flex max-h-[85vh] w-full flex-col rounded-t-2xl border border-border/60 bg-card shadow-xl sm:max-h-[80vh] sm:w-[min(32rem,calc(100vw-2rem))] sm:rounded-2xl">
        <div className="flex items-center gap-2 border-b border-border/60 p-3">
          <ShoppingBag className="h-4 w-4 shrink-0 text-amber-500" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">
              {buscando ? "Buscar producto" : "Productos que vendieron"}
            </p>
            <p className="text-[11px] text-muted-foreground">
              {buscando
                ? `${resultados.data?.total ?? 0} encontrado(s)`
                : `${items.length} producto(s) · ${total} unidad(es)`}
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

        {conBuscador && (
          <div className="border-b border-border/60 p-3 pb-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar por nombre, tienda o carpeta…"
                className="w-full rounded-lg border border-border/60 bg-background py-2 pl-8 pr-8 text-xs outline-none transition focus:border-sky-500"
              />
              {busca && (
                <button
                  type="button"
                  onClick={() => setBusca("")}
                  aria-label="Limpiar"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        )}

        {buscando ? (
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {resultados.isLoading && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando…
              </div>
            )}
            {/* El error se DICE. Antes salía el mismo "nada con X" tanto si no
                había resultados como si la petición se había caído (pasó: la
                API estaba ocupada subiendo una tanda y el buscador parecía
                roto). */}
            {resultados.isError && (
              <div className="space-y-1.5 rounded-lg border border-red-500/40 bg-red-500/10 p-2">
                <p className="text-[11px] text-red-400">
                  No se pudo buscar:{" "}
                  {resultados.error instanceof Error
                    ? resultados.error.message
                    : String(resultados.error)}
                </p>
                <button
                  type="button"
                  onClick={() => void resultados.refetch()}
                  className="rounded-md border border-red-500/40 px-2 py-1 text-[10px] font-semibold text-red-400 transition hover:bg-red-500/10"
                >
                  Reintentar
                </button>
              </div>
            )}
            {!resultados.isLoading && !resultados.isError && !resultados.data?.items.length && (
              <p className="py-6 text-center text-xs text-muted-foreground">
                Nada con “{busca}”. Prueba con una palabra del título o con la tienda.
              </p>
            )}
            {(resultados.data?.items ?? []).map((r) => (
              <ResultadoBusqueda key={`${r.source}-${r.folder}-${r.producto}`} item={r} />
            ))}
            {/* Sin esto, veinte resultados parecen TODOS los que hay. */}
            {(resultados.data?.total ?? 0) > (resultados.data?.items.length ?? 0) && (
              <p className="pt-1 text-center text-[10px] text-muted-foreground">
                Se enseñan {resultados.data?.items.length} de {resultados.data?.total}. Afina
                la búsqueda para ver el resto.
              </p>
            )}
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {vendidos.isLoading && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
              </div>
            )}
            {!vendidos.isLoading && items.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Todavía ninguno. Marca “Vendió” en la ficha de un producto y aparecerá aquí.
              </p>
            )}

            {items.map((v, i) => (
              <div
                key={`${v.folder}-${v.producto}`}
                className="flex items-center gap-2.5 rounded-lg border border-border/60 p-2"
              >
                {/* La posición ordena el ranking de un vistazo. */}
                <span className="w-4 shrink-0 text-center text-xs font-bold text-muted-foreground">
                  {i + 1}
                </span>
                {v.clean_photo_id ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={buildPhotoUrl(v.source, v.folder, v.clean_photo_id, ANCHO_CHIP)}
                    alt={v.titulo || v.producto}
                    loading="lazy"
                    className="h-12 w-12 shrink-0 rounded-md object-cover"
                  />
                ) : (
                  <div className="h-12 w-12 shrink-0 rounded-md bg-muted" />
                )}

                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-[11px] font-medium leading-snug">
                    {v.titulo || `Producto ${v.producto}`}
                  </p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {v.folder} · {v.tienda || "sin tienda"}
                  </p>
                </div>

                {/* Sumar unidades: un producto que repite es la mejor señal que
                    hay aquí de qué buscar. */}
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    disabled={sumar.isPending || (v.unidades || 1) <= 1}
                    onClick={() =>
                      sumar.mutate({
                        source: v.source, folder: v.folder,
                        producto: v.producto, delta: -1,
                      })
                    }
                    aria-label="Quitar una unidad"
                    className="h-7 w-7 rounded-md border border-border/60 text-sm text-muted-foreground transition hover:text-foreground disabled:opacity-30"
                  >
                    −
                  </button>
                  <span className="w-8 text-center text-sm font-bold tabular-nums text-amber-500">
                    {v.unidades || 1}
                  </span>
                  <button
                    type="button"
                    disabled={sumar.isPending}
                    onClick={() =>
                      sumar.mutate(
                        {
                          source: v.source, folder: v.folder,
                          producto: v.producto, delta: 1,
                        },
                        {
                          onSuccess: () => toast.success("Una venta más anotada"),
                          onError: (e) => toast.error(err(e)),
                        },
                      )
                    }
                    aria-label="Sumar una unidad"
                    className="h-7 w-7 rounded-md bg-amber-500 text-sm font-bold text-white transition hover:bg-amber-600 disabled:opacity-50"
                  >
                    +
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
    </Portal>
  );
}

/** Una fila del buscador: enseña de qué carpeta es y deja marcar la venta sin
 *  salir de aquí — que es justo para lo que se busca. Escribe en la carpeta de
 *  ESE producto, no en la que esté abierta en la página. */
function ResultadoBusqueda({ item }: { item: ProductoBuscado }) {
  const setEstado = useSetEstado();
  const [vendido, setVendido] = useState(item.sold);

  useEffect(() => setVendido(item.sold), [item.sold]);

  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-border/60 p-2">
      {item.clean_photo_id ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={buildPhotoUrl(item.source, item.folder, item.clean_photo_id, ANCHO_CHIP)}
          alt={item.titulo || item.producto}
          loading="lazy"
          className="h-12 w-12 shrink-0 rounded-md object-cover"
        />
      ) : (
        <div className="h-12 w-12 shrink-0 rounded-md bg-muted" />
      )}

      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-[11px] font-medium leading-snug">
          {item.titulo || `Producto ${item.producto}`}
        </p>
        {/* De qué carpeta es: es lo que no recuerdas cuando llega la venta. */}
        <p className="truncate text-[10px] text-muted-foreground">
          {item.folder} · nº {item.producto}
          {item.tienda ? ` · ${item.tienda}` : ""}
        </p>
      </div>

      <button
        type="button"
        disabled={setEstado.isPending}
        onClick={() => {
          const v = !vendido;
          setVendido(v);
          setEstado.mutate(
            {
              source: item.source, folder: item.folder,
              producto: item.producto, sold: v,
            },
            {
              onSuccess: () => toast.success(v ? "Marcado como vendido" : "Desmarcado"),
              onError: (e) => {
                setVendido(!v);
                toast.error(err(e));
              },
            },
          );
        }}
        className={`shrink-0 rounded-md border px-2 py-1.5 text-[11px] font-medium transition disabled:opacity-50 ${
          vendido
            ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
            : "border-border/60 text-muted-foreground hover:border-emerald-500 hover:text-emerald-500"
        }`}
      >
        💰 {vendido ? `Vendió${item.unidades > 1 ? ` ×${item.unidades}` : ""}` : "Vendió"}
      </button>
    </div>
  );
}
