"use client";

import { useState, type ReactNode } from "react";
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
  useMarkTested,
  usePlanGenerate,
  useRadarPlan,
  useRegenerateCarousels,
  useVideoTemplates,
  type BofuHook,
  type PlanEntry,
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
  const [perDay, setPerDay] = useState(2);
  const [days, setDays] = useState(7);

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
        <div className="space-y-4">
          {Array.from({ length: totalDays }, (_, i) => i + 1).map((d) => {
            const entries = byDay.get(d) ?? [];
            return (
              <div key={d}>
                <h2 className="mb-1.5 text-sm font-semibold">📅 Día {d}</h2>
                {entries.length === 0 ? (
                  <p className="text-xs text-muted-foreground">— libre —</p>
                ) : (
                  <div className="space-y-2">
                    {entries.map((e) => <DayEntry key={e.product_id} e={e} />)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DayEntry({ e }: { e: PlanEntry }) {
  const qc = useQueryClient();
  const mark = useMarkTested();
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardContent className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium">
              {e.tested && <Check className="mr-1 inline h-3.5 w-3.5 text-green-600" />}
              {e.name}
            </p>
            <p className="text-[11px] text-muted-foreground">
              ⭐ {e.score.toFixed(0)} · {VERDICT[e.ads_verdict] ?? ""} ADS {e.ads_verdict} ·{" "}
              {e.pack_ready ? (
                <span>🎠 {e.carousels_count} · 🎥 {e.presets_count}</span>
              ) : (
                <span className="text-orange-500">
                  <Loader2 className="inline h-3 w-3 animate-spin" /> generando pack…
                </span>
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
          <label className="flex shrink-0 cursor-pointer items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={e.tested}
              onChange={(ev) =>
                mark.mutate(
                  { product_id: e.product_id, tested: ev.target.checked },
                  { onSuccess: () => qc.invalidateQueries({ queryKey: ["radar-plan"] }) },
                )
              }
            />
            Probado
          </label>
        </div>

        {e.pack_ready && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-orange-500 hover:underline"
          >
            <ChevronDown className={"h-3.5 w-3.5 transition " + (open ? "rotate-180" : "")} />
            Ver vídeos + carruseles
          </button>
        )}
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
  const [tab, setTab] = useState<"video" | "carousel" | "templates" | "hooks">("video");
  const tpls = useVideoTemplates(productId);
  const [carLang, setCarLang] = useState("es");
  const [carStyle, setCarStyle] = useState("simple");
  const regen = useRegenerateCarousels();
  const bofu = useBofuHooks();
  const [bofuHooks, setBofuHooks] = useState<BofuHook[]>([]);

  if (isLoading) return <p className="text-xs text-muted-foreground">Cargando prompts…</p>;
  if (!product) return <p className="text-xs text-destructive">Producto no encontrado.</p>;

  const presets = product.video_presets ?? [];
  const carousels = (product.carousels ?? []) as unknown as Carousel[];
  const photos = (product.photos?.source ?? []).filter((p) => !p.deleted);
  const listingUrl = product.tiktok_shop?.product_url ?? "";

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
        <TabBtn active={tab === "video"} onClick={() => setTab("video")}>🎥 Vídeos IA ({presets.length})</TabBtn>
        <TabBtn active={tab === "carousel"} onClick={() => setTab("carousel")}>🎠 Carruseles ({carousels.length})</TabBtn>
        <TabBtn active={tab === "templates"} onClick={() => setTab("templates")}>⚡ Plantillas ({tpls.data?.templates.length ?? 0})</TabBtn>
        <TabBtn active={tab === "hooks"} onClick={() => setTab("hooks")}>🎣 Hooks BOFU</TabBtn>
      </div>

      {tab === "video" && (
        <div className="space-y-2">
          {presets.length === 0 && <p className="text-xs text-muted-foreground">Sin estilos.</p>}
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
          {carousels.length === 0 && <p className="text-xs text-muted-foreground">Sin carruseles.</p>}
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
            ⚡ Plantillas reutilizables (sin coste IA). Copia el prompt y <b>adjunta
            una foto del producto</b> al pegarlo en Veo 3 / Gemini. Ideal para
            volumen — sin caras IA, POV/manos.
          </p>
          {(tpls.data?.templates ?? []).map((t) => (
            <details key={t.id} className="rounded border border-border/60 p-2 text-xs">
              <summary className="cursor-pointer font-medium">
                {t.name} <span className="text-muted-foreground">· {t.niches.join("/")}</span>
              </summary>
              <div className="mt-2 space-y-1">
                {t.notes && <p className="text-[11px] text-muted-foreground">{t.notes}</p>}
                <CopyBlock label="" text={t.prompt} />
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
