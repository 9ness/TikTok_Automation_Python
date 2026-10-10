"use client";

import { Check, Copy, Download, ExternalLink, EyeOff, Loader2, RefreshCw, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { bajarEnOrden, nombreDescarga } from "@/lib/descargas";
import {
  buildFotoTandaUrl,
  buildVideoTandaUrl,
  useCompletarTanda,
  useEpocaTanda,
  useMarcarTanda,
  useMisTandas,
  useOcultarTanda,
  useOcultosTandas,
  useRecargarTandas,
  useSemaforoTanda,
  type ColorSemaforo,
  type Epoca,
  type VideoTanda,
} from "@/lib/queries/misTandas";
import { useHashtags } from "@/lib/queries/nichoPovBof";
import {
  COLOR_NICHO,
  NOMBRE_NICHO,
  colorCatalogo,
  colorModo,
  familiaModo,
} from "@/lib/tiktok-shop-ai-pro/coloresModo";
import { Caja } from "@/components/tiktok-shop-ai-pro/Paso";
import { CopyChip } from "@/components/tiktok-shop-ai-pro/CopyChip";
import { RehacerDialog } from "@/components/tiktok-shop-ai-pro/RehacerDialog";
import { MontadoEl } from "@/components/tiktok-shop-ai-pro/MontadoEl";

/** Lo que más se repite al revisar un vídeo antes de subirlo, sea del nicho
 *  que sea: cada uno es una posible sanción. */
const MOTIVOS = [
  "El producto no es el del enlace o cambia de forma/color",
  "Objeto flotando o que aparece y desaparece",
  "Manos, dedos o piernas deformes",
  "Texto o letras raras en el vídeo",
  "La voz no cuadra con lo que se ve",
  "Corte brusco o clip repetido",
  "Demasiado estático",
];

/** Semáforo de revisión antes de subir (ver guía mis-tandas.md › Semáforo). */
const SEMAFORO: Record<ColorSemaforo, { punto: string; texto: string; nombre: string }> = {
  verde: { punto: "bg-emerald-500", texto: "text-emerald-600 dark:text-emerald-400", nombre: "Sin dudas: se puede subir" },
  ambar: { punto: "bg-amber-400", texto: "text-amber-600 dark:text-amber-400", nombre: "Bien, pero producto complejo: mejor no arriesgar" },
  rojo: { punto: "bg-rose-500", texto: "text-rose-500", nombre: "Hay que rehacerlo" },
};

function PuntoSemaforo({ v }: { v: VideoTanda }) {
  const s = v.semaforo;
  return (
    <span
      title={s ? `${SEMAFORO[s.color].nombre}${s.motivo ? ` — ${s.motivo}` : ""}` : "Sin revisar"}
      className={`mr-0.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full align-middle ${
        s ? SEMAFORO[s.color].punto : "border border-muted-foreground/50"
      }`}
    />
  );
}

/** «sáb 3 oct» a partir de «2026-10-03». */
const EPOCAS: Record<Epoca, string> = {
  neutro: "⚪ Neutro",
  otono: "🍂 Otoño",
  halloween: "🎃 Halloween",
  black_friday: "🛍️ Black Friday",
  invierno: "❄️ Invierno",
  navidad: "🎄 Navidad",
};

/** La época del vídeo, editable: cuándo publicarlo en TikTok y en Meta. */
function SelectorEpoca({ v }: { v: VideoTanda }) {
  const epoca = useEpocaTanda();
  return (
    <select
      value={v.epoca ?? "neutro"}
      disabled={epoca.isPending}
      title="Época: cuándo publicarlo"
      onChange={(e) => epoca.mutate({ id: v.id, epoca: e.target.value as Epoca })}
      className="rounded border border-border/60 bg-background px-1 py-px text-[9px] font-semibold"
    >
      {(Object.keys(EPOCAS) as Epoca[]).map((k) => (
        <option key={k} value={k}>
          {EPOCAS[k]}
        </option>
      ))}
    </select>
  );
}

function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" }).replace(".", "");
}

