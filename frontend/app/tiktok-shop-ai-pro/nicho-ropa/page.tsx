"use client";

import {
  Clapperboard,
  ClipboardCopy,
  Download,
  Loader2,
  Scissors,
  Sparkles,
  Store,
  Trash2,
  Upload,
  UserPlus,
  ShoppingBag,
} from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import { useEstadoDeUsuario } from "@/lib/hooks/useEstadoRecordado";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { VendidosModal } from "@/components/tiktok-shop-ai-pro/VendidosModal";
import { EscaparateModal } from "@/components/tiktok-shop-ai-pro/EscaparateModal";
import { FotoModal } from "@/components/tiktok-shop-ai-pro/FotoModal";
import { VideoModal } from "@/components/ui/video-modal";
import { portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import {
  fotoLimpiaRopaPersonasUrl,
  fotoRopaPersonasUrl,
  useBorrarChica,
  useCarpetasRopaPersonas,
  useChicas,
  useCrearChica,
  useExtraerTextosRopaPersonas,
  usePrendasPersonas,
  usePromptsRopaPersonas,
  useSetEstadoRopaPersonas,
  useSubirVideoRopaPersonas,
  useTituloPrenda,
  videoRopaPersonasUrl,
} from "@/lib/queries/nichoRopaPersonas";
import type { PrendaPersonas } from "@/lib/types/nichoRopaPersonas";
import type { ProductoItem } from "@/lib/types/nichoPovBof";

function copiar(label: string, texto: string) {
  navigator.clipboard.writeText(texto);
  toast.success(`${label} copiado`);
}

export default function NichoRopaPersonasPage() {
  const carpetas = useCarpetasRopaPersonas();
  const [carpeta, setCarpeta] = useEstadoDeUsuario("ropa-personas:carpeta", "");
  const activa = carpeta || carpetas.data?.[0]?.slug || "";
  const prendas = usePrendasPersonas(activa);
  const extraer = useExtraerTextosRopaPersonas();
  const prompts = usePromptsRopaPersonas();

  const items = prendas.data?.items ?? [];
  const conTexto = items.filter((p) => p.titulo).length;
  const [verEscaparate, setVerEscaparate] = useState(false);
  const [verVendidos, setVerVendidos] = useState(false);
  const pendientesEscaparate = items.filter((p) => !p.en_escaparate).length;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3 p-3 pb-24">
      <div className="relative h-28 w-full overflow-hidden rounded-xl sm:h-40">
        <Image
          src={portadaDe("nicho-ropa")}
          alt="Nicho Ropa Con Personas"
          fill
          className="object-cover"
          priority
        />
        <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/80 to-transparent p-3">
          <div>
            <h1 className="text-lg font-bold text-white sm:text-xl">
              Nicho Ropa Con Personas
            </h1>
            <p className="text-[11px] text-white/70">
              La prenda puesta por tu modelo · módulo 7
            </p>
          </div>
        </div>
      </div>

      {/* 1) La modelo. Va lo primero porque sin ficha no hay vídeo, y lo
             normal es crearla una vez y reutilizarla durante semanas. */}
      <ChicasPanel />

      {/* 2) Prompts que se copian fuera de la app. */}
      <CollapsibleCard title="🧾 Prompts del curso">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            disabled={!prompts.data?.movimiento}
            onClick={() => copiar("Prompt de movimiento", prompts.data?.movimiento ?? "")}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <Clapperboard className="h-3.5 w-3.5" /> Movimiento de la chica
          </button>
          <button
            type="button"
            disabled={!prompts.data?.extraer_prenda}
            onClick={() => copiar("Prompt de aislar", prompts.data?.extraer_prenda ?? "")}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-xs transition hover:border-foreground/30 disabled:opacity-50"
          >
            <Scissors className="h-3.5 w-3.5" /> Aislar la prenda
          </button>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          El de aislar es para cuando la IA se niega a vestir a la chica (pasa
          con bikinis y lencería): deja la prenda sobre fondo blanco y esa
          imagen sirve de referencia.
        </p>
      </CollapsibleCard>

      {/* 3) Las prendas. */}
      <section className="space-y-3 rounded-xl border border-border/60 bg-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-fuchsia-500" />
          <p className="flex-1 text-sm font-semibold">Prendas</p>
          <span className="text-[11px] text-muted-foreground">
            {conTexto}/{items.length} con textos
          </span>
        </div>

        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          {(carpetas.data ?? []).map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCarpeta(c.slug)}
              className={`break-words leading-tight rounded-lg border px-2 py-1.5 text-[11px] font-medium transition ${
                activa === c.slug
                  ? "border-fuchsia-500 bg-fuchsia-500/15 text-fuchsia-500"
                  : "border-border/60 text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* Estas carpetas no traen captura de la ficha, así que el título no
            se LEE: se saca mirando la foto. Se explica porque el resultado es
            un nombre descriptivo, no el título del listado de TikTok. */}
        <p className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-2 text-[10px] leading-relaxed text-sky-500">
          Aquí no hay captura de la ficha, así que el título sale de mirar la
          foto de la prenda: un nombre corto («Short deportivo rosa con
          cordón»). Es lo que se quema en el centro del vídeo — puedes
          cambiarlo escribiendo encima.
        </p>

        <button
          type="button"
          disabled={extraer.isPending || !activa}
          onClick={() =>
            extraer.mutate(activa, {
              onSuccess: () => toast.success("Textos extraídos"),
              onError: (e) =>
                toast.error(e instanceof ApiError ? e.message : String(e)),
            })
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-fuchsia-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-50"
        >
          {extraer.isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Extrayendo…
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
        {activa && items.length > 0 && (
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

        {verEscaparate && activa && (
          <EscaparateModalRopaPersonas
            carpeta={activa}
            prendas={items}
            onClose={() => setVerEscaparate(false)}
          />
        )}

        {prendas.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando prendas…
          </div>
        )}
        {prendas.isError && (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-500">
            {(prendas.error as Error)?.message ?? "No se pudieron cargar las prendas."}
          </p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {items.map((p) => (
            <PrendaCard key={p.producto} carpeta={activa} prenda={p} />
          ))}
        </div>
      </section>
    </div>
  );
}

/** El escaparate de este nicho escribe en el índice común (por su propio
 *  endpoint), pero las fotos NO vienen del Drive del POV BOF: aquí se piden
 *  por file ID, así que se le pasan al modal las URLs de este nicho. Por eso
 *  `source` va vacío — no existe ese concepto en la ropa. */
function EscaparateModalRopaPersonas({
  carpeta,
  prendas,
  onClose,
}: {
  carpeta: string;
  prendas: PrendaPersonas[];
  onClose: () => void;
}) {
  const setEstado = useSetEstadoRopaPersonas(carpeta);
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
      fotoUrl={(p) =>
        p.clean_photo_id ? fotoRopaPersonasUrl(p.clean_photo_id) : null
      }
      descargaUrl={(p) => fotoLimpiaRopaPersonasUrl(carpeta, p.producto)}
    />
  );
}

/** Las modelos del usuario.
 *
 *  Son SUYAS: la cara es la identidad de la cuenta, así que la chica de uno no
 *  le sale a los demás. Se crea una vez con una foto de internet y su ficha se
 *  copia en cada vídeo. */
function ChicasPanel() {
  const chicas = useChicas();
  const crear = useCrearChica();
  const borrar = useBorrarChica();
  const [nombre, setNombre] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function onFoto(e: React.ChangeEvent<HTMLInputElement>) {
    const foto = e.target.files?.[0];
    e.target.value = "";
    if (!foto) return;
    if (!nombre.trim()) {
      toast.error("Ponle un nombre antes (p. ej. “Chica 1 Néstor”).");
      return;
    }
    crear.mutate(
      { nombre: nombre.trim(), foto },
      {
        onSuccess: () => {
          toast.success("Modelo creada");
          setNombre("");
        },
        onError: (err) =>
          toast.error(err instanceof ApiError ? err.message : String(err)),
      },
    );
  }

  return (
    <CollapsibleCard title="👤 Mis modelos" defaultOpen>
      <div className="space-y-2">
        <div className="flex gap-1.5">
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Nombre de la modelo"
            className="min-w-0 flex-1 rounded-lg border border-border/60 bg-background px-2 py-2 text-xs outline-none transition focus:border-fuchsia-500"
          />
          <button
            type="button"
            disabled={crear.isPending}
            onClick={() => fileRef.current?.click()}
            className="flex shrink-0 items-center gap-1.5 rounded-lg bg-fuchsia-500 px-3 py-2 text-xs font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-50"
          >
            {crear.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Creando…
              </>
            ) : (
              <>
                <UserPlus className="h-3.5 w-3.5" /> Foto
              </>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            onChange={onFoto}
            className="hidden"
          />
        </div>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Busca una foto por internet donde se le vea bien la cara. Se le pasa a
          Gemini con la plantilla del curso y sale su ficha JSON. Si en la foto
          no hay nadie te avisa, para que no acabes con la modelo de ejemplo —
          que es la que tiene todo el mundo.
        </p>

        {chicas.isLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
          </div>
        )}
        {!chicas.isLoading && (chicas.data ?? []).length === 0 && (
          <p className="py-3 text-center text-xs text-muted-foreground">
            Todavía no tienes ninguna. Crea la primera y su ficha se copiará en
            cada vídeo.
          </p>
        )}

        <div className="flex flex-wrap gap-1.5">
          {(chicas.data ?? []).map((c) => (
            <div key={c.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => copiar(`JSON de ${c.nombre}`, c.ficha_texto)}
                title="Copiar su ficha JSON"
                className="flex max-w-[14rem] items-center gap-1 break-words leading-tight rounded-lg border border-fuchsia-500/50 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-fuchsia-500 transition hover:bg-fuchsia-500/20"
              >
                <ClipboardCopy className="h-3 w-3 shrink-0" />
                <span className="truncate">{c.nombre}</span>
              </button>
              <button
                type="button"
                disabled={borrar.isPending}
                onClick={() => {
                  if (!confirm(`¿Borrar la modelo "${c.nombre}"?`)) return;
                  borrar.mutate(c.id, {
                    onError: (err) =>
                      toast.error(err instanceof ApiError ? err.message : String(err)),
                  });
                }}
                aria-label={`Borrar ${c.nombre}`}
                className="rounded-md p-1 text-muted-foreground transition hover:text-red-500 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </CollapsibleCard>
  );
}

function PrendaCard({ carpeta, prenda }: { carpeta: string; prenda: PrendaPersonas }) {
  const subir = useSubirVideoRopaPersonas();
  const guardar = useTituloPrenda();
  const [titulo, setTitulo] = useState(prenda.titulo);

  // Se guarda al salir del campo, no en cada tecla: son 38 prendas y no hace
  // falta una escritura a Redis por letra.
  function guardarTitulo() {
    const limpio = titulo.trim();
    if (limpio === prenda.titulo) return;
    guardar.mutate(
      { carpeta, producto: prenda.producto, titulo: limpio },
      {
        onSuccess: () => toast.success("Título guardado"),
        onError: (err) => {
          setTitulo(prenda.titulo);
          toast.error(err instanceof ApiError ? err.message : String(err));
        },
      },
    );
  }

  const [verFoto, setVerFoto] = useState(false);
  const [verVideo, setVerVideo] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const limpia = prenda.clean_photo_id
    ? fotoRopaPersonasUrl(prenda.clean_photo_id)
    : null;
  const ficha = prenda.titled_photo_id
    ? fotoRopaPersonasUrl(prenda.titled_photo_id)
    : null;

  return (
    <div className="space-y-2 rounded-lg border border-border/60 p-2">
      <div className="flex items-start gap-2">
        {limpia ? (
          <button
            type="button"
            onClick={() => setVerFoto(true)}
            className="shrink-0 rounded-md transition hover:ring-2 hover:ring-fuchsia-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={limpia}
              alt={prenda.titulo || prenda.producto}
              loading="lazy"
              className="h-16 w-16 rounded-md object-cover"
            />
          </button>
        ) : (
          <div className="h-16 w-16 shrink-0 rounded-md bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {prenda.producto}
            </span>
            {/* El título se ESCRIBE aquí: estas carpetas no traen captura de
                la ficha, así que no hay nada que Gemini pueda leer. Y es lo
                que se quema en el centro del vídeo. */}
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              onBlur={guardarTitulo}
              onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
              placeholder="Escribe el título…"
              className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-xs font-semibold outline-none transition hover:border-border/60 focus:border-fuchsia-500"
            />
            {guardar.isPending && (
              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
            )}
          </div>
          {/* Lo que se va a quemar, tal cual va a salir. */}
          {prenda.titulo && (
            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
              en el vídeo: {prenda.titulo} {prenda.emojis}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        <CopyChip label="📝 Título" text={prenda.titulo} siempre />
        <CopyChip label="🔎 Título TikTok" text={prenda.titulo_tiktok_completo} />
        <CopyChip label="🏪 Tienda" text={prenda.tienda} siempre />
        <CopyChip label="✍️ Caption" text={prenda.caption} />
      </div>

      {prenda.foto_aviso && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          🖼️ {prenda.foto_aviso}
        </p>
      )}
      {prenda.caption_riesgo && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-500">
          ⚠️ {prenda.caption_riesgo}
        </p>
      )}

      <div className="grid grid-cols-2 gap-1.5">
        <a
          href={fotoLimpiaRopaPersonasUrl(carpeta, prenda.producto)}
          className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
        >
          <Download className="h-3.5 w-3.5" /> Foto
        </a>
        <button
          type="button"
          disabled={subir.isPending || prenda.montando}
          onClick={() => fileRef.current?.click()}
          className="flex items-center justify-center gap-1.5 rounded-md bg-fuchsia-500 px-2 py-1.5 text-[11px] font-semibold text-white transition hover:bg-fuchsia-600 disabled:opacity-50"
        >
          {prenda.montando ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Montando…
            </>
          ) : (
            <>
              <Upload className="h-3.5 w-3.5" /> Subir vídeo
            </>
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            subir.mutate(
              { carpeta, producto: prenda.producto, file },
              {
                onSuccess: (r) => toast.success(r.message),
                onError: (err) =>
                  toast.error(err instanceof ApiError ? err.message : String(err)),
              },
            );
          }}
        />
      </div>

      {prenda.video_path && (
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={() => setVerVideo(true)}
            className="rounded-md border border-emerald-500/60 px-2 py-1.5 text-[11px] font-medium text-emerald-500 transition hover:bg-emerald-500/10"
          >
            ▶ Ver vídeo
          </button>
          <a
            href={videoRopaPersonasUrl(carpeta, prenda.producto, prenda.video_listo_at, true)}
            className="flex items-center justify-center gap-1.5 rounded-md border border-border/60 px-2 py-1.5 text-[11px] transition hover:border-foreground/30"
          >
            <Download className="h-3.5 w-3.5" /> Descargar
          </a>
        </div>
      )}

      <FotoModal
        open={verFoto}
        onOpenChange={setVerFoto}
        titulo={prenda.titulo || `Prenda ${prenda.producto}`}
        urlLimpia={limpia}
        urlTitulo={ficha}
        urlDescarga={fotoLimpiaRopaPersonasUrl(carpeta, prenda.producto)}
      />
      <VideoModal
        open={verVideo}
        onOpenChange={setVerVideo}
        title={prenda.titulo || `Prenda ${prenda.producto}`}
        filename={`ropa_personas_${prenda.producto}.mp4`}
        videoUrl={videoRopaPersonasUrl(carpeta, prenda.producto, prenda.video_listo_at)}
        downloadUrl={videoRopaPersonasUrl(
          carpeta, prenda.producto, prenda.video_listo_at, true,
        )}
      />
    </div>
  );
}
