"use client";

import { Loader2, Sparkles, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import {
  archivoLoteUrl,
  subirUno,
  useConfirmarLote,
  useRepartirLote,
  type LoteItem,
} from "@/lib/queries/nichoPovBof";
import { buildPhotoUrl } from "@/lib/queries/nichoPovBof";
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
  const repartir = useRepartirLote(root);
  const confirmar = useConfirmarLote(root);
  // Por dónde va la subida: qué fichero y su porcentaje.
  const [progreso, setProgreso] = useState<{ n: number; total: number; pct: number } | null>(null);
  const [reconociendo, setReconociendo] = useState(false);
  // Las fotos de producto salen del nicho del POV BOF también en el Largo:
  // las carpetas son las mismas.
  const fotoUrl = (s: string, f: string, id: string) => buildPhotoUrl(s, f, id, 160);
  const [abierto, setAbierto] = useState(false);
  const [reparto, setReparto] = useState<LoteItem[] | null>(null);
  const [sexo, setSexo] = useState<"auto" | "hombre" | "mujer">("auto");

  const conFoto = productos.filter((p) => p.clean_photo_id);

  /** Sube la tanda con progreso de verdad y luego pide el reparto.
   *
   *  Antes iba todo en una petición y el botón decía "subiendo y reconociendo"
   *  durante minutos, sin saber si quedaba mucho. Ahora se ve por dónde va:
   *  "vídeo 2 de 3 · 47%".
   */
  async function enviar(files: File[]) {
    if (!files.length) return;
    try {
      const tokens: string[] = [];
      const nombres = new Map<string, string>();
      for (const [i, file] of files.entries()) {
        setProgreso({ n: i + 1, total: files.length, pct: 0 });
        const tok = await subirUno({
          source, folder, file, root,
          onProgreso: (pct) => setProgreso({ n: i + 1, total: files.length, pct }),
        });
        tokens.push(tok);
        // El servidor solo conoce el token; el nombre de verdad lo tenemos
        // aquí y es lo que hay que enseñar al repasar.
        nombres.set(tok, file.name);
      }
      // Se limpia el progreso ANTES de reconocer: si no, el botón se quedaba
      // clavado en "Vídeo 3 de 3 · 100%" mientras la IA pensaba, que es la
      // parte que más tarda.
      setProgreso(null);
      setReconociendo(true);
      const r = await repartir.mutateAsync({ source, folder, tokens });
      setReparto(r.items.map((x) => ({ ...x, archivo: nombres.get(x.token) ?? x.archivo })));
      toast.success(
        `${r.reconocidos}/${r.items.length} vídeos reconocidos. Repasa y confirma.`,
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setProgreso(null);
      setReconociendo(false);
    }
  }

  const listos = (reparto ?? []).filter((i) => i.producto).length;

  function cambiar(i: number, producto: string) {
    setReparto((prev) => (prev ?? []).map((x, n) => (n === i ? { ...x, producto } : x)));
  }

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
            {progreso ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Vídeo{" "}
                {progreso.n} de {progreso.total} · {progreso.pct}%
              </>
            ) : reconociendo ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reconociendo los
                productos…
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
              disabled={Boolean(progreso) || reconociendo}
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
              {reparto.map((it, i) => {
                const asignado = conFoto.find((p) => p.producto === it.producto);
                return (
                  <div
                    key={it.token}
                    className={`space-y-1.5 rounded-lg border p-2 ${
                      it.producto ? "border-border/60" : "border-amber-500/50 bg-amber-500/5"
                    }`}
                  >
                    <div className="flex gap-2">
                      {/* El vídeo, para poder verlo: cuando no lo reconoce, el
                          nombre del fichero no dice absolutamente nada. */}
                      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                      <video
                        src={archivoLoteUrl(root, it.token)}
                        controls
                        preload="metadata"
                        playsInline
                        className="h-24 w-16 shrink-0 rounded border border-border/60 bg-black object-cover"
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <p className="truncate text-[10px] text-muted-foreground">
                          {it.archivo}
                        </p>
                        {asignado ? (
                          <div className="flex items-center gap-1.5">
                            {asignado.clean_photo_id && (
                              /* eslint-disable-next-line @next/next/no-img-element */
                              <img
                                src={fotoUrl(source, folder, asignado.clean_photo_id)}
                                alt={asignado.producto}
                                className="h-10 w-10 rounded border border-emerald-500/60 object-cover"
                              />
                            )}
                            <span className="min-w-0 flex-1 truncate text-[11px] font-semibold">
                              {asignado.producto} · {asignado.titulo || "sin título"}
                            </span>
                          </div>
                        ) : (
                          <p className="text-[10px] text-amber-500">
                            No lo ha reconocido: elígelo abajo o déjalo fuera.
                          </p>
                        )}
                        {it.por_que && (
                          <p className="text-[10px] text-muted-foreground">{it.por_que}</p>
                        )}
                      </div>
                    </div>

                    {/* Las fotos de los productos, para elegir mirando y no
                        leyendo. La asignada va marcada. */}
                    <div className="flex gap-1 overflow-x-auto pb-1">
                      <button
                        type="button"
                        onClick={() => cambiar(i, "")}
                        className={`shrink-0 rounded border px-2 py-1 text-[10px] ${
                          it.producto
                            ? "border-border/60 text-muted-foreground"
                            : "border-amber-500 text-amber-500"
                        }`}
                      >
                        fuera
                      </button>
                      {conFoto.map((p) => (
                        <button
                          key={p.producto}
                          type="button"
                          onClick={() => cambiar(i, p.producto)}
                          title={`${p.producto} · ${p.titulo ?? ""}`}
                          className={`relative shrink-0 rounded border ${
                            it.producto === p.producto
                              ? "border-emerald-500 ring-1 ring-emerald-500"
                              : "border-border/60"
                          }`}
                        >
                          {p.clean_photo_id ? (
                            /* eslint-disable-next-line @next/next/no-img-element */
                            <img
                              src={fotoUrl(source, folder, p.clean_photo_id)}
                              alt={p.producto}
                              className="h-12 w-12 rounded object-cover"
                            />
                          ) : (
                            <span className="flex h-12 w-12 items-center justify-center text-[10px]">
                              {p.producto}
                            </span>
                          )}
                          <span className="absolute bottom-0 left-0 rounded-br rounded-tl bg-black/70 px-1 text-[9px] text-white">
                            {p.producto}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}

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
