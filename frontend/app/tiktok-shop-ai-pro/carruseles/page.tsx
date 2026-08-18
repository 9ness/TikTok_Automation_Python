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
import { fechaCorta, horaCorta } from "@/lib/hora";
import { useEstadoRecordado } from "@/lib/hooks/useEstadoRecordado";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
import { useEsPro } from "@/lib/queries/auth";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { FotoProducto } from "@/components/tiktok-shop-ai-pro/FotoProducto";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import {
  buildFotoCarruselUrl,
  buildReferenciaUrl,
  buildSueltaUrl,
  useAptos,
  useAsignarSuelta,
  useBorrarChicas,
  useBorrarFotoCarrusel,
  useBorrarSuelta,
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
  useEscaparateCarrusel,
  useFraseDesdeImagen,
  useFraseReferencia,
  useGuardarFrase,
  useListos,
  type CarruselListo,
  useMarcarSubidoCarrusel,
  useMarcarSubidoSuelto,
  usePromptsCarruseles,
  useQuemarTexto,
  useQuemarTodo,
  useReferencias,
  useSinAsignar,
  useSubidosCarruseles,
  useSubirReferencia,
  useSubirChicas,
  useSubirFotoCarrusel,
  useSubirFotos2,
  type AptoCarrusel,
  type EscenarioPrompt,
  type ProgresoTanda,
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

/** En qué sitio se recrea el producto de cada categoría. Es el MISMO mapa que
 *  `ESCENARIO_POR_CATEGORIA` del backend: aquí solo hace falta para saber qué
 *  prompt copiar al bajar un grupo de fotos. */
const ESCENARIO_POR_CATEGORIA: Record<string, string> = {
  belleza: "generico",
  suplementos: "generico",
  hogar: "casa",
  tecnologia: "generico",
  fitness: "generico",
  descanso: "cama",
  salon: "sofa",
  exterior: "exterior",
  cocina: "cocina",
  bano: "bano",
  coche: "coche",
  oficina: "escritorio",
  playa: "playa",
};

/** Cómo se lee cada categoría en la tarjeta.
 *
 *  Todas valen para carrusel; lo que cambia es DÓNDE tiene que estar la chica
 *  (ver `ESCENARIO_POR_CATEGORIA` en el backend). Lo que no está aquí es
 *  `otro`, que es lo que se queda fuera. */
const CATEGORIA_LABEL: Record<string, string> = {
  belleza: "💄 belleza",
  suplementos: "💊 suplementos",
  descanso: "🛏️ dormitorio",
  salon: "🛋️ salón",
  exterior: "🌳 exterior",
  cocina: "🍳 cocina",
  bano: "🚿 baño",
  hogar: "🧽 hogar",
  coche: "🚗 coche",
  tecnologia: "🎧 tecnología",
  oficina: "🖥️ escritorio",
  fitness: "🏋️ fitness",
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
  // Los textos son del producto y se comparten: los extrae solo el admin.
  const esPro = useEsPro();
  const clasificar = useClasificarCarpeta(source, folder);
  const escribir = useEscribirMensajes(source, folder);
  const completar = useCompletarCarpetaCarrusel();
  const subirChicas = useSubirChicas();
  const quemar = useQuemarTexto(source, folder);
  const quemarTodo = useQuemarTodo();
  const subidos = useSubidosCarruseles(source, folder);
  const marcarSubido = useMarcarSubidoCarrusel(source, folder);
  // Los aptos de TODOS los catálogos: es lo que deja trabajar por ambientes en
  // Flow (bajar todas las de dormitorio de una vez) en lugar de carpeta a
  // carpeta con dos productos en cada una.
  const todosAptos = useAptos();
  const referenciasGlobal = useReferencias();
  const referenciasCargando = referenciasGlobal.isLoading;
  const subirFotos2 = useSubirFotos2();
  const aptosGlobales = todosAptos.data?.items ?? [];
  // TODAS las categorías con productos, tengan o no fotos pendientes: así se
  // ve "2/2" cuando está terminada y "2/3" cuando el curso añade una nueva.
  const totalPorCategoria = todosAptos.data?.por_categoria ?? {};

  const [verTodos, setVerTodos] = useEstadoRecordado("carruseles:vertodos", false);
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const abrirCola = useDrawerStore((s) => s.openQueue);
  const [bajando, setBajando] = useState("");
  const [bajandoLimpias, setBajandoLimpias] = useState("");
  const [bajandoCarpeta, setBajandoCarpeta] = useState("");
  // De qué categoría son las fotos que se están subiendo: el reconocimiento se
  // acota a sus productos.
  const [categoriaSubiendo, setCategoriaSubiendo] = useState("");
  const [conMano, setConMano] = useEstadoRecordado("carruseles:conmano", false);
  const fotos2Ref = useRef<HTMLInputElement>(null);
  // Qué escenario se está subiendo: hay una tanda por escenario y sin esto se
  // pintarían las cuatro girando a la vez.
  const [tandaEnCurso, setTandaEnCurso] = useState("");
  const [progresoTanda, setProgresoTanda] = useState<ProgresoTanda | null>(null);
  const [progresoFotos2, setProgresoFotos2] = useState<ProgresoTanda | null>(null);

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

  /** El prompt de la foto 2 de esa categoría, al portapapeles.
   *
   *  Cada categoría recrea el producto en SU sitio (la cocina, el dormitorio,
   *  el coche…), así que el prompt no es uno solo: se copia el del grupo que se
   *  acaba de bajar. */
  function copiarPromptProducto(categoria: string) {
    const escenario = ESCENARIO_POR_CATEGORIA[categoria] ?? "generico";
    const esc = prompts.data?.escenarios.find((e) => e.clave === escenario);
    const texto = conMano ? esc?.prompt_producto_mano : esc?.prompt_producto;
    if (!texto) return;
    navigator.clipboard.writeText(texto);
    toast.success(`Prompt de ${CATEGORIA_LABEL[categoria] ?? categoria}`);
  }

  /** Baja las fotos limpias que se llevan a Flow para hacer la foto 2.
   *
   *  `modo` es "carpeta" (los aptos de la que tienes abierta) o una CATEGORÍA
   *  (los de esa categoría en todos los catálogos, y solo los que aún no tienen
   *  foto 2). Lo segundo es lo que permite generar en Flow por ambientes en vez
   *  de ir carpeta a carpeta con dos productos en cada una.
   *
   *  Van numeradas para que en la galería salgan en el mismo orden, y de una en
   *  una — varias descargas a la vez se cancelan solas en el móvil.
   */
  async function descargarLimpias(modo: string) {
    const lista =
      modo === "carpeta"
        ? aptos
            .filter((p) => p.clean_photo_id)
            .map((p) => ({
              source,
              folder: p.folder || folder || "",
              producto: p.producto,
            }))
        : (aptosGlobales ?? [])
            .filter((a) => a.categoria === modo && !a.tiene_foto2)
            .map((a) => ({ source: a.source, folder: a.folder, producto: a.producto }));
    if (!lista.length) {
      toast.error("No hay fotos que bajar ahí");
      return;
    }
    for (const [i, p] of lista.entries()) {
      setBajandoLimpias(`${i + 1}/${lista.length}`);
      const a = document.createElement("a");
      a.href = buildCleanPhotoDownloadUrl(p.source, p.folder, p.producto);
      const orden = String(i + 1).padStart(2, "0");
      a.download = `${orden}_${p.folder}_${p.producto}`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < lista.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    setBajandoLimpias("");
    toast.success(`${lista.length} foto(s) descargadas`);
  }

  /** Baja las dos fotos YA EDITADAS de toda la carpeta, en orden: 1 y 2 del
   *  primer producto, 1 y 2 del segundo… Así se suben al carrusel sin pararse a
   *  mirar cuál va antes. */
  async function descargarCarpetaEditada() {
    if (!folder) return;
    const cola: { producto: string; tipo: keyof FotosCarrusel; version: string }[] = [];
    for (const p of aptos) {
      const f = porProducto[p.producto]?.fotos;
      if (f?.chica_txt)
        cola.push({ producto: p.producto, tipo: "chica_txt", version: f.chica_txt });
      if (f?.producto_txt)
        cola.push({ producto: p.producto, tipo: "producto_txt", version: f.producto_txt });
    }
    if (!cola.length) {
      toast.error("Esta carpeta no tiene ninguna foto editada todavía");
      return;
    }
    for (const [i, item] of cola.entries()) {
      setBajandoCarpeta(`${i + 1}/${cola.length}`);
      const a = document.createElement("a");
      a.href = buildFotoCarruselUrl(
        source, folder, item.producto, item.tipo, item.version, true,
      );
      const orden = String(i + 1).padStart(2, "0");
      a.download = `${orden}_${folder}_${item.producto}_${
        item.tipo === "chica_txt" ? 1 : 2
      }`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < cola.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    setBajandoCarpeta("");
    toast.success(`${cola.length} foto(s) descargadas`);
  }

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
        hint="Solo los productos donde la chica puede estar EN el sitio. Para filtrar el catálogo entero de una vez, ve a Configuración."
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

        {/* Cuánto del catálogo entero entra en este nicho. Es el número que
            dice si merece la pena seguir clasificando carpetas. */}
        {todosAptos.data ? (
          <p className="rounded-lg border border-border/60 px-2 py-1.5 text-center text-[11px]">
            <span className="font-semibold text-cyan-500">
              {todosAptos.data.resumen.aptos}/{todosAptos.data.resumen.clasificados}
            </span>{" "}
            productos pasan los {todosAptos.data.resumen.filtros} filtros
            {todosAptos.data.resumen.total > todosAptos.data.resumen.clasificados ? (
              <span className="text-muted-foreground">
                {" "}
                · quedan{" "}
                {todosAptos.data.resumen.total - todosAptos.data.resumen.clasificados} sin
                mirar
              </span>
            ) : null}
          </p>
        ) : null}

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
          hint="En este orden: los textos primero (el filtro los lee), luego cuáles valen y por último sus dos mensajes."
          extra={`${aptos.length} aptos`}
        >
          {esPro ? (
            <TextosDelAdmin hechos={conTexto} total={items.length} />
          ) : (
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
                  <Sparkles className="h-4 w-4" /> 1º Obtener textos ({conTexto}/{items.length})
                </>
              )}
            </button>
          )}

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
              <>🔎 2º {clasificada ? "Volver a filtrar" : "Filtrar los que valen para carrusel"}</>
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
              <>✍️ 3º Escribir los dos mensajes ({conMensaje}/{aptos.length})</>
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
              total={pendientes.data?.total_por_escenario?.[esc.clave] ?? 0}
              repuesto={pendientes.data?.repuesto_por_escenario?.[esc.clave] ?? 0}
              cargando={pendientes.isLoading || referenciasCargando}
              subiendo={subirChicas.isPending && tandaEnCurso === esc.clave}
              progreso={tandaEnCurso === esc.clave ? progresoTanda : null}
              onSubir={(files) => {
                setTandaEnCurso(esc.clave);
                setProgresoTanda({ pct: 0, hechos: 0, total: files.length });
                subirChicas.mutate(
                  {
                    escenario: esc.clave,
                    files,
                    onProgreso: (p) => setProgresoTanda(p),
                  },
                  {
                    onSuccess: (r) => {
                      if (r.fallidas) {
                        toast.error(
                          `${r.subidas}/${r.total} subidas · ${r.fallidas} fallaron` +
                            (r.error ? `: ${r.error}` : ""),
                        );
                      } else {
                        toast.success(`${r.subidas} chica(s) subidas y repartidas`);
                      }
                    },
                    onError: (e2) => toast.error(err(e2)),
                    onSettled: () => {
                      setTandaEnCurso("");
                      setProgresoTanda(null);
                    },
                  },
                );
              }}
            />
          ))}

          {/* Y el catálogo entero, que es como se usa de verdad: 190 fotos
              repartidas en treinta carpetas. Va por la cola. */}
          <button
            type="button"
            disabled={quemarTodo.isPending}
            onClick={() =>
              quemarTodo.mutate(
                // Los DOS mensajes: el trabajo se salta lo que no tenga foto o
                // mensaje, así que el mismo botón vale antes y después de tener
                // las fotos de producto.
                { tipo: "ambas" },
                {
                  onSuccess: () => {
                    toast.success("Textos de todo el catálogo en la cola");
                    abrirCola();
                  },
                  onError: (e) => toast.error(err(e)),
                },
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-fuchsia-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-50"
          >
            {quemarTodo.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Encolando…
              </>
            ) : (
              <>
                <Flame className="h-4 w-4" /> Poner los textos a TODO el catálogo
              </>
            )}
          </button>

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
          hint="Esta sí es de cada producto: en Flow subes su foto limpia y el prompt la recrea en el sitio donde se usa. No hace falta foto de referencia."
        >
          {/* La mano la decide el PRODUCTO, no el operador: lo que cabe en la
              mano se coge (crema, vitaminas) y lo que no se enseña en su sitio.
              Este check es solo para forzarla en los grandes. */}
          <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
            <input
              type="checkbox"
              className="h-4 w-4 accent-emerald-500"
              checked={conMano}
              onChange={(e) => setConMano(e.target.checked)}
            />
            Forzar la mano también en los productos grandes (señalando)
          </label>
          {/* La SEGUNDA imagen de Flow: la foto limpia del Drive. Por
              CATEGORÍA y de todos los catálogos, porque en Flow se trabaja por
              ambientes: todas las de dormitorio de una sentada, luego las de
              belleza… Carpeta a carpeta, con dos productos por carpeta, era el
              cuello de botella de este nicho. */}
          <Sub>Bajar fotos limpias + su prompt</Sub>
          <div className="space-y-1.5">
            <button
              type="button"
              disabled={Boolean(bajandoLimpias) || !aptos.length}
              onClick={() => descargarLimpias("carpeta")}
              className="flex w-full items-center justify-center gap-1 rounded-lg border border-border/60 bg-card px-2 py-1.5 text-[11px] transition hover:border-foreground/30 disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5 shrink-0" />
              Esta carpeta ({aptos.filter((p) => p.clean_photo_id).length})
            </button>
            {Object.entries(totalPorCategoria).map(([cat, total]) => {
              const hechas = todosAptos.data?.con_foto2_por_categoria?.[cat] ?? 0;
              const n = total - hechas;
              return (
              <div key={cat} className="flex items-stretch gap-1">
                <button
                  type="button"
                  disabled={Boolean(bajandoLimpias) || !n}
                  onClick={() => descargarLimpias(cat)}
                  className="flex min-w-0 flex-1 items-center gap-1 rounded-lg border border-border/60 bg-card px-2 py-1.5 text-left text-[11px] transition hover:border-foreground/30 disabled:opacity-40"
                >
                  <Download className="h-3.5 w-3.5 shrink-0" />
                  <span className="min-w-0 flex-1">{CATEGORIA_LABEL[cat] ?? cat}</span>
                  <span
                    className={`shrink-0 font-semibold ${
                      n ? "text-foreground" : "text-emerald-500"
                    }`}
                  >
                    {hechas}/{total}
                  </span>
                </button>
                {/* Su prompt: el producto se recrea en el sitio donde se usa
                    (cocina, dormitorio…), que es lo que hace que la foto 2
                    pegue con la foto 1. */}
                <button
                  type="button"
                  title="Copiar el prompt de esta categoría"
                  onClick={() => copiarPromptProducto(cat)}
                  className="shrink-0 rounded-lg border border-border/60 bg-card px-2 transition hover:border-foreground/30"
                >
                  <ClipboardCopy className="h-3.5 w-3.5" />
                </button>
                {/* Y subir las generadas DE ESA categoría: el reconocimiento
                    solo mira esos productos, así que acierta más y va más
                    rápido que comparando contra los 185. */}
                <button
                  type="button"
                  title="Subir las fotos generadas de esta categoría"
                  disabled={subirFotos2.isPending}
                  onClick={() => {
                    setCategoriaSubiendo(cat);
                    fotos2Ref.current?.click();
                  }}
                  className="shrink-0 rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-2 text-emerald-500 transition hover:bg-emerald-500/20 disabled:opacity-50"
                >
                  {subirFotos2.isPending && categoriaSubiendo === cat ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Upload className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
              );
            })}
          </div>
          {bajandoLimpias ? (
            <p className="text-center text-[10px] text-muted-foreground">
              Bajando {bajandoLimpias}…
            </p>
          ) : (
            <p className="text-center text-[10px] text-muted-foreground">
              Las de categoría son de TODOS los catálogos y solo de los que aún no
              tienen foto 2.
            </p>
          )}

          {/* La vuelta: se sueltan todas las generadas y la IA las coloca. */}
          <input
            ref={fotos2Ref}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (!files.length) return;
              setProgresoFotos2({ pct: 0, hechos: 0, total: files.length });
              subirFotos2.mutate(
                {
                  files,
                  categoria: categoriaSubiendo,
                  onProgreso: (p) => setProgresoFotos2(p),
                },
                {
                  onSuccess: (r) => {
                    toast.success(
                      `${files.length} foto(s) subidas · repartiendo ${r.pendientes} en la cola`,
                    );
                    abrirCola();
                  },
                  onError: (e2) => toast.error(err(e2)),
                  onSettled: () => {
                    setProgresoFotos2(null);
                    setCategoriaSubiendo("");
                  },
                },
              );
            }}
          />
          <button
            type="button"
            disabled={subirFotos2.isPending}
            onClick={() => {
              setCategoriaSubiendo("");
              fotos2Ref.current?.click();
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {subirFotos2.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {progresoFotos2
                  ? `Subiendo ${progresoFotos2.hechos}/${progresoFotos2.total} · ${progresoFotos2.pct}%`
                  : "Subiendo…"}
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" /> Traer las fotos generadas
              </>
            )}
          </button>
          {progresoFotos2 ? <Barra pct={progresoFotos2.pct} /> : null}
          <p className="text-center text-[10px] text-muted-foreground">
            Suéltalas todas de golpe: se suben y la IA va reconociendo en la cola de
            qué producto es cada una. Las que no reconozca salen abajo.
          </p>

          <SinAsignar folder={folder} source={source} aptos={aptosGlobales} />
        </Paso>

        <Paso
          n={4}
          color="azul"
          titulo="Editar y publicar la carpeta"
          hint="Con las dos fotos de cada producto ya puestas: se les escribe el texto de golpe y se bajan en orden (1 y 2 de cada uno)."
          extra={`${listos}/${aptos.length} listos`}
        >
          <button
            type="button"
            disabled={quemar.isPending || !folder || !conMensaje}
            onClick={() =>
              quemar.mutate(
                { tipo: "ambas" },
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
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-sky-500 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-sky-600 disabled:opacity-50"
          >
            {quemar.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Escribiendo…
              </>
            ) : (
              <>
                <Flame className="h-4 w-4" /> Mandar a editar las fotos de la carpeta
              </>
            )}
          </button>

          <button
            type="button"
            disabled={Boolean(bajandoCarpeta) || !listos}
            onClick={descargarCarpetaEditada}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/50 bg-sky-500/10 px-3 py-2 text-xs font-semibold text-sky-500 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            {bajandoCarpeta
              ? `Bajando ${bajandoCarpeta}`
              : "Bajar las fotos editadas en orden"}
          </button>
          <p className="text-center text-[10px] text-muted-foreground">
            Salen numeradas 01, 02, 03… — foto 1 y 2 del primer producto, luego las del
            segundo, y así.
          </p>

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

      <FraseDeReferencia />

      {/* Publicar por NICHO, no por carpeta: las fotos se generan por nicho, así
          que los carruseles terminados de suplementos están repartidos por
          veinte carpetas y antes había que esperar a tenerlas todas. */}
      <PorNicho />

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
        {(productos.isFetching || estado.isFetching) && !items.length && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}

        {/* Igual que en Creativos Pro: si el listado falla hay que DECIRLO, o
            la carpeta parece vacía. */}
        {(productos.isError || estado.isError) && (
          <div className="space-y-1.5 rounded-lg border border-red-500/40 bg-red-500/10 p-2">
            <p className="text-[11px] text-red-400">
              No se pudieron cargar los productos:{" "}
              {err(productos.error ?? estado.error)}
            </p>
            <button
              type="button"
              onClick={() => {
                void productos.refetch();
                void estado.refetch();
              }}
              className="rounded-md border border-red-500/40 px-2 py-1 text-[10px] font-semibold text-red-400 transition hover:bg-red-500/10"
            >
              Reintentar
            </button>
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
              ? "En esta carpeta no hay ningún producto que encaje en un carrusel."
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

/** La frase de la que salen los mensajes de la foto 2.
 *
 *  El método del curso no es inventarse los textos: se coge un carrusel de
 *  otra cuenta que YA está funcionando, se traduce su frase y se piden
 *  variantes adaptadas a cada producto. Aquí se guarda esa frase (a mano o
 *  leyéndola de una captura) y la usan todos los mensajes que se escriban
 *  después. */
function FraseDeReferencia() {
  const frase = useFraseReferencia();
  const guardar = useGuardarFrase();
  const desdeImagen = useFraseDesdeImagen();
  const [texto, setTexto] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => setTexto(frase.data?.texto ?? ""), [frase.data?.texto]);

  return (
    <Paso
      n={6}
      color="violeta"
      titulo="La frase de la que salen los mensajes"
      hint="Coge un carrusel de otra cuenta que esté funcionando: su frase, traducida. Los mensajes de la foto 2 serán variantes de esa, adaptadas a cada producto."
      extra={frase.data?.texto ? "puesta" : "sin poner"}
    >
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={2}
        placeholder="Las brumas corporales Cozy están prácticamente gratis hoy"
        className="w-full rounded-lg border border-border/60 bg-background p-2 text-[11px]"
      />
      {frase.data?.origen && (
        <p className="truncate text-[10px] text-muted-foreground">
          original: {frase.data.origen}
        </p>
      )}
      <div className="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          disabled={guardar.isPending || texto === (frase.data?.texto ?? "")}
          onClick={() =>
            guardar.mutate(
              { texto },
              {
                onSuccess: () => toast.success(texto ? "Frase guardada" : "Frase quitada"),
                onError: (e) => toast.error(err(e)),
              },
            )
          }
          className="rounded-lg bg-violet-500 px-2 py-1.5 text-[11px] font-semibold text-white transition hover:bg-violet-600 disabled:opacity-50"
        >
          {guardar.isPending ? "Guardando…" : "Guardar la frase"}
        </button>
        <button
          type="button"
          disabled={desdeImagen.isPending}
          onClick={() => ref.current?.click()}
          className="flex items-center justify-center gap-1 rounded-lg border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30 disabled:opacity-50"
        >
          {desdeImagen.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Leyendo…
            </>
          ) : (
            <>📸 Sacarla de una captura</>
          )}
        </button>
      </div>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          desdeImagen.mutate(f, {
            onSuccess: (d) => toast.success(`Frase: ${d.texto.slice(0, 40)}…`),
            onError: (x) => toast.error(err(x)),
          });
        }}
      />
      <p className="text-[10px] text-muted-foreground">
        Al cambiarla, vuelve a escribir los mensajes desde Configuración («solo
        reescribir los mensajes») para que todo el catálogo hable igual.
      </p>
    </Paso>
  );
}

