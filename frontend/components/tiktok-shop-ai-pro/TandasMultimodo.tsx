"use client";

import { Check, Copy, Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { bajarEnOrden, nombreDescarga } from "@/lib/descargas";
import {
  buildVideoRopaUrl,
  useMarcarSubidoMultimodo,
  useTandasMultimodo,
} from "@/lib/queries/nichoRopa";
import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";

/** Los vídeos hechos del Multimodo en tandas de diez.
 *
 *  El multimodo recorre ropa, zapatos y accesorios, así que lo montado queda
 *  repartido por muchas carpetas. Para publicar se trabaja al revés: por
 *  orden de montaje, bajando una tanda entera y marcando lo que se sube. */
export function TandasMultimodo() {
  const tandas = useTandasMultimodo();
  const marcar = useMarcarSubidoMultimodo();
  const [bajando, setBajando] = useState<number | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);

  const datos = tandas.data;
  // Por defecto se abre la primera tanda que aún tenga algo por subir.
  const primeraPendiente =
    datos?.tandas.find((t) => t.subidos < t.items.length)?.numero ?? null;
  const abiertaReal = abierta ?? primeraPendiente;

  // La búsqueda para la biblioteca de sonidos de TikTok: se pega tal cual
  // en "Añadir sonido → Buscar".
  async function copiarMusica(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success(`Copiado: «${texto}» — pégalo en Sonidos › Buscar de TikTok`);
    } catch {
      toast.message(`Busca en TikTok: ${texto}`);
    }
  }

  async function bajarTanda(numero: number) {
    const t = datos?.tandas.find((x) => x.numero === numero);
    if (!t) return;
    setBajando(numero);
    const r = await bajarEnOrden(
      t.items.map((v, i) => ({
        href: buildVideoRopaUrl(v.producto, v.carpeta, v.video_listo_at, true, v.formato),
        nombre:
          nombreDescarga(
            "multimodo",
            `tanda${String(numero).padStart(2, "0")}`,
            String(i + 1).padStart(2, "0"),
            v.formato,
          ) + ".mp4",
      })),
    );
    setBajando(null);
    if (r.fallidas) toast.error(`${r.bajadas} bajados · ${r.fallidas} fallaron`);
    else toast.success(`Tanda ${numero}: ${r.bajadas} vídeo(s) descargados`);
  }

  return (
    <Caja
      icono="📦"
      titulo="Vídeos listos por tandas"
      hint="Todo lo montado del multimodo, de cualquier carpeta, de diez en diez. Baja la tanda y marca lo que subas. 🎵 es la música que le va: tócala para copiar la búsqueda y pégala en TikTok › Añadir sonido › Buscar (elige uno con muchos vídeos y bájale el volumen)."
      extra={datos ? `${datos.subidos}/${datos.total} subidos` : undefined}
    >
      {tandas.isLoading ? (
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
        </p>
      ) : !datos?.tandas.length ? (
        <p className="text-[11px] text-muted-foreground">Aún no hay vídeos montados.</p>
      ) : (
        <div className="space-y-1.5">
          {datos.tandas.map((t) => {
            const completa = t.subidos >= t.items.length;
            const abiertaEsta = abiertaReal === t.numero;
            return (
              <div key={t.numero} className="rounded-lg border border-border/60">
                <div className="flex items-center gap-2 px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => setAbierta(abiertaEsta ? -1 : t.numero)}
                    className="min-w-0 flex-1 truncate text-left text-xs font-semibold sm:text-sm"
                  >
                    {abiertaEsta ? "▾" : "▸"} Tanda {t.numero}
                    <span
                      className={`ml-2 rounded-full px-1.5 py-px text-[10px] ${
                        completa
                          ? "bg-emerald-500/15 text-emerald-500"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {t.subidos}/{t.items.length} subidos
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={bajando !== null}
                    onClick={() => void bajarTanda(t.numero)}
                    className="flex shrink-0 items-center gap-1 rounded-md border border-violet-500/50 px-2 py-1 text-[11px] text-violet-400 hover:bg-violet-500/10 disabled:opacity-50"
                  >
                    {bajando === t.numero ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Download className="h-3 w-3" />
                    )}
                    Bajar
                  </button>
                </div>
                {abiertaEsta && (
                  <ul className="divide-y divide-border/40 border-t border-border/40">
                    {t.items.map((v, i) => (
                      <li
                        key={`${v.carpeta}-${v.producto}`}
                        className="flex items-center gap-2 px-2 py-1.5"
                      >
                        <span className="w-5 shrink-0 text-[10px] text-muted-foreground">
                          {i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[11px] font-medium sm:text-xs">
                            {v.titulo || `Producto ${v.producto}`}
                          </p>
                          <p className="truncate text-[10px] text-muted-foreground">
                            {v.formato_label} · {v.carpeta_label} · P{v.producto}
                          </p>
                          {v.musica?.busqueda ? (
                            <button
                              type="button"
                              onClick={() => void copiarMusica(v.musica!.busqueda)}
                              title={`${v.musica.estilo}. Otras: ${v.musica.alternativas.join(" · ")}`}
                              className="mt-0.5 flex max-w-full items-center gap-1 truncate rounded bg-violet-500/10 px-1.5 py-px text-[10px] text-violet-300 hover:bg-violet-500/20"
                            >
                              🎵 <span className="truncate">{v.musica.busqueda}</span>
                              <Copy className="h-2.5 w-2.5 shrink-0" />
                            </button>
                          ) : null}
                        </div>
                        <a
                          href={buildVideoRopaUrl(
                            v.producto, v.carpeta, v.video_listo_at, false, v.formato,
                          )}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 rounded-md border border-border/60 px-1.5 py-1 text-[10px] text-muted-foreground hover:text-foreground"
                        >
                          ▶
                        </a>
                        {v.product_url ? (
                          <a
                            href={v.product_url}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 rounded-md border border-border/60 px-1.5 py-1 text-[10px] text-muted-foreground hover:text-foreground"
                          >
                            🛍️
                          </a>
                        ) : null}
                        <button
                          type="button"
                          disabled={marcar.isPending}
                          onClick={() =>
                            marcar.mutate({
                              carpeta: v.carpeta,
                              producto: v.producto,
                              uploaded: !v.uploaded,
                            })
                          }
                          className={`flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] ${
                            v.uploaded
                              ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                              : "border-border/60 text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <Check className="h-3 w-3" />
                          {v.uploaded ? "Subido" : "Subir"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Caja>
  );
}
