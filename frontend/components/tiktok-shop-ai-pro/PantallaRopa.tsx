"use client";

import {
  Check,
  ClipboardCopy,
  Download,
  Loader2,
  Sparkles,
  Store,
  Upload,
  Shirt,
  ShoppingBag,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { nombreDescarga } from "@/lib/descargas";

import { api, ApiError } from "@/lib/api";
import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import {
  buildFotoLimpiaRopaUrl,
  buildFotoRopaUrl,
  buildVideoRopaUrl,
  nichoRopaKeys,
  useCarpetasRopa,
  useCrearMiPrenda,
  useImportarPrendasWeb,
  useImportarUrlsRopa,
  useExtraerTextosRopa,
  usePrendas,
  usePromptsRopa,
  useSetEstadoRopa,
  type PrendaItem,
} from "@/lib/queries/nichoRopa";
import { BotonDescarga } from "@/components/tiktok-shop-ai-pro/BotonDescarga";
import { Caja, Paso, Sub } from "@/components/tiktok-shop-ai-pro/Paso";
import { VideoModal } from "@/components/ui/video-modal";
import { BotonUrl } from "@/components/tiktok-shop-ai-pro/BotonUrl";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

/** Los modos de grabación: dónde está la cámara. Cada uno es un vídeo
 *  distinto de la MISMA prenda y guarda su propio estado — igual que los
 *  estilos de guion del POV BOF Largo. Añadir uno es añadirlo aquí y en
 *  `nicho_ropa/config.py:MODOS`. */
/** Los modos que enseñar mientras el backend no ha contestado.
 *
 *  Solo los dos de siempre y sin inventarse cuáles son de cada sexo: la lista
 *  buena viene con los prompts (`modos`), porque el curso no publica los
 *  mismos formatos para hombre y para mujer. */
const MODOS_FALLBACK = [
  { clave: "espejo", label: "🪞 BOF Frente a Espejo" },
];

/** Alta de prendas PROPIAS, en los cuatro catálogos del operador.
 *
 *  Mismo planteamiento que "Muestras/Tareas" del POV BOF y por el mismo
 *  motivo: una prenda se graba porque la tienda mandó muestra o porque es una
 *  tarea pagada. Aquí son CUATRO y no dos porque el género manda — lo que
 *  subas en mujer no vale para hombre, ni la prenda ni la modelo—, así que el
 *  catálogo lleva el género dentro y lo de mujer se queda en mujer.
 */
function AltaMiPrenda({
  sexo,
  onCreado,
}: {
  sexo: string;
  onCreado: (slug: string) => void;
}) {
  const crear = useCrearMiPrenda();
  const [abierto, setAbierto] = useState(false);
  const [catalogo, setCatalogo] = useState(`${sexo}_muestras`);
  const [limpia, setLimpia] = useState<File | null>(null);
  const [ficha, setFicha] = useState<File | null>(null);
  const refLimpia = useRef<HTMLInputElement>(null);
  const refFicha = useRef<HTMLInputElement>(null);

  // Solo los del sexo que se está viendo: dar de alta en el otro dejaba la
  // prenda en una carpeta que la pantalla no enseña, o sea desaparecida.
  const CATALOGOS: [string, string][] =
    sexo === "hombre"  // los dos del sexo de la pantalla, ver `sexoFijo`
      ? [
          ["hombre_muestras", "👔 Hombre · muestras"],
          ["hombre_tareas", "👔 Hombre · tareas"],
        ]
      : [
          ["mujer_muestras", "👗 Mujer · muestras"],
          ["mujer_tareas", "👗 Mujer · tareas"],
        ];
  // Al cambiar de sexo arriba, el catálogo elegido es del otro inventario.
  useEffect(() => {
    setCatalogo(`${sexo}_muestras`);
  }, [sexo]);

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
  onImportado,
}: {
  genero: string;
  onImportado: (slug: string) => void;
}) {
  const importar = useImportarPrendasWeb();

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
/** Lo que se pinta en el chip de una carpeta.
 *
 *  La etiqueta que da el backend lleva el inventario delante ("👗 Mujer web ·
 *  Carpeta_2") y en un chip no cabe — además el inventario ya lo dice la
 *  pantalla entera. Se queda con lo que distingue a una carpeta de otra.
 */
function nombreCorto(label: string): string {
  const partes = label.split("·");
  return (partes[partes.length - 1] ?? label).trim() || label;
}

export type Variante = "curso" | "web";
export type SexoRopa = "mujer" | "hombre";

/** `sexo` solo llega en la variante web y lo fija la RUTA, no un selector.
 *
 *  Mujer y hombre son dos pantallas y no una con un botón porque cada
 *  inventario se lleva en una cuenta de TikTok distinta: al entrar no hay que
 *  acordarse de en cuál te quedaste, y no se sube un ZIP de mujer al catálogo
 *  de hombre por no mirar. Todo lo demás —diseño, pasos, prompts— es idéntico.
 */
export function PantallaRopa({
  variante,
  sexo: sexoFijo = "mujer",
}: {
  variante: Variante;
  sexo?: SexoRopa;
}) {
  const esWeb = variante === "web";
  // Dónde está la cámara. Cada modo guarda SU vídeo de la misma prenda, igual
  // que los estilos de guion del POV BOF Largo: se graba la prenda de las dos
  // maneras y son dos publicaciones distintas.
  const [modo, setModo] = useEstadoDeUsuario(`ropa-web:${sexoFijo}:modo`, "espejo");
  // La carpeta y el modo se recuerdan POR PANTALLA: si compartieran clave, al
  // pasar de mujer a hombre te encontrarías en la carpeta de la otra.
  const [carpeta, setCarpeta] = useEstadoDeUsuario(
    esWeb ? `ropa-web:${sexoFijo}:carpeta` : "ropa:carpeta",
    esWeb ? "" : "camisetas",
  );
  const carpetas = useCarpetasRopa(esWeb ? sexoFijo : "", esWeb ? modo : "");
  // De quién es esta pantalla. Lo manda la ruta, así que ni hay selector ni
  // estado: los ZIP que se suban y el prompt que se enseñe son de este sexo.
  const sexo = sexoFijo;
  const genero = `${sexo}_web`;
  // Cada pantalla ve SOLO sus carpetas — y en la web, SOLO las del sexo
  // elegido arriba: son dos inventarios distintos (mujer y hombre), y con los
  // dos a la vez el selector mezclaba las carpetas propias de hombre estando
  // en mujer. Se filtra por el `sexo` que da el backend, no por el slug.
  const misCarpetas = (carpetas.data?.items ?? []).filter(
    (c) => c.web === esWeb && (!esWeb || c.sexo === sexo),
  );
  // Si la guardada es de la otra pantalla (o ya no existe), se cae a la
  // primera. Pasa al estrenar esto: la web se elegía desde "sin humanos".
  const carpetaValida = misCarpetas.some((c) => c.slug === carpeta);
  // Dónde está la cámara. Cada modo guarda SU vídeo de la misma prenda, igual
  // que los estilos de guion del POV BOF Largo: se graba la prenda de las dos
  // maneras y son dos publicaciones distintas.

  const primera = misCarpetas[0]?.slug ?? "";
  useEffect(() => {
    if (!primera || carpetaValida) return;
    setCarpeta(primera);
  }, [carpetaValida, primera, setCarpeta]);
  const prendas = usePrendas(carpeta, modo);
  // Sin carpeta elegida manda el selector de arriba: `hombre_web__` no es una
  // carpeta de verdad, pero al backend le basta para saber el sexo.
  // Los dos prompts a la vez: cada prenda usa el suyo según lo que ofrezca su
  // ficha, y se trabaja por tandas (se bajan las fotos de un grupo y se pegan
  // todas con el mismo prompt).
  const slugPrompts = carpeta || (esWeb ? `${genero}__` : "");
  // Con el modo: la pantalla enseña SOLO el prompt del modo en el que estás.
  // Con los dos a la vista era cuestión de tiempo copiar el que no era.
  const prompts = usePromptsRopa(slugPrompts, false, esWeb ? modo : "");
  // Los modos son del SEXO, no de la pantalla: en hombre hay cuatro formatos
  // y en mujer dos, y cada uno guarda su propio vídeo de la misma prenda.
  const modos = prompts.data?.modos?.length ? prompts.data.modos : MODOS_FALLBACK;
  // Al pasar de hombre a mujer, el modo guardado puede ser de los que solo
  // existen en hombre: sin esto la pantalla se queda en un modo que ya no
  // está en la lista y ningún botón sale marcado.
  useEffect(() => {
    if (!modos.length || modos.some((m) => m.clave === modo)) return;
    setModo(modos[0]!.clave);
  }, [modos, modo, setModo]);
  const promptsPlazos = usePromptsRopa(slugPrompts, true, esWeb ? modo : "");
  const extraer = useExtraerTextosRopa();

  const items = prendas.data?.items ?? [];
  // Una carpeta está "hecha" cuando todas sus prendas tienen el vídeo DE ESTE
  // modo: el progreso es por modo, igual que el vídeo.
  const carpetasHechas = misCarpetas.filter(
    (c) => !!c.total && (c.con_video ?? 0) >= c.total,
  ).length;
  const pctCarpetas = misCarpetas.length
    ? Math.round((carpetasHechas / misCarpetas.length) * 100)
    : 0;
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

  async function descargarFotos(grupo: "todas" | "plazos" | "sin" = "todas") {
    const conFoto = items
      .filter((p) => p.clean_photo_id)
      .filter((p) =>
        grupo === "todas" ? true : grupo === "plazos" ? p.plazos : !p.plazos,
      );
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

  const [bajandoVideos, setBajandoVideos] = useState("");

  async function descargarVideos(soloConUrl = false) {
    const conVideoBajar = items
      .filter((p) => p.video_path)
      .filter((p) => (soloConUrl ? p.product_url : true));
    if (!conVideoBajar.length) return;
    setBajandoVideos(`0/${conVideoBajar.length}`);
    for (const [i, p] of conVideoBajar.entries()) {
      setBajandoVideos(`${i + 1}/${conVideoBajar.length}`);
      const a = document.createElement("a");
      a.href = buildVideoRopaUrl(p.producto, carpeta, p.video_listo_at, true, modo);
      a.download = nombreDescarga("ropa", p.producto) + ".mp4";
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Una a una y con pausa: el navegador del móvil cancela las simultáneas.
      if (i < conVideoBajar.length - 1) await new Promise((r) => setTimeout(r, 900));
    }
    setBajandoVideos("");
    toast.success(`${conVideoBajar.length} vídeo(s) descargados`);
  }

  const videosConUrl = items.filter((p) => p.video_path && p.product_url).length;

  // Las prendas que ofrecen pago a plazos se trabajan aparte: llevan otro
  // prompt, y el vídeo lo dice con la voz de la persona. Bajarlas por grupos
  // es lo que evita pegar el prompt equivocado a media tanda.
  const conPlazos = items.filter((p) => p.clean_photo_id && p.plazos).length;
  const sinPlazos = items.filter((p) => p.clean_photo_id && !p.plazos).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4">
      {/* Cabecera de TEXTO, como en el POV BOF: la portada del curso ocupaba
          media pantalla en el móvil y decía menos que dos líneas. Lo primero
          que hay que ver es en qué inventario estás. */}
      {esWeb ? (
        <header className="rounded-xl border border-border/60 bg-card p-3">
          <div className="flex items-center gap-2">
            <Shirt className="h-5 w-5 shrink-0 text-violet-500" />
            <div className="min-w-0">
              <h1 className="text-base font-bold sm:text-lg">
                {sexo === "hombre" ? "Nicho Ropa Hombre" : "Nicho Ropa Mujer"}
              </h1>
              <p className="text-[11px] text-muted-foreground">
                La prenda PUESTA, grabada con el móvil · un clip de 10s por
                modo
              </p>
            </div>
          </div>
          <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
            Las prendas entran por ZIP desde la web del curso y este inventario
            es solo de {sexo}: el otro va en su pantalla. El clip sale del
            generador ya hablado, así que se le respeta su voz y no lleva
            ningún texto quemado.
          </p>
        </header>
      ) : (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={portadaDe("nicho-ropa-sin-humanos")}
            alt="Creación de Nicho Ropa Sin Humanos"
            className="h-auto w-full rounded-xl border border-border/60"
          />
        </>
      )}

      {/* "Dónde trabajas", igual que en el POV BOF y el Largo: la misma caja
          con rótulos, el mismo contador y los mismos chips de carpeta. Quien
          aprende un nicho sabe usar los otros — antes esto eran bloques
          sueltos sin título y botones el doble de altos. */}
      <Caja
        icono="📁"
        titulo="Dónde trabajas"
        hint={
          esWeb
            ? `Elige la carpeta. El inventario es de ${sexo} y el vídeo, del modo elegido.`
            : "Elige la carpeta de prendas."
        }
        extra={esWeb ? `${carpetasHechas}/${misCarpetas.length} con vídeo` : undefined}
      >
        {esWeb && (
          <>
            <Sub>Traer prendas</Sub>
            <ImportarPrendasWeb genero={genero} onImportado={(slug) => setCarpeta(slug)} />
            {misCarpetas.length > 0 && <PegarFichasRopa genero={genero} />}
            <AltaMiPrenda sexo={sexo} onCreado={(slug) => setCarpeta(slug)} />

            <Sub>Modo de grabación</Sub>
            <div className="grid grid-cols-2 gap-1.5">
              {modos.map(({ clave, label }) => (
                <button
                  key={clave}
                  type="button"
                  onClick={() => setModo(clave)}
                  className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] transition ${
                    modo === clave
                      ? "border-violet-500 bg-violet-500/10 font-semibold text-violet-400"
                      : "border-border/60 text-muted-foreground hover:border-foreground/30"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground">
              Cada modo guarda su propio vídeo: cambiar aquí no pisa lo del
              otro. Los textos, las fotos y el escaparate son comunes.
            </p>
          </>
        )}

        <Sub>Carpetas</Sub>
        {esWeb && (
          <>
            <p className="text-xs font-medium sm:text-sm">
              {carpetasHechas} / {misCarpetas.length} con vídeo
            </p>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${pctCarpetas}%` }}
              />
            </div>
          </>
        )}
        {/* Chips y no botones de dos columnas: son una decena y así caben a la
            vista, que es lo que deja saltar a cualquiera sin desplegar nada. */}
        <div className="mt-1 flex flex-wrap gap-1">
          {misCarpetas.map((c) => {
            const hecha = !!c.total && (c.con_video ?? 0) >= c.total;
            return (
              <button
                key={c.slug}
                type="button"
                onClick={() => setCarpeta(c.slug)}
                className={`break-words leading-tight rounded border px-2 py-1 text-[10px] transition ${
                  carpeta === c.slug
                    ? hecha
                      ? "border-emerald-500 bg-emerald-500/15 font-semibold text-emerald-500"
                      : "border-sky-500 bg-sky-500/15 font-semibold text-sky-400"
                    : hecha
                      ? "border-emerald-500/40 text-emerald-500"
                      : "border-border/60 text-muted-foreground hover:border-foreground/30"
                }`}
              >
                {hecha && "✓ "}
                {nombreCorto(c.label)}
                {/* Con ficha SOBRE EL TOTAL, como en el POV BOF: un "9" solo no
                    dice si la carpeta tiene nueve prendas o diez con una sin
                    enlazar, que es lo que decide si merece abrirla. */}
                {!!c.total && (
                  <span
                    title={`${c.con_url ?? 0} de ${c.total} con la ficha enlazada · ${c.con_video ?? 0} con vídeo`}
                    className={`ml-1 rounded-full px-1 py-px text-[9px] font-semibold ${
                      (c.con_url ?? 0) >= c.total
                        ? "bg-emerald-500/15 text-emerald-500"
                        : "bg-amber-500/15 text-amber-500"
                    }`}
                  >
                    {(c.con_url ?? 0) >= c.total ? c.total : `${c.con_url ?? 0}/${c.total}`}
                  </span>
                )}
              </button>
            );
          })}
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
      </Caja>

      {/* Los mismos pasos numerados y de colores que el POV BOF: entra gente
          nueva a usar esto y el orden tiene que leerse sin explicarlo. */}
      <Paso
        n={1}
        color="violeta"
        titulo="Textos de la ficha"
        hint="Lee las capturas con IA: título, tienda, caption, precio y si admite pago a plazos."
        extra={`${conTexto}/${items.length}`}
      >
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
      </Paso>

      {verEscaparate && (
        <EscaparateModalRopa
          carpeta={carpeta}
          prendas={items}
          onClose={() => setVerEscaparate(false)}
        />
      )}

      {/* Paso 2 — las fotos, que es lo primero que se lleva uno al generador */}
      <Paso
        n={2}
        color="fucsia"
        titulo="Bajar las fotos"
        hint={
          esWeb
            ? "La foto de la prenda es la referencia del generador. Si hay prendas con pago a plazos se bajan aparte: llevan otro prompt."
            : "La foto de la prenda es la referencia del generador."
        }
        extra={`${items.filter((p) => p.clean_photo_id).length} foto(s)`}
      >
        <BotonDescarga
          onClick={() => void descargarFotos()}
          cargando={false}
          etiqueta={`Todas (${sinPlazos + conPlazos})`}
        />
        {esWeb && !!conPlazos && (
          /* Los dos grupos, a la misma altura: se baja uno, se pega SU prompt
             y se generan todas seguidas. La foto es la misma en los dos; lo
             que cambia es el prompt que le toca. */
          <div className="grid grid-cols-2 gap-1.5">
            <BotonDescarga
              onClick={() => void descargarFotos("sin")}
              cargando={false}
              disabled={!sinPlazos}
              etiqueta={`Sin plazos (${sinPlazos})`}
            />
            <BotonDescarga
              onClick={() => void descargarFotos("plazos")}
              cargando={false}
              etiqueta={`💳 Con plazos (${conPlazos})`}
              tono="url"
            />
          </div>
        )}
      </Paso>

      {/* Paso 3 — el prompt que se pega en el generador */}
      <Paso
        n={3}
        color="esmeralda"
        titulo="Copiar el prompt"
        hint={
          esWeb
            ? "Se pega en el generador junto con la foto. El de plazos SOLO para las prendas que lo ofrecen: lo dice la persona del vídeo y no hay arreglo después."
            : "Se pega en el generador junto con la foto de la prenda."
        }
      >
        {esWeb && prompts.data?.video_espejo ? (
          /* Las dos versiones, a la misma altura. Quién graba lo decide la
             carpeta: en las de hombre sale en masculino. Solo sale en el modo
             espejo — el backend lo manda vacío en los demás. */
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() =>
                copiar(
                  `Prompt espejo (${prompts.data?.sexo ?? ""})`,
                  prompts.data?.video_espejo,
                )
              }
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
            >
              <ClipboardCopy className="h-3.5 w-3.5 shrink-0" /> Espejo · sin
              plazos
            </button>
            <button
              type="button"
              onClick={() =>
                copiar(
                  `Prompt espejo con plazos (${promptsPlazos.data?.sexo ?? ""})`,
                  promptsPlazos.data?.video_espejo,
                )
              }
              className="flex items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-2 text-xs text-violet-400 transition hover:border-violet-400"
            >
              <ClipboardCopy className="h-3.5 w-3.5 shrink-0" /> Espejo · 💳 con
              plazos
            </button>
          </div>
        ) : null}
        {esWeb && (
          <p className="text-[10px] text-muted-foreground">
            {modos.find((m) => m.clave === modo)?.label ?? ""} · quien graba lo
            decide la carpeta:{" "}
            {prompts.data?.sexo === "hombre" ? "👔 hombre" : "👗 mujer"}.
          </p>
        )}
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
              {/* En orden: primero la imagen (paso 1) a lo ancho, y debajo
                  los DOS guiones del paso 2 uno al lado del otro — son la
                  misma cosa en sus dos versiones, así que van juntos. */}
              <button
                type="button"
                onClick={() => copiar(`Imagen · ${e.label}`, e.imagen)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
              >
                <ClipboardCopy className="h-3.5 w-3.5 shrink-0" /> 1 · Imagen
                (Flow)
              </button>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => copiar(`Guion · ${e.label}`, e.guion)}
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30"
                >
                  <ClipboardCopy className="h-3.5 w-3.5 shrink-0" /> 2 · Guion
                </button>
                <button
                  type="button"
                  onClick={() =>
                    copiar(
                      `Guion con plazos · ${e.label}`,
                      // El guion es lo único que cambia entre las dos
                      // versiones; la imagen del paso 1 es la misma.
                      (promptsPlazos.data?.mof10 ?? []).find(
                        (x) => x.clave === e.clave,
                      )?.guion ?? e.guion,
                    )
                  }
                  className="flex items-center justify-center gap-1.5 rounded-lg border border-violet-500/50 px-3 py-2 text-xs text-violet-400 transition hover:border-violet-400"
                >
                  <ClipboardCopy className="h-3.5 w-3.5 shrink-0" /> 2 · Guion 💳
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
      </Paso>

      {/* Paso 4 — lo que ya está montado */}
      <Paso
        n={4}
        color="azul"
        titulo="Descargar lo ya montado"
        hint="Los vídeos listos para subir a TikTok. Se bajan en el orden que ves en pantalla."
        extra={`${conVideo}/${items.length}`}
      >
        <div className="grid grid-cols-2 gap-1.5">
          <BotonDescarga
            onClick={() => void descargarVideos()}
            cargando={!!bajandoVideos}
            progreso={bajandoVideos}
            disabled={!conVideo}
            etiqueta={`Vídeos ${conVideo}/${items.length}`}
          />
          <BotonDescarga
            onClick={() => void descargarVideos(true)}
            cargando={false}
            disabled={!!bajandoVideos || !videosConUrl}
            etiqueta={`🔗 Con URL (${videosConUrl})`}
            tono="url"
          />
        </div>
      </Paso>

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
        <p className="text-sm font-semibold">Prendas</p>
        {/* Dos por fila desde tablet, como los productos del POV BOF: en una
            sola columna hay que bajar diez pantallas para ver la carpeta
            entera, y lo que se hace aquí es ir saltando de prenda en prenda. */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <PrendaCard
              key={p.producto}
              prenda={p}
              carpeta={carpeta}
              esWeb={esWeb}
              modo={modo}
              onCopiar={copiar}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function PrendaCard({
  prenda,
  carpeta,
  esWeb,
  modo,
  onCopiar,
}: {
  prenda: PrendaItem;
  carpeta: string;
  esWeb: boolean;
  /** Modo de grabación en el que se está trabajando: decide QUÉ vídeo se ve
   *  y dónde se guarda el que se suba. */
  modo: string;
  onCopiar: (label: string, texto?: string) => void;
}) {
  const setEstado = useSetEstadoRopa(carpeta);
  const qc = useQueryClient();
  // Con XHR y no `fetch` para tener progreso REAL de subida: un clip son
  // decenas de MB desde el móvil y sin porcentaje no se sabe si va o se colgó
  // (mismo patrón que el POV BOF).
  const [pct, setPct] = useState<number | null>(null);
  // Qué audio lleva el vídeo. Vacío es el defecto de cada pantalla: mudo en
  // las del curso, y la voz que ya trae el clip en las de la web.
  const [audio, setAudio] = useState("");
  const [verVideo, setVerVideo] = useState(false);
  const [verFoto, setVerFoto] = useState(false);

  function elegirArchivo(file: File | null) {
    if (!file) return;
    // "mudo" solo existe en la web: es pedir que se tire la voz del clip.
    const sexo = audio === "hombre" || audio === "mujer" ? audio : "";
    setPct(0);
    const fd = new FormData();
    fd.append("producto", prenda.producto);
    fd.append("carpeta", carpeta);
    fd.append("sexo", sexo);
    if (esWeb && audio === "mudo") fd.append("conservar_audio", "0");
    fd.append("modo", modo);
    fd.append("file", file);

    const base = api.baseUrl;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${base}/api/v1/nicho-ropa/video/upload`);
    const apiKey = process.env.NEXT_PUBLIC_API_KEY;
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setPct(null);
      try {
        const r = JSON.parse(xhr.responseText) as { ok?: boolean; message?: string };
        if (r.ok) toast.success(r.message || "En la cola, editando…");
        else toast.error(r.message || "Error subiendo el vídeo");
      } catch {
        toast.error(`Error ${xhr.status} subiendo el vídeo`);
      }
      // Sin esto la lista no se entera de que hay un montaje en marcha y el
      // sondeo no arranca: había que recargar para ver el botón de Ver.
      void qc.invalidateQueries({ queryKey: nichoRopaKeys.prendas(carpeta) });
    };
    xhr.onerror = () => {
      setPct(null);
      toast.error("Error de red al subir");
    };
    xhr.send(fd);
  }

  const caption = prenda.caption
    ? `${prenda.emojis ? `${prenda.emojis} ` : ""}${prenda.caption}`
    : "";

  return (
    /* Apretada como las del POV BOF: el borde marca el estado (verde en
       cuanto hay vídeo) y los huecos son de 1,5 en vez de 2 — con veinte
       prendas, cada respiro de más es media pantalla de scroll. */
    <div
      className={`space-y-1.5 rounded-xl border bg-card p-2.5 transition ${
        prenda.video_path
          ? "border-emerald-500/50"
          : "border-border/60 hover:border-emerald-500/30"
      }`}
    >
      <div className="flex gap-2">
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
              className="h-16 w-16 rounded-lg object-cover transition hover:opacity-80"
            />
          </button>
        ) : (
          <div className="h-16 w-16 shrink-0 rounded-lg bg-muted" />
        )}
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="flex flex-wrap items-baseline gap-x-1.5 text-xs font-semibold">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {prenda.producto}
            </span>
            {prenda.sin_stock && (
              <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-500">
                🚫 Sin stock
              </span>
            )}
            {prenda.video_path && (
              <span className="text-[10px] font-normal text-emerald-500">
                <Check className="inline h-3 w-3" /> vídeo listo
              </span>
            )}
            {prenda.montando && (
              <span className="text-[10px] font-normal text-amber-500">
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

      {/* Si su ficha ofrece pago a plazos. Aquí no se extrae el precio, así
          que lo marca el operador mirándola — y de esto depende QUÉ PROMPT le
          toca: el vídeo lo dice con la voz de la persona y prometerlo de más
          solo se arregla generando el clip otra vez. Con esto marcado, la
          prenda entra en el grupo "💳 Con plazos" de la descarga de arriba. */}
      {esWeb && (
        /* Lo dice la FICHA: sale al extraer los textos, igual que en el POV
           BOF. El botón está para corregirla —una captura cortada, o el
           vendedor que lo cambia— y un toque más devuelve el control a la
           ficha. De esto depende qué prompt le toca a la prenda. */
        <button
          type="button"
          onClick={() =>
            setEstado.mutate(
              prenda.plazos_manual == null
                ? { producto: prenda.producto, plazos: !prenda.plazos }
                : { producto: prenda.producto, plazos_auto: true },
              {
                onError: (e) =>
                  toast.error(e instanceof ApiError ? e.message : String(e)),
              },
            )
          }
          title={
            prenda.plazos_manual == null
              ? "Lo dice su ficha. Tócalo para corregirlo."
              : "Corregido a mano. Tócalo para volver a lo que diga la ficha."
          }
          className={`w-full rounded-md border px-2 py-1 text-[10px] font-medium transition ${
            prenda.plazos
              ? "border-violet-500 bg-violet-500/15 text-violet-400"
              : "border-border/60 text-muted-foreground hover:border-violet-500/50"
          }`}
        >
          {prenda.plazos ? "💳 Con pago a plazos" : "💳 Sin pago a plazos"}
          {prenda.plazos_manual != null && " · a mano"}
          {prenda.precio ? ` · ${prenda.precio} €` : ""}
        </button>
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

      {/* Mientras se monta, igual que en el POV BOF: la lista se sondea sola
          y el botón de Ver aparece al terminar, pero sin esta línea no se sabe
          si el vídeo se está haciendo o se quedó a medias. */}
      {prenda.montando && (
        <p className="flex items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Montando el vídeo…
        </p>
      )}

      <div className="grid grid-cols-2 gap-2">
        <label className="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-1.5 text-[11px] transition hover:border-foreground/30">
          {pct !== null ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Subiendo {pct}%
            </>
          ) : (
            <>
              <Upload className="h-3.5 w-3.5" /> Subir vídeo
            </>
          )}
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
          // En verde cuando hay algo que ver, como en los demás nichos: es la
          // señal de "esta prenda ya está hecha" sin leer nada.
          className={`rounded-lg border px-3 py-1.5 text-[11px] transition disabled:opacity-40 ${
            prenda.video_path
              ? "border-emerald-500/60 text-emerald-500 hover:bg-emerald-500/10"
              : "border-border/60 hover:border-foreground/30"
          }`}
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
            ? buildVideoRopaUrl(
                prenda.producto, carpeta, prenda.video_listo_at, false, modo,
              )
            : null
        }
        downloadUrl={
          prenda.video_path
            ? buildVideoRopaUrl(
                prenda.producto, carpeta, prenda.video_listo_at, true, modo,
              )
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
