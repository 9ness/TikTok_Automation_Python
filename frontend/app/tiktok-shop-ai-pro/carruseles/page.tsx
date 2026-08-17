"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Flame,
  GalleryHorizontalEnd,
  Loader2,
  ShoppingBag,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { horaCorta } from "@/lib/hora";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import {
  buildFotoCarruselUrl,
  buildReferenciaUrl,
  useBorrarFotoCarrusel,
  useBorrarReferencia,
  useCambiarEscenario,
  useChicasPendientes,
  useClasificarCarpeta,
  useCompletarCarpetaCarrusel,
  useEditarMensaje,
  useEscribirMensajes,
  useEstadoCarruseles,
  useFoldersCarruseles,
  useMarcarApto,
  useMarcarSubidoCarrusel,
  usePromptsCarruseles,
  useQuemarTexto,
  useReferencias,
  useSubidosCarruseles,
  useSubirReferencia,
  useSubirChicas,
  useSubirFotoCarrusel,
  type EscenarioPrompt,
  type FotosCarrusel,
  type ProductoCarrusel,
} from "@/lib/queries/nichoCarruseles";
// El catálogo es EL MISMO del Nicho POV BOF (igual que en Creativos Pro):
// fuentes, carpetas, fotos, textos, hashtags y escaparate. Duplicarlo habría
// significado volver a pagar la extracción de textos con Gemini.
import {
  buildCleanPhotoDownloadUrl,
  buildPhotoUrl,
  useExtraerTextos,
  useHashtags,
  useProductos,
  useSources,
} from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

const VACIO: ProductoCarrusel = {
  categoria: "",
  apto: false,
  apto_manual: null,
  escenario: "generico",
  escenario_manual: "",
  mensaje1: "",
  mensaje2: "",
  fotos: { chica: "", chica_txt: "", producto: "", producto_txt: "" },
  subido_at: 0,
};

/** Cómo se lee cada categoría en la tarjeta. Las tres últimas son productos
 *  grandes: valen para carrusel, pero con la chica EN el sitio del producto. */
const CATEGORIA_LABEL: Record<string, string> = {
  belleza: "💄 belleza",
  suplementos: "💊 suplementos",
  descanso: "🛏️ dormitorio",
  salon: "🛋️ salón",
  exterior: "🌳 exterior",
};

