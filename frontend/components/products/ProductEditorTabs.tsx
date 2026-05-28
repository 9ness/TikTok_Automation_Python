"use client";

import { useState } from "react";
import {
  Image as ImageIcon,
  Link2,
  Loader2,
  Sparkles,
  Tag,
  Target,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  useAnalyzeUrlPreview,
  useReanalyzeProduct,
  useUpdateProduct,
} from "@/lib/queries/products";
import { useVoices } from "@/lib/queries/voices";
import type {
  Product,
  ProductUpdateInput,
  Tier,
  TikTokShopMeta,
} from "@/lib/types/product";
import { HooksEditor } from "./HooksEditor";
import { NanoBananaPromptDialog } from "./NanoBananaPromptDialog";
import { PhotoManager } from "./PhotoManager";
import { PresetsManager } from "./PresetsManager";
import { ResearchPanel } from "./ResearchPanel";
import { TabHint } from "./TabHint";
import { cn } from "@/lib/utils";
import { LANGUAGE_OPTIONS } from "@/lib/language";
import { formatLocal } from "@/lib/dates";

// Definición de los 5 tabs como tarjetas. Cada tab tiene un `mode`
// que pinta el borde/fondo según convención del producto:
//   - auto    → verde (Gemini lo rellena)
//   - mixed   → azul  (auto inicial + editable a mano)
//   - manual  → gris  (lo decides tú)
type TabMode = "auto" | "mixed" | "manual";

const PRODUCT_TABS: {
  value: string;
  title: string;
  icon: typeof Tag;
  mode: TabMode;
  hint: string;
}[] = [
  {
    value: "identity",
    title: "Identidad",
    icon: Tag,
    mode: "mixed",
    hint: "Nombre, marca, precio…",
  },
  {
    value: "photos",
    title: "Fotos",
    icon: ImageIcon,
    mode: "mixed",
    hint: "Referencias para los modelos AI",
  },
  {
    value: "analysis",
    title: "Análisis",
    icon: Sparkles,
    mode: "auto",
    hint: "Gemini lee las fotos",
  },
  {
    value: "audience",
    title: "Audiencia",
    icon: Target,
    mode: "auto",
    hint: "Auto-rellenada por Análisis",
  },
  {
    value: "presets",
    title: "Presets",
    icon: Wand2,
    mode: "auto",
    hint: "Blueprints de vídeo",
  },
];

const MODE_BORDER: Record<TabMode, { card: string; active: string; dot: string; label: string }> = {
  auto: {
    card: "border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/60",
    active: "border-emerald-500 bg-emerald-500/15",
    dot: "bg-emerald-500",
    label: "Auto-generado",
  },
  mixed: {
    card: "border-sky-500/30 bg-sky-500/5 hover:border-sky-500/60",
    active: "border-sky-500 bg-sky-500/15",
    dot: "bg-sky-500",
    label: "Auto + editable",
  },
  manual: {
    card: "border-slate-500/30 bg-slate-500/5 hover:border-slate-500/60",
    active: "border-slate-500 bg-slate-500/15",
    dot: "bg-slate-500",
    label: "Manual",
  },
};

const TIERS: { value: Tier; label: string }[] = [
  { value: "standard", label: "🟢 Standard" },
  { value: "advanced", label: "🟡 Advanced" },
  { value: "pro", label: "🔴 Pro" },
  { value: "veo3_prompt_only", label: "🟣 Veo 3" },
  { value: "nano_banana_prompt_only", label: "🍌 Nano Banana" },
];

const RESOLUTIONS = ["480p", "720p", "1080p-SR", "1440p-SR"];
const STYLES = [
  "asmr_macro",
  "ugc_natural",
  "lifestyle_aspirational",
  "cinematic_premium",
  "testimonial_voice",
  "before_after",
  "demo_use",
];
const TONES = ["energetic", "calm", "informative"] as const;