/** «Carpeta_30» → «Carpeta 30». */
function nombreCarpeta(c: string): string {
  return (c || "").replace(/_/g, " ").trim();
}

/** Qué carpetas lleva la tanda, con cuántos vídeos de cada una. */
function resumenCarpetas(items: VideoTanda[]) {
  const vistas = new Map<string, number>();
  for (const v of items) {
    const k = `${v.catalogo_label} · ${nombreCarpeta(v.carpeta_corta)}`;
    vistas.set(k, (vistas.get(k) ?? 0) + 1);
  }
  return [...vistas.entries()];
}

/** Qué lleva la tanda: un chip por nicho+modo con cuántos vídeos, en el
 *  color de ese modo. */
function resumenModos(items: VideoTanda[]) {
  const vistos = new Map<string, { clave: string; label: string; color: string; n: number }>();
  for (const v of items) {
    const f = familiaModo(v.nicho, v.modo, v.modo_label);
    const actual = vistos.get(f.clave);
    if (actual) actual.n += 1;
    else vistos.set(f.clave, { ...f, n: 1 });
  }
  return [...vistos.values()];
}

function Miniatura({ v }: { v: VideoTanda }) {
  const [rota, setRota] = useState(false);
  if (rota) {
    return (
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-dashed border-border/40 text-[9px] text-muted-foreground sm:h-12 sm:w-12">
        {NOMBRE_NICHO[v.nicho]}
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={buildFotoTandaUrl(v, 96)}
      alt=""
      loading="lazy"
      onError={() => setRota(true)}
      className="h-10 w-10 shrink-0 rounded-md border border-border/40 bg-white object-contain sm:h-12 sm:w-12"
    />
  );
}

/** Los vídeos montados del usuario, de TODOS sus nichos, de diez en diez.
 *
 *  No es un nicho: cada botón escribe en el documento del nicho del vídeo, así
 *  que lo que se marca aquí sale marcado en su pantalla y al revés. El orden
 *  es fijo (lo nuevo entra al final) y cada tanda abierta lleva la fecha en la
 *  que toca subirla. */
export function MisTandas() {
  const [verCerradas, setVerCerradas] = useState(false);
  const tandas = useMisTandas(verCerradas);
  const recargar = useRecargarTandas();
  const marcar = useMarcarTanda(verCerradas);
  const semaforo = useSemaforoTanda();
  const tagsPov = useHashtags("nicho-pov-bof").data ?? [];
  const tagsLargo = useHashtags("pov-bof-largo").data ?? [];
  const tagsMm = useHashtags("nicho-ropa-mujer").data ?? [];
  const hashtagsDe: Record<string, string[]> = {
    "nicho-pov-bof": tagsPov,
    "pov-bof-largo": tagsLargo,
    "nicho-ropa-mujer": tagsMm,
  };
  const captionDe = (v: VideoTanda) =>
    v.caption
      ? [v.caption, v.emojis, (hashtagsDe[v.hashtags_nicho] ?? []).join(" ")].filter(Boolean).join(" ")
      : "";

  const [aRehacer, setARehacer] = useState<VideoTanda | null>(null);
  // Qué descarga de tanda está en marcha («12|todos»): solo se bloquea ESE
  // botón, el resto de la pantalla sigue usable.
  const [bajando, setBajando] = useState<string | null>(null);
  // Pide confirmación en la propia fila antes de quitar un vídeo.
  const [aOcultar, setAOcultar] = useState<string | null>(null);
  const [verOcultos, setVerOcultos] = useState(false);
  const ocultar = useOcultarTanda();
  const completar = useCompletarTanda();
  // Pide un segundo toque antes de marcar toda la tanda.
  const [aCompletar, setACompletar] = useState<number | null>(null);
  const listaOcultos = useOcultosTandas(verOcultos);
  const [progreso, setProgreso] = useState("");
  const [abierta, setAbierta] = useState<number | null>(null);

  const datos = tandas.data;
  const primeraPendiente = datos?.tandas.find((t) => t.abierta)?.numero ?? null;
  const abiertaReal = abierta ?? primeraPendiente;

  const nombre = (numero: number, i: number, v: VideoTanda) =>
    nombreDescarga(
      "tanda",
      String(numero).padStart(3, "0"),
      String(i + 1).padStart(2, "0"),
      NOMBRE_NICHO[v.nicho] ?? v.nicho,
      v.modo,
    ) + ".mp4";

  /** Baja la tanda entera o solo lo que falta por subir. Sin stock nunca
   *  (no se puede publicar). Cada vídeo conserva su puesto en el nombre, así
   *  la carpeta del móvil cuadra con esta lista. */
  async function bajarTanda(numero: number, soloPendientes: boolean) {
    const t = datos?.tandas.find((x) => x.numero === numero);
    if (!t) return;
    const clave = `${numero}|${soloPendientes ? "pendientes" : "todos"}`;
    setBajando(clave);
    const elegidos = t.items
      .map((v, i) => ({ v, i }))
      .filter(({ v }) => (soloPendientes ? !v.uploaded && !v.sin_stock : !(v.sin_stock && !v.uploaded)));
    const r = await bajarEnOrden(
      elegidos.map(({ v, i }) => ({ href: buildVideoTandaUrl(v, true), nombre: nombre(numero, i, v) })),
      (hechos, total) => setProgreso(`${hechos}/${total}`),
      3,
    );
    setBajando(null);
    setProgreso("");
    if (r.fallidas) toast.error(`${r.bajadas} bajados · ${r.fallidas} fallaron`);
    else toast.success(`Tanda ${numero}: ${r.bajadas} vídeo(s) descargados`);
  }

  async function copiarMusica(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success(`Copiado: «${texto}» — pégalo en Sonidos › Buscar de TikTok`);
    } catch {
      toast.message(`Busca en TikTok: ${texto}`);
    }
  }

  return (
    <Caja
      icono="📦"
      titulo="Vídeos para subir, de diez en diez"
      hint="Todo lo montado en tus nichos, en el orden en que toca publicarlo. Baja la tanda, copia el caption de cada vídeo, ábrelo en la tienda y pulsa «Subido» al publicarlo. Lo que marques aquí queda marcado en la pantalla de su nicho."
      extra={
        datos
          ? `${datos.abiertas} por subir` +
            (datos.subidos_hoy ? ` · hoy ${datos.subidos_hoy}` : "") +
            (datos.sin_stock ? ` · 🚫 ${datos.sin_stock}` : "")
          : undefined
      }
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => recargar.mutate(verCerradas)}
          disabled={recargar.isPending}
          className="flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          title="Volver a leer los nichos (lo que acaben de montar los agentes)"
        >
          <RefreshCw className={`h-3 w-3 ${recargar.isPending ? "animate-spin" : ""}`} /> Recargar
        </button>
        {datos?.cerradas ? (
          <button
            type="button"
            onClick={() => setVerCerradas((x) => !x)}
            className={`rounded-md border px-2 py-1 text-[10px] ${
              verCerradas
                ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                : "border-border/60 text-muted-foreground hover:text-foreground"
            }`}
          >
            {verCerradas ? "Ocultar" : "Ver"} las {datos.cerradas} tandas cerradas
          </button>
        ) : null}
        {datos?.ocultos ? (
          <button
            type="button"
            onClick={() => setVerOcultos((x) => !x)}
            className={`rounded-md border px-2 py-1 text-[10px] ${
              verOcultos
                ? "border-rose-500/60 bg-rose-500/10 text-rose-500"
                : "border-border/60 text-muted-foreground hover:text-foreground"
            }`}
          >
            <EyeOff className="mr-1 inline h-3 w-3" />
            {verOcultos ? "Ocultar" : "Ver"} los {datos.ocultos} quitados
          </button>
        ) : null}
      </div>

      {verOcultos ? (
        <div className="mb-2 rounded-lg border border-rose-500/30 bg-rose-500/5 p-2">
          <p className="mb-1 text-[10px] text-muted-foreground">
            Quitados de la lista (no se van a subir). «Devolver» lo vuelve a poner en su puesto.
          </p>
          {listaOcultos.isLoading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          ) : (
            <ul className="space-y-1">
              {(listaOcultos.data ?? []).map((v) => (
                <li key={v.id} className="flex flex-wrap items-center gap-1 text-[11px]">
                  <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${COLOR_NICHO[v.nicho] ?? ""}`}>
                    {NOMBRE_NICHO[v.nicho] ?? v.nicho}
                  </span>
                  {v.modo_label ? (
                    <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${colorModo(v.nicho, v.modo)}`}>
                      {v.modo_label}
                    </span>
                  ) : null}
                  <span className="min-w-0 flex-1 break-words">
                    {v.titulo || `Producto ${v.producto}`}{" "}
                    <span className="text-[10px] text-muted-foreground">
                      · {v.catalogo_label} · {nombreCarpeta(v.carpeta_corta)} · Producto {v.producto}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => ocultar.mutate({ id: v.id, oculto: false })}
                    className="rounded-md border border-border/60 px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground"
                  >
                    Devolver
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {datos?.solo_meta?.length ? (
        <details className="mb-2 rounded-lg border border-sky-500/30 bg-sky-500/5 p-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-sky-600 dark:text-sky-400">
            📘 Solo Meta (mudos) · {datos.solo_meta.length}
          </summary>
          <p className="my-1 text-[10px] text-muted-foreground">
            Vídeos sin voz: en esta cuenta no se suben a TikTok. Se publican en Meta (uno al día, por época).
          </p>
          <ul className="space-y-1">
            {datos.solo_meta.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-1 text-[11px]">
                <PuntoSemaforo v={v} />
                {v.modo_label ? (
                  <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${colorModo(v.nicho, v.modo)}`}>
                    {v.modo_label}
                  </span>
                ) : null}
                <SelectorEpoca v={v} />
                <span className="min-w-0 flex-1 break-words">
                  {v.titulo || `Producto ${v.producto}`}{" "}
                  <span className="text-[10px] text-muted-foreground">
                    · {v.catalogo_label} · {nombreCarpeta(v.carpeta_corta)} · Producto {v.producto}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {datos?.esperando_stock?.length ? (
        <details className="mb-2 rounded-lg border border-rose-500/30 bg-rose-500/5 p-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-rose-500">
            ⏳ Esperando stock · {datos.esperando_stock.length}
          </summary>
          <p className="my-1 text-[10px] text-muted-foreground">
            Montados pero sin stock en TikTok Shop: no ocupan sitio en las tandas. Si el producto
            vuelve, pulsa 🚫 y entra solo en la siguiente tanda que le toque.
          </p>
          <ul className="space-y-1">
            {datos.esperando_stock.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-1 text-[11px]">
                <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${COLOR_NICHO[v.nicho] ?? ""}`}>
                  {NOMBRE_NICHO[v.nicho] ?? v.nicho}
                </span>
                {v.modo_label ? (
                  <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${colorModo(v.nicho, v.modo)}`}>
                    {v.modo_label}
                  </span>
                ) : null}
                <span className="min-w-0 flex-1 break-words">
                  {v.titulo || `Producto ${v.producto}`}{" "}
                  <span className="text-[10px] text-muted-foreground">
                    · {v.catalogo_label} · {nombreCarpeta(v.carpeta_corta)} · Producto {v.producto}
                  </span>
                </span>
                {v.product_url ? (
                  <a
                    href={v.product_url}
                    target="_blank"
                    rel="noreferrer"
                    title="Abrir la ficha para ver si ha vuelto"
                    className="rounded-md border border-border/60 px-1.5 py-0.5 text-[10px]"
                  >
                    🛍️
                  </a>
                ) : null}
                <button
                  type="button"
                  onClick={() => marcar.mutate({ id: v.id, sin_stock: false, video: v })}
                  className="rounded-md border border-rose-500/60 bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-500"
                  title="Ha vuelto: quitar «sin stock»"
                >
                  🚫 Ha vuelto
                </button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {tandas.isLoading ? (
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Cargando…
        </p>
      ) : tandas.isError ? (
        <p className="text-[11px] text-rose-500">No se pudieron leer las tandas: {tandas.error.message}</p>
      ) : !datos?.tandas.length ? (
        <p className="text-[11px] text-muted-foreground">
          No hay nada por subir. Cuando se monte un vídeo en cualquiera de tus nichos, aparece aquí solo.
        </p>
      ) : (
        <div className="space-y-1.5">
          {datos.tandas.map((t) => {
            const completa = !t.abierta;
            const abiertaEsta = abiertaReal === t.numero;
            return (
              <div
                key={t.numero}
                className={`rounded-lg border ${completa ? "border-border/40 opacity-80" : "border-border/60"}`}
              >
                <div className="flex items-center gap-2 px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => setAbierta(abiertaEsta ? -1 : t.numero)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="text-xs font-semibold sm:text-sm">
                      {abiertaEsta ? "▾" : "▸"} Tanda {t.numero}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span
                        className={`rounded-full px-1.5 py-px text-[9px] font-semibold ${
                          completa ? "bg-emerald-500/15 text-emerald-500" : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {t.subidos}/{t.total} subidos
                      </span>
                      {t.fecha ? (
                        <span className="rounded-full bg-sky-500/15 px-1.5 py-px text-[9px] font-semibold text-sky-600 dark:text-sky-400">
                          📅 {fechaCorta(t.fecha)}
                          {t.temporada ? ` · ${t.temporada}` : ""}
                        </span>
                      ) : null}
                      {resumenModos(t.items).map((m) => (
                        <span
                          key={m.clave}
                          className={`rounded-full px-1.5 py-px text-[9px] font-semibold ${m.color}`}
                        >
                          {m.label} · {m.n}
                        </span>
                      ))}
                      {t.sin_stock ? (
                        <span className="rounded-full bg-rose-500/15 px-1.5 py-px text-[9px] font-semibold text-rose-500">
                          🚫 {t.sin_stock}
                        </span>
                      ) : null}
                      {resumenCarpetas(t.items).map(([k, n]) => (
                        <span
                          key={k}
                          className="rounded-full border border-border/60 px-1.5 py-px text-[9px] font-semibold text-muted-foreground"
                        >
                          📁 {k} · {n}
                        </span>
                      ))}
                      {t.rehacer ? (
                        <span className="rounded-full bg-orange-500/15 px-1.5 py-px text-[9px] font-semibold text-orange-500">
                          🔁 {t.rehacer}
                        </span>
                      ) : null}
                      {t.semaforo && t.semaforo.verde + t.semaforo.ambar + t.semaforo.rojo > 0 ? (
                        <span
                          title="Revisión antes de subir (pendientes): sin dudas · producto complejo · rehacer"
                          className="rounded-full border border-border/60 px-1.5 py-px text-[9px] font-semibold"
                        >
                          🟢 {t.semaforo.verde} · 🟡 {t.semaforo.ambar} · 🔴 {t.semaforo.rojo}
                        </span>
                      ) : null}
                    </span>
                  </button>
                  <div className="flex shrink-0 flex-col items-stretch gap-1">
                    {t.abierta ? (
                      <button
                        type="button"
                        disabled={completar.isPending}
                        onClick={() => {
                          if (aCompletar === t.numero) {
                            completar.mutate(t.items.map((v) => v.id));
                            setACompletar(null);
                          } else setACompletar(t.numero);
                        }}
                        onBlur={() => setACompletar((x) => (x === t.numero ? null : x))}
                        title="Da la tanda por terminada y pasa a la siguiente. No marca nada como subido"
                        className={`flex items-center justify-center gap-1 rounded-md border px-2 py-1 text-[11px] disabled:opacity-50 ${
                          aCompletar === t.numero
                            ? "border-emerald-500 bg-emerald-500/20 text-emerald-500"
                            : "border-emerald-500/50 text-emerald-500 hover:bg-emerald-500/10"
                        }`}
                      >
                        {completar.isPending && aCompletar === null ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Check className="h-3 w-3" />
                        )}
                        {aCompletar === t.numero
                          ? t.items.some((v) => !v.uploaded && !v.sin_stock)
                            ? `¿Cerrar? ${t.items.filter((v) => !v.uploaded && !v.sin_stock).length} sin subir`
                            : "¿Cerrar la tanda?"
                          : "Tanda completada"}
                      </button>
                    ) : null}
                    {(
                      [
                        [false, "Todos", t.items.filter((v) => !(v.sin_stock && !v.uploaded)).length],
                        [true, "Pendientes", t.items.filter((v) => !v.uploaded && !v.sin_stock).length],
                      ] as const
                    ).map(([solo, etiqueta, cuantos]) => {
                      const clave = `${t.numero}|${solo ? "pendientes" : "todos"}`;
                      if (solo && (cuantos === 0 || cuantos === t.items.length)) return null;
                      return (
                        <button
                          key={clave}
                          type="button"
                          disabled={bajando === clave || cuantos === 0}
                          onClick={() => void bajarTanda(t.numero, solo)}
                          title={solo ? "Bajar solo lo que falta por subir" : "Bajar la tanda entera"}
                          className={`flex items-center justify-center gap-1 rounded-md border px-2 py-1 text-[11px] disabled:opacity-50 ${
                            solo
                              ? "border-orange-500/50 text-orange-500 hover:bg-orange-500/10"
                              : "border-violet-500/50 text-violet-400 hover:bg-violet-500/10"
                          }`}
                        >
                          {bajando === clave ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                          {bajando === clave && progreso ? progreso : `${etiqueta} (${cuantos})`}
                        </button>
                      );
                    })}
                  </div>
                </div>
                {abiertaEsta && (
                  <ul className="divide-y divide-border/40 border-t border-border/40">
                    {t.items.map((v, i) => (
                      <li
                        key={v.id}
                        className={`flex flex-col gap-1 px-2 py-1.5 ${v.sin_stock && !v.uploaded ? "bg-rose-500/5" : ""}`}
                      >
                        <div className="flex items-center gap-2">
                          <span className="w-4 shrink-0 text-[10px] text-muted-foreground">{i + 1}</span>
                          <Miniatura v={v} />
                          <div className="min-w-0 flex-1">
                            <p
                              className={`break-words text-[11px] font-medium leading-tight sm:text-xs ${
                                v.sin_stock && !v.uploaded ? "text-muted-foreground line-through" : ""
                              }`}
                            >
                              <PuntoSemaforo v={v} /> {v.titulo || `Producto ${v.producto}`}
                            </p>
                            <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                              <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${COLOR_NICHO[v.nicho] ?? ""}`}>
                                {NOMBRE_NICHO[v.nicho] ?? v.nicho}
                              </span>
                              {v.modo_label ? (
                                <span className={`rounded px-1.5 py-px text-[9px] font-semibold ${colorModo(v.nicho, v.modo)}`}>
                                  {v.modo_label}
                                </span>
                              ) : null}
                              {v.flecha ? (
                                <span className="rounded bg-muted px-1.5 py-px text-[9px] font-semibold">➡️ Flecha</span>
                              ) : null}
                              <span className={`rounded border px-1.5 py-px text-[9px] font-semibold ${colorCatalogo(v.catalogo)}`}>
                                {v.catalogo_label || v.catalogo}
                              </span>
                              <span className="rounded bg-muted px-1.5 py-px text-[9px] font-semibold text-foreground">
                                📁 {nombreCarpeta(v.carpeta_corta)} · Producto {v.producto}
                              </span>
                              <MontadoEl ts={v.video_listo_at} />
                              <SelectorEpoca v={v} />
                              {v.desde ? (
                                <span
                                  title="Su carpeta no se publica antes de este día"
                                  className="rounded bg-sky-500/15 px-1.5 py-px text-[9px] font-semibold text-sky-600 dark:text-sky-400"
                                >
                                  📅 desde {fechaCorta(v.desde)}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                        {v.semaforo && !v.uploaded && v.semaforo.color !== "verde" ? (
                          <p className={`break-words pl-6 text-[10px] ${SEMAFORO[v.semaforo.color].texto}`}>
                            {v.semaforo.color === "ambar" ? "🟡" : "🔴"} {v.semaforo.motivo || SEMAFORO[v.semaforo.color].nombre}
                          </p>
                        ) : null}
                        {v.sin_stock && !v.uploaded ? (
                          <p className="break-words pl-6 text-[10px] text-rose-500">
                            🚫 Sin stock: no se sube ni se baja con la tanda. Si el producto vuelve, pulsa 🚫 otra vez.
                          </p>
                        ) : null}
                        {v.rehacer ? (
                          <p className="break-words pl-6 text-[10px] text-orange-500">
                            🔁 Rehacer{v.rehacer_nota ? `: ${v.rehacer_nota}` : ""}
                          </p>
                        ) : v.rehecho && !v.uploaded ? (
                          <p className="pl-6 text-[10px] text-sky-400">✨ Rehecho — revísalo antes de subirlo</p>
                        ) : null}
                        <div className="flex min-w-0 flex-wrap items-center gap-1 pl-6">
                          <CopyChip label="✍️ Caption" text={captionDe(v)} siempre />
                          <CopyChip label="🔎 Título" text={v.titulo_tiktok_completo || v.titulo || ""} siempre />
                          <CopyChip label="🏪 Tienda" text={v.tienda || ""} siempre />
                          {v.musica?.busqueda ? (
                            <button
                              type="button"
                              onClick={() => void copiarMusica(v.musica!.busqueda)}
                              title={`${v.musica.estilo}. Otras: ${v.musica.alternativas.join(" · ")}`}
                              className="flex min-w-0 max-w-full items-center gap-1 rounded bg-violet-500/10 px-1.5 py-1 text-left text-[10px] text-violet-300 hover:bg-violet-500/20"
                            >
                              <span className="shrink-0">🎵</span>
                              <span className="min-w-0 break-words leading-tight">{v.musica.busqueda}</span>
                              <Copy className="h-2.5 w-2.5 shrink-0" />
                            </button>
                          ) : null}
                          {v.pantalla ? (
                            <Link
                              href={v.pantalla as never}
                              title="Abrir la pantalla de su nicho"
                              className="flex items-center gap-0.5 rounded px-1 py-1 text-[10px] text-muted-foreground hover:text-foreground"
                            >
                              <ExternalLink className="h-2.5 w-2.5" /> {NOMBRE_NICHO[v.nicho]}
                            </Link>
                          ) : null}
                        <div className="ml-auto flex items-center gap-1">
                          {/* Un enlace normal, como en el POV BOF Largo: el
                              navegador baja cada vídeo por su cuenta y se pueden
                              pedir varios a la vez sin esperar. */}
                          <a
                            href={buildVideoTandaUrl(v, true)}
                            download={nombre(t.numero, i, v)}
                            title="Descargar este vídeo"
                            className="flex shrink-0 items-center rounded-md border border-border/60 px-1.5 py-1 text-muted-foreground hover:text-foreground"
                          >
                            <Download className="h-3 w-3" />
                          </a>
                          {v.product_url ? (
                            <a
                              href={v.product_url}
                              target="_blank"
                              rel="noreferrer"
                              title="Abrir la ficha en TikTok Shop"
                              className="shrink-0 rounded-md border border-border/60 px-1.5 py-1 text-[10px] text-muted-foreground hover:text-foreground"
                            >
                              🛍️
                            </a>
                          ) : null}
                          {(!v.uploaded || v.sin_stock) && (
                            <button
                              type="button"
                              onClick={() => marcar.mutate({ id: v.id, sin_stock: !v.sin_stock, video: v })}
                              title={
                                v.sin_stock
                                  ? "Quitar «sin stock» (el producto ha vuelto)"
                                  : "Marcar sin stock: el producto ya no está en TikTok Shop"
                              }
                              className={`flex shrink-0 items-center rounded-md border px-1.5 py-1 text-[10px] ${
                                v.sin_stock
                                  ? "border-rose-500/60 bg-rose-500/15 text-rose-500"
                                  : "border-border/60 text-muted-foreground hover:text-rose-500"
                              }`}
                            >
                              🚫
                            </button>
                          )}
                          <span className="flex shrink-0 items-center gap-0.5 rounded-md border border-border/60 px-1 py-0.5">
                            {(["verde", "ambar", "rojo"] as const).map((c) => (
                              <button
                                key={c}
                                type="button"
                                disabled={semaforo.isPending}
                                onClick={() =>
                                  semaforo.mutate({
                                    id: v.id,
                                    color: v.semaforo?.color === c ? "" : c,
                                    motivo: v.semaforo?.color === c ? "" : "marcado a mano",
                                  })
                                }
                                title={v.semaforo?.color === c ? "Quitar el color" : SEMAFORO[c].nombre}
                                className={`h-3.5 w-3.5 rounded-full ${SEMAFORO[c].punto} ${
                                  v.semaforo?.color === c ? "ring-2 ring-foreground/60" : "opacity-30 hover:opacity-80"
                                }`}
                              />
                            ))}
                          </span>
                          <button
                            type="button"
                            disabled={!v.puede_rehacer}
                            onClick={() =>
                              v.rehacer ? marcar.mutate({ id: v.id, rehacer: false }) : setARehacer(v)
                            }
                            title={
                              !v.puede_rehacer
                                ? "El POV BOF no tiene «rehacer»: se rehace desde su pantalla"
                                : v.rehacer
                                  ? "Quitar «rehacer»"
                                  : "Marcar para rehacer"
                            }
                            className={`flex shrink-0 items-center rounded-md border px-1.5 py-1 disabled:opacity-30 ${
                              v.rehacer
                                ? "border-orange-500/60 bg-orange-500/15 text-orange-500"
                                : "border-border/60 text-muted-foreground hover:text-orange-500"
                            }`}
                          >
                            <RotateCcw className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (aOcultar === v.id) {
                                ocultar.mutate({ id: v.id, oculto: true });
                                setAOcultar(null);
                              } else setAOcultar(v.id);
                            }}
                            onBlur={() => setAOcultar((x) => (x === v.id ? null : x))}
                            title="Quitar de la lista: ya no lo vas a subir (no se borra nada del nicho)"
                            className={`flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] ${
                              aOcultar === v.id
                                ? "border-rose-500/60 bg-rose-500/15 text-rose-500"
                                : "border-border/60 text-muted-foreground hover:text-rose-500"
                            }`}
                          >
                            <EyeOff className="h-3 w-3" />
                            {aOcultar === v.id ? "¿Quitar?" : null}
                          </button>
                          <button
                            type="button"
                            onClick={() => marcar.mutate({ id: v.id, uploaded: !v.uploaded })}
                            className={`flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] ${
                              v.uploaded
                                ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-500"
                                : "border-border/60 text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            <Check className="h-3 w-3" />
                            {v.uploaded ? (
                              "Subido"
                            ) : (
                              <>
                                <span className="hidden sm:inline">Marcar subido</span>
                                <span className="sm:hidden">Subir</span>
                              </>
                            )}
                          </button>
                        </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
      <RehacerDialog
        abierto={aRehacer !== null}
        onCerrar={() => setARehacer(null)}
        titulo={aRehacer ? `${aRehacer.titulo || `Producto ${aRehacer.producto}`} · ${aRehacer.nicho_label}` : ""}
        motivos={MOTIVOS}
        onMarcar={(nota) => aRehacer && marcar.mutate({ id: aRehacer.id, rehacer: true, rehacer_nota: nota })}
      />
    </Caja>
  );
}
