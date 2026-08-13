"use client";

import { Loader2, Sparkles, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  useConfirmarLote,
  useSubirLote,
  type LoteItem,
} from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

/** Subir los vídeos de una carpeta de golpe y que cada uno vaya a su producto.
 *
 *  El vídeo se genera fuera (Magnific, Veo3, Kling) y vuelve con un nombre que
 *  no dice nada, así que había que subirlos de uno en uno a su ficha. Aquí se
 *  sueltan todos, la IA los reparte mirando los fotogramas y el operador solo
 *  repasa.
 *
 *  Lo importante del repaso: la IA acierta de sobra con productos distintos,
 *  pero con colchones o sofás gemelos se equivoca, y cuando se equivoca lo hace
 *  con total seguridad. Por eso esto PROPONE y no monta nada hasta que se
 *  confirma — y cuando no lo tiene claro deja el vídeo sin asignar en vez de
 *  colocarlo en cualquier sitio.
 */
export function SubidaMasiva({
  source,
  folder,
  productos,
  root = "/api/v1/nicho-pov-bof",
}: {
  source: string;
  folder: string;
  /** Solo se usan el número, el título y si tiene foto: sirve igual la ficha
   *  del POV BOF que la del Largo. */
  productos: Pick<ProductoItem, "producto" | "titulo" | "clean_photo_id">[];
  /** Raíz de la API del nicho. En el Largo cada producto lleva dos clips y de
   *  eso se encarga su endpoint, no esta pantalla. */
  root?: string;
}) {
  const subir = useSubirLote(root);
  const confirmar = useConfirmarLote(root);
  const [abierto, setAbierto] = useState(false);
  const [reparto, setReparto] = useState<LoteItem[] | null>(null);
  const [sexo, setSexo] = useState<"auto" | "hombre" | "mujer">("auto");

  const conFoto = productos.filter((p) => p.clean_photo_id);

  function enviar(files: File[]) {
    if (!files.length) return;
    subir.mutate(
      // Sin lista: se compara contra toda la carpeta. Marcar antes a qué
      // productos ibas era un paso más para ahorrar poco, y si te dejabas uno
      // su vídeo se quedaba sin sitio.
      { source, folder, productos: [], files },
      {
        onSuccess: (r) => {
          setReparto(r.items);
          toast.success(
            `${r.reconocidos}/${r.items.length} vídeos reconocidos. Repasa y confirma.`,
          );
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const listos = (reparto ?? []).filter((i) => i.producto).length;

  return (
    <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <Sparkles className="h-4 w-4 text-emerald-500" /> Subir todos los vídeos
        </span>
        <span className="text-[11px] text-muted-foreground">{abierto ? "▾" : "▸"}</span>
      </button>

      {abierto && (
        <div className="space-y-2">
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Suelta los vídeos de la carpeta y se reparten solos. No hace falta
            que estén todos: los productos sin vídeo se quedan como están, y si
            alguno no se reconoce lo asignas tú. Repasas y confirmas.
          </p>

          <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600">
            {subir.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo y
                reconociendo…
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" /> Elegir vídeos
              </>
            )}
            <input
              type="file"
              accept="video/*"
              multiple
              disabled={subir.isPending}
              className="hidden"
              onChange={(e) => {
                const f = Array.from(e.target.files ?? []);
                e.target.value = "";
                enviar(f);
              }}
            />
          </label>

          {reparto && (
            <div className="space-y-1.5">
              {reparto.map((it, i) => (
                <div
                  key={it.token}
                  className={`space-y-1 rounded-lg border p-2 ${
                    it.producto ? "border-border/60" : "border-amber-500/50 bg-amber-500/5"
                  }`}
                >
                  <p className="truncate text-[10px] text-muted-foreground">
                    {it.archivo}
                  </p>
                  <div className="flex items-center gap-1.5">
                    <select
                      value={it.producto}
                      onChange={(e) => {
                        const v = e.target.value;
                        setReparto((prev) =>
                          (prev ?? []).map((x, n) =>
                            n === i ? { ...x, producto: v } : x,
                          ),
                        );
                      }}
                      className="flex-1 rounded-md border border-border/60 bg-background px-2 py-1 text-xs"
                    >
                      <option value="">— sin asignar —</option>
                      {conFoto.map((p) => (
                        <option key={p.producto} value={p.producto}>
                          {p.producto} · {(p.titulo || "sin título").slice(0, 34)}
                        </option>
                      ))}
                    </select>
                  </div>
                  {it.por_que && (
                    <p className="text-[10px] text-muted-foreground">{it.por_que}</p>
                  )}
                  {!it.producto && (
                    <p className="text-[10px] text-amber-500">
                      No lo ha reconocido: elígelo tú o déjalo fuera.
                    </p>
                  )}
                </div>
              ))}

              <div className="flex rounded-md border border-border/60 p-0.5 text-[11px]">
                {(["auto", "hombre", "mujer"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSexo(s)}
                    className={`flex-1 rounded px-1.5 py-1 transition ${
                      sexo === s
                        ? "bg-emerald-500 font-semibold text-white"
                        : "text-muted-foreground"
                    }`}
                  >
                    {s === "auto" ? "🖐️ Auto" : s === "hombre" ? "👨 Hombre" : "👩 Mujer"}
                  </button>
                ))}
              </div>

              <button
                type="button"
                disabled={confirmar.isPending || !listos}
                onClick={() =>
                  confirmar.mutate(
                    {
                      source,
                      folder,
                      items: (reparto ?? [])
                        .filter((i) => i.producto)
                        .map((i) => ({ token: i.token, producto: i.producto })),
                      sexo,
                      con_gancho: true,
                      con_titulo: true,
                      con_cta: true,
                      con_flecha: true,
                    },
                    {
                      onSuccess: (r) => {
                        toast.success(`${r.encolados} vídeo(s) en la cola, editando…`);
                        for (const m of r.mensajes) toast.info(m);
                        setReparto(null);
                      },
                      onError: (e) =>
                        toast.error(e instanceof ApiError ? e.message : String(e)),
                    },
                  )
                }
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
              >
                {confirmar.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Encolando…
                  </>
                ) : (
                  <>Mandar a editar ({listos})</>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