export function ProductEditorTabs({ product }: { product: Product }) {
  const [active, setActive] = useState<string>("identity");

  return (
    <div className="space-y-3">
      {/* Leyenda compacta — chuleta de colores arriba del todo */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground sm:text-xs">
        <span>Leyenda:</span>
        {(["mixed", "auto", "manual"] as TabMode[]).map((m) => (
          <span key={m} className="flex items-center gap-1">
            <span className={cn("h-2 w-2 rounded-full", MODE_BORDER[m].dot)} />
            {MODE_BORDER[m].label}
          </span>
        ))}
      </div>

      {/* Grid de tarjetas — 2 cols mobile, 5 cols desktop */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {PRODUCT_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = active === tab.value;
          const colors = MODE_BORDER[tab.mode];
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => setActive(tab.value)}
              className={cn(
                "group flex flex-col items-start gap-1 rounded-lg border-2 px-2.5 py-2 text-left transition-all sm:gap-1.5 sm:px-3 sm:py-2.5",
                isActive ? colors.active : colors.card,
              )}
            >
              <div className="flex w-full items-center justify-between gap-1">
                <Icon className="h-4 w-4 shrink-0 sm:h-5 sm:w-5" />
                <span className={cn("h-1.5 w-1.5 rounded-full", colors.dot)} />
              </div>
              <strong className="text-[11px] sm:text-sm">{tab.title}</strong>
              <span className="line-clamp-2 text-[9px] leading-tight text-muted-foreground sm:text-[10px]">
                {tab.hint}
              </span>
            </button>
          );
        })}
      </div>

      {/* Contenido del tab activo */}
      <div className="pt-2">
        {active === "identity" && <IdentityTab product={product} />}
        {active === "photos" && <PhotoManager product={product} />}
        {active === "analysis" && <AnalysisTab product={product} />}
        {active === "audience" && <AudienceTab product={product} />}
        {active === "presets" && <PresetsManager product={product} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper: form state inicializado del producto.
//
// Solo lee `initial` en el primer render — si el producto cambia desde fuera,
// hay que remontar el editor (usar `key={product.id}` en el caller).
// ---------------------------------------------------------------------------
function useDirtyForm<T>(initial: T) {
  const [value, setValue] = useState<T>(() => initial);
  return [value, setValue] as const;
}

async function persist(
  update: ReturnType<typeof useUpdateProduct>,
  payload: ProductUpdateInput,
  successMessage: string,
) {
  try {
    await update.mutateAsync(payload);
    toast.success(successMessage);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : "Error al guardar.";
    toast.error(message);
  }
}

// ---------------------------------------------------------------------------
// Tab: Identidad
// ---------------------------------------------------------------------------
function IdentityTab({ product }: { product: Product }) {
  const update = useUpdateProduct(product.id);
  const analyzeUrl = useAnalyzeUrlPreview();
  const [rawText, setRawText] = useState("");
  const [form, setForm] = useDirtyForm({
    name: product.name,
    slug: product.slug,
    brand: product.brand ?? "",
    category: product.category,
    subcategory: product.subcategory ?? "",
    language: product.language || "es_ES",
    shop: { ...product.tiktok_shop },
  });

  function setShop<K extends keyof TikTokShopMeta>(key: K, value: TikTokShopMeta[K]) {
    setForm((f) => ({ ...f, shop: { ...f.shop, [key]: value } }));
  }

  /** Auto-rellenar el form desde la URL y/o texto pegado. NO guarda —
   *  el usuario revisa y pulsa "Guardar identidad" cuando esté contento.
   *  TikTok Shop suele bloquear el scraping puro, así que el textarea
   *  "info pegada" es plan B fiable: el user copia del dashboard de
   *  TikTok Shop y Gemini extrae los campos. */
  async function handleAnalyzeUrl() {
    const url = form.shop.product_url?.trim();
    const text = rawText.trim();
    if (!url && !text) {
      toast.error("Pega la URL de TikTok Shop o texto del producto");
      return;
    }
    try {
      const result = await analyzeUrl.mutateAsync({
        url: url || undefined,
        raw_text: text || undefined,
      });
      // Aplicar lo que se haya detectado (sin sobrescribir lo que ya tenga
      // valor manual del usuario salvo que esté vacío).
      setForm((f) => ({
        ...f,
        name: result.name && !f.name.trim() ? result.name : f.name,
        brand: result.brand && !f.brand.trim() ? result.brand : f.brand,
        category:
          result.category && (f.category === "otros" || !f.category.trim())
            ? result.category
            : f.category,
        subcategory:
          result.subcategory && !f.subcategory.trim()
            ? result.subcategory
            : f.subcategory,
        shop: {
          ...f.shop,
          price_eur:
            result.price_eur != null && f.shop.price_eur == null
              ? result.price_eur
              : f.shop.price_eur,
        },
      }));
      const detected = [
        result.name && "nombre",
        result.brand && "marca",
        result.category && "categoría",
        result.price_eur != null && "precio",
      ].filter(Boolean);
      if (detected.length === 0) {
        toast.warning(
          "No se detectó información. " +
            (result.warnings[0] || "TikTok Shop puede bloquear el scraping."),
        );
      } else {
        toast.success(`Detectado: ${detected.join(", ")}. Revisa y guarda.`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Análisis falló");
    }
  }

  // ── Comisión dual % + € ─────────────────────────────────────────
  // El backend persiste solo `commission_rate` (porcentaje, 0-1). El €
  // es derivado: price_eur × rate. Aquí ofrecemos los 2 inputs y
  // sincronizamos en función del que se edita.
  const price = form.shop.price_eur ?? 0;
  const rate = form.shop.commission_rate ?? 0;
  const commissionEur = price > 0 ? price * rate : 0;

  function setRate(newRate: number) {
    setShop("commission_rate", Math.max(0, Math.min(1, newRate)));
  }

  function setCommissionEur(eur: number) {
    if (price <= 0) {
      toast.warning("Pon primero el Precio EUR para calcular el porcentaje");
      return;
    }
    const newRate = eur / price;
    setShop("commission_rate", Math.max(0, Math.min(1, newRate)));
  }

  async function save() {
    const payload: ProductUpdateInput = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      brand: form.brand.trim() || null,
      category: form.category.trim() || "otros",
      subcategory: form.subcategory.trim() || null,
      language: form.language,
      tiktok_shop: {
        product_url: form.shop.product_url || null,
        product_id: form.shop.product_id || null,
        commission_rate: form.shop.commission_rate,
        price_eur: form.shop.price_eur,
      },
    };
    await persist(update, payload, "Identidad guardada.");
  }

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-2">
      <FormField label="Nombre">
        <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
      </FormField>
      <FormField label="Slug">
        <Input value={form.slug} onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))} />
      </FormField>
      <FormField label="Marca">
        <Input
          value={form.brand}
          onChange={(e) => setForm((f) => ({ ...f, brand: e.target.value }))}
        />
      </FormField>
      <FormField label="Categoría">
        <Input
          value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
        />
      </FormField>
      <FormField label="Subcategoría">
        <Input
          value={form.subcategory}
          onChange={(e) => setForm((f) => ({ ...f, subcategory: e.target.value }))}
        />
      </FormField>
      <FormField label="Idioma del contenido">
        <select
          className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={form.language}
          onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
          title="Afecta voz + guion + subtítulos. Regenera presets tras cambiarlo para que se apliquen."
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.code} value={opt.code}>
              {opt.label}
            </option>
          ))}
        </select>
      </FormField>
      <FormField label="Precio EUR">
        <Input
          type="number"
          step="0.01"
          value={form.shop.price_eur ?? ""}
          onChange={(e) =>
            setShop("price_eur", e.target.value === "" ? null : Number(e.target.value))
          }
        />
      </FormField>

      {/* URL TikTok Shop + textarea + botón Analizar (ocupa fila entera) */}
      <FormField label="URL TikTok Shop" className="md:col-span-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={form.shop.product_url ?? ""}
            onChange={(e) => setShop("product_url", e.target.value || null)}
            placeholder="https://shop-xx.tiktok.com/view/product/..."
            className="flex-1"
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleAnalyzeUrl}
            disabled={
              analyzeUrl.isPending ||
              (!form.shop.product_url?.trim() && !rawText.trim())
            }
            className="shrink-0"
          >
            {analyzeUrl.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            <span className="ml-2">Analizar</span>
          </Button>
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Pega la URL del producto. TikTok Shop suele bloquear el scraping
          puro, así que también puedes pegar título / precio / descripción
          en la caja de abajo — Gemini extrae los campos.
        </p>
        <Textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder={
            "Opcional · pega texto del producto (título, precio, descripción del " +
            "dashboard de TikTok Shop, share text del móvil…). Plan B fiable cuando " +
            "el scraping no devuelve nada."
          }
          rows={3}
          className="mt-2 text-xs"
        />
      </FormField>

      <FormField label="Product ID TT Shop">
        <Input
          value={form.shop.product_id ?? ""}
          onChange={(e) => setShop("product_id", e.target.value || null)}
        />
      </FormField>
      {/* Hueco para alinear el grid 2-col (Product ID solo) */}
      <div className="hidden md:block" />

      {/* Comisión dual: % ↔ € sincronizado */}
      <FormField label="Comisión %">
        <div className="flex items-center gap-2">
          <Input
            type="number"
            step="0.1"
            min="0"
            max="100"
            value={(rate * 100).toFixed(1)}
            onChange={(e) => setRate(Number(e.target.value) / 100)}
          />
          <span className="text-sm text-muted-foreground">%</span>
        </div>
      </FormField>
      <FormField label="Comisión € (importe)">
        <div className="flex items-center gap-2">
          <Input
            type="number"
            step="0.01"
            min="0"
            value={commissionEur > 0 ? commissionEur.toFixed(2) : ""}
            disabled={price <= 0}
            placeholder={price <= 0 ? "Pon antes el Precio EUR" : "0.00"}
            onChange={(e) => setCommissionEur(Number(e.target.value))}
          />
          <span className="text-sm text-muted-foreground">€</span>
        </div>
        {price > 0 && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            {commissionEur.toFixed(2)}€ = {(rate * 100).toFixed(1)}% de{" "}
            {price.toFixed(2)}€. Edita cualquiera de los 2 — el otro se recalcula.
          </p>
        )}
      </FormField>

      <div className="md:col-span-2">
        <Button onClick={save} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar identidad
        </Button>
      </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Audiencia
