"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { useMarcarFoto, useTandasFotos, urlZipTandaFotos } from "@/lib/queries/misTandas";
import { BotonFotosEnOrden } from "@/components/tiktok-shop-ai-pro/BotonFotosEnOrden";

/** «sáb 3 oct» a partir de «2026-10-03». */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" }).replace(".", "");
}

/** Pestaña «Fotos» de Mis tandas: los carruseles de «Replicar carrusel» en
 *  tandas de diez, con su PROPIO contador (no son vídeos ni cuentan para la
 *  cuota del día). ZIP de la tanda entera; cada carrusel baja sus fotos una a una y en orden, y «Subido». */
export function CarruselesReplicados() {
  const [verCerradas, setVerCerradas] = useState(false);
  const tandas = useTandasFotos(verCerradas);
  const marcar = useMarcarFoto();
  const [abierta, setAbierta] = useState<number | null>(null);
  const datos = tandas.data;
  const primera = datos?.tandas.find((t) => t.abierta)?.numero ?? null;
  const abiertaReal = abierta ?? primera;

  return (
    <Caja
      icono="🖼️"
      titulo="Tandas de fotos"
      hint="Carruseles con su texto quemado, de diez en diez. Se hacen en Replicar carrusel; aquí entran en cuanto tienen una foto."
      extra={datos ? `${datos.subidos}/${datos.total} subidos` : undefined}
    >
      <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
        {datos ? (
          <>
            <span className="rounded-full bg-muted px-1.5 py-px font-semibold">
              {datos.abiertas} por subir
            </span>
            <span className="rounded-full bg-emerald-500/15 px-1.5 py-px font-semibold text-emerald-500">
              {datos.cerradas} cerradas
            </span>
            <span className="rounded-full border border-border/60 px-1.5 py-px font-semibold">
              {datos.completos}/{datos.total} completos
            </span>
          </>
        ) : null}
        <label className="ml-auto flex items-center gap-1">
          <input type="checkbox" checked={verCerradas} onChange={(e) => setVerCerradas(e.target.checked)} />
          Ver cerradas
        </label>
      </div>

      {tandas.isLoading ? (
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
        </p>
      ) : tandas.isError ? (
        <p className="text-[11px] text-rose-500">No se pudieron leer las fotos: {tandas.error.message}</p>
      ) : !datos?.tandas.length ? (
        <p className="text-[11px] text-muted-foreground">
          No hay carruseles por subir. Cuando subas la primera foto de uno en Replicar carrusel, aparece aquí.
        </p>
      ) : (
        <div className="space-y-1.5">
          {datos.tandas.map((t) => {
            const esta = abiertaReal === t.numero;
            return (
              <div
                key={t.numero}
                className={`rounded-lg border ${t.abierta ? "border-border/60" : "border-border/40 opacity-80"}`}
              >
                <div className="flex items-center gap-2 px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => setAbierta(esta ? -1 : t.numero)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="text-xs font-semibold sm:text-sm">
                      {esta ? "▾" : "▸"} Tanda {t.numero}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span
                        className={`rounded-full px-1.5 py-px text-[9px] font-semibold ${
                          t.abierta ? "bg-muted text-muted-foreground" : "bg-emerald-500/15 text-emerald-500"
                        }`}
                      >
                        {t.subidos}/{t.total} subidos
                      </span>
                      {t.fecha ? (
                        <span className="rounded-full bg-sky-500/15 px-1.5 py-px text-[9px] font-semibold text-sky-600 dark:text-sky-400">
                          📅 {fechaCorta(t.fecha)}
                        </span>
                      ) : null}
                      {t.completos < t.total ? (
                        <span className="rounded-full bg-amber-500/15 px-1.5 py-px text-[9px] font-semibold text-amber-500">
                          {t.total - t.completos} a medias
                        </span>
                      ) : null}
                    </span>
                  </button>
                  <a
                    href={urlZipTandaFotos(t.numero, t.subidos > 0)}
                    className="flex shrink-0 items-center gap-1 rounded-lg border border-sky-500/50 px-2 py-1 text-[10px] font-semibold text-sky-400 hover:bg-sky-500/10"
                    title={t.subidos > 0 ? "Solo los que faltan por subir" : "Todos los carruseles de la tanda"}
                  >
                    <Download className="h-3 w-3" /> {t.subidos > 0 ? "ZIP pendientes" : "ZIP tanda"}
                  </a>
                </div>
                {esta && t.items ? (
                  <ul className="grid grid-cols-1 gap-1.5 border-t border-border/40 p-2 sm:grid-cols-2">
                    {t.items.map((c, i) => (
                      <li
                        key={c.id}
                        className={`space-y-1 rounded-lg border px-2 py-1.5 ${
                          c.subido ? "border-emerald-500/40 bg-emerald-500/[0.04]" : "border-border/60"
                        }`}
                      >
                        <p className="truncate text-[11px] font-medium">
                          {String(i + 1).padStart(2, "0")} · {c.titulo}
                        </p>
                        <p className="truncate text-[10px] text-muted-foreground">
                          {new Date(c.creado_at * 1000).toLocaleDateString("es-ES")} ·{" "}
                          <span className={c.completo ? "text-emerald-400" : "text-amber-400"}>
                            {c.hechas}/{c.diapositivas} fotos
                          </span>
                        </p>
                        <div className="flex flex-wrap items-center gap-1">
                          <BotonFotosEnOrden
                            id={c.id}
                            disabled={!c.hechas}
                            etiqueta="Fotos"
                            className="rounded px-2 py-1 text-[10px]"
                          />
                          <CopyChip
                            label="Caption"
                            text={[c.caption, c.hashtags.join(" ")].filter(Boolean).join(" ")}
                          />
                          <a
                            href="/tiktok-shop-ai-pro/replicar-carrusel"
                            className="rounded border border-border/60 px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
                          >
                            Abrir
                          </a>
                          <button
                            type="button"
                            disabled={marcar.isPending}
                            onClick={() => marcar.mutate({ id: c.id, subido: !c.subido })}
                            className={`ml-auto rounded border px-2 py-1 text-[10px] font-semibold disabled:opacity-40 ${
                              c.subido
                                ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-500"
                                : "border-border/60 text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            {c.subido ? "✓ Subido" : "Subido"}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </Caja>
  );
}
