"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Loader2,
  Sparkles,
  Store,
  Upload,
  ShoppingBag,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { nombreDescarga } from "@/lib/descargas";

import { ApiError } from "@/lib/api";
import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import {
  buildFotoLimpiaRopaUrl,
  buildFotoRopaUrl,
  buildVideoRopaUrl,
  useCarpetasRopa,
  useCrearMiPrenda,
  useImportarPrendasWeb,
  useImportarUrlsRopa,
  useExtraerTextosRopa,
  usePrendas,
  usePromptsRopa,
  useSetEstadoRopa,
  useSubirVideoRopa,
  type PrendaItem,
} from "@/lib/queries/nichoRopa";
import { VideoModal } from "@/components/ui/video-modal";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

/** Alta de prendas PROPIAS, en los cuatro catálogos del operador.
 *
 *  Mismo planteamiento que "Muestras/Tareas" del POV BOF y por el mismo
 *  motivo: una prenda se graba porque la tienda mandó muestra o porque es una
 *  tarea pagada. Aquí son CUATRO y no dos porque el género manda — lo que
 *  subas en mujer no vale para hombre, ni la prenda ni la modelo—, así que el
 *  catálogo lleva el género dentro y lo de mujer se queda en mujer.
 */
function AltaMiPrenda({ onCreado }: { onCreado: (slug: string) => void }) {
  const crear = useCrearMiPrenda();
  const [abierto, setAbierto] = useState(false);
  const [catalogo, setCatalogo] = useState("mujer_muestras");
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);

  const CATALOGOS: [string, string][] = [
    ["mujer_muestras", "👗 Mujer · muestras"],
    ["mujer_tareas", "👗 Mujer · tareas"],
    ["hombre_muestras", "👔 Hombre · muestras"],
    ["hombre_tareas", "👔 Hombre · tareas"],
  ];

  function enviar() {
    if (!limpia) {
      toast.error("Falta la foto de la prenda.");
      return;
    }
    crear.mutate(
      { genero: catalogo, fotoLimpia: limpia, fotoFicha: ficha },
      {
        onSuccess: (r) => {
          toast.success(`Prenda ${r.prenda} añadida a «${r.carpeta}»`);
          setLimpia(null);
          setFicha(null);
          if (refLimpia.current) refLimpia.current.value = "";
          if (refFicha.current) refFicha.current.value = "";
          onCreado(r.slug);
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
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
        <span className="truncate text-[10px] text-emerald-500">✓ {archivo.name}</span>
      )}
    </label>
  );

  return (
    <section className="space-y-2 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-3">
      {/* Plegado por defecto, como en el POV BOF: dar de alta es cosa de una
          vez al día y desplegado empuja el selector de carpetas pantalla
          abajo cada vez que se entra. */}
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-xs font-semibold sm:text-sm">
          ➕ Añadir una prenda mía
        </span>
        <span className="text-[11px] text-muted-foreground">{abierto ? "▾" : "▸"}</span>
      </button>
      {!abierto ? null : (
        <>
          <div className="grid grid-cols-2 gap-1.5">
            {CATALOGOS.map(([slug, label]) => (
              <button
                key={slug}
                type="button"
                onClick={() => setCatalogo(slug)}
                className={`rounded-lg border px-2 py-1.5 text-[11px] transition ${
                  catalogo === slug
                    ? "border-emerald-500 bg-emerald-500/10 font-semibold text-emerald-500"
                    : "border-border/60 text-muted-foreground hover:border-foreground/30"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {campo(refLimpia, "Foto limpia", "La prenda, sin texto encima", limpia, setLimpia)}
            {campo(refFicha, "Foto descripción", "La captura de la ficha (opcional)", ficha, setFicha)}
          </div>
          <button
            type="button"
            disabled={crear.isPending || !limpia}
            onClick={enviar}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:opacity-50"
          >
            {crear.isPending ? "Subiendo…" : "Añadir prenda"}
          </button>
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            Las carpetas se llenan de 10 en 10 y son independientes por
            catálogo: lo que subas en mujer no aparece en hombre. A partir de
            ahí se usa igual que una prenda de la web — textos, prompts y
            vídeo.
          </p>
        </>
      )}
    </section>
  );
}

/** Subir ZIPs de prendas de la web del curso.
 *
 *  Su web tiene dos inventarios —mujer y hombre— con 31 carpetas de diez cada
 *  uno. Cada carpeta importada aparece como una categoría más del selector,
 *  así que a partir de ahí funciona igual que las cuatro de siempre.
 */
function ImportarPrendasWeb({
  genero,
  setGenero,
  onImportado,
}: {
  genero: string;
  setGenero: (v: string) => void;
  onImportado: (slug: string) => void;
}) {
  const importar = useImportarPrendasWeb();

  return (
    <div className="space-y-2 rounded-lg border border-violet-500/40 bg-violet-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Sube los ZIP de la web. Elige primero de quién es —las carpetas van
        separadas y el prompt del espejo sale en su sexo— y puedes{" "}
        <strong className="text-foreground">elegir varios de golpe</strong>.
        Volver a subirlos solo toca lo que haya cambiado.
      </p>

      <div className="grid grid-cols-2 gap-1.5">
        {[
          ["mujer_web", "👗 Mujer"],
          ["hombre_web", "👔 Hombre"],
        ].map(([slug, etiqueta]) => (
          <button
            key={slug}
            type="button"
            onClick={() => setGenero(slug as string)}
            className={`rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
              genero === slug
                ? "border-violet-500 bg-violet-500/15 text-violet-400"
                : "border-border/60 text-muted-foreground"
            }`}
          >
            {etiqueta}
          </button>
        ))}
      </div>

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

/** Qué inventario enseña la pantalla.
 *
 *  `curso` son las cuatro carpetas planas del Drive del curso: la prenda en
 *  percha o sobre una alfombra, sin nadie. `web` es el catálogo que Jonny
 *  publica en su página y que entra por ZIP en carpetas de diez, donde la
 *  prenda va PUESTA y grabada frente al espejo.
 *
 *  Son dos nichos distintos con el mismo motor detrás (mismas fotos, mismos
 *  textos, mismo montaje), así que comparten pantalla y solo cambia lo que
 *  de verdad es distinto: las carpetas, el prompt y qué pasa con el audio. */
export type Variante = "curso" | "web";

export function PantallaRopa({ variante }: { variante: Variante }) {
  const esWeb = variante === "web";
  const [carpeta, setCarpeta] = useEstadoDeUsuario(
    esWeb ? "ropa-web:carpeta" : "ropa:carpeta",
    esWeb ? "" : "camisetas",
  );
  const carpetas = useCarpetasRopa();
  // Cada pantalla ve SOLO sus carpetas.
  const misCarpetas = (carpetas.data?.items ?? []).filter((c) => c.web === esWeb);
  // Si la guardada es de la otra pantalla (o ya no existe), se cae a la
  // primera. Pasa al estrenar esto: la web se elegía desde "sin humanos".
  const carpetaValida = misCarpetas.some((c) => c.slug === carpeta);
  // De quién son los ZIP que se están subiendo. Sirve además para el prompt
  // mientras no haya ninguna carpeta: sin esto, elegir "Hombre" y ver el
  // prompt en femenino parece un fallo (y lo parecía).
  const [genero, setGenero] = useState("mujer_web");
  const primera = misCarpetas[0]?.slug ?? "";
  useEffect(() => {
    if (!primera || carpetaValida) return;
    setCarpeta(primera);
  }, [carpetaValida, primera, setCarpeta]);
  const prendas = usePrendas(carpeta);
  // Sin carpeta elegida manda el selector de arriba: `hombre_web__` no es una
  // carpeta de verdad, pero al backend le basta para saber el sexo.
  const prompts = usePromptsRopa(carpeta || (esWeb ? `${genero}__` : ""));
  const extraer = useExtraerTextosRopa();

  const items = prendas.data?.items ?? [];
  const conTexto = items.filter((p) => p.titulo).length;
  const conVideo = items.filter((p) => p.video_path).length;
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;

  function copiar(label: string, texto?: string) {
    if (!texto) return;
    navigator.clipboard.writeText(texto);
    toast.success(`${label} copiado`);
  }

  async function descargarFotos() {
    const conFoto = items.filter((p) => p.clean_photo_id);
    if (!conFoto.length) return;
    // Una a una con retardo: el navegador móvil cancela las simultáneas.
    for (const [i, p] of conFoto.entries()) {
      const a = document.createElement("a");
      a.href = buildFotoLimpiaRopaUrl(p.producto, carpeta);
      a.download = nombreDescarga("ropa", p.producto) + ".jpg";
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (i < conFoto.length - 1) await new Promise((r) => setTimeout(r, 600));
    }
    toast.success(`${conFoto.length} foto(s) descargadas`);
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={portadaDe(esWeb ? "nicho-ropa" : "nicho-ropa-sin-humanos")}
        alt={
          esWeb
            ? "Creación de Nicho Ropa Mujer/Hombre"
            : "Creación de Nicho Ropa Sin Humanos"
        }
        className="h-auto w-full rounded-xl border border-border/60"
      />

      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        {esWeb && (
          <ImportarPrendasWeb
            genero={genero}
            setGenero={setGenero}
            onImportado={(slug) => setCarpeta(slug)}
          />
        )}
        {esWeb && misCarpetas.length > 0 && (
          <PegarFichasRopa genero={genero} />
        )}
        {esWeb && <AltaMiPrenda onCreado={(slug) => setCarpeta(slug)} />}

        <div className="grid grid-cols-2 gap-2">
          {misCarpetas.map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCarpeta(c.slug)}
              className={`break-words leading-tight rounded-lg border px-3 py-2 text-xs transition ${
                carpeta === c.slug
                  ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/30"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        {esWeb && !misCarpetas.length && !carpetas.isLoading ? (
          <p className="rounded-lg border border-border/60 px-2.5 py-2 text-[11px] text-muted-foreground">
            Aún no hay ninguna carpeta: sube arriba los ZIP que descargues de
            la web y cada uno aparecerá aquí como una carpeta de diez prendas.
          </p>
        ) : (
          <p className="text-xs font-medium sm:text-sm">
            {items.length} prenda(s) · {conTexto} con texto · {conVideo} con vídeo
          </p>
        )}
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {esWeb ? (
            <>
              El clip sale del generador <strong>ya hablado</strong>, así que se
              le respeta su voz. No lleva ningún texto en pantalla: ni gancho,
              ni título, ni CTA.
            </>
          ) : (
            <>
              Este nicho NO lleva texto en pantalla: ni gancho, ni título, ni
              CTA. Y el vídeo sale <strong>mudo</strong> — la música se la pones
              tú al publicar.
            </>
          )}
        </p>
      </section>

      {/* Paso 1 — textos */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <p className="text-sm font-semibold">1 · Textos</p>
        <button
          type="button"
          disabled={extraer.isPending || items.length === 0}
          onClick={() =>
            extraer.mutate(carpeta, {
              onSuccess: () => toast.success("Textos extraídos"),
              onError: (e) =>
                toast.error(e instanceof ApiError ? e.message : String(e)),
            })
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-700 disabled:opacity-50"
        >
          {extraer.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Leyendo capturas…
            </>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5" /> Obtener textos ({conTexto}/
              {items.length})
            </>
          )}
        </button>

        {/* El ranking de vendidos es ÚNICO y global: dice qué tipo de producto
            buscar, así que se abre desde cualquier nicho. */}
        <button
          type="button"
          onClick={() => setVerVendidos(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-500 transition hover:bg-amber-500/20"
        >
          <ShoppingBag className="h-3.5 w-3.5" />
          Productos que vendieron
        </button>

        {verVendidos && (
          <VendidosModal conBuscador={false} onClose={() => setVerVendidos(false)} />
        )}

        {/* El escaparate es común a todos los nichos: si el producto ya se
            metió desde el POV BOF o desde otra carpeta, aquí sale hecho. */}
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => setVerEscaparate(true)}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-500 transition hover:bg-sky-500/20"
          >
            <Store className="h-3.5 w-3.5" />
            Meter en el escaparate
            <span
              className={`rounded-full px-1.5 text-[10px] font-bold ${
                pendientesEscaparate ? "bg-sky-500 text-black" : "bg-emerald-500 text-black"
              }`}
            >
              {`${items.length - pendientesEscaparate}/${items.length}`}
            </span>
          </button>
        )}
      </section>

      {verEscaparate && (
        <EscaparateModalRopa
          carpeta={carpeta}
          prendas={items}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      {/* Paso 2 — prompts */}
      <section className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
        <p className="text-sm font-semibold">2 · Generar fuera</p>
        <p className="text-[11px] text-muted-foreground">
          Copia el prompt y la foto de la prenda al generador.
        </p>
        {esWeb ? (
          /* El de la web es UNO solo, el del espejo, y quién graba lo decide
             la carpeta: en las de hombre sale en masculino. */
          <button
            type="button"
            onClick={() =>
              copiar(
                `Prompt espejo (${prompts.data?.sexo ?? ""})`,
                prompts.data?.video_espejo,
              )
            }
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-500/5 px-3 py-2 text-xs transition hover:border-violet-400"
          >
            <ClipboardCopy className="h-3.5 w-3.5" /> Prompt del espejo · 1
            tirada{" "}
            <span className="text-muted-foreground">
              ({prompts.data?.sexo === "hombre" ? "👔 hombre" : "👗 mujer"})
            </span>
          </button>
        ) : null}
        {esWeb &&
          (prompts.data?.mof10 ?? []).map((e) => (
            /* Dos pasos: la imagen se hace en Flow y esa imagen se anima con
               voz en Omni. Sale un clip ÚNICO de 10s, sin montaje. */
            <div key={e.clave} className="space-y-1 rounded-lg border border-border/60 p-2">
              <p className="text-[11px] font-medium">
                10 s · {e.label}
                {e.derivado && (
                  <span
                    title="El curso solo publica este estilo para el otro sexo: este texto lo hemos derivado cambiando lo de la persona"
                    className="ml-1.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-500"
                  >
                    derivado
                  </span>
                )}
              </p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => copiar(`Imagen · ${e.label}`, e.imagen)}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
                >
                  <ClipboardCopy className="h-3.5 w-3.5" /> 1 · Imagen (Flow)
                </button>
                <button
                  type="button"
                  onClick={() => copiar(`Guion · ${e.label}`, e.guion)}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
                >
                  <ClipboardCopy className="h-3.5 w-3.5" /> 2 · Guion (Omni)
                </button>
              </div>
            </div>
          ))}
        {!esWeb && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <button
              type="button"
              onClick={() => copiar("Prompt de imagen", prompts.data?.imagen)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5" /> Prompt imagen
            </button>
            {/* Las dos versiones del prompt de vídeo. La única diferencia es la
                frase de la mano acariciando la ropa. */}
            <button
              type="button"
              onClick={() => copiar("Prompt con manos", prompts.data?.video_con_manos)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · con manos
            </button>
            <button
              type="button"
              onClick={() => copiar("Prompt sin manos", prompts.data?.video_sin_manos)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · sin manos
            </button>
            {/* Otro escenario distinto, no una variante del de alfombra. */}
            <button
              type="button"
              onClick={() => copiar("Prompt percha", prompts.data?.video_percha)}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5" /> Vídeo · percha
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={descargarFotos}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" /> Descargar todas las fotos
        </button>
      </section>

      {prendas.isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Leyendo la carpeta de Drive…
        </div>
      )}
      {prendas.isError && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
          {(prendas.error as Error)?.message ?? "No se pudo leer la carpeta."}
        </p>
      )}

      <section className="space-y-2">
        <p className="text-sm font-semibold">3 · Prendas</p>
        {items.map((p) => (
          <PrendaCard
            key={p.producto}
            prenda={p}
            carpeta={carpeta}
            esWeb={esWeb}
            onCopiar={copiar}
          />
        ))}
      </section>
    </div>
  );
}

function PrendaCard({
  prenda,
  carpeta,
  esWeb,
  onCopiar,
}: {
  prenda: PrendaItem;
  carpeta: string;
  esWeb: boolean;
  onCopiar: (label: string, texto?: string) => void;
}) {
  const subir = useSubirVideoRopa();
  // Qué audio lleva el vídeo. Vacío es el defecto de cada pantalla: mudo en
  // las del curso, y la voz que ya trae el clip en las de la web.
  const [audio, setAudio] = useState("");
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);

  function elegirArchivo(file: File | null) {
    if (!file) return;
    // "mudo" solo existe en la web: es pedir que se tire la voz del clip.
    const sexo = audio === "hombre" || audio === "mujer" ? audio : "";
    subir.mutate(
      {
        producto: prenda.producto,
        carpeta,
        file,
        sexo,
        conservar_audio: esWeb && audio === "mudo" ? "0" : "",
      },
      {
        onSuccess: (r) => toast.success(r.message),
        onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  const caption = prenda.caption
    ? `${prenda.emojis ? `${prenda.emojis} ` : ""}${prenda.caption}`
    : "";

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
      <div className="flex gap-2.5">
        {prenda.clean_photo_id ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            title="Ver la foto limpia y la captura con título"
            className="shrink-0"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={buildFotoRopaUrl(prenda.clean_photo_id)}
              alt={`Prenda ${prenda.producto}`}
              loading="lazy"
              className="h-20 w-20 rounded-lg object-cover transition hover:opacity-80"
            />
          </button>
        ) : (
          <div className="h-20 w-20 shrink-0 rounded-lg bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold">
            {prenda.producto}
            {prenda.sin_stock && (
              <span className="ml-1.5 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-500">
                🚫 Sin stock
              </span>
            )}
            {prenda.video_path && (
              <span className="ml-1.5 text-[10px] font-normal text-emerald-500">
                <Check className="inline h-3 w-3" /> vídeo listo
              </span>
            )}
            {prenda.montando && (
              <span className="ml-1.5 text-[10px] font-normal text-amber-500">
                montando…
              </span>
            )}
          </p>
          <p className="line-clamp-2 whitespace-pre-line text-[11px] leading-snug">
            {prenda.titulo || "— sin textos todavía —"}
          </p>
          {prenda.tienda && (
            <p className="truncate text-[10px] text-muted-foreground">{prenda.tienda}</p>
          )}
        </div>
      </div>

      {prenda.foto_aviso && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-500">
          {prenda.foto_aviso}
        </p>
      )}
      {prenda.caption_riesgo && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-500">
          Caption arriesgado: {prenda.caption_riesgo}
        </p>
      )}

      {/* Los mismos tres botones que en el Nicho POV BOF: el caption para
          publicar, y el título de TikTok y la tienda para poder BUSCAR el
          producto en el Centro de Afiliados. */}
      <div className="flex flex-wrap gap-1">
        <CopyChip label="✍️ Caption" text={caption} siempre />
        <BotonUrl url={prenda.product_url} />
        <CopyChip label="🔎 Título TikTok" text={prenda.titulo_tiktok_completo} siempre />
        <CopyChip label="🏪 Tienda" text={prenda.tienda} siempre />
      </div>
      {caption && (
        <p className="rounded-lg border border-border/60 px-2.5 py-1.5 text-[11px] text-muted-foreground">
          {caption}
        </p>
      )}

      <div className={`grid gap-1 ${esWeb ? "grid-cols-4" : "grid-cols-3"}`}>
        {/* El defecto va primero: es lo que el operador quiere casi siempre.
            En la web es la voz del propio clip; en el curso, mudo. */}
        {(esWeb
          ? [
              { v: "", label: "Su voz" },
              { v: "mudo", label: "Mudo" },
              { v: "hombre", label: "Voz H" },
              { v: "mujer", label: "Voz M" },
            ]
          : [
              { v: "", label: "Mudo" },
              { v: "hombre", label: "Voz H" },
              { v: "mujer", label: "Voz M" },
            ]
        ).map((op) => (
          <button
            key={op.v || "defecto"}
            type="button"
            onClick={() => setAudio(op.v)}
            className={`rounded-md border px-2 py-1 text-[10px] transition ${
              audio === op.v
                ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-500"
                : "border-border/60 text-muted-foreground hover:border-foreground/30"
            }`}
          >
            {op.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30">
          {subir.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5" />
          )}
          Subir vídeo
          <input
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="button"
          disabled={!prenda.video_path}
          onClick={() => setVerVideo(true)}
          className="rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30 disabled:opacity-40"
        >
          Ver / descargar
        </button>
      </div>

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={`Prenda ${prenda.producto}`}
        urlLimpia={
          prenda.clean_photo_id ? buildFotoRopaUrl(prenda.clean_photo_id) : null
        }
        urlTitulo={
          prenda.titled_photo_id ? buildFotoRopaUrl(prenda.titled_photo_id) : null
        }
        urlDescarga={
          prenda.clean_photo_id
            ? buildFotoLimpiaRopaUrl(prenda.producto, carpeta)
            : null
        }
      />

      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={`Prenda ${prenda.producto}`}
        filename={`ropa_${prenda.producto}.mp4`}
        videoUrl={
          prenda.video_path
            ? buildVideoRopaUrl(prenda.producto, carpeta, prenda.video_listo_at)
            : null
        }
        downloadUrl={
          prenda.video_path
            ? buildVideoRopaUrl(prenda.producto, carpeta, prenda.video_listo_at, true)
            : null
        }
        localPath={prenda.video_path}
      />
    </div>
  );
}

/** El escaparate de la ropa escribe en el índice común (su propio endpoint),
 *  pero su Drive es otro: las fotos no se piden por `source/folder` sino por
 *  file ID, así que se le pasan las URLs a mano. Tampoco hay `source`: es UNA
 *  carpeta compartida por enlace. */
function EscaparateModalRopa({
  carpeta,
  prendas,
  onClose,
}: {
  carpeta: string;
  prendas: PrendaItem[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoRopa(carpeta);
  return (
    <EscaparateModal
      source=""
      folder={carpeta}
      productos={prendas as unknown as ProductoItem[]}
      onClose={onClose}
      marcarEstado={(vars, opts) =>
        setEstado.mutate(
          { producto: vars.producto, en_escaparate: vars.en_escaparate },
          opts,
        )
      }
      // El endpoint de foto de este nicho no redimensiona: se ignora el ancho.
      fotoUrl={(p) => (p.clean_photo_id ? buildFotoRopaUrl(p.clean_photo_id) : null)}
      fotoFichaUrl={(p) => (p.titled_photo_id ? buildFotoRopaUrl(p.titled_photo_id) : null)}
      descargaUrl={(p) => buildFotoLimpiaRopaUrl(p.producto, carpeta)}
    />
  );
}


/** Pegar de golpe las fichas de TikTok del catálogo de ropa de la web.
 *
 *  Va aquí y no en Configuración —donde están las del POV BOF— porque el
 *  pegote no dice de quién es: su web tiene los dos inventarios con las
 *  carpetas numeradas igual, y el sexo lo da el selector de arriba. Sacarlo de
 *  ese selector es lo que evita meter la ropa de hombre en las carpetas de
 *  mujer sin que nada chille.
 */
function PegarFichasRopa({ genero }: { genero: string }) {
  const importar = useImportarUrlsRopa();
  const [abierto, setAbierto] = useState(false);

  async function subir(f: File | null) {
    if (!f) return;
    let filas: unknown[];
    try {
      filas = JSON.parse(await f.text());
    } catch {
      toast.error("Ese fichero no es el JSON de la consola.");
      return;
    }
    if (!Array.isArray(filas) || !filas.length) {
      toast.error("El fichero no trae ninguna fila.");
      return;
    }
    importar.mutate(
      { genero, filas },
      {
        onSuccess: (r) => {
          toast.success(
            `${r.guardados} ficha(s) en ${r.carpetas} carpeta(s)` +
              (r.agotados ? ` · ${r.agotados} sin stock` : ""),
          );
          if (r.descartadas?.length) {
            toast.warning(
              `${r.descartadas.length} enlace(s) no son de TikTok, sin guardar`,
              { duration: 10000 },
            );
          }
          if (r.sin_carpeta?.length) {
            toast.warning(
              `Sin guardar, no hay esa carpeta: ${r.sin_carpeta.join(", ")}`,
              { duration: 10000 },
            );
          }
          setAbierto(false);
        },
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : String(e)),
      },
    );
  }

  if (!abierto) {
    return (
      <button
        type="button"
        onClick={() => setAbierto(true)}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/5 px-3 py-1.5 text-[11px] font-medium text-emerald-500 transition hover:border-emerald-400"
      >
        🔗 Pegar las fichas de TikTok de golpe
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-2">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        El mismo guion que en Configuración, pero ejecutado en la página de{" "}
        <strong className="text-foreground">
          {genero === "hombre_web" ? "ropa de hombre" : "ropa de mujer"}
        </strong>{" "}
        de su web. Sube aquí el <code>fichas.json</code> que te descargue.
      </p>
      <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-700">
        {importar.isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Guardando…
          </>
        ) : (
          <>📄 Elegir fichas.json</>
        )}
        <input
          type="file"
          accept=".json,application/json"
          disabled={importar.isPending}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            e.target.value = "";
            void subir(f);
          }}
        />
      </label>
      <button
        type="button"
        onClick={() => setAbierto(false)}
        className="w-full rounded-lg border border-border/60 px-2 py-1.5 text-[11px] text-muted-foreground transition hover:border-foreground/30"
      >
        Cerrar
      </button>
    </div>
  );
}