// ---------------------------------------------------------------------------
function AudienceTab({ product }: { product: Product }) {
  const update = useUpdateProduct(product.id);
  const [form, setForm] = useDirtyForm({
    target_audience: product.target_audience.join("\n"),
    key_features: product.key_features.join("\n"),
    selling_points: product.selling_points.join("\n"),
  });

  async function save() {
    await persist(
      update,
      {
        target_audience: form.target_audience.split("\n").map((s) => s.trim()).filter(Boolean),
        key_features: form.key_features.split("\n").map((s) => s.trim()).filter(Boolean),
        selling_points: form.selling_points.split("\n").map((s) => s.trim()).filter(Boolean),
      },
      "Audiencia guardada.",
    );
  }

  return (
    <div className="space-y-4">
      <FormField label="Audiencia objetivo (una por línea)">
        <Textarea
          rows={4}
          value={form.target_audience}
          onChange={(e) => setForm((f) => ({ ...f, target_audience: e.target.value }))}
        />
      </FormField>
      <FormField label="Key features (una por línea)">
        <Textarea
          rows={4}
          value={form.key_features}
          onChange={(e) => setForm((f) => ({ ...f, key_features: e.target.value }))}
        />
      </FormField>
      <FormField label="Selling points (uno por línea)">
        <Textarea
          rows={4}
          value={form.selling_points}
          onChange={(e) => setForm((f) => ({ ...f, selling_points: e.target.value }))}
        />
      </FormField>
      <Button onClick={save} disabled={update.isPending}>
        {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
        Guardar audiencia
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Config técnica
// ---------------------------------------------------------------------------
function ConfigTab({ product }: { product: Product }) {
  const update = useUpdateProduct(product.id);
  const [form, setForm] = useDirtyForm({
    default_tier: product.video_config.default_tier,
    default_duration: product.video_config.default_duration,
    default_resolution: product.video_config.default_resolution,
    preferred_styles: new Set(product.video_config.preferred_styles),
  });

  function toggleStyle(s: string) {
    setForm((f) => {
      const next = new Set(f.preferred_styles);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return { ...f, preferred_styles: next };
    });
  }

  async function save() {
    await persist(
      update,
      {
        default_tier: form.default_tier,
        default_duration: form.default_duration,
        default_resolution: form.default_resolution,
        preferred_styles: Array.from(form.preferred_styles),
      },
      "Configuración guardada.",
    );
  }

  return (
    <div>
      <TabHint mode="manual" source="Tú lo eliges">
        Valores por defecto al generar vídeos de este producto. Los puedes
        cambiar en <code>/tiktok-shop/generate</code> al encolar cada vídeo.
        Standard / Advanced son i2v (1 foto + animación), Pro es ref2v
        multi-shot (hasta 9 fotos), Veo 3 es prompt-only (máx 10s).
      </TabHint>
      <div className="grid gap-4 md:grid-cols-2">
      <FormField label="Tier por defecto">
        <Select
          value={form.default_tier}
          onValueChange={(v) => setForm((f) => ({ ...f, default_tier: v as Tier }))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIERS.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FormField>
      <FormField label="Duración (s)">
        <Input
          type="number"
          min="5"
          max="30"
          value={form.default_duration}
          onChange={(e) =>
            setForm((f) => ({ ...f, default_duration: Number(e.target.value) }))
          }
        />
      </FormField>
      <FormField label="Resolución">
        <Select
          value={form.default_resolution}
          onValueChange={(v) => setForm((f) => ({ ...f, default_resolution: v }))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RESOLUTIONS.map((r) => (
              <SelectItem key={r} value={r}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FormField>
      <FormField label="Estilos preferidos" className="md:col-span-2">
        <div className="flex flex-wrap gap-2">
          {STYLES.map((s) => {
            const active = form.preferred_styles.has(s);
            return (
              <Button
                key={s}
                type="button"
                size="sm"
                variant={active ? "default" : "outline"}
                onClick={() => toggleStyle(s)}
              >
                {s}
              </Button>
            );
          })}
        </div>
      </FormField>

      <div className="md:col-span-2">
        <Button onClick={save} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar config
        </Button>
      </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Voz
// ---------------------------------------------------------------------------
function VoiceTab({ product }: { product: Product }) {
  const update = useUpdateProduct(product.id);
  const voices = useVoices({ language: "es" });
  const [voiceId, setVoiceId] = useState(
    product.video_config.voice_preference.voice_id ?? "",
  );
  const [tone, setTone] = useState<(typeof TONES)[number]>(
    product.video_config.voice_preference.tone,
  );

  async function save() {
    const isPreset = voices.data?.items.find(
      (v) => v.minimax_voice_id === voiceId,
    )?.is_preset;
    await persist(
      update,
      {
        voice_preference: {
          type: isPreset ? "tts_preset" : "voice_clone",
          voice_id: voiceId || null,
          tone,
        },
      },
      "Voz guardada.",
    );
  }

  return (
    <div>
      <TabHint mode="manual" source="Tú lo eliges">
        Voz que usará el TTS para narrar los presets scripted. Presets MiniMax
        ES por defecto. Voces clonadas se gestionan desde{" "}
        <code>/creator-reward/tools/voices</code>.
      </TabHint>
      <div className="grid gap-4 md:grid-cols-2">
      <FormField label="Voz preferida">
        <Select value={voiceId} onValueChange={setVoiceId}>
          <SelectTrigger>
            <SelectValue placeholder={voices.isLoading ? "Cargando…" : "Seleccionar voz"} />
          </SelectTrigger>
          <SelectContent>
            {(voices.data?.items ?? []).map((v) => (
              <SelectItem key={v.id} value={v.minimax_voice_id}>
                {v.is_preset ? "🎚️" : "🎤"} {v.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FormField>
      <FormField label="Tono">
        <Select value={tone} onValueChange={(v) => setTone(v as (typeof TONES)[number])}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TONES.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FormField>

      <div className="md:col-span-2">
        <Button onClick={save} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar voz
        </Button>
      </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Análisis
// ---------------------------------------------------------------------------
function AnalysisTab({ product }: { product: Product }) {
  const reanalyze = useReanalyzeProduct();
  const [nanoOpen, setNanoOpen] = useState(false);

  async function handleReanalyze() {
    try {
      const res = await reanalyze.mutateAsync(product.id);
      toast.success(
        `Re-analizado. ${res.key_features.length} features, ${res.suggested_audiences.length} audiencias.`,
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error en análisis.";
      toast.error(message);
    }
  }

  const cleanPackagingFlag = product.video_config.has_complex_packaging;
  const needsRegen = product.needs_nano_banana_regeneration;
  const quality = product.photos_quality_assessment;
  const warnings = product.last_analysis_warnings ?? [];

  const QUALITY_LABEL: Record<string, { label: string; cls: string }> = {
    high: { label: "Alta", cls: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300" },
    medium: { label: "Media", cls: "bg-amber-500/20 text-amber-700 dark:text-amber-300" },
    low: { label: "Baja", cls: "bg-rose-500/20 text-rose-700 dark:text-rose-300" },
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border p-4">
        <h3 className="font-semibold">Re-analizar producto</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Hace todo en una llamada:
        </p>
        <ul className="mt-1 ml-4 list-disc text-xs text-muted-foreground sm:text-sm">
          <li>Gemini Vision lee las fotos → audiencias, features, packaging</li>
          <li>Gemini Web Search → reviews Amazon/AliExpress (pains, benefits, objections)</li>
          <li>Apify TikTok → top 10 vídeos virales del producto</li>
          <li>Gemini analiza los 5 mejores vídeos (visual + audio) → patrones</li>
        </ul>
        <p className="mt-1 text-[11px] text-muted-foreground sm:text-xs">
          Coste ~$0.15. El paso 1 (fotos) es síncrono; los 2-4 corren en
          background — puedes cerrar el navegador.
        </p>
        <Button className="mt-3" onClick={handleReanalyze} disabled={reanalyze.isPending}>
          {reanalyze.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          <Sparkles className="h-4 w-4" /> Re-analizar
        </Button>
        {product.last_analyzed_at && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            Último análisis: {formatLocal(product.last_analyzed_at)}
          </p>
        )}
      </div>

      {/* Diagnóstico explicativo */}
      {product.last_analyzed_at && (
        <div className="space-y-3 rounded-md border p-4">
          <h3 className="text-sm font-semibold">Diagnóstico de las fotos</h3>

          {/* Calidad general */}
          {quality && QUALITY_LABEL[quality] && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Calidad:</span>
              <span
                className={cn(
                  "rounded px-2 py-0.5 text-xs font-medium",
                  QUALITY_LABEL[quality]!.cls,
                )}
              >
                {QUALITY_LABEL[quality]!.label}
              </span>
            </div>
          )}

          {/* Packaging complejo */}
          <div className="rounded-md border border-muted p-2 text-xs">
            <div className="flex items-center justify-between">
              <strong>Packaging complejo</strong>
              <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold",
                cleanPackagingFlag
                  ? "bg-amber-500/20 text-amber-700 dark:text-amber-300"
                  : "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
              )}>
                {cleanPackagingFlag ? "SÍ" : "NO"}
              </span>
            </div>
            <p className="mt-1 text-muted-foreground">
              {cleanPackagingFlag ? (
                <>
                  La etiqueta del producto tiene texto/logo prominente.
                  Importante <strong>solo si vas a Pro multi-shot</strong> (i2v
                  Standard/Advanced con 1 foto NO recrea texto, simplemente
                  anima la foto que le das tal cual — sin problema).
                </>
              ) : (
                <>Etiqueta limpia, sin texto que pueda confundir al modelo.</>
              )}
            </p>
          </div>

          {/* Needs Nano Banana */}
          <div className="rounded-md border border-muted p-2 text-xs">
            <div className="flex items-center justify-between">
              <strong>Recomendado regenerar con Nano Banana</strong>
              <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold",
                needsRegen
                  ? "bg-amber-500/20 text-amber-700 dark:text-amber-300"
                  : "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
              )}>
                {needsRegen ? "SÍ" : "NO"}
              </span>
            </div>
            <p className="mt-1 text-muted-foreground">
              {needsRegen ? (
                <>
                  Las fotos están <strong>por debajo de 1024px</strong> en algún
                  lado (típico de og:image de TikTok 260×260 y resultados de
                  Google Images 600-800px). Para 🟢 Standard/🟡 Advanced (1 foto
                  ampliada) <strong>vale lo que tienes</strong> — no es
                  bloqueante. Para 🔴 Pro multi-shot o 🍌 Nano Banana,
                  regenera para subir resolución.
                </>
              ) : (
                <>Fotos con resolución suficiente para todos los tiers.</>
              )}
            </p>
          </div>

          {/* Warnings detallados de Gemini */}
          {warnings.length > 0 && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs">
              <strong className="text-amber-700 dark:text-amber-300">
                Detalles del análisis ({warnings.length})
              </strong>
              <ul className="mt-1 space-y-0.5 text-muted-foreground">
                {warnings.map((w, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span>•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="rounded-md border p-4">
        <h3 className="font-semibold">Generar prompt Nano Banana 2</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Crea fotos premium en Gemini chat a partir de las fotos source. El prompt es manual.
        </p>
        <Button className="mt-3" variant="outline" onClick={() => setNanoOpen(true)}>
          🍌 Abrir asistente
        </Button>
      </div>

      <NanoBananaPromptDialog product={product} open={nanoOpen} onOpenChange={setNanoOpen} />

      {/* Investigación profunda (reviews + TikTok) — se rellena con el
          mismo botón Re-analizar de arriba. Aparece como sección
          adicional aquí dentro para no duplicar tabs. */}
      <div className="border-t pt-4">
        <h3 className="mb-2 text-sm font-semibold">🔬 Investigación profunda</h3>
        <ResearchPanel product={product} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function FormField({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`space-y-2 ${className ?? ""}`}>
      <Label>{label}</Label>
      {children}
    </div>
  );
}
