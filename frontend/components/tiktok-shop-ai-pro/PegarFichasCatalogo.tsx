"use client";

import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useImportarUrls } from "@/lib/queries/nichoPovBof";

/** Sube el `fichas.json` de un catálogo del POV BOF (hoy, el Inventario
 *  General).
 *
 *  Es el gemelo de `PegarFichasRopa`: el mismo fichero que baja el guion de
 *  consola, pero el de ropa va por su endpoint porque sus carpetas llevan el
 *  género en el slug. Aquí se sube el FICHERO en vez de pegar el texto (eso ya
 *  está en el panel de URLs): son ~310 filas y en el móvil pegarlas a mano no
 *  se puede.
 */
export function PegarFichasCatalogo({ source }: { source: string }) {
  const importar = useImportarUrls();

  async function subir(f: File | null) {
    if (!f) return;
    let filas: unknown[];
    try {
      filas = JSON.parse(await f.text());
    } catch {
      toast.error("Ese fichero no es el JSON de la consola.");
      return;
    }
    if (!Array.isArray(filas) || !filas.length) {
      toast.error("El fichero no trae ninguna fila.");
      return;
    }
    importar.mutate(
      { source, filas },
      {
        onSuccess: (r) => {
          toast.success(
            `${r.guardados} ficha(s) en ${r.carpetas} carpeta(s)` +
              (r.agotados ? ` · ${r.agotados} sin stock` : ""),
          );
          // Callar esto dejaría enlaces sin guardar pareciendo que fue bien.
          if (r.descartadas?.length) {
            toast.warning(
              `${r.descartadas.length} enlace(s) no son de TikTok, sin guardar`,
              { duration: 10000 },
            );
          }
          if (r.sin_carpeta?.length) {
            toast.warning(
              `Sin guardar, no hay esa carpeta: ${r.sin_carpeta.join(", ")}`,
              { duration: 10000 },
            );
          }
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  return (
    <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-700">
      {importar.isPending ? (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
        </>
      ) : (
        <>📄 Elegir fichas.json</>
      )}
      <input
        type="file"
        accept=".json,application/json"
        disabled={importar.isPending}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          e.target.value = "";
          void subir(f);
        }}
      />
    </label>
  );
}
