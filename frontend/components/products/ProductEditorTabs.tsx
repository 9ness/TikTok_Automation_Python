"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
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
  return (
    <Tabs defaultValue="identity" className="space-y-4">
      <TabsList className="flex-wrap">
        <TabsTrigger value="identity">Identidad</TabsTrigger>
        <TabsTrigger value="audience">Audiencia</TabsTrigger>
        <TabsTrigger value="config">Config técnica</TabsTrigger>
        <TabsTrigger value="voice">Voz</TabsTrigger>
        <TabsTrigger value="hooks">Hooks</TabsTrigger>
        <TabsTrigger value="photos">Fotos</TabsTrigger>
        <TabsTrigger value="analysis">Análisis</TabsTrigger>
      </TabsList>

      <TabsContent value="identity">
        <IdentityTab product={product} />
      </TabsContent>
      <TabsContent value="audience">
        <AudienceTab product={product} />
      </TabsContent>
      <TabsContent value="config">
        <ConfigTab product={product} />
      </TabsContent>
      <TabsContent value="voice">
        <VoiceTab product={product} />
      </TabsContent>
      <TabsContent value="hooks">
        <HooksEditor product={product} />
      </TabsContent>
      <TabsContent value="photos">
        <PhotoManager product={product} />
      </TabsContent>
      <TabsContent value="analysis">
        <AnalysisTab product={product} />
      </TabsContent>
    </Tabs>
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
  const [form, setForm] = useDirtyForm({
    name: product.name,
    slug: product.slug,
    brand: product.brand ?? "",
    category: product.category,
    subcategory: product.subcategory ?? "",
    shop: { ...product.tiktok_shop },
  });

  function setShop<K extends keyof TikTokShopMeta>(key: K, value: TikTokShopMeta[K]) {
    setForm((f) => ({ ...f, shop: { ...f.shop, [key]: value } }));
  }

  async function save() {
    const payload: ProductUpdateInput = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      brand: form.brand.trim() || null,
      category: form.category.trim() || "otros",
      subcategory: form.subcategory.trim() || null,
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
      <FormField label="URL TikTok Shop">
        <Input
          value={form.shop.product_url ?? ""}
          onChange={(e) => setShop("product_url", e.target.value || null)}
        />
      </FormField>
      <FormField label="Product ID TT Shop">
        <Input
          value={form.shop.product_id ?? ""}
          onChange={(e) => setShop("product_id", e.target.value || null)}
        />
      </FormField>
      <FormField label={`Comisión (${(form.shop.commission_rate * 100).toFixed(0)}%)`}>
        <Input
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={form.shop.commission_rate}
          onChange={(e) => setShop("commission_rate", Number(e.target.value))}
        />
      </FormField>

      <div className="md:col-span-2">
        <Button onClick={save} disabled={update.isPending}>
          {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Guardar identidad
        </Button>
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

  return (
    <div className="space-y-4">
      <div className="rounded-md border p-4">
        <h3 className="font-semibold">Re-analizar con Gemini Vision</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Lee las fotos del producto y actualiza key features, audiencias y selling points.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge variant={cleanPackagingFlag ? "destructive" : "secondary"}>
            Packaging complejo: {cleanPackagingFlag ? "sí" : "no"}
          </Badge>
          <Badge variant={needsRegen ? "destructive" : "secondary"}>
            Needs Nano Banana: {needsRegen ? "sí" : "no"}
          </Badge>
          {product.last_analyzed_at && (
            <Badge variant="outline">
              Último análisis: {product.last_analyzed_at.slice(0, 19).replace("T", " ")}
            </Badge>
          )}
        </div>
        <Button className="mt-3" onClick={handleReanalyze} disabled={reanalyze.isPending}>
          {reanalyze.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          <Sparkles className="h-4 w-4" /> Re-analizar
        </Button>
      </div>

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
