"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useImportarUrlsRopa } from "@/lib/queries/nichoRopa";

/** Sube el `fichas.json` que baja el guion de consola, para el inventario de
 *  ropa del sexo que toque. Igual que el importador de ZIP: se usa en la
 *  pantalla del nicho y en Configuración.
 */
export function PegarFichasRopa({ genero }: { genero: string }) {
  const importar = useImportarUrlsRopa();
  const [abierto, setAbierto] = useState(false);

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
      { genero, filas },
      {
        onSuccess: (r) => {
          toast.success(
            `${r.guardados} ficha(s) en ${r.carpetas} carpeta(s)` +
              (r.agotados ? ` · ${r.agotados} sin stock` : ""),
          );
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
          setAbierto(false);
        },
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 px-3 py-1.5 text-[11px] font-medium text-emerald-500 transition hover:border-emerald-400"
      >
        🔗 Pegar las fichas de TikTok de golpe
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        El mismo guion que en Configuración, pero ejecutado en la página de{" "}
        <strong className="text-foreground">
          {genero === "hombre_web" ? "ropa de hombre" : "ropa de mujer"}
        </strong>{" "}
        de su web. Sube aquí el <code>fichas.json</code> que te descargue.
      </p>
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
      <button
        type="button"
        onClick={() => setAbierto(false)}
        className="w-full rounded-lg border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition hover:border-foreground/30"
      >
        Cerrar
      </button>
    </div>
  );
}
