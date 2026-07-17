"use client";

/**
 * Calendario por FECHAS reales: rejilla del mes → día → productos.
 *
 * Rendimiento (la razón de que esté partido así): la rejilla del mes usa
 * `useMonth`, que NO trae datos de producto — solo lo guardado en la entrada.
 * Los prompts/fotos se piden con `useDay` al abrir un día concreto. El
 * calendario viejo enriquecía TODAS las entradas de golpe: iba bien con 15
 * productos y se arrastraba con 200. Si algún día hace falta algo del producto
 * en la rejilla, hay que guardarlo en la entrada, NO llamar al producto.
 */

import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Calendar as CalendarIcon,
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  useBofuHooks,
  useAddBatch,
  useAutoDay,
  usePlanPack,
  useProblemVideos,
  useRegenerateCarousels,
  useVideoTemplates,
  type BofuHook,
  type ProblemVideo,
} from "@/lib/queries/radar";
import {
  calendarKeys,
  useCalendarMonths,
  useDay,
  useMonth,
  useRemoveCalendarEntries,
  type CalendarEntryDetail,
} from "@/lib/queries/calendar";
import { useProduct, productKeys } from "@/lib/queries/products";

import { MonthGrid, shiftMonth, todayIso } from "./MonthGrid";
import { OutcomeBar } from "./OutcomeBar";
import { FormatRanking, StatsRow } from "./Stats";

const VERDICT: Record<string, string> = {
  fuerte: "📢🔥", media: "📢", baja: "🔇", desconocida: "❔",
};