export default function CarruselesPage() {
  const sources = useSources();
  const [source, setSource] = useEstadoRecordado("carruseles:fuente", "aleatorios_1");
  const folders = useFoldersCarruseles(source);
  const [picked, setPicked] = useEstadoRecordado<string | null>("carruseles:carpeta", null);
  const folder = picked ?? folders.data?.current ?? null;

  const productos = useProductos(source, folder);
  const estado = useEstadoCarruseles(source, folder);
  const prompts = usePromptsCarruseles();
  const pendientes = useChicasPendientes();

  const extraer = useExtraerTextos();
  const clasificar = useClasificarCarpeta(source, folder);
  const escribir = useEscribirMensajes(source, folder);
  const completar = useCompletarCarpetaCarrusel();
  const subirChicas = useSubirChicas();
  const quemar = useQuemarTexto(source, folder);
  const subidos = useSubidosCarruseles(source, folder);
  const marcarSubido = useMarcarSubidoCarrusel(source, folder);

  const [verTodos, setVerTodos] = useEstadoRecordado("carruseles:vertodos", false);
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const [bajando, setBajando] = useState("");
  // Qué escenario se está subiendo: hay una tanda por escenario y sin esto se
  // pintarían las cuatro girando a la vez.
  const [tandaEnCurso, setTandaEnCurso] = useState("");

  const items = productos.data ?? [];
  const porProducto = estado.data?.productos ?? {};
  const horasSubida = subidos.data ?? {};
  const conTexto = items.filter((p) => p.titulo).length;
  const aptos = items.filter((p) => (porProducto[p.producto] ?? VACIO).apto);
  const visibles = verTodos ? items : aptos;
  const conMensaje = aptos.filter((p) => porProducto[p.producto]?.mensaje1).length;
  const listos = aptos.filter((p) => {
    const f = porProducto[p.producto]?.fotos;
    return f?.chica_txt && f?.producto_txt;
  }).length;
  const hecha = folders.data?.items.find((f) => f.name === folder)?.completed ?? false;
  const clasificada = estado.data?.clasificada ?? false;

  /** Baja las dos fotos de un producto, en orden (1 chica, 2 producto). */
  async function descargarPar(producto: string, fotos: FotosCarrusel) {
    if (!folder) return;
    const cola: [keyof FotosCarrusel, string][] = [
      ["chica_txt", fotos.chica_txt],
      ["producto_txt", fotos.producto_txt],
    ];
    setBajando(producto);
    for (const [i, [tipo, version]] of cola.entries()) {
      if (!version) continue;
      const a = document.createElement("a");
      a.href = buildFotoCarruselUrl(source, folder, producto, tipo, version, true);
      a.download = `${folder}_${producto}_${i + 1}`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Un respiro entre las dos: varias descargas a la vez se cancelan solas
      // en el navegador del móvil (mismo motivo que en Creativos Pro).
      if (i === 0) await new Promise((r) => setTimeout(r, 600));
    }
    setBajando("");
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <GalleryHorizontalEnd className="h-5 w-5 shrink-0 text-cyan-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Carruseles</h1>
            <p className="text-[11px] text-muted-foreground">
              Dos fotos: chica sorprendida + producto, con el texto quemado
            </p>
          </div>
        </div>
      </header>

      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="Solo los productos donde la chica puede estar EN el sitio: belleza, suplementos, dormitorio, salón y exterior."
        extra={
          folders.data
            ? `${folders.data.done}/${folders.data.total} hechas · ${folders.data.aptos} aptos`
            : undefined
        }
      >
        <Sub>Catálogo</Sub>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => {
                setSource(s.slug);
                setPicked(null);
              }}
              className={`truncate rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                source === s.slug
                  ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <Sub>Carpetas</Sub>
        {/* Cada carpeta enseña CUÁNTOS aptos tiene. Filtrando a belleza y
            suplementos la mayoría se queda en dos o tres productos y algunas en
            cero: sin este número se abren una a una para nada. */}
        <div className="flex flex-wrap gap-1">
          {(folders.data?.items ?? []).map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => setPicked(f.name)}
              className={`truncate rounded border px-2 py-1 text-[10px] transition ${
                folder === f.name
                  ? f.completed
                    ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                    : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                  : f.completed
                    ? "border-emerald-500/40 text-emerald-500"
                    : f.clasificada && !f.aptos
                      ? "border-border/40 text-muted-foreground/50"
                      : "border-border/60 text-muted-foreground"
              }`}
            >
              {f.completed && "✓ "}
              {f.name}
              {f.clasificada ? (
                <span className="ml-1 opacity-70">· {f.aptos}</span>
              ) : null}
            </button>
          ))}
        </div>

        {folder && (
          <button
            type="button"
            disabled={completar.isPending}
            onClick={() =>
              completar.mutate(
                { source, folder, completed: !hecha },
                { onError: (e) => toast.error(err(e)) },
              )
            }
            className={`flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold transition ${
              hecha
                ? "border-border/60 text-muted-foreground"
                : "border-emerald-500 bg-emerald-500/15 text-emerald-500"
            }`}
          >
            <Check className="h-3.5 w-3.5" />
            {hecha ? "Desmarcar carpeta" : "Carpeta completada"}
          </button>
        )}
      </Caja>

      <section className="space-y-2">
        <div className="flex items-center gap-2 px-1">
          <Sparkles className="h-4 w-4 shrink-0 text-fuchsia-500" />
          <p className="text-sm font-semibold">Cómo se hace un carrusel</p>
          {folder ? (
            <span className="ml-auto text-[10px] text-muted-foreground">{folder}</span>
          ) : null}
        </div>

        <Paso
          n={1}
          color="violeta"
          titulo="Preparar la carpeta"
          hint="Lee las fichas con IA y decide qué productos valen: solo belleza y suplementación."
          extra={`${aptos.length} aptos`}
        >
          <button
            type="button"
            disabled={extraer.isPending || !folder}
            onClick={() =>
              extraer.mutate(
                { source, folder: folder! },
                {
                  onSuccess: () => toast.success("Textos extraídos"),
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
          >
            {extraer.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Extrayendo textos…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" /> Obtener textos ({conTexto}/{items.length})
              </>
            )}
          </button>

          <button
            type="button"
            disabled={clasificar.isPending || !folder || !conTexto}
            onClick={() =>
              clasificar.mutate(undefined, {
                onSuccess: (r) =>
                  toast.success(
                    `${
                      Object.values(r.productos).filter((p) => p.apto).length
                    } productos valen para carrusel`,
                  ),
                onError: (e) => toast.error(err(e)),
              })
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 bg-violet-500/10 px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/20 disabled:opacity-50"
          >
            {clasificar.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Mirando la carpeta…
              </>
            ) : (
              <>🔎 {clasificada ? "Volver a filtrar" : "Filtrar belleza y suplementos"}</>
            )}
          </button>

          <button
            type="button"
            disabled={escribir.isPending || !aptos.length}
            onClick={() =>
              escribir.mutate(undefined, {
                onSuccess: (r) => toast.success(`${r.escritos} productos con mensajes`),
                onError: (e) => toast.error(err(e)),
              })
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 bg-violet-500/10 px-3 py-2 text-xs font-semibold text-violet-400 transition hover:bg-violet-500/20 disabled:opacity-50"
          >
            {escribir.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Escribiendo mensajes…
              </>
            ) : (
              <>✍️ Escribir los dos mensajes ({conMensaje}/{aptos.length})</>
            )}
          </button>

          <div className="grid grid-cols-2 gap-1.5">
            <div
              className={`flex items-center justify-center gap-1.5 truncate rounded-lg border px-2 py-1.5 text-[11px] font-semibold ${
                listos === aptos.length && aptos.length > 0
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 text-muted-foreground"
              }`}
            >
              <span className="truncate">🖼️ Listos {listos}/{aptos.length}</span>
            </div>
            <button
              type="button"
              onClick={() => setVerEscaparate(true)}
              className="flex items-center justify-center gap-1.5 truncate rounded-lg border border-sky-500/50 bg-sky-500/10 px-2 py-1.5 text-[11px] font-semibold text-sky-500 transition hover:bg-sky-500/20"
            >
              <span className="truncate">🏪 Escaparate</span>
            </button>
          </div>
        </Paso>

        <Paso
          n={2}
          color="fucsia"
          titulo="La tanda de chicas (foto 1)"
          hint="La foto 1 no depende del producto, solo del SITIO: en casa, en la cama, en el sofá o fuera. Se generan de golpe en Flow para todos los catálogos."
          extra={pendientes.data ? `faltan ${pendientes.data.faltan}` : undefined}
        >
          <p className="text-center text-[10px] text-muted-foreground">
            En Flow: adjunta la foto de referencia + el prompt del escenario, en formato{" "}
            <span className="font-semibold text-cyan-500">
              {prompts.data?.formato ?? "9:16"}
            </span>
            . Cada escenario va por su lado: una chica del sofá no vale para un producto
            de jardín.
          </p>

          <Referencia
            tipo="chica"
            titulo="Foto de referencia (chica)"
            hint="Se adjunta SIEMPRE en Flow junto al prompt. Es la del curso; puedes poner otra."
          />

          {/* Una tarjeta por escenario: su cuenta, su prompt y su tanda. */}
          {(prompts.data?.escenarios ?? []).map((esc) => (
            <TandaEscenario
              key={esc.clave}
              escenario={esc}
              faltan={pendientes.data?.por_escenario?.[esc.clave] ?? 0}
              subiendo={subirChicas.isPending && tandaEnCurso === esc.clave}
              onSubir={(files) => {
                setTandaEnCurso(esc.clave);
                subirChicas.mutate(
                  { escenario: esc.clave, files },
                  {
                    onSuccess: (r) =>
                      toast.success(
                        `${r.asignadas} chicas repartidas` +
                          (r.sobran_fotos ? ` · sobran ${r.sobran_fotos}` : "") +
                          (r.faltan ? ` · siguen faltando ${r.faltan}` : ""),
                      ),
                    onError: (e2) => toast.error(err(e2)),
                    onSettled: () => setTandaEnCurso(""),
                  },
                );
              }}
            />
          ))}

          {/* El quemado de la foto 1 es masivo por carpeta: mismo gesto para
              las diez, que es justo lo que hace que esto salga a cuenta. */}
          <button
            type="button"
            disabled={quemar.isPending || !folder || !conMensaje}
            onClick={() =>
              quemar.mutate(
                { tipo: "chica" },
                {
                  onSuccess: (r) =>
                    toast.success(
                      `${r.quemadas} fotos con texto` +
                        (r.saltados.length ? ` · saltadas: ${r.saltados.join(", ")}` : ""),
                    ),
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-fuchsia-500/50 bg-fuchsia-500/10 px-3 py-2 text-xs font-semibold text-fuchsia-400 transition hover:bg-fuchsia-500/20 disabled:opacity-50"
          >
            {quemar.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Escribiendo…
              </>
            ) : (
              <>
                <Flame className="h-3.5 w-3.5" /> Poner el mensaje 1 a toda la carpeta
              </>
            )}
          </button>
        </Paso>

        <Paso
          n={3}
          color="esmeralda"
          titulo="La foto del producto (foto 2)"
          hint="Esta sí es de cada producto. En Flow van DOS imágenes: la de referencia (la composición) y la foto limpia del producto."
        >
          <Referencia
            tipo="producto"
            titulo="Foto de referencia (composición)"
            hint="La PRIMERA imagen de Flow: un producto colocado en un sitio bonito. El curso no da ninguna, elige tú una que te guste."
          />
          <button
            type="button"
            disabled={!prompts.data}
            onClick={() => {
              navigator.clipboard.writeText(prompts.data?.producto ?? "");
              toast.success("Prompt copiado");
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Prompt producto (Flow)
          </button>
          <p className="text-center text-[10px] text-muted-foreground">
            La SEGUNDA imagen es la foto limpia de cada producto: se baja desde su
            tarjeta, abajo.
          </p>
        </Paso>

        <Paso
          n={4}
          color="azul"
          titulo="Publicar"
          hint="Baja las dos fotos en orden, súbelas como carrusel y pega el caption. Marca cada uno al publicarlo."
        >
          <button
            type="button"
            onClick={() => setVerVendidos(true)}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-500 transition hover:bg-amber-500/20"
          >
            <ShoppingBag className="h-3.5 w-3.5" />
            Ver qué productos vendieron
          </button>
        </Paso>
      </section>

      {verVendidos && <VendidosModal onClose={() => setVerVendidos(false)} />}
      {verEscaparate && folder && (
        <EscaparateModal
          source={source}
          folder={folder}
          productos={items}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        {(productos.isLoading || estado.isLoading) && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}

        {/* Por defecto solo los aptos: son dos o tres de diez y el resto solo
            estorba. Se pueden ver todos para forzar alguno a mano. */}
        <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
          <input
            type="checkbox"
            className="h-4 w-4 accent-fuchsia-500"
            checked={verTodos}
            onChange={(e) => setVerTodos(e.target.checked)}
          />
          Ver también los que no valen
          <span className="ml-auto text-[10px] text-muted-foreground">
            {visibles.length}/{items.length}
          </span>
        </label>

        {!visibles.length && !productos.isLoading && (
          <p className="py-4 text-center text-[11px] text-muted-foreground">
            {clasificada
              ? "En esta carpeta no hay nada de belleza ni suplementos."
              : "Pulsa «Filtrar belleza y suplementos» para saber cuáles valen."}
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {visibles.map((p) => (
            <CarruselCard
              key={`${source}-${folder}-${p.producto}`}
              source={source}
              folder={folder!}
              producto={p}
              datos={porProducto[p.producto] ?? VACIO}
              bajando={bajando === p.producto}
              subido={Boolean(horasSubida[p.producto])}
              subidoAt={horasSubida[p.producto] ?? 0}
              onDescargar={() => descargarPar(p.producto, (porProducto[p.producto] ?? VACIO).fotos)}
              onSubido={(v) =>
                marcarSubido.mutate(
                  { producto: p.producto, uploaded: v },
                  { onError: (e) => toast.error(err(e)) },
                )
              }
            />
          ))}
        </div>
      </section>
    </div>
  );
}

/** La foto que hay que ADJUNTAR en Flow junto al prompt.
 *
 *  Los dos prompts del curso son de imagen-a-imagen ("genera una imagen
 *  similar", "cambia el producto de la primera imagen por el de la segunda"),
 *  así que sin referencia no hay nada que generar. La de la chica sale del
 *  Drive del curso; la del producto la pone el operador. */
function Referencia({
  tipo,
  titulo,
  hint,
}: {
  tipo: "chica" | "producto";
  titulo: string;
  hint: string;
}) {
  const referencias = useReferencias();
  const subir = useSubirReferencia();
  const borrar = useBorrarReferencia();
  const ref = useRef<HTMLInputElement>(null);
  const estado = referencias.data?.[tipo];
  const url = estado?.hay ? buildReferenciaUrl(tipo, estado.version) : null;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/60 p-2">
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={titulo}
            loading="lazy"
            className="h-14 w-14 rounded-md object-cover"
          />
        </a>
      ) : (
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border border-dashed border-border/60 text-[9px] text-muted-foreground">
          sin foto
        </div>
      )}

      <div className="min-w-0 flex-1 space-y-1">
        <p className="truncate text-[11px] font-semibold">{titulo}</p>
        <p className="text-[10px] leading-snug text-muted-foreground">{hint}</p>
        <input
          ref={ref}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            subir.mutate(
              { tipo, file },
              {
                onSuccess: () => toast.success("Referencia cambiada"),
                onError: (e2) => toast.error(err(e2)),
              },
            );
          }}
        />
        <div className="flex flex-wrap gap-1">
          {estado?.hay && (
            <a
              href={buildReferenciaUrl(tipo, estado.version, true)}
              className="flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] transition hover:border-foreground/30"
            >
              <Download className="h-3 w-3" /> Bajar
            </a>
          )}
          <button
            type="button"
            disabled={subir.isPending}
            onClick={() => ref.current?.click()}
            className="flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] transition hover:border-foreground/30 disabled:opacity-50"
          >
            {subir.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Upload className="h-3 w-3" />
            )}
            {estado?.hay ? "Cambiar" : "Subir"}
          </button>
          {estado?.propia && tipo === "chica" && (
            <button
              type="button"
              onClick={() =>
                borrar.mutate(tipo, { onError: (e) => toast.error(err(e)) })
              }
              className="rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-foreground/30"
            >
              Volver a la del curso
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Un escenario de chica: cuántas faltan, su prompt de Flow y su tanda.
 *
 *  Van por separado porque una chica del sofá no vale para un producto de
 *  jardín: el reparto es dentro del escenario. */
function TandaEscenario({
  escenario,
  faltan,
  subiendo,
  onSubir,
}: {
  escenario: EscenarioPrompt;
  faltan: number;
  subiendo: boolean;
  onSubir: (files: File[]) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div
      className={`space-y-1.5 rounded-lg border p-2 ${
        faltan ? "border-fuchsia-500/40 bg-fuchsia-500/5" : "border-border/60 opacity-70"
      }`}
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-semibold">{escenario.label}</p>
          <p className="truncate text-[10px] text-muted-foreground">{escenario.para}</p>
        </div>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold ${
            faltan ? "bg-fuchsia-500/20 text-fuchsia-400" : "text-muted-foreground"
          }`}
        >
          {faltan}
        </span>
      </div>

      <input
        ref={ref}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onSubir(files);
        }}
      />
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(escenario.prompt);
            toast.success("Prompt copiado");
          }}
          className="flex items-center justify-center gap-1 rounded-md border border-border/60 bg-card px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
        >
          <ClipboardCopy className="h-3.5 w-3.5" /> Prompt
        </button>
        <button
          type="button"
          disabled={subiendo || !faltan}
          onClick={() => ref.current?.click()}
          className="flex items-center justify-center gap-1 rounded-md bg-fuchsia-500 px-2 py-1.5 text-[11px] font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-40"
        >
          {subiendo ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Subir tanda
        </button>
      </div>
    </div>
  );
}

