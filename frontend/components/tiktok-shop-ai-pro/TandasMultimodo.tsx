"use client";

import { Check, Copy, Download, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { bajarEnOrden, nombreDescarga } from "@/lib/descargas";
import {
  buildFotoRopaUrl,
  buildVideoRopaUrl,
  useMarcarSubidoMultimodo,
  useRehacerMultimodo,
  useSinStockMultimodo,
  useTandasMultimodo,
  type VideoMultimodo,
} from "@/lib/queries/nichoRopa";
import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { RehacerDialog } from "@/components/tiktok-shop-ai-pro/RehacerDialog";
import { useHashtags } from "@/lib/queries/nichoPovBof";

/** Los fallos que más se repiten en los clips del multimodo (con chica o
 *  con mano): se revisan antes de subir, porque cada uno es una sanción. */
const MOTIVOS_MULTIMODO = [
  "Objeto flotando o suspendido en el aire (móvil, bolso…)",
  "Aparece o desaparece algo de golpe",
  "Manos, piernas o pies de más o deformes",
  "Se ve de espaldas o sin el móvil en el espejo",
  "La prenda o el producto cambia de color o forma",
  "Zapato o pieza de más",
  "Texto o letras en el vídeo",
  "Demasiado estático",
];

/** Los vídeos hechos del Multimodo en tandas de diez.
 *
 *  El multimodo recorre ropa, zapatos y accesorios, así que lo montado queda
 *  repartido por muchas carpetas. Para publicar se trabaja al revés: por
 *  orden de montaje, bajando una tanda entera y marcando lo que se sube. */
export function TandasMultimodo() {
  const tandas = useTandasMultimodo();
  // Los mismos hashtags que las tarjetas de Moda Mujer: el caption se copia
  // entero (texto, emojis y hashtags), que es lo que se pega en TikTok.
  const hashtags = useHashtags("nicho-ropa-mujer").data ?? [];
  const captionDe = (v: { caption?: string; emojis?: string }) =>
    v.caption ? [v.caption, v.emojis, hashtags.join(" ")].filter(Boolean).join(" ") : "";
  const marcar = useMarcarSubidoMultimodo();
  const rehacer = useRehacerMultimodo();
  const sinStock = useSinStockMultimodo();
  const [aRehacer, setARehacer] = useState<VideoMultimodo | null>(null);
  const [bajando, setBajando] = useState<number | null>(null);
  const [bajandoUno, setBajandoUno] = useState<string | null>(null);
  // "3/10" mientras baja, como al bajar los vídeos de una carpeta.
  const [progreso, setProgreso] = useState("");
  const [abierta, setAbierta] = useState<number | null>(null);

  const datos = tandas.data;
  // Por defecto se abre la primera tanda que aún tenga algo por subir. Lo
  // que está sin stock no cuenta: no se puede publicar.
  const primeraPendiente =
    datos?.tandas.find((t) => t.subidos + (t.sin_stock ?? 0) < t.items.length)?.numero ?? null;
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

  /** Un vídeo suelto, con el MISMO nombre que al bajar la tanda entera. */
  async function bajarUno(numero: number, i: number, v: VideoMultimodo) {
    setBajandoUno(`${v.carpeta}-${v.producto}`);
    const r = await bajarEnOrden([
      {
        href: buildVideoRopaUrl(v.producto, v.carpeta, v.video_listo_at, true, v.formato),
        nombre:
          nombreDescarga(
            "multimodo",
            `tanda${String(numero).padStart(2, "0")}`,
            String(i + 1).padStart(2, "0"),
            v.formato,
          ) + ".mp4",
      },
    ]);
    setBajandoUno(null);
    if (r.fallidas) toast.error("No se pudo descargar el vídeo");
  }

  async function bajarTanda(numero: number) {
    const t = datos?.tandas.find((x) => x.numero === numero);
    if (!t) return;
    setBajando(numero);
    // Sin stock no se baja (no se puede publicar), pero el resto conserva su
    // número de puesto en el nombre: la tanda descargada sigue cuadrando.
    const saltados = t.items.filter((v) => v.sin_stock && !v.uploaded).length;
    const r = await bajarEnOrden(
      t.items.map((v, i) => ({ v, i })).filter(({ v }) => !(v.sin_stock && !v.uploaded)).map(({ v, i }) => ({
        href: buildVideoRopaUrl(v.producto, v.carpeta, v.video_listo_at, true, v.formato),
        nombre:
          nombreDescarga(
            "multimodo",
            `tanda${String(numero).padStart(2, "0")}`,
            String(i + 1).padStart(2, "0"),
            v.formato,
          ) + ".mp4",
      })),
      (hechos, total) => setProgreso(`${hechos}/${total}`),
      // Son vídeos de ~10 MB: de uno en uno, la tanda tardaba minutos.
      3,
    );
    setBajando(null);
    setProgreso("");
    if (r.fallidas) toast.error(`${r.bajadas} bajados · ${r.fallidas} fallaron`);
    else
      toast.success(
        `Tanda ${numero}: ${r.bajadas} vídeo(s) descargados` +
          (saltados ? ` · ${saltados} sin stock no bajado(s)` : ""),
      );
  }

  return (
    <Caja
      icono="📦"
      titulo="Vídeos listos por tandas"
      hint="Todo lo montado del multimodo, de cualquier carpeta, de diez en diez. Baja la tanda, copia el caption y la música de cada vídeo y pulsa «Marcar subido» al publicarlo. 🎵 es la música que le va: tócala para copiar la búsqueda y pégala en TikTok › Añadir sonido › Buscar (elige uno con muchos vídeos y bájale el volumen)."
      extra={
        datos
          ? `${datos.subidos}/${datos.total} subidos` +
            (datos.sin_stock ? ` · 🚫 ${datos.sin_stock}` : "")
          : undefined
      }
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
            // Sin stock cuenta como cerrado: no hay nada más que hacer con él.
            const completa = t.subidos + (t.sin_stock ?? 0) >= t.items.length;
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
                    {t.sin_stock ? (
                      <span className="ml-1 rounded-full bg-rose-500/15 px-1.5 py-px text-[10px] text-rose-500">
                        🚫 {t.sin_stock}
                      </span>
                    ) : null}
                    {t.items.some((x) => x.rehacer) ? (
                      <span className="ml-1 rounded-full bg-orange-500/15 px-1.5 py-px text-[10px] text-orange-500">
                        🔁 {t.items.filter((x) => x.rehacer).length}
                      </span>
                    ) : null}
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
                    {bajando === t.numero && progreso ? progreso : "Bajar"}
                  </button>
                </div>
                {abiertaEsta && (
                  <ul className="divide-y divide-border/40 border-t border-border/40">
                    {t.items.map((v, i) => (
                      <li
                        key={`${v.carpeta}-${v.producto}`}
                        className={`flex flex-col gap-1 px-2 py-1.5 ${
                          v.sin_stock && !v.uploaded ? "bg-rose-500/5" : ""
                        }`}
                      >
                        {/* Arriba la ficha y las acciones; los chips van en su
                            propia línea a lo ancho: en un móvil estrecho no
                            caben al lado y se aplastaban. */}
                        <div className="flex items-center gap-2">
                          <span className="w-4 shrink-0 text-[10px] text-muted-foreground">
                            {i + 1}
                          </span>
                          {v.foto_id ? (
                            <a
                              href={buildFotoRopaUrl(v.foto_id)}
                              target="_blank"
                              rel="noreferrer"
                              title="Ver la foto del producto"
                              className="shrink-0"
                            >
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={buildFotoRopaUrl(v.foto_id, 96)}
                                alt=""
                                loading="lazy"
                                className="h-10 w-10 rounded-md border border-border/40 bg-white object-contain sm:h-12 sm:w-12"
                              />
                            </a>
                          ) : (
                            <div className="h-10 w-10 shrink-0 rounded-md border border-dashed border-border/40 sm:h-12 sm:w-12" />
                          )}
                          <div className="min-w-0 flex-1">
                            <p
                              className={`truncate text-[11px] font-medium sm:text-xs ${
                                v.sin_stock && !v.uploaded ? "text-muted-foreground line-through" : ""
                              }`}
                            >
                              {v.titulo || `Producto ${v.producto}`}
                            </p>
                            <p className="truncate text-[10px] text-muted-foreground">
                              {v.formato_label} · {v.carpeta_label} · P{v.producto}
                            </p>
                          </div>
                          <button
                            type="button"
                            disabled={bajandoUno !== null}
                            onClick={() => void bajarUno(t.numero, i, v)}
                            title="Descargar este vídeo"
                            className="flex shrink-0 items-center rounded-md border border-border/60 px-1.5 py-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
                          >
                            {bajandoUno === `${v.carpeta}-${v.producto}` ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Download className="h-3 w-3" />
                            )}
                          </button>
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
                          {/* Sin stock: como en POV BOF, el producto ya no está en
                              TikTok Shop. Solo en lo que falta por subir; se
                              quita de un toque si el producto vuelve. */}
                          {(!v.uploaded || v.sin_stock) && (
                            <button
                              type="button"
                              onClick={() =>
                                sinStock.mutate({
                                  carpeta: v.carpeta,
                                  producto: v.producto,
                                  sin_stock: !v.sin_stock,
                                })
                              }
                              title={
                                v.sin_stock
                                  ? "Quitar «sin stock» (el producto ha vuelto)"
                                  : "Marcar sin stock: el producto ya no está en TikTok Shop"
                              }
                              className={`flex shrink-0 items-center rounded-md border px-1.5 py-1 text-[10px] ${
                                v.sin_stock
                                  ? "border-rose-500/60 bg-rose-500/15 text-rose-500"
                                  : "border-border/60 text-muted-foreground hover:text-rose-500"
                              }`}
                            >
                              🚫
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              v.rehacer
                                ? rehacer.mutate({ carpeta: v.carpeta, producto: v.producto, rehacer: false })
                                : setARehacer(v)
                            }
                            title={v.rehacer ? "Quitar «rehacer»" : "Marcar para rehacer"}
                            className={`flex shrink-0 items-center rounded-md border px-1.5 py-1 ${
                              v.rehacer
                                ? "border-orange-500/60 bg-orange-500/15 text-orange-500"
                                : "border-border/60 text-muted-foreground hover:text-orange-500"
                            }`}
                          >
                            <RotateCcw className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
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
                            {v.uploaded ? "Subido" : (
                              <>
                                <span className="hidden sm:inline">Marcar subido</span>
                                <span className="sm:hidden">Subir</span>
                              </>
                            )}
                          </button>
                        </div>
                        {v.sin_stock && !v.uploaded ? (
                          <p className="break-words pl-6 text-[10px] text-rose-500">
                            🚫 Sin stock: no se sube ni se baja con la tanda. Si el producto
                            vuelve, pulsa 🚫 otra vez y queda en su puesto.
                          </p>
                        ) : null}
                        {v.rehacer ? (
                          <p className="break-words pl-6 text-[10px] text-orange-500">
                            🔁 Rehacer{v.rehacer_nota ? `: ${v.rehacer_nota}` : ""}
                          </p>
                        ) : v.rehecho && !v.uploaded ? (
                          <p className="pl-6 text-[10px] text-sky-400">
                            ✨ Rehecho — revísalo antes de subirlo
                          </p>
                        ) : null}
                        <div className="flex min-w-0 flex-wrap items-center gap-1 pl-6">
                          <CopyChip label="✍️ Caption" text={captionDe(v)} siempre />
                          {/* Si el enlace del producto no corresponde (la web del curso
                              se equivoca a veces), se busca a mano en TikTok con el
                              título y la tienda, igual que en POV BOF Largo. */}
                          <CopyChip
                            label="🔎 Título"
                            text={v.titulo_tiktok_completo || v.titulo || ""}
                            siempre
                          />
                          <CopyChip label="🏪 Tienda" text={v.tienda || ""} siempre />
                          {v.musica?.busqueda ? (
                            <button
                              type="button"
                              onClick={() => void copiarMusica(v.musica!.busqueda)}
                              title={`${v.musica.estilo}. Otras: ${v.musica.alternativas.join(" · ")}`}
                              className="flex min-w-0 max-w-full items-center gap-1 rounded bg-violet-500/10 px-1.5 py-1 text-left text-[10px] text-violet-300 hover:bg-violet-500/20"
                            >
                              <span className="shrink-0">🎵</span>
                              <span className="min-w-0 break-words leading-tight">{v.musica.busqueda}</span>
                              <Copy className="h-2.5 w-2.5 shrink-0" />
                            </button>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
      <RehacerDialog
        abierto={aRehacer !== null}
        onCerrar={() => setARehacer(null)}
        titulo={aRehacer ? `${aRehacer.titulo || `Producto ${aRehacer.producto}`} · ${aRehacer.formato_label}` : ""}
        motivos={MOTIVOS_MULTIMODO}
        onMarcar={(nota) =>
          aRehacer &&
          rehacer.mutate({
            carpeta: aRehacer.carpeta,
            producto: aRehacer.producto,
            rehacer: true,
            rehacer_nota: nota,
          })
        }
      />
    </Caja>
  );
}
