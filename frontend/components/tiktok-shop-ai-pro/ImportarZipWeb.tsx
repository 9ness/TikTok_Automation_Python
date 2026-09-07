"use client";

import { Loader2, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { alElegirEnLaApp, alSubirCadaFichero, haySubidaNativa, subirConLaApp } from "@/lib/subidaNativa";
import {
  nichoPovBofKeys,
  useImportarProductosWeb,
  useImportarProductosWebLote,
} from "@/lib/queries/nichoPovBof";
import { useDrawerStore } from "@/lib/stores/drawerStore";

/** Subir un ZIP de la web del curso.
 *
 *  El catálogo se actualiza a menudo, así que esto está pensado para
 *  RESUBIRSE: la carpeta se llama como el ZIP y cada producto se compara con
 *  lo que ya había. Después de importar se dice cuáles son nuevos, porque son
 *  justo a los que hay que ponerles la ficha de TikTok.
 */
export function ImportarZipWeb({
  source = "productos_web",
  onImportado,
}: {
  /** A qué catálogo van los ZIP: el de la web vieja o el inventario nuevo. */
  source?: string;
  onImportado: (carpeta: string) => void;
}) {
  const qcWeb = useQueryClient();
  const importar = useImportarProductosWeb();
  const lote = useImportarProductosWebLote();
  const abrirCola = useDrawerStore((s) => s.openQueue);
  const entrada = useRef<HTMLInputElement>(null);
  // Cuántos ZIP está subiendo la app y cuántos ha terminado. En el WebView el
  // selector NO le devuelve los ficheros al `<input>` —pasó igual con los
  // vídeos—, así que ahí sube la app y la web solo recoge el resultado.
  const [porLaApp, setPorLaApp] = useState<{ total: number; hechos: number } | null>(
    null,
  );
  // Una línea por carpeta, no solo la última: con 31 ZIP, ver solo el
  // resultado del último no dice nada.
  const [hechas, setHechas] = useState<
    {
      carpeta: string;
      nuevos: string[];
      actualizados: string[];
      iguales: string[];
      incompletos: string[];
    }[]
  >([]);

  function apuntar(r: {
    carpeta: string;
    nuevos: string[];
    actualizados: string[];
    iguales: string[];
    incompletos: string[];
  }) {
    setHechas((antes) => [...antes.filter((x) => x.carpeta !== r.carpeta), r]);
  }

  /** Se lo pasa a la app si sabe subir. `false` = que lo haga la web. */
  function lanzarConLaApp(nombres: string[]): boolean {
    if (!haySubidaNativa() || !nombres.length) return false;
    const base = api.baseUrl;
    const lanzada = subirConLaApp({
      url: `${base}/api/v1/nicho-pov-bof/productos-web/importar`,
      apiKey: process.env.NEXT_PUBLIC_API_KEY ?? "",
      // Uno por ZIP: el servidor importa cada uno en su petición y contesta
      // con lo que ha entrado.
      tareas: nombres.map((nombre) => ({ nombre, campos: {} })),
    });
    if (!lanzada) return false;
    setPorLaApp({ total: nombres.length, hechos: 0 });
    toast.success(`${nombres.length} ZIP(s) subiendo con la app`);
    return true;
  }

  // Lo que va terminando la app, ZIP a ZIP.
  useEffect(() => alSubirCadaFichero((nombre, respuesta) => {
    let r: {
      carpeta?: string;
      nuevos?: string[];
      actualizados?: string[];
      iguales?: string[];
      incompletos?: string[];
    } = {};
    try {
      r = JSON.parse(respuesta || "{}");
    } catch {
      // Respuesta rota: cuenta igual, pero no se puede resumir.
    }
    if (r.carpeta) {
      apuntar({
        carpeta: r.carpeta,
        nuevos: r.nuevos ?? [],
        actualizados: r.actualizados ?? [],
        iguales: r.iguales ?? [],
        incompletos: r.incompletos ?? [],
      });
    } else {
      toast.error(`No se pudo importar ${nombre}`);
    }
    setPorLaApp((v) => (v ? { ...v, hechos: v.hechos + 1 } : v));
    void qcWeb.invalidateQueries({ queryKey: nichoPovBofKeys.all });
  }), [qcWeb]);

  // Si el selector de la app no llegó a devolverlos al `<input>`, la app avisa
  // aparte con los NOMBRES y con eso basta: sube ella.
  useEffect(() => alElegirEnLaApp((nombres) => {
    const zips = nombres.filter((n) => n.toLowerCase().endsWith(".zip"));
    if (zips.length) lanzarConLaApp(zips);
  }), []);

  return (
    <div className="space-y-2 rounded-lg border border-cyan-500/40 bg-cyan-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Sube los ZIP de la web —<strong className="text-foreground">puedes
        elegir los 31 de golpe</strong>—. Cada carpeta se llama como su fichero,
        así que puedes volver a subirlos cuando los actualicen: solo se tocan
        los productos que hayan cambiado, y la primera vez es la lenta. Con más
        de uno va a la cola y ahí ves el avance.
      </p>

      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-cyan-600">
        {lote.isPending || importar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo…
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" /> Subir ZIPs de la web
          </>
        )}
        <input
          ref={entrada}
          type="file"
          accept=".zip,application/zip"
          multiple
          disabled={lote.isPending || importar.isPending}
          className="hidden"
          onChange={(e) => {
            const fs = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (!fs.length) return;
            // UNO se importa al momento, que es cuestión de segundos; VARIOS
            // van a la cola: treinta y uno son cientos de MB y aquí se agotaría
            // el tiempo a mitad, sin saber por dónde iba.
            if (lanzarConLaApp(fs.map((f) => f.name))) return;
            const uno = fs[0];
            if (fs.length === 1 && uno) {
              importar.mutate(
                { archivo: uno, source },
                {
                  onSuccess: (r) => {
                    apuntar(r);
                    onImportado(r.carpeta);
                    const n = r.nuevos.length + r.actualizados.length;
                    toast.success(
                      n ? `${r.carpeta}: ${n} producto(s) puestos` : `${r.carpeta}: sin cambios`,
                    );
                  },
                  onError: (err) => toast.error(err.message),
                },
              );
              return;
            }
            lote.mutate(
              { archivos: fs, source },
              {
                onSuccess: (r) => {
                  toast.success(`${r.zips} ZIP(s) en la cola`);
                  abrirCola();
                },
                onError: (err) => toast.error(err.message),
              },
            );
          }}
        />
      </label>

      {porLaApp && porLaApp.hechos < porLaApp.total && (
        <p className="flex items-center gap-1.5 text-[10px] text-cyan-400">
          <Loader2 className="h-3 w-3 animate-spin" />
          Subiendo con la app · {porLaApp.hechos} de {porLaApp.total}
        </p>
      )}

      {hechas.length > 0 && (
        <div className="space-y-1 text-[10px] leading-tight">
          {(() => {
            const nuevos = hechas.reduce((n, x) => n + x.nuevos.length, 0);
            const cambiados = hechas.reduce((n, x) => n + x.actualizados.length, 0);
            const iguales = hechas.reduce((n, x) => n + x.iguales.length, 0);
            return (
              <>
                <p className="font-semibold text-foreground">
                  {hechas.length} carpeta(s) · {nuevos} nuevo(s), {cambiados} cambiado(s),
                  {" "}
                  {iguales} sin tocar
                </p>
                {cambiados > 0 && (
                  <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-500">
                    Los cambiados llevaban otro producto en ese número: se les
                    ha tirado todo lo guardado (textos, guion, escenas, clips,
                    vídeo y las marcas). Vuelve a darles «Obtener textos».
                  </p>
                )}
              </>
            );
          })()}
          <div className="max-h-40 space-y-0.5 overflow-y-auto">
            {hechas.map((x) => (
              <p key={x.carpeta} className="text-muted-foreground">
                <strong className="text-foreground">{x.carpeta}</strong>
                {x.nuevos.length ? (
                  <span className="text-emerald-500"> · nuevos: {x.nuevos.join(", ")}</span>
                ) : null}
                {x.actualizados.length ? (
                  /* Cambiar de foto es cambiar de PRODUCTO: su web renumera
                     al añadir cosas. Todo lo que había guardado con ese número
                     se ha tirado, así que hay que volver a sacarles los
                     textos. */
                  <span className="text-amber-500">
                    {" "}
                    · cambiados (empiezan de cero): {x.actualizados.join(", ")}
                  </span>
                ) : null}
                {!x.nuevos.length && !x.actualizados.length ? " · sin cambios" : null}
                {x.incompletos.length ? ` · sin las dos fotos: ${x.incompletos.length}` : null}
              </p>
            ))}
          </div>
          <p className="text-muted-foreground">
            A los <span className="text-emerald-500">nuevos</span> hay que ponerles la URL.
          </p>
        </div>
      )}

    </div>
  );
}