/** Los carruseles ya terminados de un nicho, vengan de la carpeta que vengan.
 *
 *  Es lo que permite empezar a publicar sin tener el catálogo entero hecho:
 *  se genera la tanda de un nicho, se quema el texto y ya se puede subir, con
 *  el "subido" apuntado en la carpeta de cada producto. */
function PorNicho() {
  const [categoria, setCategoria] = useState("");
  const listos = useListos(categoria);
  const hashtags = useHashtags().data ?? [];
  const marcar = useMarcarSubidoSuelto();
  const escaparate = useEscaparateCarrusel();
  const [bajando, setBajando] = useState("");
  const cuentas = listos.data?.por_categoria ?? {};
  const items = categoria ? (listos.data?.items ?? []) : [];

  async function bajarPar(p: CarruselListo) {
    const cola: [keyof FotosCarrusel, string][] = [
      ["chica_txt", p.fotos.chica_txt],
      ["producto_txt", p.fotos.producto_txt],
    ];
    setBajando(`${p.folder}|${p.producto}`);
    for (const [i, [tipo, version]] of cola.entries()) {
      if (!version) continue;
      const a = document.createElement("a");
      a.href = buildFotoCarruselUrl(p.source, p.folder, p.producto, tipo, version, true);
      a.download = `${p.folder}_${p.producto}_${i + 1}`.replace(/[^a-zA-Z0-9_.-]+/g, "_");
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Un respiro entre las dos: el móvil cancela las descargas simultáneas.
      if (i === 0) await new Promise((r) => setTimeout(r, 600));
    }
    setBajando("");
  }

  /** Todas las parejas del nicho, en orden y numeradas: 01, 02, 03… */
  async function bajarTodo() {
    const pendientes = items.filter((p) => !p.subido_at);
    for (const [n, p] of pendientes.entries()) {
      setBajando(`${n + 1}/${pendientes.length}`);
      const cola: [keyof FotosCarrusel, string][] = [
        ["chica_txt", p.fotos.chica_txt],
        ["producto_txt", p.fotos.producto_txt],
      ];
      for (const [i, [tipo, version]] of cola.entries()) {
        if (!version) continue;
        const a = document.createElement("a");
        a.href = buildFotoCarruselUrl(p.source, p.folder, p.producto, tipo, version, true);
        const orden = String(n + 1).padStart(2, "0");
        a.download = `${orden}_${p.folder}_${p.producto}_${i + 1}`.replace(
          /[^a-zA-Z0-9_.-]+/g, "_",
        );
        document.body.appendChild(a);
        a.click();
        a.remove();
        await new Promise((r) => setTimeout(r, 600));
      }
    }
    setBajando("");
  }

  return (
    <Paso
      n={5}
      color="esmeralda"
      titulo="Publicar por nicho"
      hint="Los carruseles ya terminados, junten la carpeta que junten. Marca «subido» y se apunta en su carpeta."
      extra={
        listos.data
          ? `${Object.values(cuentas).reduce((a, b) => a + b, 0)} listos`
          : undefined
      }
    >
      <div className="space-y-1.5">
        {Object.entries(cuentas)
          .sort((a, b) => b[1] - a[1])
          .map(([cat, n]) => (
            <button
              key={cat}
              type="button"
              onClick={() => setCategoria(categoria === cat ? "" : cat)}
              className={`flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left text-[11px] transition ${
                categoria === cat
                  ? "border-sky-500 bg-sky-500/15 text-sky-400"
                  : "border-border/60 hover:border-foreground/30"
              }`}
            >
              <span className="min-w-0 flex-1">{CATEGORIA_LABEL[cat] ?? cat}</span>
              <span className="shrink-0 font-semibold">{n}</span>
            </button>
          ))}
        {!Object.keys(cuentas).length && !listos.isLoading && (
          <p className="py-2 text-center text-[11px] text-muted-foreground">
            Todavía no hay ningún carrusel con sus dos fotos escritas.
          </p>
        )}
        {listos.isLoading && (
          <p className="flex items-center justify-center gap-2 py-2 text-[11px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Mirando qué está listo…
          </p>
        )}
      </div>

      {categoria && items.length > 1 && (
        <button
          type="button"
          disabled={Boolean(bajando)}
          onClick={bajarTodo}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/20 disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {bajando.includes("/")
            ? `Bajando ${bajando}`
            : `Bajar los ${items.filter((p) => !p.subido_at).length} sin subir, en orden`}
        </button>
      )}

      {categoria && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {items.map((p) => {
            const clave = `${p.folder}|${p.producto}`;
            const subido = p.subido_at > 0;
            return (
              <div
                key={clave}
                className={`space-y-1 rounded-lg border p-1.5 ${
                  subido ? "border-emerald-500/50 bg-emerald-500/5" : "border-border/60"
                }`}
              >
                <div className="grid grid-cols-2 gap-1">
                  {(["chica_txt", "producto_txt"] as const).map((tipo) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={tipo}
                      src={buildFotoCarruselUrl(
                        p.source, p.folder, p.producto, tipo, p.fotos[tipo], false, 260,
                      )}
                      alt={tipo}
                      loading="lazy"
                      className="aspect-[9/16] w-full rounded object-cover"
                    />
                  ))}
                </div>
                <p className="truncate text-[10px] text-muted-foreground">
                  {p.folder} · {p.producto}
                </p>
                <p className="line-clamp-2 text-[10px] leading-tight">{p.titulo}</p>
                {/* Lo que hay que pegar en TikTok al publicar: el caption es el
                    que más se usa, y ya va con emojis y hashtags puestos. */}
                <div className="flex flex-wrap gap-1">
                  {/* Mismo orden y mismos botones que en Creativos Pro, que es
                      donde el operador ya tiene la mano hecha. */}
                  <CopyChip label="🔎 Título TikTok" text={p.titulo_tiktok_completo} siempre />
                  <CopyChip label="🏪 Tienda" text={p.tienda} siempre />
                  <CopyChip
                    label="✍️ Caption"
                    siempre
                    text={
                      [p.caption, p.emojis, hashtags.join(" ")].filter(Boolean).join(" ")
                    }
                  />
                </div>
                <div className="flex gap-1">
                  <button
                    type="button"
                    disabled={bajando === clave}
                    onClick={() => bajarPar(p)}
                    className="flex flex-1 items-center justify-center gap-1 rounded border border-border/60 px-1.5 py-1 text-[10px] transition hover:border-foreground/40 disabled:opacity-50"
                  >
                    <Download className="h-3 w-3" /> Bajar
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      marcar.mutate(
                        {
                          source: p.source, folder: p.folder,
                          producto: p.producto, uploaded: !subido,
                        },
                        { onError: (e) => toast.error(err(e)) },
                      )
                    }
                    className={`flex-1 rounded border px-1.5 py-1 text-[10px] font-semibold transition ${
                      subido
                        ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
                        : "border-border/60 hover:border-foreground/40"
                    }`}
                  >
                    {subido ? "✓ subido" : "📤 subido"}
                  </button>
                </div>
                {/* El escaparate es del PRODUCTO, no del nicho: marcarlo aquí
                    se ve marcado en POV BOF, Largo y los demás. */}
                <button
                  type="button"
                  onClick={() =>
                    escaparate.mutate(
                      {
                        source: p.source, folder: p.folder,
                        producto: p.producto, en_escaparate: !p.en_escaparate,
                      },
                      { onError: (e) => toast.error(err(e)) },
                    )
                  }
                  className={`w-full rounded border px-1.5 py-1 text-[10px] font-semibold transition ${
                    p.en_escaparate
                      ? "border-sky-500 bg-sky-500/15 text-sky-400"
                      : "border-border/60 text-muted-foreground hover:border-foreground/40"
                  }`}
                >
                  🏪 escaparate
                </button>
              </div>
            );
          })}
        </div>
      )}
    </Paso>
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
  const url = estado?.hay ? buildReferenciaUrl(tipo, estado.version, false, "", 160) : null;

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
                borrar.mutate({ tipo }, { onError: (e) => toast.error(err(e)) })
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

