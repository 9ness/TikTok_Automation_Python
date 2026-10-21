"use client";

import { Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { AltaMiProducto } from "@/components/tiktok-shop-ai-pro/AltaMiProducto";
import { CajaPrioridades } from "@/components/tiktok-shop-ai-pro/Marcas";
import { CajaReembolsables } from "@/components/tiktok-shop-ai-pro/Reembolsable";
import { Caja, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { useFolders, useSources } from "@/lib/queries/nichoPovBof";

/** Cuántos productos caben en una carpeta (`MIS_PRODUCTOS_POR_CARPETA`). */
const POR_CARPETA = 10;
const NUEVA = "__nueva__";

/** «Subir productos»: alta de los productos FÍSICOS de cada cuenta (los que se
 *  tienen en casa y se graban de verdad). El backend ya filtra el catálogo por
 *  usuario: ness/nestor2 ven el suyo y Ana el suyo (`usuarios` en SOURCES).
 *  Después se trabajan desde cualquier nicho (POV BOF, Largo, réplicas). */
export default function SubirProductosPage() {
  const fuentes = useSources().data?.items ?? [];
  // Los físicos de la cuenta y, si la cuenta lo tiene, «Muestras productos».
  // En los dos el alta deja marcar la muestra como reembolsable.
  const fisicos = fuentes.filter(
    (f) => f.slug.startsWith("productos_fisicos") || f.slug === "mis_productos",
  );
  const [source, setSource] = useState("");
  const [carpeta, setCarpeta] = useState("");
  useEffect(() => {
    if (!source && fisicos[0]) setSource(fisicos[0].slug);
  }, [fisicos, source]);
  const carpetas = (useFolders(source).data?.items ?? []).filter((c) => !c.virtual);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-3 p-3 pb-24 sm:space-y-4">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Upload className="h-5 w-5 shrink-0 text-emerald-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Subir productos</h1>
            <p className="text-[11px] text-muted-foreground">
              Tus productos físicos o tus muestras: foto limpia, ficha y enlace de TikTok Shop
            </p>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Lo que subas aquí sale en el catálogo «📦 Productos físicos» de tu cuenta (nadie más lo
          ve) o en «Muestras productos», y se usa desde POV BOF, POV BOF Largo o para replicar un
          viral. Si lo tienes en casa, va a Productos físicos; Muestras es para lo que se trabaja
          solo con IA. En los dos puedes marcarla como reembolsable (💸) al subirla.
        </p>
      </header>

      <Caja icono="📁" titulo="Dónde se guarda" hint="Elige carpeta o deja que vaya a la que toca">
        {fisicos.length > 1 && (
          <>
            <Sub>Catálogo</Sub>
            <div className="flex flex-wrap gap-1.5">
              {fisicos.map((f) => (
                <button
                  key={f.slug}
                  type="button"
                  onClick={() => {
                    setSource(f.slug);
                    setCarpeta("");
                  }}
                  className={`rounded-full border px-2.5 py-1 text-[11px] ${
                    source === f.slug ? "border-emerald-500 bg-emerald-500/10" : "border-border/60"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </>
        )}
        {!fisicos.length && (
          <p className="text-[11px] text-muted-foreground">
            Tu cuenta no tiene catálogo de productos físicos.
          </p>
        )}
        <Sub>Carpeta</Sub>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setCarpeta("")}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${
              carpeta === "" ? "border-emerald-500 bg-emerald-500/10" : "border-border/60"
            }`}
          >
            Automática
          </button>
          {carpetas.map((c) => {
            const llena = (c.total ?? 0) >= POR_CARPETA;
            return (
              <button
                key={c.name}
                type="button"
                disabled={llena}
                onClick={() => setCarpeta(c.name)}
                className={`truncate rounded-full border px-2.5 py-1 text-[11px] disabled:opacity-40 ${
                  carpeta === c.name ? "border-emerald-500 bg-emerald-500/10" : "border-border/60"
                }`}
              >
                {c.name} · {c.total ?? 0}/{POR_CARPETA}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setCarpeta(NUEVA)}
            className={`rounded-full border px-2.5 py-1 text-[11px] ${
              carpeta === NUEVA ? "border-emerald-500 bg-emerald-500/10" : "border-border/60"
            }`}
          >
            ＋ Carpeta nueva
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground">
          {carpeta === ""
            ? "Va a la última carpeta con hueco; al llegar a 10 se abre la siguiente sola."
            : carpeta === NUEVA
              ? "Se abre una carpeta nueva y todo lo que subas ahora va a ella."
              : `Va a «${carpeta}».`}
        </p>
      </Caja>

      <CajaPrioridades />
      <CajaReembolsables source={source} />

      {source && (
        <AltaMiProducto
          key={`${source}|${carpeta}`}
          source={source}
          carpeta={carpeta}
          abiertoInicial
          onCreado={(c) => {
            if (carpeta === NUEVA) setCarpeta(c);
          }}
        />
      )}
    </div>
  );
}
