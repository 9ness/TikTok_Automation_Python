"use client";

import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { useImportarPrendasWeb } from "@/lib/queries/nichoRopa";

/** Sube los ZIP del inventario de ropa (mujer u hombre) de la web del curso.
 *
 *  Vive aparte de la pantalla del nicho porque se usa en los dos sitios: allí
 *  y en Configuración, donde está el flujo entero de traerse el catálogo.
 */
export function ImportarPrendasWeb({
  genero,
  onImportado,
}: {
  genero: string;
  onImportado: (slug: string) => void;
}) {
  const importar = useImportarPrendasWeb();

  return (
    <div className="space-y-2 rounded-lg border border-violet-500/40 bg-violet-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Sube aquí los ZIP del inventario de{" "}
        <strong className="text-foreground">
          {genero === "mujer_web" ? "mujer" : "hombre"}
        </strong>{" "}
        — puedes elegir varios de golpe. Los del otro sexo van en su pantalla:
        cada uno lleva sus carpetas. Volver a subirlos solo toca lo que haya
        cambiado.
      </p>

      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-600">
        {importar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Importando…
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" /> Subir ZIPs de{" "}
            {genero === "mujer_web" ? "mujer" : "hombre"}
          </>
        )}
        <input
          type="file"
          accept=".zip,application/zip"
          multiple
          disabled={importar.isPending}
          className="hidden"
          onChange={async (e) => {
            const fs = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (!fs.length) {
              toast.error("El selector no devolvió ningún ZIP.");
              return;
            }
            // De uno en uno y esperando: cada ZIP escribe en el Drive montado y
            // lanzarlos a la vez solo se estorbaría.
            let nuevos = 0;
            for (const f of fs) {
              try {
                const r = await importar.mutateAsync({ archivo: f, genero });
                nuevos += r.nuevos.length;
                onImportado(r.slug);
              } catch (err) {
                toast.error(err instanceof Error ? err.message : String(err));
              }
            }
            toast.success(`${fs.length} ZIP(s) · ${nuevos} prenda(s) nueva(s)`);
          }}
        />
      </label>
    </div>
  );
}
