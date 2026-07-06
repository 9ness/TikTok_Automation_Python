"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Calendar as CalendarIcon,
  Check,
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Rocket,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  useBofuHooks,
  useDeletePlan,
  useAddBatch,
  useMarkTested,
  usePlanGenerate,
  usePlanPack,
  useProblemVideos,
  useRadarPlan,
  useRegenerateCarousels,
  useRemoveFromPlan,
  useVideoTemplates,
  type BofuHook,
  type PlanEntry,
  type ProblemVideo,
} from "@/lib/queries/radar";
import { useProduct, productKeys } from "@/lib/queries/products";

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

export default function CalendarPage() {
  const qc = useQueryClient();
  const planQ = useRadarPlan();
  const gen = usePlanGenerate();
  const del = useDeletePlan();
  const addBatch = useAddBatch();
  const [perDay, setPerDay] = useState(10);
  const [days, setDays] = useState(7);
  const [selectedDay, setSelectedDay] = useState(1);
  const [batch, setBatch] = useState("");
  // Tipos de generación al añadir. Por defecto NINGUNO (se elige después).
  const [gens, setGens] = useState<string[]>([]);
  const toggleGen = (g: string) =>
    setGens((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));

  const submitBatch = () => {
    const raw = batch.trim();
    if (!raw) return;
    addBatch.mutate(
      { raw, per_day: perDay, gens },
      {
        onSuccess: (r) => {
          if (r.added > 0) {
            toast.success(
              `${r.added} añadido(s) a la cola${r.failed ? ` · ${r.failed} fallaron` : ""}`,
            );
            // Deja en el textarea solo las líneas que fallaron, con el motivo.
            const failed = r.results.filter((x) => !x.ok);
            setBatch(failed.map((x) => x.line).join("\n"));
            if (failed.length)
              toast.error(`${failed.length} sin añadir: ${failed[0].message}`);
            qc.invalidateQueries({ queryKey: ["radar-plan"] });
          } else {
            toast.error(r.results[0]?.message ?? "No se añadió ninguno.");
          }
        },
        onError: (e) => toast.error(e.message),
      },
    );
  };

  const plan = planQ.data;
  const byDay = new Map<number, PlanEntry[]>();
  (plan?.entries ?? []).forEach((e) => {
    byDay.set(e.day, [...(byDay.get(e.day) ?? []), e]);
  });
  const totalDays = Math.max(plan?.days ?? days, ...(plan?.entries.map((e) => e.day) ?? [1]));
  const done = (plan?.entries ?? []).filter((e) => e.tested).length;
  const total = plan?.entries.length ?? 0;

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex items-center gap-2">
        <CalendarIcon className="h-6 w-6 text-orange-500" />
        <h1 className="text-xl font-bold sm:text-2xl">Calendario</h1>
      </div>
      <p className="text-xs text-muted-foreground sm:text-sm">
        Qué producto probar cada día, con sus prompts de vídeo y carruseles listos.
      </p>

      {/* Añadir productos por URL (en lote, flujo Kalodata manual) */}
      <Card>
        <CardContent className="space-y-2 p-4">
          <p className="text-sm font-semibold">➕ Añadir productos a la cola</p>
          <textarea
            value={batch}
            onChange={(e) => setBatch(e.target.value)}
            rows={4}
            placeholder={
              "Un producto por línea:  Nombre del producto — https://www.tiktok.com/view/product/...\n" +
              "Nombre otro producto — https://...\n" +
              "(pega varios de golpe, se añaden en orden)"
            }
            className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 font-mono text-[11px]"
          />
          {/* Tipos de generación (opcional al añadir; por defecto NINGUNO) */}
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
                    "rounded-full border px-2.5 py-1 text-[11px] transition " +
                    (on
                      ? "border-orange-500 bg-orange-500/10 font-medium text-orange-600"
                      : "border-border text-muted-foreground hover:border-foreground/40")
                  }
                >
                  {on ? "✓ " : ""}
                  {g.label}
                </button>
              );
            })}
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              Se añaden a la cola ({perDay}/día). Sin marcar nada = solo se añaden;
              generas los prompts luego en cada producto.
            </p>
            <Button disabled={addBatch.isPending || !batch.trim()} onClick={submitBatch}>
              {addBatch.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="mr-2 h-4 w-4" />
              )}
              Añadir a la cola
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Generar plan automático */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <label className="text-xs">
            Productos/día
            <input type="number" value={perDay} min={1} max={20}
              onChange={(e) => setPerDay(+e.target.value)}
              className="ml-2 w-16 rounded-md border border-border bg-background px-2 py-1" />
          </label>
          <label className="text-xs">
            Días
            <input type="number" value={days} min={1} max={14}
              onChange={(e) => setDays(+e.target.value)}
              className="ml-2 w-16 rounded-md border border-border bg-background px-2 py-1" />
          </label>
          <Button
            disabled={gen.isPending}
            onClick={() =>
              gen.mutate(
                { per_day: perDay, days },
                {
                  onSuccess: (r) => {
                    toast.success(r.message);
                    qc.invalidateQueries({ queryKey: ["radar-plan"] });
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
          >
            {gen.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Rocket className="mr-2 h-4 w-4" />}
            Generar plan {perDay}/día
          </Button>
          <p className="text-[11px] text-muted-foreground">
            Importa los top candidatos del Radar y genera sus packs (en la cola).
          </p>
        </CardContent>
      </Card>

      {total > 0 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">{done}/{total} probados</p>
          <Button
            variant="ghost" size="sm"
            onClick={() =>
              del.mutate(undefined, {
                onSuccess: () => {
                  toast.success("Plan borrado");
                  qc.invalidateQueries({ queryKey: ["radar-plan"] });
                },
              })
            }
          >
            <Trash2 className="mr-1 h-4 w-4" /> Borrar plan
          </Button>
        </div>
      )}

      {planQ.isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando calendario…</p>
      ) : !plan?.exists || total === 0 ? (
        <p className="text-sm text-muted-foreground">
          Sin plan todavía. Genera uno arriba, o añade productos desde el <b>Radar</b> (botón &quot;Al calendario&quot;).
        </p>
      ) : (
        <div className="space-y-3">
          {/* Fila de días clicables */}
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: totalDays }, (_, i) => i + 1).map((d) => {
              const entries = byDay.get(d) ?? [];
              const doneD = entries.filter((e) => e.tested).length;
              const active = d === selectedDay;
              return (
                <button
                  key={d}
                  onClick={() => setSelectedDay(d)}
                  className={
                    "flex flex-col items-center rounded-lg border px-3 py-1.5 text-xs transition " +
                    (active
                      ? "border-orange-500 bg-orange-500/10 font-semibold"
                      : "border-border text-muted-foreground hover:border-foreground/40")
                  }
                >
                  <span>Día {d}</span>
                  <span className="text-[10px]">
                    {entries.length === 0 ? "libre" : `${doneD}/${entries.length} ✓`}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Productos del día seleccionado */}
          <div>
            <h2 className="mb-1.5 text-sm font-semibold">📅 Día {selectedDay}</h2>
            {(byDay.get(selectedDay) ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">— día libre —</p>
            ) : (
              <div className="space-y-2">
                {(byDay.get(selectedDay) ?? []).map((e) => (
                  <DayEntry key={e.product_id} e={e} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DayEntry({ e }: { e: PlanEntry }) {
  const qc = useQueryClient();
  const mark = useMarkTested();
  const remove = useRemoveFromPlan();
  const pack = usePlanPack();
  const [open, setOpen] = useState(false);
  // El plan no sabe si hay un job activo: marcamos "generando" solo tras
  // pulsar el botón, así un pack pendiente no muestra un spinner falso.
  const [packing, setPacking] = useState(false);
  // Estado local del check → feedback instantáneo (el plan se refresca cada
  // 5s mientras se generan packs y pisaba el estado del checkbox controlado).
  const [tested, setTested] = useState(e.tested);
  useEffect(() => setTested(e.tested), [e.tested]);
  // Mientras se generan los vídeos IA, refresca el plan hasta que aparezcan.
  useEffect(() => {
    if (!packing) return;
    if (e.ai_ready) {
      setPacking(false);
      return;
    }
    const t = setInterval(
      () => qc.invalidateQueries({ queryKey: ["radar-plan"] }),
      6000,
    );
    return () => clearInterval(t);
  }, [packing, e.ai_ready, qc]);

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

  return (
    <Card>
      <CardContent className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {tested && <Check className="mr-1 inline h-3.5 w-3.5 text-green-600" />}
              {e.name}
            </p>
            <p className="text-[11px] text-muted-foreground">
              ⭐ {e.score.toFixed(0)} · {VERDICT[e.ads_verdict] ?? ""} ADS {e.ads_verdict} ·{" "}
              🎯 {e.problem_videos_count} · ⚡ plantillas · 🎣 {e.hooks_count}
              {e.ai_ready && (
                <span> · 🎥 {e.presets_count} · 🎠 {e.carousels_count}</span>
              )}
            </p>
            {e.tiktok_url && (
              <a
                href={e.tiktok_url}
                target="_blank"
                rel="noreferrer"
                className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-orange-500 hover:underline"
              >
                <ExternalLink className="h-3 w-3" /> Abrir ficha (descargar fotos)
              </a>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <label className="flex cursor-pointer items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={tested}
                onChange={(ev) => {
                  const v = ev.target.checked;
                  setTested(v);   // instantáneo
                  mark.mutate(
                    { product_id: e.product_id, tested: v },
                    {
                      onError: () => setTested(!v),   // revierte si falla
                      onSuccess: () => qc.invalidateQueries({ queryKey: ["radar-plan"] }),
                    },
                  );
                }}
              />
              Probado
            </label>
            <button
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(
                  { product_id: e.product_id },
                  {
                    onSuccess: () => {
                      toast.success("Quitado del calendario");
                      qc.invalidateQueries({ queryKey: ["radar-plan"] });
                    },
                  },
                )
              }
              className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-red-500"
              title="Quitar del calendario (no borra el producto)"
            >
              <Trash2 className="h-3 w-3" /> quitar
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-orange-500 hover:underline"
          >
            <ChevronDown className={"h-3.5 w-3.5 transition " + (open ? "rotate-180" : "")} />
            Ver prompts
          </button>
          {!e.ai_ready &&
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
          {problemToShow.map((v, i) => (
            <details key={i} className="rounded border border-border/60 p-2 text-xs" open={i === 0}>
              <summary className="cursor-pointer font-medium">
                {i + 1}. {v.concept}
                {v.format && (
                  <span className="ml-1 rounded bg-orange-500/10 px-1.5 py-0.5 text-[10px] text-orange-600">
                    {v.format}
                  </span>
                )}{" "}
                <span className="text-muted-foreground">· {v.emotion}</span>
              </summary>
              <div className="mt-2 space-y-2">
                {v.angle && <p className="text-[11px] text-muted-foreground">🎯 {v.angle}</p>}
                <CopyBlock label="🟣 Prompt Veo 3 (10s · adjunta foto)" text={v.veo3_prompt} />
                {v.spoken_line && <CopyBlock label="🗣️ Lo que dice (voz)" text={v.spoken_line} />}
                {v.hook_text && <CopyBlock label="📌 Texto gancho (en pantalla arriba)" text={v.hook_text} />}
                {v.cta_text && <CopyBlock label="🛒 CTA (abajo, al carrito)" text={v.cta_text} />}
                {v.caption && <CopyBlock label="✍️ Caption (descripción del post · sin hashtags)" text={v.caption} />}
              </div>
            </details>
          ))}
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
            ⚡ Plantillas reutilizables (sin coste IA). Flujo Kling: genera la <b>foto
            del 1er frame</b> en Nano Banana (adjunta la foto del producto), y pásala a
            <b> Kling</b> como start-frame. Sin caras IA, POV/manos.
          </p>
          {(tpls.data?.templates ?? []).map((t) => (
            <details key={t.id} className="rounded border border-border/60 p-2 text-xs">
              <summary className="cursor-pointer font-medium">
                {t.name} <span className="text-muted-foreground">· {t.niches.join("/")}</span>
              </summary>
              <div className="mt-2 space-y-1">
                {t.notes && <p className="text-[11px] text-muted-foreground">{t.notes}</p>}
                <CopyBlock label="🍌 1er frame (Nano Banana + foto producto)" text={t.first_frame_prompt} />
                <CopyBlock label="🎬 Kling (i2v desde el 1er frame)" text={t.kling_prompt} />
                <CopyBlock label="🟣 Veo 3 (alternativa texto→vídeo)" text={t.prompt} />
              </div>
            </details>
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
