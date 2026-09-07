"use client";

import { Loader2, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  useImportarPrendasWeb,
  useImportarPrendasWebLote,
} from "@/lib/queries/nichoRopa";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Una línea del resumen: lo que dijo el import de ESE ZIP. */
type Resultado = {
  carpeta: string;
  nuevos: string[];
  actualizados: string[];
  iguales: string[];
  incompletos: string[];
  error?: string;
};

/** Sube los ZIP del inventario de ropa (mujer u hombre) de la web del curso.
 *
 *  Vive aparte de la pantalla del nicho porque se usa en los dos sitios: allí
 *  y en Configuración, donde está el flujo entero de traerse el catálogo.
 *
 *  Enseña el resultado CARPETA A CARPETA, como el del POV BOF. Con un solo
 *  aviso al final ("27 ZIP(s)") pasó lo peor que puede pasar: se subieron 27 y
 *  entró una, y desde la pantalla no había forma de saberlo — hubo que mirar
 *  el Drive a mano.
 */
export function ImportarPrendasWeb({
  genero,
  onImportado,
}: {
  genero: string;
  onImportado: (slug: string) => void;
}) {
  const importar = useImportarPrendasWeb();
  const lote = useImportarPrendasWebLote();
  const abrirCola = useDrawerStore((s) => s.openQueue);
  const [hechas, setHechas] = useState<Resultado[]>([]);
  const [vaPor, setVaPor] = useState<{ hechos: number; total: number } | null>(null);

  const nuevos = hechas.reduce((n, x) => n + x.nuevos.length, 0);
  const cambiados = hechas.reduce((n, x) => n + x.actualizados.length, 0);
  const iguales = hechas.reduce((n, x) => n + x.iguales.length, 0);
  const fallidas = hechas.filter((x) => x.error);

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
        {importar.isPending || lote.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {vaPor ? `Importando ${vaPor.hechos}/${vaPor.total}…` : "Importando…"}
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
          disabled={importar.isPending || lote.isPending}
          className="hidden"
          onChange={async (e) => {
            const fs = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (!fs.length) {
              toast.error("El selector no devolvió ningún ZIP.");
              return;
            }
            setHechas([]);
            // VARIOS van a la cola: son cientos de MB y de uno en uno por HTTP
            // se corta a mitad sin decir por dónde iba (con 27 entró UNO). Uno
            // solo se hace al momento, que es cuestión de segundos.
            if (fs.length > 1) {
              lote.mutate(
                { archivos: fs, genero },
                {
                  onSuccess: (r) => {
                    toast.success(`${r.zips} ZIP(s) en la cola`);
                    abrirCola();
                  },
                  onError: (err) => toast.error(err.message),
                },
              );
              return;
            }
            // De uno en uno y esperando: cada ZIP escribe en el Drive montado y
            // lanzarlos a la vez solo se estorbaría.
            for (const [i, f] of fs.entries()) {
              setVaPor({ hechos: i, total: fs.length });
              try {
                const r = await importar.mutateAsync({ archivo: f, genero });
                setHechas((antes) => [
                  ...antes.filter((x) => x.carpeta !== r.carpeta),
                  r,
                ]);
                onImportado(r.slug);
              } catch (err) {
                // El que falla NO puede desaparecer del resumen: es justo el
                // que hay que volver a subir.
                setHechas((antes) => [
                  ...antes,
                  {
                    carpeta: f.name.replace(/\.zip$/i, ""),
                    nuevos: [],
                    actualizados: [],
                    iguales: [],
                    incompletos: [],
                    error: err instanceof Error ? err.message : String(err),
                  },
                ]);
              }
            }
            setVaPor(null);
            toast.success(`${fs.length} ZIP(s) procesados`);
          }}
        />
      </label>

      {hechas.length > 0 && (
        <div className="space-y-1 text-[10px] leading-tight">
          <p className="font-semibold text-foreground">
            {hechas.length} ZIP(s) · {nuevos} nueva(s), {cambiados} cambiada(s),{" "}
            {iguales} sin tocar
            {fallidas.length ? ` · ${fallidas.length} FALLIDO(S)` : ""}
          </p>
          {cambiados > 0 && (
            <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-500">
              Las cambiadas llevaban otra prenda en ese número: se les ha tirado
              todo lo guardado. Vuelve a darles «Obtener textos».
            </p>
          )}
          <div className="max-h-40 space-y-0.5 overflow-y-auto">
            {hechas.map((x) => (
              <p key={x.carpeta} className="text-muted-foreground">
                <strong className="text-foreground">{x.carpeta}</strong>
                {x.error ? (
                  <span className="text-red-500"> · falló: {x.error}</span>
                ) : (
                  <>
                    {x.nuevos.length ? (
                      <span className="text-emerald-500">
                        {" "}
                        · nuevas: {x.nuevos.length}
                      </span>
                    ) : null}
                    {x.actualizados.length ? (
                      <span className="text-amber-500">
                        {" "}
                        · cambiadas: {x.actualizados.join(", ")}
                      </span>
                    ) : null}
                    {x.iguales.length ? ` · ${x.iguales.length} sin tocar` : ""}
                    {!x.nuevos.length && !x.actualizados.length && !x.iguales.length
                      ? " · no entró ninguna foto"
                      : ""}
                    {x.incompletos.length
                      ? ` · sin las dos fotos: ${x.incompletos.join(", ")}`
                      : ""}
                  </>
                )}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
