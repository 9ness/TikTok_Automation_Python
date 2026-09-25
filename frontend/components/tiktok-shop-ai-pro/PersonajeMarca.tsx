"use client";

import { Download, Loader2, Upload, UserRound } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  buildPersonajeMarcaUrl,
  usePersonajeMarca,
  useSubirPersonajeMarca,
} from "@/lib/queries/nichoRopa";

/** El personaje fijo de Marca Personal, guardado en la app.
 *
 *  Los prompts de espejo y zapatos multi escena piden adjuntar en Flow "tu
 *  personaje de referencia" junto con la prenda. Antes esa foto no estaba en
 *  ningún sitio de la app: se buscaba cada vez, y una IA que trabajase sola no
 *  tenía de dónde sacarla. Uno por usuario — la cara es la de SU cuenta. */
export function PersonajeMarca() {
  const estado = usePersonajeMarca();
  const subir = useSubirPersonajeMarca();
  const hay = !!estado.data?.hay;
  const v = estado.data?.v ?? 0;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/60 p-2">
      <div className="h-14 w-10 shrink-0 overflow-hidden rounded bg-muted">
        {hay ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={buildPersonajeMarcaUrl(v)}
            alt="Tu personaje"
            className="h-full w-full object-cover"
          />
        ) : (
          <UserRound className="m-auto mt-4 h-5 w-5 text-muted-foreground" />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[11px] font-medium">👤 Tu personaje</p>
        <p className="text-[10px] leading-snug text-muted-foreground">
          {hay
            ? "Se adjunta en Flow junto con la prenda en espejo y zapatos multi escena."
            : "Aún no lo has subido: sin él, cada vídeo sale con una persona distinta."}
        </p>
        <div className="flex flex-wrap gap-1.5">
          <label className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] hover:border-violet-500/60">
            {subir.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Upload className="h-3 w-3" />
            )}
            {hay ? "Cambiar personaje" : "Subir personaje"}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={subir.isPending}
              onChange={(ev) => {
                const f = ev.target.files?.[0];
                ev.target.value = "";
                if (!f) return;
                subir.mutate(f, {
                  onSuccess: () => toast.success("Personaje guardado"),
                  onError: (err) =>
                    toast.error(err instanceof ApiError ? err.message : String(err)),
                });
              }}
            />
          </label>
          {hay && (
            <a
              href={buildPersonajeMarcaUrl(v, true)}
              className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] hover:border-sky-500/60"
            >
              <Download className="h-3 w-3" /> Bajar personaje
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