/** URL al endpoint que sirve la foto (api_key por query — <img> no manda headers). */
function buildPhotoUrl(productId: string, filename: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${productId}/photos/${encodeURIComponent(filename)}/file${qs}`;
}

function prettyDate(iso: string): string {
  const p = iso.split("-");
  const dt = new Date(Date.UTC(Number(p[0] ?? 0), Number(p[1] ?? 1) - 1, Number(p[2] ?? 1)));
  return dt.toLocaleDateString("es-ES", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  });
}

export default function CalendarPage() {
  const qc = useQueryClient();
  const today = todayIso();
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selected, setSelected] = useState(today);

  const monthQ = useMonth(month);
  const dayQ = useDay(selected);
  const monthsQ = useCalendarMonths();
  const removeEntries = useRemoveCalendarEntries();

  // Al cambiar de mes, saltar al día 1 si el seleccionado es de otro mes.
  useEffect(() => {
    if (!selected.startsWith(month)) setSelected(`${month}-01`);
  }, [month, selected]);

  const entries = monthQ.data?.entries ?? [];
  const dayEntries = dayQ.data ?? [];

  // ── Añadir productos a mano (URL de TikTok Shop) ──────────────────
  const addBatch = useAddBatch();
  const [rows, setRows] = useState<{ url: string; name: string }[]>([{ url: "", name: "" }]);
  const setRow = (i: number, k: "url" | "name", val: string) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, [k]: val } : r)));
  const addRow = () => setRows((prev) => [...prev, { url: "", name: "" }]);
  const removeRow = (i: number) =>
    setRows((prev) => (prev.length > 1 ? prev.filter((_, j) => j !== i) : prev));
  const [gens, setGens] = useState<string[]>([]);
  const toggleGen = (g: string) =>
    setGens((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: calendarKeys.month(month) });
    qc.invalidateQueries({ queryKey: calendarKeys.day(selected) });
    qc.invalidateQueries({ queryKey: calendarKeys.months });
  };

  const submitBatch = () => {
    const valid = rows.filter((r) => r.url.trim());
    if (!valid.length) return;
    const raw = valid.map((r) => `${r.name.trim()} — ${r.url.trim()}`).join("\n");
    addBatch.mutate(
      { raw, date: selected, gens },
      {
        onSuccess: (r) => {
          if (r.added > 0) {
            toast.success(`${r.added} añadido(s) al ${selected}`);
            const failedUrls = new Set(
              r.results.filter((x) => !x.ok).map((x) => x.line.match(/https?:\/\/\S+/)?.[0] ?? ""),
            );
            const remaining = valid.filter((row) => failedUrls.has(row.url.trim()));
            setRows(remaining.length ? remaining : [{ url: "", name: "" }]);
            const failed = r.results.filter((x) => !x.ok);
            if (failed.length)
              toast.error(`${failed.length} sin añadir: ${failed[0]?.message ?? ""}`);
            refreshAll();
          } else {
            toast.error(r.results[0]?.message ?? "No se añadió ninguno.");
          }
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  // ── Radar v2: llenar el día seleccionado ──────────────────────────
  const autoDayM = useAutoDay();
  const [autoTopN, setAutoTopN] = useState(6);
  const [autoMaxIfl, setAutoMaxIfl] = useState(250);
  const [autoMinEur, setAutoMinEur] = useState(1);
  // 3 vídeos/producto mientras se aprende: son 3 FORMATOS distintos, así que
  // testean el creativo además del producto. Bajar a 1 cuando se sepa cuál gana.
  const [autoVids, setAutoVids] = useState(3);
  const runAutoDay = () => {
    autoDayM.mutate(
      {
        date: selected,
        top_n: autoTopN,
        max_influencers: autoMaxIfl,
        min_commission_eur: autoMinEur,
        videos_per_product: autoVids,
        gens: ["problem_videos"],
      },
      {
        onSuccess: (r) => {
          if (!r.ok) {
            toast.error(r.message || "No se pudo lanzar la búsqueda");
            return;
          }
          toast.success(r.message || "Buscando productos con ADS frescos…");
          setTimeout(refreshAll, 20_000);
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-center gap-2">
        <CalendarIcon className="h-6 w-6 text-orange-500" />
        <h1 className="text-xl font-bold sm:text-2xl">Calendario</h1>
        {monthsQ.data && monthsQ.data.length > 1 && (
          <select
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="ml-auto rounded-md border border-border bg-background px-2 py-1 text-xs"
          >
            {monthsQ.data.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}
      </div>

      <MonthGrid
        month={month}
        entries={entries}
        selected={selected}
        onSelect={setSelected}
        onPrev={() => setMonth((m) => shiftMonth(m, -1))}
        onNext={() => setMonth((m) => shiftMonth(m, 1))}
      />

      <StatsRow stats={monthQ.data?.stats} />
      <FormatRanking stats={monthQ.data?.stats} />

      {/* Llenar el día seleccionado con lo que TikTok impulsa ahora */}
      <Card className="border-purple-500/40 bg-purple-500/[0.03]">
        <CardContent className="space-y-2.5 p-4">
          <div>
            <p className="text-sm font-semibold">🎯 Llenar este día automáticamente</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Busca qué productos están recibiendo <strong>inyección de ADS ahora mismo</strong> en
              España, descarta los saturados y los deja en el <strong>{prettyDate(selected)}</strong>{" "}
              con sus prompts listos.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <NumField label="Productos" value={autoTopN} onChange={setAutoTopN} min={1} max={20} w="w-16" />
            <NumField
              label="Vídeos/producto" value={autoVids} onChange={setAutoVids} min={1} max={5} w="w-16"
              title="3 = las 3 versiones son formatos distintos (UGC / dramatización / POV) → testeas el creativo además del producto. Baja a 1 cuando sepas cuál te funciona."
            />
            <NumField
              label="Máx. creadores" value={autoMaxIfl} onChange={setAutoMaxIfl} min={5} w="w-20"
              title="Cuantos más creadores, más se reparte la inyección de GMV Max"
            />
            <NumField
              label="Mín. €/venta" value={autoMinEur} onChange={setAutoMinEur} min={0} step={0.5} w="w-20"
              title="Un 12% de un producto de 10€ son 1,20€ — filtra por lo que cobras de verdad"
            />
            <Button
              size="sm"
              onClick={runAutoDay}
              disabled={autoDayM.isPending}
              className="bg-purple-600 text-white hover:bg-purple-700"
            >
              {autoDayM.isPending ? (
                <><Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> Buscando…</>
              ) : (
                <>🎯 Llenar ({autoTopN * autoVids} vídeos)</>
              )}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Tarda un par de minutos — el progreso se ve en la Cola.
          </p>
        </CardContent>
      </Card>

      {/* Añadir productos a mano por URL */}
      <Card>
        <CardContent className="space-y-2 p-4">
          <p className="text-sm font-semibold">➕ Añadir productos al {selected}</p>
          <div className="space-y-1.5">
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className="w-4 shrink-0 text-[11px] text-muted-foreground">{i + 1}.</span>
                <input
                  value={r.url}
                  onChange={(e) => setRow(i, "url", e.target.value)}
                  placeholder="URL de TikTok Shop"
                  className="min-w-0 flex-[2] rounded-md border border-border bg-background px-2 py-1.5 text-[11px]"
                />
                <input
                  value={r.name}
                  onChange={(e) => setRow(i, "name", e.target.value)}
                  placeholder="Título del producto"
                  className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-[11px]"
                />
                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  disabled={rows.length === 1}
                  className="shrink-0 text-muted-foreground hover:text-red-500 disabled:opacity-30"
                  title="Quitar fila"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={addRow}
            className="text-[11px] font-medium text-orange-500 hover:underline"
          >
            + Añadir otro producto
          </button>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Generar ahora:</span>
            {[
              { id: "problem_videos", label: "🎯 Vídeos-problema" },
              { id: "bofu_hooks", label: "🎣 Hooks BOFU" },
              { id: "styles", label: "🎬 8-9 estilos" },
            ].map((g) => {
              const on = gens.includes(g.id);
              return (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => toggleGen(g.id)}
                  className={
                    "rounded-full border px-2 py-0.5 text-[11px] transition " +
                    (on
                      ? "border-orange-500 bg-orange-500/10 text-orange-500"
                      : "border-border text-muted-foreground hover:border-foreground/50")
                  }
                >
                  {g.label}
                </button>
              );
            })}
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] text-muted-foreground">
              Sin marcar nada = solo se añaden; generas los prompts luego.
            </p>
            <Button size="sm" onClick={submitBatch} disabled={addBatch.isPending}>
              {addBatch.isPending ? (
                <><Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> Añadiendo…</>
              ) : (
                <>🚀 Añadir</>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── El día seleccionado ── */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <h2 className="text-sm font-semibold capitalize">
          {prettyDate(selected)}
          {selected === today && (
            <span className="ml-1.5 rounded bg-orange-500/15 px-1.5 py-0.5 text-[10px] text-orange-500">
              hoy
            </span>
          )}
        </h2>
        {dayEntries.length > 0 && (
          <button
            onClick={() => {
              if (!confirm(`¿Vaciar el ${selected}? (${dayEntries.length} productos)`)) return;
              removeEntries.mutate(
                { date: selected },
                {
                  onSuccess: (r) => {
                    toast.success(`${r.removed} quitado(s)`);
                    refreshAll();
                  },
                  onError: (e) => toast.error(e.message),
                },
              );
            }}
            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-red-500"
          >
            <Trash2 className="h-3 w-3" /> Vaciar día
          </button>
        )}
      </div>

      {dayQ.isLoading ? (
        <p className="text-xs text-muted-foreground">Cargando…</p>
      ) : dayEntries.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center">
            <p className="text-sm text-muted-foreground">Sin productos este día.</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Usa 🎯 Llenar este día, o añádelos por URL arriba.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {dayEntries.map((e) => (
            <DayProductCard key={e.product_id} e={e} onChanged={refreshAll} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Campo numérico que SE DEJA VACIAR mientras escribes.
 *
 * El fallo obvio es recortar al mínimo en cada pulsación: al borrar el "6"
 * para teclear "4", el campo queda vacío un instante → Number("") es 0 → se
 * sube a min → te reescribe un "1" encima y no hay forma de cambiarlo.
 * Aquí el texto crudo vive en local y solo se normaliza al salir del campo
 * (o al pulsar Enter); mientras tanto se propaga hacia arriba únicamente si
 * ya es un número válido dentro de rango.
 */
function NumField({
  label, value, onChange, min, max, step, w, title,
}: {
  label: string; value: number; onChange: (n: number) => void;
  min?: number; max?: number; step?: number; w: string; title?: string;
}) {
  const [raw, setRaw] = useState(String(value));
  // Solo re-sincroniza si el padre cambia de verdad (no en cada tecla, porque
  // un valor fuera de rango o vacío no se propaga).
  useEffect(() => setRaw(String(value)), [value]);

  const inRange = (n: number) =>
    (min === undefined || n >= min) && (max === undefined || n <= max);

  const commit = () => {
    let n = Number(raw);
    if (raw.trim() === "" || Number.isNaN(n)) n = min ?? 0;
    if (min !== undefined) n = Math.max(min, n);
    if (max !== undefined) n = Math.min(max, n);
    setRaw(String(n));
    onChange(n);
  };

  return (
    <label className="flex flex-col gap-0.5" title={title}>
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={raw}
        onChange={(e) => {
          const v = e.target.value;
          setRaw(v);
          const n = Number(v);
          if (v.trim() !== "" && !Number.isNaN(n) && inRange(n)) onChange(n);
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        className={w + " rounded-md border border-border bg-background px-2 py-1.5 text-[11px]"}
      />
    </label>
  );
}

function DayProductCard({
  e,
  onChanged,
}: {
  e: CalendarEntryDetail;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const remove = useRemoveCalendarEntries();
  const pack = usePlanPack();
  const [open, setOpen] = useState(false);
  const [packing, setPacking] = useState(false);

  // Los formatos de las versiones salen del producto — solo hacen falta al
  // abrir el día, y `useProduct` está cacheado por react-query.
  const { data: product } = useProduct(e.product_id);
  const versionLabels: string[] = ((product?.problem_videos ?? []) as ProblemVideo[]).map(
    (v, i) => v.format || v.concept || `Versión ${i + 1}`,
  );

  useEffect(() => {
    if (!packing) return;
    if (e.presets_count > 0 || e.carousels_count > 0) {
      setPacking(false);
      return;
    }
    const t = setInterval(onChanged, 6000);
    return () => clearInterval(t);
  }, [packing, e.presets_count, e.carousels_count, onChanged]);

  const genAI = () => {
    setPacking(true);
    pack.mutate(
      { product_id: e.product_id },
      {
        onSuccess: () => toast.success("Vídeos IA + carruseles en cola"),
        onError: () => {
          setPacking(false);
          toast.error("No se pudo encolar");
        },
      },
    );
  };

  const aiReady = e.presets_count > 0 || e.carousels_count > 0;

  return (
    <Card className={e.sold ? "border-green-500/40" : undefined}>
      <CardContent className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium">{e.name}</p>
            <p className="text-[11px] text-muted-foreground">
              ⭐ {e.score.toFixed(0)} · {VERDICT[e.ads_verdict] ?? ""} ADS {e.ads_verdict}
              {e.influencer_count > 0 && (
                <span title="Creadores estimados (EchoTik infravalora ~2.6x; esto ya va corregido). Contrástalo en la ficha de TikTok → Información de la promoción.">
                  {" · 👥 ~"}{e.influencer_count}
                </span>
              )}
              {e.commission_eur > 0 && <> · 💰 {e.commission_eur.toFixed(2)}€/venta</>}
              {" · "}🎯 {e.problem_videos_count}
              {aiReady && <> · 🎥 {e.presets_count} · 🎠 {e.carousels_count}</>}
            </p>
            {/* Cómo encontrar el producto.
                NO se pone enlace a `tiktok.com/view/product/<id>`: TikTok lo
                bloquea con "Security Check" en web Y devuelve "Hubo un
                problema" en la app — verificado. Lo que funciona es buscar el
                NOMBRE en el Centro de Afiliados, y la TIENDA es lo que
                desambigua cuando varias venden lo mismo. */}
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(e.name);
                  toast.success("Nombre copiado — búscalo en el Centro de Afiliados");
                }}
                className="inline-flex items-center gap-1 rounded-md border border-orange-500/40 bg-orange-500/10 px-2 py-1 text-[11px] font-medium text-orange-500 hover:bg-orange-500/20"
              >
                <Copy className="h-3 w-3" /> Copiar nombre
              </button>
              {e.seller_name && (
                <span
                  className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground"
                  title="Tienda — comprueba que es esta al buscarlo, varias pueden vender lo mismo"
                >
                  🏪 {e.seller_name}
                </span>
              )}
            </div>
          </div>
          <button
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(
                { date: e.date, product_ids: [e.product_id] },
                {
                  onSuccess: () => {
                    toast.success("Quitado del calendario");
                    onChanged();
                  },
                },
              )
            }
            className="inline-flex shrink-0 items-center gap-0.5 text-[10px] text-muted-foreground hover:text-red-500"
            title="Quitar del calendario (no borra el producto)"
          >
            <Trash2 className="h-3 w-3" /> quitar
          </button>
        </div>

        <OutcomeBar e={e} versionLabels={versionLabels} />

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-orange-500 hover:underline"
          >
            <ChevronDown className={"h-3.5 w-3.5 transition " + (open ? "rotate-180" : "")} />
            Ver prompts
          </button>
          {!aiReady &&
            (packing || pack.isPending ? (
              <span className="inline-flex items-center gap-1 text-xs text-orange-500">
                <Loader2 className="h-3 w-3 animate-spin" /> generando vídeos IA…
              </span>
            ) : (
              <button
                onClick={genAI}
                className="text-xs text-muted-foreground hover:text-orange-500 hover:underline"
                title="Generar estilos de vídeo IA + carruseles (más lento)"
              >
                ✨ Generar vídeos IA + carruseles
              </button>
            ))}
        </div>
        {open && <ProductPrompts productId={e.product_id} />}
      </CardContent>
    </Card>
  );
}

interface Slide {
  slide_number?: number;
  role?: string;
  on_screen_text?: string;
  swipe_cue?: string;
  image_prompt?: string;
}
interface Carousel {
  format?: string;
  concept?: string;
  hook_caption?: string;
  hashtags?: string[];
  suggested_sound?: string;
  slides?: Slide[];
}

function ProductPrompts({ productId }: { productId: string }) {
  const qc = useQueryClient();
  const { data: product, isLoading } = useProduct(productId);
  const [tab, setTab] = useState<"problem" | "video" | "carousel" | "templates" | "hooks">("problem");
  const tpls = useVideoTemplates(productId);
  const [carLang, setCarLang] = useState("es");
  const [carStyle, setCarStyle] = useState("simple");
  const regen = useRegenerateCarousels();
  const bofu = useBofuHooks();
  const [bofuHooks, setBofuHooks] = useState<BofuHook[]>([]);
  const probVids = useProblemVideos();
  const [problemVideos, setProblemVideos] = useState<ProblemVideo[]>([]);
  const [uploadingIdx, setUploadingIdx] = useState<number | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [processingIdx, setProcessingIdx] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1.18);

  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";
  const readyUrl = (i: number) =>
    `${apiBase}/api/v1/tiktok-shop/radar/videos/problem/ready?product_id=${productId}&concept_index=${i}` +
    (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : "");
  const uploadVideo = (i: number, f: File) => {
    setUploadingIdx(i);
    setUploadPct(0);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("product_id", productId);
    fd.append("concept_index", String(i));
    fd.append("zoom", String(zoom));
    // XHR para tener progreso de subida (fetch no lo expone).
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/tiktok-shop/radar/videos/problem/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setUploadPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploadingIdx(null);
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.ok) {
          toast.success(data.message ?? "En la cola, procesando…");
          setProblemVideos([]);   // usa datos del producto (traen ready_video)
          setProcessingIdx(i);    // → polling hasta que el runner lo deje listo
        } else toast.error(data.message ?? "Error procesando");
      } catch {
        toast.error("Respuesta inválida del servidor");
      }
    };
    xhr.onerror = () => {
      setUploadingIdx(null);
      toast.error("Error subiendo el vídeo");
    };
    xhr.send(fd);
  };

  // Mientras el job de la cola procesa, refresca hasta que aparezca ready_video.
  useEffect(() => {
    if (processingIdx === null) return;
    const done = (product?.problem_videos?.[processingIdx] as ProblemVideo | undefined)?.ready_video;
    if (done) {
      setProcessingIdx(null);
      toast.success("Vídeo listo para descargar");
      return;
    }
    const t = setInterval(
      () => qc.invalidateQueries({ queryKey: productKeys.detail(productId) }),
      5000,
    );
    return () => clearInterval(t);
  }, [processingIdx, product, productId, qc]);

  if (isLoading) return <p className="text-xs text-muted-foreground">Cargando prompts…</p>;
  if (!product) return <p className="text-xs text-destructive">Producto no encontrado.</p>;

  const presets = product.video_presets ?? [];
  const carousels = (product.carousels ?? []) as unknown as Carousel[];
  const photos = (product.photos?.source ?? []).filter((p) => !p.deleted);
  const listingUrl = product.tiktok_shop?.product_url ?? "";
  const problemToShow: ProblemVideo[] = problemVideos.length
    ? problemVideos
    : ((product.problem_videos ?? []) as ProblemVideo[]);

  return (
    <div className="mt-1 rounded-md border border-border p-2">
      {/* Fotos del producto: de dónde sacarlas para adjuntar */}
      <div className="mb-2 rounded bg-muted/50 p-2">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[11px] font-medium">📸 Fotos para adjuntar</span>
          {listingUrl && (
            <a
              href={listingUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-orange-500 hover:underline"
            >
              <ExternalLink className="h-3 w-3" /> Ficha TikTok Shop (fotos oficiales)
            </a>
          )}
        </div>
        {photos.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {photos.map((ph) => {
              const url = buildPhotoUrl(product.id, ph.filename);
              return (
                <a key={ph.filename} href={url} download={ph.filename} target="_blank" rel="noreferrer" title="Descargar" className="relative block">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={url} alt="" className="h-14 w-14 rounded border border-border object-cover" />
                  <Download className="absolute bottom-0.5 right-0.5 h-3 w-3 text-white drop-shadow" />
                </a>
              );
            })}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            Sin fotos descargadas. Usa el enlace de la ficha para bajar las oficiales.
          </p>
        )}
        <p className="mt-1 text-[10px] text-muted-foreground">
          Adjunta estas (o las de la ficha) al pegar los prompts en Veo 3 / Nano Banana.
        </p>
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        <TabBtn active={tab === "problem"} onClick={() => setTab("problem")}>🎯 Vídeos problema ({(problemVideos.length || (product.problem_videos?.length ?? 0))})</TabBtn>
        <TabBtn active={tab === "video"} onClick={() => setTab("video")}>🎥 Vídeos IA ({presets.length})</TabBtn>
        <TabBtn active={tab === "carousel"} onClick={() => setTab("carousel")}>🎠 Carruseles ({carousels.length})</TabBtn>
        <TabBtn active={tab === "templates"} onClick={() => setTab("templates")}>⚡ Plantillas ({tpls.data?.templates.length ?? 0})</TabBtn>
        <TabBtn active={tab === "hooks"} onClick={() => setTab("hooks")}>🎣 Hooks BOFU</TabBtn>
      </div>

      {tab === "problem" && (
        <div className="space-y-2">
          <p className="rounded bg-muted/50 p-2 text-[11px] text-muted-foreground">
            🎯 Vídeos que <b>atacan el problema</b> del cliente (medio embudo). Copia el
            prompt en <b>Veo 3 de Gemini</b> (adjunta la foto del producto) para un vídeo
            de ~10s, y superpón los <b>textos en pantalla</b> que van al lado. Sin caras IA.
          </p>
          <button
            disabled={probVids.isPending}
            onClick={() =>
              probVids.mutate(
                { product_id: productId, language: "es", n: 3 },
                {
                  onSuccess: (r) => {
                    if (r.ok && r.videos?.length) {
                      setProblemVideos(r.videos);
                      qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
                    } else toast.error("No se pudieron generar.");
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
            className="inline-flex items-center gap-1 rounded-md bg-orange-500 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {probVids.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            {problemToShow.length ? "Regenerar vídeos" : "Generar vídeos problema"}
          </button>
          {problemToShow.length === 0 && !probVids.isPending && (
            <p className="text-xs text-muted-foreground">Aún no generados — pulsa el botón.</p>
          )}
          {problemToShow.length > 0 && (
            <div className="flex items-center gap-2 rounded bg-muted/40 p-2 text-[11px]">
              <span>🔍 Zoom quita-marca:</span>
              <input
                type="range" min={1} max={1.4} step={0.02} value={zoom}
                onChange={(e) => setZoom(+e.target.value)}
                className="h-1 w-32"
              />
              <span className="font-mono">{zoom.toFixed(2)}×</span>
              <span className="text-muted-foreground">
                (sube si aún se ve la marca de agua; aplica al subir vídeo)
              </span>
            </div>
          )}
          {problemToShow.map((v, i) => {
            const fileInput = (
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadVideo(i, f);
                  e.target.value = "";
                }}
              />
            );
            const actionBtn =
              uploadingIdx === i ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
                  <Loader2 className="h-3 w-3 animate-spin" /> {uploadPct}%
                </span>
              ) : processingIdx === i ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
                  <Loader2 className="h-3 w-3 animate-spin" /> en cola…
                </span>
              ) : v.ready_video ? (
                <div className="flex items-center gap-1.5">
                  <a
                    href={readyUrl(i)}
                    download
                    className="inline-flex items-center gap-1 rounded-md bg-green-600 px-2.5 py-1.5 text-[11px] font-semibold text-white"
                  >
                    <Download className="h-3.5 w-3.5" /> Descargar
                  </a>
                  <label className="cursor-pointer text-[10px] text-muted-foreground hover:underline" title="re-subir">
                    {fileInput}↻
                  </label>
                </div>
              ) : (
                <label className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-orange-500 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-orange-600">
                  {fileInput}📤 Subir vídeo
                </label>
              );
            return (
              <div key={i} className="rounded-lg border border-border/60 p-2.5 text-xs">
                {/* Cabecera: V# + formato + botón subir/descargar */}
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-semibold">V{i + 1}</span>{" "}
                    <span className="text-muted-foreground">{v.concept}</span>
                    {v.format && (
                      <span className="ml-1 inline-block rounded bg-orange-500/10 px-1.5 py-0.5 text-[10px] text-orange-600">
                        {v.format}
                      </span>
                    )}
                  </div>
                  <div className="shrink-0">{actionBtn}</div>
                </div>

                {/* Chips: copiar cada prompt/texto con 1 clic (sin ocupar espacio) */}
                <div className="flex flex-wrap gap-1.5">
                  {v.image_prompt ? (
                    <>
                      <CopyChip label="🖼️ Paso 1 imagen" text={v.image_prompt} primary />
                      <CopyChip label="🎬 Paso 2 animar" text={v.animate_prompt ?? ""} primary />
                    </>
                  ) : (
                    <CopyChip label="🟣 Prompt Veo 3" text={v.veo3_prompt} primary />
                  )}
                  <CopyChip label="📌 Gancho" text={v.hook_text} />
                  <CopyChip label="🛒 CTA" text={v.cta_text} />
                  <CopyChip label="✍️ Caption" text={v.caption} />
                  {v.spoken_line && <CopyChip label="🗣️ Voz" text={v.spoken_line} />}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {tab === "video" && (
        <div className="space-y-2">
          {presets.length === 0 && <p className="text-xs text-muted-foreground">Sin vídeos IA todavía — pulsa &quot;✨ Generar vídeos IA&quot; arriba. Mientras, usa la pestaña ⚡ Plantillas.</p>}
          {presets.map((p, i) => (
            <details key={i} className="rounded border border-border/60 p-2 text-xs">
              <summary className="cursor-pointer font-medium">
                {i + 1}. {p.name} · {p.kind}{p.angle ? `/${p.angle}` : ""} · {p.duration_s}s
              </summary>
              <div className="mt-2 space-y-2">
                {p.voice_script && <CopyBlock label="🎙️ Guion de voz" text={p.voice_script} />}
                {p.seedance_prompt && <CopyBlock label="🎬 Prompt Seedance" text={p.seedance_prompt} />}
                {p.veo3_prompt && <CopyBlock label="🟣 Prompt Veo 3" text={p.veo3_prompt} />}
                {p.cta && <p className="text-muted-foreground">CTA: {p.cta}</p>}
              </div>
            </details>
          ))}
        </div>
      )}

      {tab === "carousel" && (
        <div className="space-y-2">
          {/* Selector de idioma + regenerar */}
          <div className="flex flex-wrap items-center gap-2 rounded bg-muted/50 p-2">
            <span className="text-[11px] font-medium">Idioma:</span>
            <select
              value={carLang}
              onChange={(e) => setCarLang(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-0.5 text-xs"
            >
              <option value="es">🇪🇸 Español</option>
              <option value="en">🇬🇧 English</option>
            </select>
            <span className="text-[11px] font-medium">Texto:</span>
            <select
              value={carStyle}
              onChange={(e) => setCarStyle(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-0.5 text-xs"
              title="Estilo del texto para A/B"
            >
              <option value="simple">Simple (sin caja)</option>
              <option value="box">Caja de color</option>
              <option value="outline">Contorno</option>
            </select>
            <button
              disabled={regen.isPending}
              onClick={() =>
                regen.mutate(
                  { product_id: productId, language: carLang, text_style: carStyle },
                  {
                    onSuccess: (r) => {
                      if (r.ok) {
                        toast.success(`${r.count} carruseles regenerados (${r.language})`);
                        qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
                      } else toast.error("No se pudieron regenerar.");
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
              className="inline-flex items-center gap-1 rounded-md bg-orange-500 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {regen.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              Regenerar carruseles
            </button>
            <span className="text-[10px] text-muted-foreground">texto en pantalla + sin hashtags en la imagen</span>
          </div>
          {carousels.length === 0 && <p className="text-xs text-muted-foreground">Sin carruseles todavía — pulsa &quot;✨ Generar vídeos IA + carruseles&quot; arriba (o &quot;Regenerar carruseles&quot;).</p>}
          {carousels.map((c, i) => (
            <details key={i} className="rounded border border-border/60 p-2 text-xs">
              <summary className="cursor-pointer font-medium">
                Carrusel {i + 1} · {c.format} — {(c.concept ?? "").slice(0, 50)}
              </summary>
              <div className="mt-2 space-y-2">
                <CopyBlock label="📝 Caption (sin hashtags)" text={c.hook_caption ?? ""} />
                {c.hashtags && c.hashtags.length > 0 && (
                  <CopyBlock label="#️⃣ Hashtags (opcional)" text={c.hashtags.join(" ")} />
                )}
                {c.suggested_sound && <p className="text-muted-foreground">🎵 {c.suggested_sound}</p>}
                {(c.slides ?? []).map((s, j) => (
                  <div key={j} className="space-y-1">
                    <p className="font-medium">
                      Slide {s.slide_number} [{s.role}] — &quot;{s.on_screen_text}&quot;
                      {s.swipe_cue ? `  ↪ ${s.swipe_cue}` : ""}
                    </p>
                    <CopyBlock label="" text={s.image_prompt ?? ""} />
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      )}

      {tab === "templates" && (
        <div className="space-y-2">
          <p className="rounded bg-muted/50 p-2 text-[11px] text-muted-foreground">
            ⚡ Plantillas simples (sin coste IA, sin caras — POV/manos). Copia el
            prompt con 1 clic, genéralo en Kling/Veo, y <b>súbelo aquí para editarlo</b>
            {" "}(quita-marca + flecha + gancho) igual que los vídeos-problema.
          </p>
          {(tpls.data?.templates ?? []).map((t) => (
            <TemplateEditCard
              key={t.id}
              t={t}
              apiBase={apiBase}
              apiKey={apiKey}
              defaultZoom={zoom}
            />
          ))}
        </div>
      )}

      {tab === "hooks" && (() => {
        const persisted = (product.bofu_hooks ?? []) as BofuHook[];
        const hooksToShow = bofuHooks.length ? bofuHooks : persisted;
        return (
        <div className="space-y-2">
          <p className="rounded bg-muted/50 p-2 text-[11px] text-muted-foreground">
            🎣 Hooks BOFU (parte baja del embudo): textos cortos y simples — a
            menudo solo el nombre del producto + empujón a la venta. Para A/B.
          </p>
          <button
            disabled={bofu.isPending}
            onClick={() =>
              bofu.mutate(
                { product_id: productId, language: "es", n: 10 },
                {
                  onSuccess: (r) => {
                    setBofuHooks(r.hooks);
                    qc.invalidateQueries({ queryKey: productKeys.detail(productId) });
                    toast.success(`${r.hooks.length} hooks generados`);
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
            className="inline-flex items-center gap-1 rounded-md bg-orange-500 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {bofu.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            {hooksToShow.length ? "Regenerar hooks BOFU" : "Generar hooks BOFU"}
          </button>
          {hooksToShow.length > 0 && (
            <div className="space-y-1">
              {hooksToShow.map((h, i) => (
                <div key={i} className="flex items-center gap-2 rounded border border-border/60 p-1.5 text-xs">
                  <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">{h.type}</span>
                  <span className="flex-1">{h.text}</span>
                  <button
                    onClick={() => { navigator.clipboard.writeText(h.text); toast.success("Copiado"); }}
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                    title="Copiar"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        );
      })()}
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={
        "rounded-full border px-2.5 py-0.5 text-xs " +
        (active ? "border-orange-500 bg-orange-500/10 font-medium" : "border-border text-muted-foreground")
      }
    >
      {children}
    </button>
  );
}

/** Botón compacto: copia el texto al portapapeles sin mostrarlo (ahorra espacio). */
function CopyChip({ label, text, primary }: { label: string; text: string; primary?: boolean }) {
  if (!text) return null;
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        toast.success("Copiado");
      }}
      title={`Copiar: ${label}`}
      className={
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition " +
        (primary
          ? "border-purple-500/40 bg-purple-500/10 text-purple-500 hover:bg-purple-500/20"
          : "border-border text-muted-foreground hover:border-foreground/50 hover:text-foreground")
      }
    >
      <Copy className="h-3 w-3" /> {label}
    </button>
  );
}

/** Tarjeta de plantilla ⚡ con la MISMA interfaz simple que los vídeos-problema:
 *  chips para copiar los prompts + subir vídeo para editar (editor libre) +
 *  descargar. No depende de un concepto guardado — usa /videos/edit/*. */
function TemplateEditCard({
  t,
  apiBase,
  apiKey,
  defaultZoom,
}: {
  t: import("@/lib/queries/radar").VideoTemplate;
  apiBase: string;
  apiKey: string;
  defaultZoom: number;
}) {
  const [hook, setHook] = useState("");
  const [uploading, setUploading] = useState(false);
  const [pct, setPct] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [token, setToken] = useState<string | null>(null);

  const readyUrl = token
    ? `${apiBase}/api/v1/tiktok-shop/radar/videos/edit/ready?token=${token}` +
      (apiKey ? `&api_key=${encodeURIComponent(apiKey)}` : "")
    : "";

  // Poll: la descarga da 404 hasta que la cola termina → cuando responde OK,
  // mostramos el botón de descargar.
  useEffect(() => {
    if (!processing || !token) return;
    const id = setInterval(async () => {
      try {
        const r = await fetch(readyUrl, { method: "HEAD" });
        if (r.ok) {
          setProcessing(false);
          clearInterval(id);
        }
      } catch {
        /* sigue intentando */
      }
    }, 4000);
    return () => clearInterval(id);
  }, [processing, token, readyUrl]);

  const onUpload = (f: File) => {
    setUploading(true);
    setPct(0);
    setToken(null);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("hook_text", hook.trim());
    fd.append("cta_text", hook.trim() ? "Míralo aquí 👇🛒" : "");
    fd.append("zoom", String(defaultZoom));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBase}/api/v1/tiktok-shop/radar/videos/edit/upload`);
    if (apiKey) xhr.setRequestHeader("X-API-Key", apiKey);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploading(false);
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.ok && data.token) {
          setToken(data.token);
          setProcessing(true);
          toast.success("En la cola, editando…");
        } else toast.error(data.message ?? "Error");
      } catch {
        toast.error("Respuesta inválida del servidor");
      }
    };
    xhr.onerror = () => {
      setUploading(false);
      toast.error("Error de red al subir");
    };
    xhr.send(fd);
  };

  const fileInput = (
    <input
      type="file"
      accept="video/*"
      className="hidden"
      onChange={(e) => {
        const f = e.target.files?.[0];
        if (f) onUpload(f);
        e.target.value = "";
      }}
    />
  );
  const actionBtn = uploading ? (
    <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
      <Loader2 className="h-3 w-3 animate-spin" /> {pct}%
    </span>
  ) : processing ? (
    <span className="inline-flex items-center gap-1 text-[11px] text-orange-500">
      <Loader2 className="h-3 w-3 animate-spin" /> editando…
    </span>
  ) : token ? (
    <div className="flex items-center gap-1.5">
      <a
        href={readyUrl}
        download
        className="inline-flex items-center gap-1 rounded-md bg-green-600 px-2.5 py-1.5 text-[11px] font-semibold text-white"
      >
        <Download className="h-3.5 w-3.5" /> Descargar
      </a>
      <label className="cursor-pointer text-[10px] text-muted-foreground hover:underline" title="editar otro">
        {fileInput}↻
      </label>
    </div>
  ) : (
    <label className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-orange-500 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-orange-600">
      {fileInput}📤 Subir vídeo
    </label>
  );

  return (
    <div className="rounded-lg border border-border/60 p-2.5 text-xs">
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="font-semibold">{t.name}</span>{" "}
          <span className="text-muted-foreground">· {t.niches.join("/")}</span>
        </div>
        <div className="shrink-0">{actionBtn}</div>
      </div>
      {t.notes && <p className="mb-1.5 text-[10px] text-muted-foreground">{t.notes}</p>}
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        <CopyChip label="🍌 1er frame" text={t.first_frame_prompt} primary />
        <CopyChip label="🎬 Kling" text={t.kling_prompt} primary />
        <CopyChip label="🟣 Veo 3" text={t.prompt} />
      </div>
      {/* Gancho opcional que se quema al editar (las plantillas no traen uno). */}
      <input
        value={hook}
        onChange={(e) => setHook(e.target.value)}
        placeholder="Gancho opcional para el vídeo (se quema al editar)…"
        className="w-full rounded-md border border-border bg-background px-2 py-1 text-[11px]"
      />
    </div>
  );
}

function CopyBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      {label && <p className="mb-0.5 text-[11px] font-medium">{label}</p>}
      <div className="flex items-start gap-1">
        <pre className="flex-1 overflow-x-auto whitespace-pre-wrap rounded bg-muted p-2 text-[11px]">{text}</pre>
        <button
          onClick={() => {
            navigator.clipboard.writeText(text);
            toast.success("Copiado");
          }}
          className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
          title="Copiar"
        >
          <Copy className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