/** Un producto: sus dos mensajes, sus dos fotos y el botón de bajarlas. */
function CarruselCard({
  source,
  folder,
  producto: p,
  datos,
  bajando,
  subido,
  subidoAt,
  onDescargar,
  onSubido,
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
  datos: ProductoCarrusel;
  bajando: boolean;
  subido: boolean;
  subidoAt: number;
  onDescargar: () => void;
  onSubido: (v: boolean) => void;
}) {
  const hashtags = useHashtags();
  const prompts = usePromptsCarruseles();
  const marcarApto = useMarcarApto(source, folder);
  const cambiarEscenario = useCambiarEscenario(source, folder);
  const subirFoto = useSubirFotoCarrusel(source, folder);
  const quemar = useQuemarTexto(source, folder);
  const editar = useEditarMensaje(source, folder);
  const fotoRef = useRef<HTMLInputElement>(null);
  const [mensaje2, setMensaje2] = useState(datos.mensaje2);

  // Igual que en el POV BOF: al cambiar de carpeta React reutiliza la tarjeta
  // (los productos se numeran 1..10 en todas), y sin esto el campo se quedaría
  // con el texto del producto anterior.
  useEffect(() => setMensaje2(datos.mensaje2), [datos.mensaje2]);

  const limpia = p.clean_photo_id ? buildPhotoUrl(source, folder, p.clean_photo_id) : null;
  const caption = [p.caption, p.emojis, (hashtags.data ?? []).join(" ")]
    .filter(Boolean)
    .join(" ");
  const listo = Boolean(datos.fotos.chica_txt && datos.fotos.producto_txt);

  return (
    <div
      className={`space-y-2 rounded-lg border p-2 ${
        datos.apto ? "border-border/60" : "border-border/40 opacity-70"
      }`}
    >
      <div className="flex items-start gap-2">
        {limpia ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={limpia}
            alt={p.titulo ?? p.producto}
            loading="lazy"
            className="h-16 w-16 shrink-0 rounded-md object-cover"
          />
        ) : (
          <div className="h-16 w-16 shrink-0 rounded-md bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {p.producto}
            </span>
            <span className="truncate">{p.titulo ?? "sin título"}</span>
          </p>
          {datos.categoria ? (
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {CATEGORIA_LABEL[datos.categoria] ?? "— no encaja en carrusel"}
              {datos.apto_manual !== null ? " · a mano" : ""}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() =>
            marcarApto.mutate(
              { producto: p.producto, apto: datos.apto ? false : true },
              { onError: (e) => toast.error(err(e)) },
            )
          }
          className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold transition ${
            datos.apto
              ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          {datos.apto ? "Apto" : "No apto"}
        </button>
      </div>

      {/* Las dos fotos, en el orden en que se publican. */}
      <div className="grid grid-cols-2 gap-1.5">
        <FotoCarrusel
          titulo="1 · chica"
          source={source}
          folder={folder}
          producto={p.producto}
          version={datos.fotos.chica_txt || datos.fotos.chica}
          tipo={datos.fotos.chica_txt ? "chica_txt" : "chica"}
          conTexto={Boolean(datos.fotos.chica_txt)}
        />
        <FotoCarrusel
          titulo="2 · producto"
          source={source}
          folder={folder}
          producto={p.producto}
          version={datos.fotos.producto_txt || datos.fotos.producto}
          tipo={datos.fotos.producto_txt ? "producto_txt" : "producto"}
          conTexto={Boolean(datos.fotos.producto_txt)}
        />
      </div>

      {/* Dónde va la chica. Sale de la categoría, pero se puede cambiar: un
          difusor de aroma es belleza y queda mejor con la chica en el sofá. */}
      {datos.apto ? (
        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          Chica en
          <select
            value={datos.escenario}
            onChange={(e) =>
              cambiarEscenario.mutate(
                { producto: p.producto, escenario: e.target.value },
                { onError: (e2) => toast.error(err(e2)) },
              )
            }
            className="min-w-0 flex-1 truncate rounded border border-border/60 bg-background px-1.5 py-1 text-[10px]"
          >
            {(prompts.data?.escenarios ?? []).map((esc) => (
              <option key={esc.clave} value={esc.clave}>
                {esc.label}
              </option>
            ))}
          </select>
          {datos.escenario_manual ? <span title="cambiado a mano">✎</span> : null}
        </label>
      ) : null}

      {datos.mensaje1 ? (
        <p className="rounded border border-border/60 px-2 py-1 text-[10px] text-muted-foreground">
          <span className="font-semibold text-foreground">1.</span> {datos.mensaje1}
        </p>
      ) : null}

      {/* El mensaje 2 se puede corregir a mano: lleva el nombre del producto y
          es lo que más canta si el modelo lo acorta mal. */}
      <textarea
        value={mensaje2}
        onChange={(e) => setMensaje2(e.target.value)}
        onBlur={() => {
          if (mensaje2.trim() === datos.mensaje2.trim()) return;
          editar.mutate(
            { producto: p.producto, mensaje2: mensaje2 },
            { onError: (e) => toast.error(err(e)) },
          );
        }}
        rows={2}
        placeholder="Mensaje 2 (el de la foto del producto)"
        className="w-full rounded border border-border/60 bg-background px-2 py-1 text-[10px] leading-relaxed"
      />

      <input
        ref={fotoRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          subirFoto.mutate(
            { producto: p.producto, tipo: "producto", file },
            {
              onSuccess: () => toast.success("Foto 2 subida"),
              onError: (e2) => toast.error(err(e2)),
            },
          );
        }}
      />

      {/* La foto limpia del producto es la SEGUNDA imagen que pide Flow para
          generar la foto 2. Por el endpoint de descarga, no por el de ver: el
          `download` de un <a> se ignora entre orígenes distintos. */}
      <a
        href={buildCleanPhotoDownloadUrl(source, folder, p.producto, "limpia")}
        className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
      >
        <Download className="h-3.5 w-3.5" /> Bajar foto del producto (para Flow)
      </a>

      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          disabled={subirFoto.isPending}
          onClick={() => fotoRef.current?.click()}
          className="flex items-center justify-center gap-1 rounded-md border border-emerald-500/50 bg-emerald-500/10 px-2 py-1.5 text-[11px] font-semibold text-emerald-500 transition hover:bg-emerald-500/20 disabled:opacity-50"
        >
          {subirFoto.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Subir foto 2
        </button>
        <button
          type="button"
          disabled={quemar.isPending || !datos.fotos.producto || !mensaje2.trim()}
          onClick={() =>
            quemar.mutate(
              { producto: p.producto, tipo: "producto" },
              {
                onSuccess: () => toast.success("Mensaje 2 escrito"),
                onError: (e) => toast.error(err(e)),
              },
            )
          }
          className="flex items-center justify-center gap-1 rounded-md border border-fuchsia-500/50 bg-fuchsia-500/10 px-2 py-1.5 text-[11px] font-semibold text-fuchsia-400 transition hover:bg-fuchsia-500/20 disabled:opacity-50"
        >
          {quemar.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Flame className="h-3.5 w-3.5" />
          )}
          Poner mensaje 2
        </button>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="🔎 Título TikTok" text={p.titulo_tiktok_completo ?? ""} siempre />
        <CopyChip label="✍️ Caption" text={caption} siempre />
      </div>

      <div className="flex gap-1">
        <button
          type="button"
          disabled={!listo || bajando}
          onClick={onDescargar}
          className="flex flex-1 items-center justify-center gap-1 rounded-md border border-sky-500/50 bg-sky-500/10 px-2 py-1.5 text-[11px] font-semibold text-sky-500 transition hover:bg-sky-500/20 disabled:opacity-40"
        >
          {bajando ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
          Bajar las 2
        </button>
        <button
          type="button"
          onClick={() => onSubido(!subido)}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            subido
              ? "border-sky-500 bg-sky-500/15 text-sky-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          📤 Subido
          {subido && subidoAt ? (
            <span className="ml-1 font-normal opacity-80">{horaCorta(subidoAt)}</span>
          ) : null}
        </button>
      </div>
    </div>
  );
}

/** Miniatura de una de las dos fotos del carrusel (o el hueco si falta). */
function FotoCarrusel({
  titulo,
  source,
  folder,
  producto,
  version,
  tipo,
  conTexto,
}: {
  titulo: string;
  source: string;
  folder: string;
  producto: string;
  version: string;
  tipo: keyof FotosCarrusel;
  conTexto: boolean;
}) {
  const borrar = useBorrarFotoCarrusel(source, folder);
  if (!version) {
    return (
      <div className="flex aspect-[9/16] flex-col items-center justify-center rounded-md border border-dashed border-border/60 text-[10px] text-muted-foreground">
        {titulo}
        <span className="opacity-60">sin foto</span>
      </div>
    );
  }
  const url = buildFotoCarruselUrl(source, folder, producto, tipo, version);
  return (
    <div className="relative">
      <a href={url} target="_blank" rel="noopener noreferrer">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={titulo}
          loading="lazy"
          className="aspect-[9/16] w-full rounded-md object-cover"
        />
      </a>
      <span
        className={`absolute left-1 top-1 rounded px-1 text-[9px] font-semibold ${
          conTexto ? "bg-emerald-500/90 text-white" : "bg-black/70 text-white"
        }`}
      >
        {titulo}
        {conTexto ? " ✓" : ""}
      </span>
      <button
        type="button"
        title="Quitar esta foto"
        onClick={() =>
          borrar.mutate(
            { producto, tipo: tipo.startsWith("chica") ? "chica" : "producto" },
            { onError: (e) => toast.error(err(e)) },
          )
        }
        className="absolute right-1 top-1 rounded bg-black/70 p-1 text-white transition hover:bg-red-500"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  );
}