/** Las fotos de producto que la IA no supo colocar.
 *
 *  No se tiran —son generaciones de Flow que han costado su rato—: se enseñan
 *  aquí con un desplegable para ponerlas en su producto a mano. */
function SinAsignar({
  source,
  folder,
  aptos,
}: {
  source: string;
  folder: string | null;
  aptos: AptoCarrusel[];
}) {
  const sueltas = useSinAsignar();
  const asignar = useAsignarSuelta();
  const borrar = useBorrarSuelta();
  const items = sueltas.data ?? [];
  if (!items.length) return null;

  // Primero los de la carpeta abierta: casi siempre es de ahí lo que falla.
  const candidatos = [...aptos].sort((a, b) => {
    const suyo = (x: AptoCarrusel) => (x.folder === folder && x.source === source ? 0 : 1);
    return suyo(a) - suyo(b);
  });

  return (
    <div className="space-y-1.5 rounded-lg border border-amber-500/40 bg-amber-500/5 p-2">
      <p className="text-[11px] font-semibold text-amber-500">
        Sin reconocer ({items.length})
      </p>
      <p className="text-[10px] text-muted-foreground">
        No se han tirado. Dile a cuál es cada una y se coloca.
      </p>
      {items.map((f) => (
        <div key={f.archivo} className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={buildSueltaUrl(f.archivo, f.version)}
            alt={f.archivo}
            loading="lazy"
            className="h-12 w-12 shrink-0 rounded-md object-cover"
          />
          <select
            defaultValue=""
            onChange={(e) => {
              const destino = candidatos.find((c) => c.ref === e.target.value);
              if (!destino) return;
              asignar.mutate(
                {
                  archivo: f.archivo,
                  source: destino.source,
                  folder: destino.folder,
                  producto: destino.producto,
                },
                {
                  onSuccess: () => toast.success("Colocada"),
                  onError: (e2) => toast.error(err(e2)),
                },
              );
            }}
            className="min-w-0 flex-1 truncate rounded border border-border/60 bg-background px-1.5 py-1 text-[10px]"
          >
            <option value="">¿De qué producto es?</option>
            {candidatos.map((c) => (
              <option key={c.ref} value={c.ref}>
                {c.folder} · {c.producto} · {c.titulo || "sin título"}
                {c.tiene_foto2 ? " (ya tiene)" : ""}
              </option>
            ))}
          </select>
          <button
            type="button"
            title="Tirar esta foto"
            onClick={() =>
              borrar.mutate(f.archivo, { onError: (e) => toast.error(err(e)) })
            }
            className="shrink-0 rounded border border-border/60 p-1 text-muted-foreground transition hover:border-red-500 hover:text-red-500"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  );
}

/** Barra de subida. Lo que se ve mientras el navegador manda los ficheros: sin
 *  ella, una tanda de 78 fotos parece colgada tres minutos. */
function Barra({ pct }: { pct: number }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
      <div
        className="h-full bg-fuchsia-500 transition-all"
        style={{ width: `${Math.max(2, pct)}%` }}
      />
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
  total,
  repuesto,
  cargando,
  subiendo,
  progreso,
  onSubir,
}: {
  escenario: EscenarioPrompt;
  faltan: number;
  /** Productos de este escenario en total (los hechos son total - faltan). */
  total: number;
  /** Chicas de sobra guardadas para este escenario. */
  repuesto: number;
  /** Aún no han llegado los datos: no es que no haya nada. */
  cargando: boolean;
  subiendo: boolean;
  /** Progreso de la subida de ESTE escenario (null si no es el suyo). */
  progreso: ProgresoTanda | null;
  onSubir: (files: File[]) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const refFoto = useRef<HTMLInputElement>(null);
  const referencias = useReferencias();
  const subirRef = useSubirReferencia();
  const borrarRef = useBorrarReferencia();
  const borrarChicas = useBorrarChicas();
  // La referencia de ESTE escenario. Es lo que de verdad decide cómo sale la
  // chica: con la del curso (una mujer de unos 35 en una cocina) salían así
  // todas, también las de la playa.
  const suya = referencias.data?.[`chica_${escenario.clave}`];

  return (
    <div
      className={`space-y-1.5 rounded-lg border p-2 ${
        faltan ? "border-fuchsia-500/40 bg-fuchsia-500/5" : "border-border/60 opacity-70"
      }`}
    >
      <div className="flex items-center gap-2">
        {/* Su foto de referencia: se toca para cambiarla solo en este
            escenario. Sin ella se usa la general. */}
        <input
          ref={refFoto}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            subirRef.mutate(
              { tipo: "chica", escenario: escenario.clave, file },
              {
                onSuccess: () =>
                  toast.success(`Referencia de ${escenario.label} guardada`),
                onError: (e2) => toast.error(err(e2)),
              },
            );
          }}
        />
        <button
          type="button"
          title={
            suya?.propia
              ? "Referencia propia de este escenario (toca para cambiarla)"
              : "Usa la referencia general — toca para poner una de este escenario"
          }
          onClick={() => refFoto.current?.click()}
          className={`h-11 w-11 shrink-0 overflow-hidden rounded-md border transition ${
            suya?.propia ? "border-fuchsia-500" : "border-dashed border-border/60"
          }`}
        >
          {suya?.hay ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={buildReferenciaUrl("chica", suya.version, false, escenario.clave, 160)}
              alt={escenario.label}
              loading="lazy"
              className={`h-full w-full object-cover ${suya.propia ? "" : "opacity-50"}`}
            />
          ) : (
            <span className="text-[9px] text-muted-foreground">ref</span>
          )}
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-semibold">{escenario.label}</p>
          <p className="truncate text-[10px] text-muted-foreground">
            {cargando
              ? "cargando… · "
              : suya?.propia
                ? "referencia propia · "
                : "⚠️ sin referencia propia · "}
            {escenario.para}
          </p>
        </div>
        {/* Hechas/total, no solo lo que falta: así se ve que una tanda entró a
            medias (8/20) y, cuando el catálogo crezca, que hay más por hacer
            (20/34). */}
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold ${
            !faltan && total
              ? "bg-emerald-500/20 text-emerald-500"
              : faltan
                ? "bg-fuchsia-500/20 text-fuchsia-400"
                : "text-muted-foreground"
          }`}
        >
          {cargando ? "…" : `${total - faltan}/${total}`}
          {!cargando && repuesto ? (
            <span
              title={`${repuesto} de sobra esperando: se colocan solas cuando el curso añada productos de este sitio`}
              className="ml-1 font-normal opacity-80"
            >
              +{repuesto}
            </span>
          ) : null}
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
        {/* Se puede subir aunque no falte ninguna: lo que sobre se guarda de
            repuesto y se coloca solo cuando el curso añada productos de este
            sitio. Volver a Flow por dos fotos no compensa. */}
        <button
          type="button"
          disabled={subiendo || cargando}
          onClick={() => ref.current?.click()}
          className={`flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-semibold transition disabled:opacity-40 ${
            faltan
              ? "bg-fuchsia-500 text-white hover:bg-fuchsia-600"
              : "border border-border/60 text-muted-foreground hover:border-foreground/40"
          }`}
        >
          {subiendo ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          {subiendo && progreso
            ? `${progreso.hechos}/${progreso.total} · ${progreso.pct}%`
            : faltan
              ? `Subir tanda (${faltan})`
              : "Subir de repuesto"}
        </button>
      </div>
      {/* Crear la referencia desde CERO, sin adjuntar foto: con una imagen de
          referencia el modelo copia la cara —y con ella la edad—, así que es la
          única forma de tener una chica más joven. Se genera, se sube aquí como
          referencia del escenario y ya todas las tandas salen así. */}
      {/* Qué chica va en este escenario. La referencia es lo que manda en la
          tanda —la cara, la edad y el estilo salen de ella—, así que elegirla
          es la mitad del trabajo. */}
      {!suya?.propia ? (
        <p className="rounded border border-border/60 px-2 py-1 text-[10px] leading-snug text-muted-foreground">
          <span className="font-semibold text-foreground">Busca o crea:</span>{" "}
          {escenario.busqueda}
        </p>
      ) : null}

      <div className="flex items-center gap-2">
        {/* Subir la foto de referencia de ESTE escenario. Va como botón con
            texto y no solo en la miniatura: en móvil el toque en 44 px se
            pierde, y sin referencia la tanda no sirve. */}
        <button
          type="button"
          disabled={subirRef.isPending}
          onClick={() => refFoto.current?.click()}
          className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold transition disabled:opacity-50 ${
            suya?.propia
              ? "border-border/60 text-muted-foreground hover:border-foreground/30"
              : "border-fuchsia-500 bg-fuchsia-500/15 text-fuchsia-400"
          }`}
        >
          {subirRef.isPending
            ? "Subiendo…"
            : suya?.propia
              ? "Cambiar referencia"
              : "Subir referencia"}
        </button>

        {suya?.hay ? (
          <a
            href={buildReferenciaUrl("chica", suya.version, true, escenario.clave)}
            title="Bajar la referencia (tamaño original)"
            className="flex shrink-0 items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-foreground/30"
          >
            <Download className="h-3 w-3" /> Bajar
          </a>
        ) : null}
        <button
          type="button"
          onClick={() => {
            navigator.clipboard.writeText(escenario.prompt_referencia);
            toast.success("JSON para crear la referencia copiado");
          }}
          className="flex-1 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-foreground/30"
        >
          JSON para crear esta referencia
        </button>
        {suya?.propia ? (
          <button
            type="button"
            onClick={() =>
              borrarRef.mutate(
                { tipo: "chica", escenario: escenario.clave },
                { onError: (e) => toast.error(err(e)) },
              )
            }
            className="shrink-0 text-[10px] text-muted-foreground underline-offset-2 hover:underline"
          >
            Quitar
          </button>
        ) : null}
      </div>

      {/* Repetir la tanda desde cero. Hace falta porque una subida que entra a
          medias no deja saber cuáles llegaron, y volver a subirlas todas
          colocaría las repetidas en productos que no tocan. */}
      {total - faltan > 0 ? (
        <button
          type="button"
          disabled={borrarChicas.isPending}
          onClick={() => {
            if (
              !window.confirm(
                `¿Borrar las ${total - faltan} fotos de chica de "${escenario.label}"? ` +
                  "Tendrás que volver a subirlas todas.",
              )
            )
              return;
            borrarChicas.mutate(escenario.clave, {
              onSuccess: (r) => toast.success(`${r.borradas} fotos borradas`),
              onError: (e) => toast.error(err(e)),
            });
          }}
          className="w-full text-[10px] text-muted-foreground underline-offset-2 transition hover:text-red-400 hover:underline disabled:opacity-50"
        >
          {borrarChicas.isPending
            ? "Borrando…"
            : `Borrar las ${total - faltan} fotos ya subidas`}
        </button>
      ) : null}

      {subiendo && progreso ? <Barra pct={progreso.pct} /> : null}
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
  const quemarTodo = useQuemarTodo();
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
        <FotoProducto
          src={limpia}
          alt={p.titulo ?? p.producto}
          className="h-16 w-16 shrink-0 rounded-md object-cover"
        />
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {p.producto}
            </span>
            <span className="truncate">{p.titulo ?? "sin título"}</span>
          </p>
          {/* Cuándo lo subió al Drive quien comparte los productos: es lo que
              distingue un producto NUEVO de uno que se quedó sin hacer. */}
          {p.subida_at ? (
            <p className="truncate text-[10px] text-muted-foreground">
              subido al Drive el {fechaCorta(p.subida_at)}
            </p>
          ) : null}
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
  const url = buildFotoCarruselUrl(source, folder, producto, tipo, version, false, 540);
  return (
    <div className="relative">
      <a
        href={buildFotoCarruselUrl(source, folder, producto, tipo, version)}
        target="_blank"
        rel="noopener noreferrer"
      >
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
