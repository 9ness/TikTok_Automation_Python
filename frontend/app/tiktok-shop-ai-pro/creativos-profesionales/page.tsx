"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Link2,
  Loader2,
  Sparkles,
  Store,
  ShoppingBag,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { nombreDescarga } from "@/lib/descargas";

import { ApiError } from "@/lib/api";
import { fechaCorta, horaCorta } from "@/lib/hora";
import {
  useEstadoDeUsuario,
  useEstadoRecordado,
} from "@/lib/hooks/useEstadoRecordado";
import {
  esVentaNueva,
  FUENTE_TOP_VENDIDOS,
  verTopVendidos,
} from "@/lib/topVendidos";
import { TextosDelAdmin } from "@/components/tiktok-shop-ai-pro/TextosDelAdmin";
import { useEsPro } from "@/lib/queries/auth";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { FiltroSoloUrl } from "@/components/tiktok-shop-ai-pro/FiltroSoloUrl";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { FotoProducto } from "@/components/tiktok-shop-ai-pro/FotoProducto";
import { MagnificSpaces } from "@/components/tiktok-shop-ai-pro/MagnificSpaces";
import { Caja, OSepara, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import {
  useCompletarCarpetaCreativos,
  useFoldersCreativos,
  useMarcarSubidoCreativo,
  usePromptCreativos,
  useSubidosCreativos,
} from "@/lib/queries/nichoCreativos";
// El catálogo es EL MISMO del Nicho POV BOF: fuentes, fotos, textos, hashtags,
// escaparate y vendidos. Duplicarlo habría significado extraer los textos dos
// veces con Gemini y que las dos copias se separaran a la primera corrección.
import {
  buildCleanPhotoDownloadUrl,
  buildPhotoUrl,
  useExtraerTextos,
  useHashtags,
  useProductos,
  useSetEstado,
  useSources,
  ANCHO_VISOR,
} from "@/lib/queries/nichoPovBof";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function err(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export default function CreativosProPage() {
  const sources = useSources();
  const [source, setSource] = useEstadoDeUsuario("creativos:fuente", "aleatorios_1");
  const folders = useFoldersCreativos(source);
  const [picked, setPicked] = useEstadoDeUsuario<string | null>("creativos:carpeta", null);
  const folder = picked ?? folders.data?.current ?? null;
  const productos = useProductos(source, folder);
  const prompt = usePromptCreativos();
  const extraer = useExtraerTextos();
  // Los textos son del producto y se comparten: los extrae solo el admin.
  const esPro = useEsPro();
  const completar = useCompletarCarpetaCreativos();
  // Qué creativos ya se publicaron: propio de este nicho, se marca a mano.
  const subidos = useSubidosCreativos(source, folder);
  const marcarSubido = useMarcarSubidoCreativo(source, folder);
  const horasSubida = subidos.data ?? {};

  const [bajando, setBajando] = useState("");
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);

  const items = productos.data ?? [];
  const conTexto = items.filter((p) => p.titulo).length;
  const subidosCarpeta = items.filter((p) => horasSubida[p.producto]).length;
  const esTopVendidos = source === FUENTE_TOP_VENDIDOS;
  const [soloSinSubir, setSoloSinSubir] = useEstadoRecordado(
    "creativos:topventas:sinsubir", false,
  );
  const [soloConUrl, setSoloConUrl] = useEstadoDeUsuario("creativos:solo-url", false);
  // "Subido" aquí es el CREATIVO, no el vídeo: un producto puede tener el
  // vídeo publicado y el creativo aún no.
  const enPantalla = useMemo(
    () =>
      verTopVendidos(items, {
        activo: esTopVendidos,
        soloSinSubir,
        yaSubido: (p) => Boolean(horasSubida[p.producto]),
      }),
    [items, esTopVendidos, soloSinSubir, horasSubida],
  );
  // Sin la ficha enlazada no se puede publicar, así que este filtro es
  // "enséñame solo lo que puedo sacar hoy" — el mismo de los dos POV BOF.
  const conUrlEnPantalla = enPantalla.filter((p) => Boolean(p.product_url)).length;
  const itemsVisibles = useMemo(
    () => (soloConUrl ? enPantalla.filter((p) => Boolean(p.product_url)) : enPantalla),
    [enPantalla, soloConUrl],
  );
  const enEscaparate = items.filter((p) => p.en_escaparate).length;
  const fotosTotales = items.filter((p) => p.titled_photo_id).length;
  const fotosConUrl = items.filter((p) => p.titled_photo_id && p.product_url).length;
  const hecha = folders.data?.items.find((f) => f.name === folder)?.completed ?? false;

  // Se bajan las fotos CON LA DESCRIPCIÓN (la captura de la ficha), no las
  // limpias: el prompt del creativo pide integrar los beneficios del producto,
  // y esos solo están en la ficha. Con la foto limpia el generador no tiene de
  // dónde sacarlos y se los inventa — que es justo lo que el prompt prohíbe.
  async function descargarFotos(soloUrl = false) {
    const conFoto = items.filter(
      (p) => p.titled_photo_id && (!soloUrl || p.product_url),
    );
    if (!folder || !conFoto.length) {
      toast.error(
        soloUrl
          ? "Ninguno de los que tienen ficha enlazada tiene foto de la ficha"
          : "Ningún producto de esta carpeta tiene foto de la ficha",
      );
      return;
    }
    // Una a una con un respiro: varias descargas simultáneas se bloquean o se
    // cancelan solas en el navegador del móvil.
    for (const [i, p] of conFoto.entries()) {
      setBajando(`${i + 1}/${conFoto.length}`);
      const a = document.createElement("a");
      // Por el endpoint de descarga, NO por el de ver: `download` se ignora
      // entre orígenes distintos y la API es otro origen, así que quien fuerza
      // la descarga es el Content-Disposition del backend. Con la URL de ver,
      // el móvil abría las fotos en pestañas y no bajaba ninguna.
      a.href = buildCleanPhotoDownloadUrl(source, folder, p.producto, "ficha");
      a.download = nombreDescarga(folder, p.producto, "ficha");
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < conFoto.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    setBajando("");
    toast.success(`${conFoto.length} foto(s) descargadas`);
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <header className="rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 shrink-0 text-cyan-500" />
          <div className="min-w-0">
            <h1 className="text-base font-bold sm:text-lg">Creativos Pro</h1>
            <p className="text-[11px] text-muted-foreground">
              Un creativo publicitario por producto · sin vídeo
            </p>
          </div>
        </div>
      </header>

      {/* Dónde trabajas, con rótulos: mismo lenguaje que los otros nichos. */}
      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint="Elige el catálogo y la carpeta. El progreso es de Creativos Pro, aparte del vídeo."
        extra={folders.data ? `${folders.data.done}/${folders.data.total} hechas` : undefined}
      >
        <Sub>Catálogo</Sub>
        {/* Dos por línea en móvil desde que son cuatro fuentes. */}
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(sources.data?.items ?? []).map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => {
                setSource(s.slug);
                setPicked(null);
              }}
              className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
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
        {/* Progreso: es SUYO. Haber hecho una carpeta en POV BOF no la deja
            hecha aquí — un creativo no es un vídeo. */}
        {folders.data && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>
                {folders.data.done}/{folders.data.total} carpetas
              </span>
              <span className="truncate font-medium text-foreground">{folder}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-cyan-500 transition-all"
                style={{
                  width: `${folders.data.total ? (folders.data.done / folders.data.total) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1">
          {(folders.data?.items ?? []).map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => setPicked(f.name)}
              className={`break-words leading-tight rounded border px-2 py-1 text-[10px] transition ${
                // Verde si la carpeta abierta está hecha, azul si no (igual
                // que en POV BOF): con un solo color no se sabía si la que
                // tienes delante está terminada.
                folder === f.name
                  ? f.completed
                    ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                    : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                  : f.completed
                    ? "border-emerald-500/40 text-emerald-500"
                    : "border-border/60 text-muted-foreground"
              }`}
            >
              {f.completed && "✓ "}
              {f.name}
              {/* Cuántos productos de esta carpeta tienen ya la ficha
                  enlazada: es el trabajo que hay dentro, sin entrar a mirar.
                  No sale cuando es 0 — un cero en cada chip es ruido. */}
              {!!f.con_url && (
                <span className="ml-1 rounded-full bg-emerald-500/15 px-1 py-px text-[9px] font-semibold text-emerald-500">
                  {f.con_url}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Cerrar la carpeta, dentro de su caja: es lo que se pulsa nada más
            terminar y antes quedaba suelto entre dos bloques. */}
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

      {/* Los mismos pasos y colores que el POV BOF, aunque aquí sean tres: el
          creativo es una IMAGEN, no hay vídeo que traer ni que montar. Quien
          aprende un nicho sabe usar los otros. */}
      <section className="space-y-2">
        <div className="flex items-center gap-2 px-1">
          <Sparkles className="h-4 w-4 shrink-0 text-fuchsia-500" />
          <p className="text-sm font-semibold">Cómo se hace un creativo</p>
          {folder ? (
            <span className="ml-auto text-[10px] text-muted-foreground">{folder}</span>
          ) : null}
        </div>

        <Paso
          n={1}
          color="violeta"
          titulo="Preparar los textos"
          hint="Lee la ficha de cada producto con IA. El creativo saca de ahí los beneficios que se escriben encima."
          extra={`${conTexto}/${items.length}`}
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
                  <Sparkles className="h-4 w-4" /> Obtener textos ({conTexto}/{items.length})
                </>
              )}
            </button>
          )}

          <div className="grid grid-cols-2 gap-1.5">
            <div
              className={`flex items-center justify-center gap-1.5 break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-semibold ${
                subidosCarpeta === items.length && items.length > 0
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-border/60 text-muted-foreground"
              }`}
            >
              <span className="break-words leading-tight">📤 Subidos {subidosCarpeta}/{items.length}</span>
            </div>
            <button
              type="button"
              onClick={() => setVerEscaparate(true)}
              className={`flex items-center justify-center gap-1.5 break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition ${
                enEscaparate === items.length && items.length > 0
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                  : "border-sky-500/50 bg-sky-500/10 text-sky-500 hover:bg-sky-500/20"
              }`}
            >
              <span className="break-words leading-tight">🏪 Escaparate {enEscaparate}/{items.length}</span>
            </button>
          </div>
        </Paso>

        <Paso
          n={2}
          color="fucsia"
          titulo="Generar el creativo fuera"
          hint={`Baja la foto de la ficha y genera la imagen en formato ${prompt.data?.formato ?? "3:4"} — en cuadrado es el error fácil de este nicho.`}
        >
          <button
            type="button"
            disabled={Boolean(bajando) || !items.length}
            onClick={() => void descargarFotos()}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            {bajando
              ? `Bajando ${bajando}`
              : `Fotos de la ficha (${items.filter((p) => p.titled_photo_id).length})`}
          </button>

          {/* En una carpeta a medias, lo único que hace falta bajarse es lo que
              se va a publicar. Se esconde si ya están todas enlazadas: ahí
              duplicaría el botón de arriba. */}
          {fotosConUrl > 0 && fotosConUrl < fotosTotales && (
            <button
              type="button"
              disabled={Boolean(bajando)}
              onClick={() => void descargarFotos(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-500 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              <Link2 className="h-3.5 w-3.5" />
              Con URL ({fotosConUrl})
            </button>
          )}

          <MagnificSpaces spaces={["carrusel"]} />
          <OSepara />
          <button
            type="button"
            disabled={!prompt.data}
            onClick={() => {
              navigator.clipboard.writeText(prompt.data?.imagen ?? "");
              toast.success("Prompt copiado");
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
          </button>
          <p className="text-center text-[11px] font-semibold text-cyan-500">
            Genera en formato {prompt.data?.formato ?? "3:4"}
          </p>
        </Paso>

        <Paso
          n={3}
          color="azul"
          titulo="Publicar"
          hint="El creativo se sube tal cual desde tu galería: aquí no se monta nada. Marca cada uno cuando lo publiques."
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

      {/* El escaparate es el mismo para todos los nichos: si el producto ya se
          metió desde el POV BOF (o desde otra carpeta), aquí sale hecho. */}
      {verEscaparate && folder && (
        <EscaparateModal
          source={source}
          folder={folder}
          productos={items}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      {/* Los productos de la carpeta, ya fuera de los pasos. */}
      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        {productos.isFetching && !items.length && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando productos…
          </div>
        )}

        {/* Sin esto la pantalla se quedaba MUDA cuando el listado fallaba: ni
            productos, ni spinner, ni motivo. Y el fallo pasa —el Drive tarda o
            devuelve 502 mientras hay un trabajo pesado en la cola. */}
        {productos.isError && (
          <div className="space-y-1.5 rounded-lg border border-red-500/40 bg-red-500/10 p-2">
            <p className="text-[11px] text-red-400">
              No se pudieron cargar los productos: {err(productos.error)}
            </p>
            <button
              type="button"
              onClick={() => void productos.refetch()}
              className="rounded-md border border-red-500/40 px-2 py-1 text-[10px] font-semibold text-red-400 transition hover:bg-red-500/10"
            >
              Reintentar
            </button>
          </div>
        )}

        {esTopVendidos && items.length > 0 && (
          <label className="flex items-center gap-2 rounded-lg border border-border/60 p-2 text-[11px]">
            <input
              type="checkbox"
              className="h-4 w-4 accent-fuchsia-500"
              checked={soloSinSubir}
              onChange={(e) => setSoloSinSubir(e.target.checked)}
            />
            Solo los que no he subido
            <span className="ml-auto text-[10px] text-muted-foreground">
              {enPantalla.length}/{items.length}
            </span>
          </label>
        )}

        <FiltroSoloUrl
          activo={soloConUrl}
          onChange={setSoloConUrl}
          conUrl={conUrlEnPantalla}
          total={enPantalla.length}
        />

        {/* Carpeta vacía: casi siempre es que el curso ha borrado sus fotos
            del Drive de origen (pasa cada pocas semanas). Nuestra copia las
            conserva, así que se dice dónde mirar en vez de dejar el hueco. */}
        {!productos.isFetching && !productos.isError && !items.length && folder && (
          <p className="py-4 text-center text-[11px] text-muted-foreground">
            Esta carpeta está vacía en el Drive del curso: o todavía no han subido nada
            (las de los días siguientes se crean por adelantado) o han borrado sus fotos
            — en ese caso, ábrela desde el catálogo «🗄️ Copia».
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {itemsVisibles.map((p) => (
            <CreativoCard
              key={`${source}-${folder}-${p.producto}`}
              source={source}
              folder={folder!}
              producto={p}
              esTopVendidos={esTopVendidos}
              subido={Boolean(horasSubida[p.producto])}
              subidoAt={horasSubida[p.producto] ?? 0}
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

/** Ficha de producto SIN nada de vídeo: aquí no se sube nada ni se marca
 *  "Subido". Solo lo que hace falta para publicar el creativo — buscar el
 *  producto (título TikTok + tienda) y la descripción (caption + hashtags). */
function CreativoCard({
  source,
  folder,
  producto: p,
  esTopVendidos = false,
  subido,
  subidoAt,
  onSubido,
}: {
  source: string;
  folder: string;
  producto: ProductoItem;
  /** En "Top vendidos" se enseña cuántas veces vendió y si es reciente. */
  esTopVendidos?: boolean;
  /** Si el CREATIVO de este producto ya se publicó. Es propio de este nicho:
   *  "subido" en el POV BOF es el vídeo, y son dos publicaciones distintas. */
  subido: boolean;
  /** Cuándo se marcó (epoch). Se enseña para comprobar que el toque entró. */
  subidoAt: number;
  onSubido: (v: boolean) => void;
}) {
  const [verFoto, setVerFoto] = useState(false);
  const setEstado = useSetEstado();
  const hashtags = useHashtags();
  const [enEscaparate, setEnEscaparate] = useState(p.en_escaparate);
  const [sold, setSold] = useState(p.sold);

  // Sin esto, las tarjetas mienten al cambiar de carpeta: React reutiliza el
  // componente cuando la `key` coincide (los productos se numeran 1..10 en
  // TODAS las carpetas), y `useState` solo mira su valor inicial la primera
  // vez. Resultado: entrabas en una carpeta nueva y salían marcados los
  // productos que lo estaban en la anterior. Mismo arreglo que en el POV BOF.
  useEffect(() => {
    setEnEscaparate(p.en_escaparate);
    setSold(p.sold);
  }, [p.en_escaparate, p.sold]);

  // Dos tamaños a propósito: la tarjeta pinta una miniatura y el visor pide una
  // más grande solo al abrirlo. A tamaño original una carpeta se llevaba ~300 MB
  // de RAM en el móvil y Chrome cerraba la app (ver `ANCHO_MINIATURA`).
  const limpia = p.clean_photo_id ? buildPhotoUrl(source, folder, p.clean_photo_id) : null;
  const ficha = p.titled_photo_id ? buildPhotoUrl(source, folder, p.titled_photo_id) : null;
  const limpiaVisor = p.clean_photo_id
    ? buildPhotoUrl(source, folder, p.clean_photo_id, ANCHO_VISOR)
    : null;
  const fichaVisor = p.titled_photo_id
    ? buildPhotoUrl(source, folder, p.titled_photo_id, ANCHO_VISOR)
    : null;

  // Los hashtags son COMUNES a todos los nichos: si se añade uno en POV BOF
  // aparece aquí. Lo pidió así el operador.
  const caption = [p.caption, p.emojis, (hashtags.data ?? []).join(" ")]
    .filter(Boolean)
    .join(" ");

  const push = (patch: Record<string, unknown>) =>
    setEstado.mutate(
      { source, folder, producto: p.producto, ...patch },
      { onError: (e) => toast.error(err(e)) },
    );

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => setVerFoto(true)}
          className="shrink-0 rounded-md transition hover:ring-2 hover:ring-cyan-500"
        >
          <FotoProducto
            src={limpia}
            alt={p.titulo ?? p.producto}
            className="h-16 w-16 rounded-md object-cover"
          />
        </button>
        <div className="min-w-0 flex-1">
          <p className="flex items-baseline gap-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {p.producto}
            </span>
            <span className="truncate">{p.titulo ?? "sin título"}</span>
          </p>
          {p.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{p.tienda}</p>
          )}
          {p.subida_at ? (
            <p className="truncate text-[10px] text-muted-foreground">
              subido al Drive el {fechaCorta(p.subida_at)}
            </p>
          ) : null}
          {esTopVendidos && p.ventas > 0 && (
            <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px]">
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-semibold text-emerald-500">
                🔥 {p.ventas} {p.ventas === 1 ? "venta" : "ventas"}
              </span>
              {esVentaNueva(p.vendido_at) && (
                <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-500">
                  nuevo
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      {/* Solo lo que se usa al publicar un creativo. */}
      <div className="flex flex-wrap gap-1">
        <CopyChip label="🔎 Título TikTok" text={p.titulo_tiktok_completo ?? ""} siempre />
        <CopyChip label="🏪 Tienda" text={p.tienda ?? ""} siempre />
        <CopyChip label="✍️ Caption" text={caption} siempre />
        <BotonUrl
          url={p.product_url}
          source={source}
          folder={p.folder || folder}
          producto={p.producto}
        />
      </div>

      {p.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {p.caption_riesgo}
        </p>
      )}

      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => {
            const v = !enEscaparate;
            setEnEscaparate(v);
            push({ en_escaparate: v });
          }}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            enEscaparate
              ? "border-cyan-500 bg-cyan-500/15 text-cyan-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          🏪 Escaparate
        </button>
        {/* Lo marca el operador a mano: aquí no hay montaje que termine, el
            creativo se genera fuera. */}
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
        <button
          type="button"
          onClick={() => {
            const v = !sold;
            setSold(v);
            push({ sold: v });
          }}
          className={`flex-1 rounded-md border px-2 py-1.5 text-[11px] font-medium transition ${
            sold
              ? "border-emerald-500 bg-emerald-500/15 text-emerald-500"
              : "border-border/60 text-muted-foreground"
          }`}
        >
          💰 Vendió
        </button>
      </div>


      {/* Se baja la de la FICHA también aquí, no solo en la descarga masiva:
          el creativo necesita los beneficios del producto y solo están ahí. */}
      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={p.titulo ?? `Producto ${p.producto}`}
        urlLimpia={limpiaVisor}
        urlTitulo={fichaVisor}
        urlDescarga={buildCleanPhotoDownloadUrl(source, folder, p.producto, "ficha")}
        textoDescarga="Descargar la foto con la descripción"
      />
    </div>
  );
}
