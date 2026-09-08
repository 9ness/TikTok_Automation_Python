"use client";

import { Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useCrearMiProducto } from "@/lib/queries/nichoPovBof";

/** Alta de un producto PROPIO subiendo sus fotos: la limpia, la captura de la
 *  ficha y las capturas extra (características, medidas, qué trae).
 *
 *  Vive aquí y no en una pantalla porque lo usan TRES: POV BOF, POV BOF Largo
 *  y UGC Desde 0. El producto es el mismo —el backend lo guarda con el mismo
 *  convenio de nombres del curso, en el catálogo del operador— y quien lo da
 *  de alta es quien lo tenga delante, no quien vaya a grabarlo: obligar a
 *  cambiar de pantalla para subir dos fotos era el único motivo para entrar
 *  al POV BOF desde el UGC.
 *
 *  Las capturas extra son las que dan de qué hablar cuando la tienda pide un
 *  vídeo de 30 o 60 segundos: con el título solo, Gemini estira lo mismo con
 *  más adjetivos.
 */
export function AltaMiProducto({
  source = "mis_productos",
  onCreado,
}: {
  /** En cuál de los dos catálogos del operador cae el producto. */
  source?: string;
  onCreado?: (carpeta: string) => void;
}) {
  const crear = useCrearMiProducto();
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);
  // Capturas de MÁS: características, medidas, qué trae. Son las que dan de
  // qué hablar cuando la tienda pide un vídeo de 30 o 40 segundos; con el
  // título solo, Gemini estira lo mismo con más adjetivos.
  const refExtras = useRef<HTMLInputElement>(null);
  const [extras, setExtras] = useState<File[]>([]);
  const [abierto, setAbierto] = useState(false);
  // La cola de la sesión: los productos preparados que aún no se han subido.
  // Lo que tarda una subida NO es el servidor (las dos fotos se escriben en
  // Drive en el mismo segundo, medido); son los megas saliendo del móvil. Con
  // veinte productos eso es media hora mirando la pantalla de uno en uno, así
  // que se preparan todos y se sube del tirón.
  const [cola, setCola] = useState<
    { limpia: File; ficha: File | null; extras: File[] }[]
  >([]);
  const [subiendoLote, setSubiendoLote] = useState(0);

  function limpiarCampos() {
    setLimpia(null);
    setFicha(null);
    setExtras([]);
    if (refLimpia.current) refLimpia.current.value = "";
    if (refFicha.current) refFicha.current.value = "";
    if (refExtras.current) refExtras.current.value = "";
  }

  function encolar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    setCola((prev) => [...prev, { limpia, ficha, extras }]);
    limpiarCampos();
  }

  async function subirCola() {
    // De uno en uno, no a la vez: son megas por la misma línea y en paralelo
    // solo se estorban. Además así el error dice EXACTAMENTE cuál falló y los
    // que ya subieron se quedan subidos.
    const pendientes = [...cola];
    let ultimaCarpeta = "";
    for (const [i, item] of pendientes.entries()) {
      setSubiendoLote(i + 1);
      try {
        const r = await crear.mutateAsync({
          fotoLimpia: item.limpia,
          fotoFicha: item.ficha,
          fotosExtra: item.extras,
          source,
        });
        ultimaCarpeta = r.carpeta;
        setCola((prev) => prev.filter((x) => x !== item));
      } catch (e) {
        setSubiendoLote(0);
        toast.error(
          `Se subieron ${i} de ${pendientes.length}. Falló el ${i + 1}: ` +
            (e instanceof ApiError ? e.message : String(e)),
        );
        return;
      }
    }
    setSubiendoLote(0);
    toast.success(`${pendientes.length} producto(s) añadidos`);
    if (ultimaCarpeta) onCreado?.(ultimaCarpeta);
  }

  function enviar() {
    if (!limpia) {
      toast.error("Falta la foto del producto.");
      return;
    }
    crear.mutate(
      { fotoLimpia: limpia, fotoFicha: ficha, fotosExtra: extras, source },
      {
        onSuccess: (r) => {
          toast.success(
            `Producto ${r.producto} añadido a «${r.carpeta}»` +
              (extras.length ? ` · ${extras.length} captura(s) más` : ""),
          );
          onCreado?.(r.carpeta);
          limpiarCampos();
        },
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const campo = (
    ref: React.RefObject<HTMLInputElement>,
    titulo: string,
    ayuda: string,
    archivo: File | null,
    set: (f: File | null) => void,
  ) => (
    <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-emerald-500/60">
      <span className="text-[11px] font-semibold">{titulo}</span>
      <span className="text-[10px] text-muted-foreground">{ayuda}</span>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        onChange={(e) => set(e.target.files?.[0] ?? null)}
        className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
      />
      {archivo && (
        <span className="truncate text-[10px] text-emerald-500">
          ✓ {archivo.name}
        </span>
      )}
    </label>
  );

  return (
    <section className="space-y-2 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-3">
      {/* Plegado por defecto: dar de alta un producto es cosa de una vez al
          día, y desplegado empujaba la lista de carpetas media pantalla abajo
          cada vez que se abría el nicho. */}
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-xs font-semibold sm:text-sm">➕ Añadir un producto mío</span>
        <span className="text-[11px] text-muted-foreground">{abierto ? "▾" : "▸"}</span>
      </button>
      {!abierto ? null : (
      <>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {campo(refLimpia, "Foto limpia", "La del producto, sin texto encima", limpia, setLimpia)}
        {campo(refFicha, "Foto descripción", "La captura de la ficha (opcional)", ficha, setFicha)}
      </div>
      {/* Solo hacen falta para los guiones largos, así que no ocupan sitio
          arriba: van debajo y en una sola línea. */}
      <label className="flex cursor-pointer flex-col gap-1 rounded-lg border border-dashed border-border/60 p-2.5 transition hover:border-emerald-500/60">
        <span className="text-[11px] font-semibold">
          Más capturas (opcional)
        </span>
        <span className="text-[10px] text-muted-foreground">
          Características, medidas, qué trae. Con ellas se puede pedir un guion
          de 30 o 40 segundos; con el título solo, no.
        </span>
        <input
          ref={refExtras}
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => setExtras(Array.from(e.target.files ?? []))}
          className="mt-1 block w-full text-[10px] text-muted-foreground file:mr-2 file:rounded file:border-0 file:bg-muted file:px-2 file:py-1 file:text-[10px]"
        />
        {!!extras.length && (
          <span className="truncate text-[10px] text-emerald-500">
            ✓ {extras.length} captura(s)
          </span>
        )}
      </label>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <button
          type="button"
          disabled={crear.isPending || !limpia || !!subiendoLote}
          onClick={enviar}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
        >
          {crear.isPending && !subiendoLote ? "Subiendo…" : "Añadir producto"}
        </button>
        {/* Preparar sin subir: lo que tarda son los megas saliendo del móvil,
            así que con varios productos compensa dejarlos listos y subirlos de
            una tacada en vez de esperar delante de cada uno. */}
        <button
          type="button"
          disabled={!limpia || !!subiendoLote}
          onClick={encolar}
          title="Se queda preparado aquí y se sube al final, con los demás"
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/50 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/10 disabled:opacity-50"
        >
          ＋ Preparar y añadir otro
        </button>
      </div>

      {!!cola.length && (
        <div className="space-y-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2">
          <p className="text-[11px] font-semibold">
            {cola.length} producto(s) preparados
            {subiendoLote ? ` · subiendo el ${subiendoLote} de ${cola.length}…` : ""}
          </p>
          <ul className="space-y-0.5">
            {cola.map((item, i) => (
              <li
                key={`${item.limpia.name}-${i}`}
                className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
              >
                <span className="truncate">
                  {i + 1}. {item.limpia.name}
                  {item.ficha ? " + ficha" : " · sin ficha"}
                  {item.extras.length ? ` + ${item.extras.length} captura(s)` : ""}
                </span>
                {!subiendoLote && (
                  <button
                    type="button"
                    aria-label={`Quitar el producto ${i + 1} de la cola`}
                    onClick={() => setCola((prev) => prev.filter((_, j) => j !== i))}
                    className="ml-auto rounded px-1 transition hover:text-red-500"
                  >
                    ✕
                  </button>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button"
            disabled={!!subiendoLote}
            onClick={() => void subirCola()}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {subiendoLote ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo{" "}
                {subiendoLote}/{cola.length}…
              </>
            ) : (
              <>⬆️ Subir los {cola.length}</>
            )}
          </button>
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Van de uno en uno por la misma línea. No cierres la pestaña
            mientras suben; si falla uno, los anteriores se quedan subidos y te
            digo cuál fue.
          </p>
        </div>
      )}

      <p className="text-[10px] leading-relaxed text-muted-foreground">
        Las carpetas se llenan de 10 en 10: al llegar al 11 se abre la siguiente
        sola. Después se usa igual que un producto del curso — textos, caption,
        voz y vídeo.
      </p>
      </>
      )}
    </section>
  );
}
