"use client";

import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useSubirClipLargo } from "@/lib/queries/povBofLargo";
import type { ProductoLargo } from "@/lib/types/povBofLargo";

/** Modo Épico del POV BOF Largo: los golpes del guion y un hueco por golpe
 *  para su clip épico (5 s de Kling desde la imagen con fondo épico). Al
 *  llenar clips + insertos, la app monta sola. */
export function InsertosEpicos({
  p,
  source,
  folder,
  campos,
}: {
  p: ProductoLargo;
  source: string;
  folder: string;
  /** Los mismos ajustes que mandan los huecos de clip (voz, herramientas). */
  campos: {
    sexo: string;
    conGancho: boolean;
    conTitulo: boolean;
    conCta: boolean;
    conFlecha: boolean;
    conSubliminal: boolean;
    estiloTexto: string;
  };
}) {
  const subir = useSubirClipLargo();
  const golpes = p.golpes || [];
  if (!golpes.length) return null;
  const subidos = new Set(p.insertos_subidos || []);
  return (
    <div className="space-y-1.5 rounded-lg border border-fuchsia-500/40 bg-fuchsia-500/[0.06] p-2">
      <p className="text-[11px] font-semibold text-fuchsia-400">⚡ Insertos épicos</p>
      {golpes.map((g, i) => {
        const n = i + 1;
        return (
          <div key={n} className="flex items-center gap-2 text-[10px] sm:text-xs">
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">
                {n}. {g.texto}
              </p>
              <p className="truncate text-muted-foreground">tras «{g.tras}» · {g.escena}</p>
            </div>
            <label
              className={`shrink-0 cursor-pointer rounded border px-2 py-1 font-semibold ${
                subidos.has(n)
                  ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-400"
                  : "border-fuchsia-500/60 text-fuchsia-400"
              }`}
            >
              {subir.isPending ? "Subiendo…" : subidos.has(n) ? `✓ Inserto ${n}` : `Inserto ${n}`}
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(ev) => {
                  const f = ev.target.files?.[0];
                  ev.target.value = "";
                  if (!f) return;
                  subir.mutate(
                    {
                      source,
                      folder,
                      producto: p.producto,
                      slot: 1,
                      file: f,
                      inserto: n,
                      ...campos,
                    },
                    {
                      onSuccess: (r) => toast.success(r.message),
                      onError: (e: unknown) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  );
                }}
              />
            </label>
          </div>
        );
      })}
    </div>
  );
}
