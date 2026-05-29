"use client";

import { useMemo, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, Image as ImageIcon, Loader2, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  useEnqueueGeneration,
  usePreviewNanoBananaPrompt,
  usePreviewVeo3Prompt,
} from "@/lib/queries/generations";
import { useProducts } from "@/lib/queries/products";
import { useUsers } from "@/lib/queries/users";
import { useVoices } from "@/lib/queries/voices";
import { useDrawerStore } from "@/lib/stores/drawerStore";
import type { Product, Tier } from "@/lib/types/product";
import type {
  ClipPhotoOverride,
  EnqueueRequest,
  StrategyValue,
} from "@/lib/types/generation";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIERS: { value: Tier; label: string; cost: string; tooltip: string }[] = [
  {
    value: "standard",
    label: "🟢 Standard",
    cost: "$0.27 / 15s",
    tooltip: "Seedance 1.5 Fast — volumen, validación, hooks",
  },
  {
    value: "advanced",
    label: "🟡 Advanced",
    cost: "$0.71 / 15s",
    tooltip: "Seedance 1.5 Pro — productos prometedores, A/B testing",
  },
  {
    value: "pro",
    label: "🔴 Pro",
    cost: "$1.08 / 15s",
    tooltip: "Seedance 2.0 Reference — productos ganadores, multi-shot",
  },
  {
    value: "veo3_prompt_only",
    label: "🟣 Veo 3",
    cost: "$0 (manual)",
    tooltip: "Solo prompt 8s — pegar en Gemini chat",
  },
  {
    value: "nano_banana_prompt_only",
    label: "🍌 Nano Banana",
    cost: "$0 (manual)",
    tooltip: "Solo prompt para fotos premium — pegar en Gemini chat con las fotos source",
  },
];

const DURATIONS = [5, 10, 12, 15, 20, 24, 25, 30];

const RESOLUTIONS_BY_TIER: Record<string, string[]> = {
  standard: ["720p"],
  advanced: ["480p", "720p"],
  pro: ["480p", "720p", "1080p-SR", "1440p-SR"],
  veo3_prompt_only: ["720p"],
  nano_banana_prompt_only: ["720p"],
};

const HOOK_CATEGORIES = [
  "curiosity",
  "problem_solution",
  "social_proof",
  "before_after",
  "shock",
  "tutorial",
];

// ---------------------------------------------------------------------------
// Wizard form
// ---------------------------------------------------------------------------

interface WizardForm {
  username: string;
  productId: string;
  tier: Tier;
  strategy: StrategyValue;
  durationSeconds: number;
  resolution: string;
  hookCategory: string;
  hookCustom: string;
  targetAudience: string;
  shoppable: boolean;
  voiceEnabled: boolean;
  voiceId: string;
  clipPhotoOverrides: ClipPhotoOverride[];
  nanoBananaAngles: number;
  fruitMode: boolean;
  fruitHint: string;
  narrativeAngle: string;
}

const PROMPT_ONLY_TIERS: Tier[] = ["veo3_prompt_only", "nano_banana_prompt_only"];

const STEPS = [
  "Usuario y producto",
  "Tier",
  "Estrategia",
  "Duración",
  "Fotos",
  "Hook",
  "Voz",
  "Resumen",
] as const;

export function GeneratorWizard() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<WizardForm>({
    username: "",
    productId: "",
    tier: "standard",
    strategy: "dynamic",
    durationSeconds: 15,
    resolution: "720p",
    hookCategory: "curiosity",
    hookCustom: "",
    targetAudience: "Generalista",
    shoppable: false,
    voiceEnabled: true,
    voiceId: "Spanish_EnergeticBoy",
    clipPhotoOverrides: [],
    nanoBananaAngles: 5,
    fruitMode: false,
    fruitHint: "",
    narrativeAngle: "",
  });
  const enqueue = useEnqueueGeneration();
  const previewVeo3 = usePreviewVeo3Prompt();
  const previewNanoBanana = usePreviewNanoBananaPrompt();
  const openQueue = useDrawerStore((s) => s.openQueue);

  const [promptModal, setPromptModal] = useState<
    | { kind: "veo3" | "nano_banana"; prompt: string; meta?: string }
    | null
  >(null);

  function patch<K extends keyof WizardForm>(key: K, value: WizardForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  const stepValid = useMemo(() => isStepValid(step, form), [step, form]);
  const lastStep = step === STEPS.length - 1;

  function next() {
    if (!stepValid) return;
    setStep((s) => Math.min(STEPS.length - 1, s + 1));
  }
  function prev() {
    setStep((s) => Math.max(0, s - 1));
  }

  async function submit() {
    // Veo3 / Nano Banana → endpoints síncronos, NO encolar. Mostramos el
    // prompt en modal copyable. El resto (Atlas Seedance) sí pasa por la cola.
    if (form.tier === "veo3_prompt_only") {
      try {
        const res = await previewVeo3.mutateAsync({
          username: form.username,
          product_id: form.productId,
          hook_category: form.hookCategory,
          hook_custom: form.hookCustom.trim() || null,
          target_audience: form.targetAudience.trim() || "Generalista",
          fruit_mode: form.fruitMode,
          fruit_hint: form.fruitMode ? form.fruitHint.trim() || null : null,
          narrative_angle: form.fruitMode ? form.narrativeAngle || null : null,
        });
        setPromptModal({
          kind: "veo3",
          prompt: res.prompt,
          meta: form.fruitMode
            ? `🍉 Personaje fruta · estilo: ${res.style}`
            : `Hook: "${res.hook_text}" · estilo: ${res.style}`,
        });
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Error generando prompt Veo 3.");
      }
      return;
    }
    if (form.tier === "nano_banana_prompt_only") {
      try {
        const res = await previewNanoBanana.mutateAsync({
          username: form.username,
          product_id: form.productId,
          n_angles: form.nanoBananaAngles,
        });
        setPromptModal({
          kind: "nano_banana",
          prompt: res.prompt,
          meta: `${res.n_angles} ángulos · pega en Gemini chat con las fotos source`,
        });
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Error generando prompt Nano Banana.");
      }
      return;
    }

    const payload: EnqueueRequest = buildPayload(form);
    try {
      const res = await enqueue.mutateAsync(payload);
      toast.success(
        `Encolado · job ${res.job_id.slice(0, 8)} · pos ${res.position_in_queue} · $${res.estimated_cost.toFixed(2)} estimado`,
      );
      openQueue();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Error al encolar.";
      toast.error(message);
    }
  }

  async function copyPromptToClipboard() {
    if (!promptModal) return;
    try {
      await navigator.clipboard.writeText(promptModal.prompt);
      toast.success("Prompt copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar — selecciónalo manualmente.");
    }
  }

  const isPromptOnly = PROMPT_ONLY_TIERS.includes(form.tier);
  const submitPending =
    enqueue.isPending || previewVeo3.isPending || previewNanoBanana.isPending;

  return (
    <div className="space-y-6">
      <Stepper current={step} steps={STEPS} />

      <Card>
        <CardContent className="space-y-4 p-6">
          {step === 0 && <StepUserProduct form={form} patch={patch} />}
          {step === 1 && <StepTier form={form} patch={patch} />}
          {step === 2 && <StepStrategy form={form} patch={patch} />}
          {step === 3 && <StepDuration form={form} patch={patch} />}
          {step === 4 && <StepPhotos form={form} patch={patch} />}
          {step === 5 && <StepHook form={form} patch={patch} />}
          {step === 6 && <StepVoice form={form} patch={patch} />}
          {step === 7 && <StepReview form={form} patch={patch} />}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="outline" onClick={prev} disabled={step === 0}>
          <ChevronLeft className="h-4 w-4" /> Anterior
        </Button>

        {!lastStep ? (
          <Button onClick={next} disabled={!stepValid}>
            Siguiente <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={submit} disabled={!stepValid || submitPending}>
            {submitPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isPromptOnly ? (
              <Sparkles className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            {isPromptOnly ? "Generar prompt" : "Encolar generación"}
          </Button>
        )}
      </div>

      {/* Modal con el prompt generado (Veo 3 / Nano Banana). No encola nada. */}
      <Dialog open={promptModal !== null} onOpenChange={(o) => !o && setPromptModal(null)}>
        <DialogContent className="w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {promptModal?.kind === "veo3"
                ? "🟣 Prompt Veo 3 listo"
                : "🍌 Prompt Nano Banana listo"}
            </DialogTitle>
            <DialogDescription>
              {promptModal?.kind === "veo3"
                ? "Pega este prompt en Gemini chat junto a las fotos del producto. 8s, single shot, 9:16."
                : "Pega este prompt en Gemini chat con las fotos source del producto. Sube las fotos generadas a 'Photos generated'."}
              {promptModal?.meta ? ` · ${promptModal.meta}` : ""}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            readOnly
            value={promptModal?.prompt ?? ""}
            className="min-h-[260px] font-mono text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setPromptModal(null)}>
              Cerrar
            </Button>
            <Button onClick={copyPromptToClipboard} disabled={!promptModal?.prompt}>
              <Copy className="h-4 w-4" />
              Copiar prompt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function isStepValid(step: number, form: WizardForm): boolean {
  switch (step) {
    case 0:
      return Boolean(form.username && form.productId);
    case 1:
      return TIERS.some((t) => t.value === form.tier);
    case 2:
      return form.strategy === "cinematic" || form.strategy === "dynamic";
    case 3:
      return DURATIONS.includes(form.durationSeconds) && form.resolution.length > 0;
    case 4:
      return true; // pasos 4 (fotos) opcional
    case 5:
      return form.hookCategory.length > 0 && form.targetAudience.length > 0;
    case 6:
      return !form.voiceEnabled || form.voiceId.length > 0;
    case 7:
      return true;
    default:
      return false;
  }
}

function buildPayload(form: WizardForm): EnqueueRequest {
  return {
    username: form.username,
    product_id: form.productId,
    tier: form.tier,
    duration_seconds: form.durationSeconds,
    resolution: form.resolution,
    strategy: form.strategy,
    voice_enabled: form.voiceEnabled,
    voice_id: form.voiceEnabled ? form.voiceId || null : null,
    hook_category: form.hookCategory,
    hook_custom: form.hookCustom.trim() || null,
    target_audience: form.targetAudience.trim() || "Generalista",
    shoppable: form.shoppable,
    ai_disclosure: true,
    clip_photo_overrides:
      form.clipPhotoOverrides.length > 0 ? form.clipPhotoOverrides : null,
  };
}

// ---------------------------------------------------------------------------
// Stepper
// ---------------------------------------------------------------------------

function Stepper({
  current,
  steps,
}: {
  current: number;
  steps: readonly string[];
}) {
  return (
    <ol className="flex flex-wrap items-center gap-1">
      {steps.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={label} className="flex items-center gap-1">
            <div
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                done && "bg-primary text-primary-foreground",
                active && "border-2 border-primary text-primary",
                !done && !active && "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className="h-4 w-4" /> : i + 1}
            </div>
            <span
              className={cn(
                "hidden text-xs sm:inline",
                active ? "font-semibold" : "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 hidden h-px w-4 bg-border md:inline-block" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

interface StepProps {
  form: WizardForm;
  patch: <K extends keyof WizardForm>(key: K, value: WizardForm[K]) => void;
}

function StepUserProduct({ form, patch }: StepProps) {
  const users = useUsers({ limit: 200 });
  const products = useProducts({ limit: 200 });

  const activeUsers = (users.data?.items ?? []).filter((u) => !u.deleted);
  const activeProducts = (products.data?.items ?? []).filter((p) => !p.deleted);

  const selectedUser = activeUsers.find((u) => u.username === form.username);
  const assignedSet = new Set(selectedUser?.assigned_products ?? []);
  const eligibleProducts = activeProducts.filter((p) => assignedSet.has(p.id));

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label>Cuenta TikTok</Label>
        <Select value={form.username} onValueChange={(v) => patch("username", v)}>
          <SelectTrigger>
            <SelectValue placeholder={users.isLoading ? "Cargando…" : "Selecciona cuenta"} />
          </SelectTrigger>
          <SelectContent>
            {activeUsers.map((u) => (
              <SelectItem key={u.id} value={u.username}>
                {u.username} · {u.niche}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>Producto (asignado al usuario)</Label>
        <Select
          value={form.productId}
          onValueChange={(v) => patch("productId", v)}
          disabled={!form.username}
        >
          <SelectTrigger className="h-auto py-1.5">
            <SelectValue
              placeholder={
                form.username
                  ? eligibleProducts.length === 0
                    ? "Sin productos asignados"
                    : "Selecciona producto"
                  : "Elige cuenta primero"
              }
            />
          </SelectTrigger>
          <SelectContent>
            {eligibleProducts.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                <ProductOption product={p} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function ProductOption({ product }: { product: Product }) {
  const cover = pickProductCoverUrl(product);
  return (
    <div className="flex items-center gap-2">
      {cover ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={cover}
          alt=""
          className="h-7 w-7 shrink-0 rounded object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-muted">
          <ImageIcon className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      )}
      <span className="truncate text-sm">{product.name}</span>
    </div>
  );
}

function pickProductCoverUrl(product: Product): string | null {
  const photo =
    product.photos.generated.find((p) => !p.deleted) ??
    product.photos.source.find((p) => !p.deleted);
  if (!photo?.filename) return null;
  const base =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
  const key = process.env.NEXT_PUBLIC_API_KEY;
  const qs = key ? `?api_key=${encodeURIComponent(key)}` : "";
  return `${base}/api/v1/products/${product.id}/photos/${encodeURIComponent(photo.filename)}/file${qs}`;
}

function StepTier({ form, patch }: StepProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {TIERS.map((t) => {
        const active = form.tier === t.value;
        return (
          <button
            key={t.value}
            type="button"
            onClick={() => {
              patch("tier", t.value);
              const allowed = RESOLUTIONS_BY_TIER[t.value] ?? ["720p"];
              if (!allowed.includes(form.resolution)) {
                patch("resolution", allowed[0]!);
              }
            }}
            className={cn(
              "rounded-md border p-4 text-left transition-colors",
              active ? "border-primary bg-primary/5" : "hover:bg-accent/50",
            )}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold">{t.label}</span>
              <Badge variant="outline">{t.cost}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t.tooltip}</p>
          </button>
        );
      })}
    </div>
  );
}

function StepStrategy({ form, patch }: StepProps) {
  const options: { value: StrategyValue; title: string; desc: string }[] = [
    {
      value: "dynamic",
      title: "⚡ Dinámico TikTok",
      desc: "Cambios de plano frecuentes, mejor retención.",
    },
    {
      value: "cinematic",
      title: "🎬 Cinematográfico",
      desc: "Pocos cambios de plano, calidad pulida.",
    },
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {options.map((o) => {
        const active = form.strategy === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => patch("strategy", o.value)}
            className={cn(
              "rounded-md border p-4 text-left transition-colors",
              active ? "border-primary bg-primary/5" : "hover:bg-accent/50",
            )}
          >
            <p className="font-semibold">{o.title}</p>
            <p className="mt-1 text-xs text-muted-foreground">{o.desc}</p>
          </button>
        );
      })}
    </div>
  );
}

function StepDuration({ form, patch }: StepProps) {
  const allowed = RESOLUTIONS_BY_TIER[form.tier] ?? ["720p"];
  const clipsApprox = Math.ceil(form.durationSeconds / 5);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label>Duración (s)</Label>
        <Select
          value={String(form.durationSeconds)}
          onValueChange={(v) => patch("durationSeconds", Number(v))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DURATIONS.map((d) => (
              <SelectItem key={d} value={String(d)}>
                {d}s
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>Resolución</Label>
        <Select value={form.resolution} onValueChange={(v) => patch("resolution", v)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allowed.map((r) => (
              <SelectItem key={r} value={r}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="md:col-span-2 rounded-md border bg-card/50 p-3 text-sm text-muted-foreground">
        ~{clipsApprox} clip(s) de 5s. La estrategia <strong>{form.strategy}</strong>{" "}
        define cómo se asignan fotos a clips.
      </div>
    </div>
  );
}

function StepPhotos({ form }: StepProps) {
  // Simplificado: en este wizard la asignación manual de fotos por clip
  // se deja para una iteración futura. Si el usuario no pone overrides,
  // el director auto-asigna.
  return (
    <div className="space-y-2 text-sm">
      <p>
        Asignación manual de fotos por clip — <strong>opcional</strong>.
      </p>
      <p className="text-muted-foreground">
        Por defecto, el director auto-asigna fotos basándose en el `type` y la
        estrategia. Si quieres control total clip-a-clip, lo añadiremos en una
        iteración futura.
      </p>
      <Badge variant="outline">
        {form.clipPhotoOverrides.length === 0
          ? "Auto-asignación activada"
          : `${form.clipPhotoOverrides.length} overrides definidos`}
      </Badge>
    </div>
  );
}

function StepHook({ form, patch }: StepProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label>Categoría de hook</Label>
        <Select
          value={form.hookCategory}
          onValueChange={(v) => patch("hookCategory", v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOOK_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label>Audiencia objetivo</Label>
        <Input
          value={form.targetAudience}
          onChange={(e) => patch("targetAudience", e.target.value)}
          placeholder="Gymbros, skincare girlies, etc."
        />
      </div>
      <div className="md:col-span-2 space-y-2">
        <Label>Hook custom (opcional)</Label>
        <Textarea
          rows={2}
          value={form.hookCustom}
          onChange={(e) => patch("hookCustom", e.target.value)}
          placeholder="¿Sabías que…? (sobreescribe el de la categoría)"
        />
      </div>
      <div className="md:col-span-2 flex items-center gap-2">
        <Switch
          id="shoppable"
          checked={form.shoppable}
          onCheckedChange={(v) => patch("shoppable", v)}
        />
        <Label htmlFor="shoppable" className="text-sm">
          Vídeo shoppable (cuenta para Pilot Program)
        </Label>
      </div>
    </div>
  );
}

function StepVoice({ form, patch }: StepProps) {
  const voices = useVoices({ language: "es" });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Switch
          id="voice-enabled"
          checked={form.voiceEnabled}
          onCheckedChange={(v) => patch("voiceEnabled", v)}
        />
        <Label htmlFor="voice-enabled" className="text-sm">
          Generar voz con MiniMax
        </Label>
      </div>
      {form.voiceEnabled && (
        <div className="space-y-2">
          <Label>Voz</Label>
          <Select value={form.voiceId} onValueChange={(v) => patch("voiceId", v)}>
            <SelectTrigger>
              <SelectValue placeholder={voices.isLoading ? "Cargando…" : "Selecciona voz"} />
            </SelectTrigger>
            <SelectContent>
              {(voices.data?.items ?? []).map((v) => (
                <SelectItem key={v.id} value={v.minimax_voice_id}>
                  {v.is_preset ? "🎚️" : "🎤"} {v.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}

function StepReview({ form, patch }: StepProps) {
  const cost = estimateCost(form);
  const isPromptOnly = PROMPT_ONLY_TIERS.includes(form.tier);
  return (
    <div className="space-y-3">
      <Row label="Cuenta" value={form.username} />
      <Row label="Producto" value={form.productId} mono />
      <Row label="Tier" value={form.tier} />
      {!isPromptOnly && (
        <>
          <Row label="Estrategia" value={form.strategy} />
          <Row
            label="Duración × Resolución"
            value={`${form.durationSeconds}s · ${form.resolution}`}
          />
        </>
      )}
      {form.tier !== "nano_banana_prompt_only" && (
        <Row label="Hook" value={form.hookCustom || form.hookCategory} />
      )}
      <Row label="Audiencia" value={form.targetAudience} />
      {!isPromptOnly && (
        <>
          <Row label="Voz" value={form.voiceEnabled ? form.voiceId : "(sin voz)"} />
          <Row label="Shoppable" value={form.shoppable ? "Sí" : "No"} />
        </>
      )}

      {form.tier === "nano_banana_prompt_only" && (
        <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
          <Label className="text-xs">Número de ángulos a pedir</Label>
          <Select
            value={String(form.nanoBananaAngles)}
            onValueChange={(v) => patch("nanoBananaAngles", Number(v))}
          >
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[4, 5, 6, 7, 8].map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n} ángulos
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {form.tier === "veo3_prompt_only" && (
        <div className="space-y-3 rounded-md border border-orange-500/40 bg-orange-500/5 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <Label className="text-xs font-semibold">🍉 Personaje de fruta</Label>
              <p className="text-[10px] text-muted-foreground">
                Mini-historia viral: cabezas de fruta + drama/chisme + CTA al carrito.
              </p>
            </div>
            <Switch
              checked={form.fruitMode}
              onCheckedChange={(v) => patch("fruitMode", v)}
            />
          </div>
          {form.fruitMode && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-[10px]">Enfoque</Label>
                <Select
                  value={form.narrativeAngle || "auto"}
                  onValueChange={(v) =>
                    patch("narrativeAngle", v === "auto" ? "" : v)
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">🤖 Que elija la IA</SelectItem>
                    <SelectItem value="dramatico">🎭 Dramático</SelectItem>
                    <SelectItem value="chismoso">👀 Chismoso</SelectItem>
                    <SelectItem value="comico-burla">😂 Cómico / burla</SelectItem>
                    <SelectItem value="aspiracional">✨ Aspiracional</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-[10px]">Fruta (opcional)</Label>
                <Input
                  value={form.fruitHint}
                  onChange={(e) => patch("fruitHint", e.target.value)}
                  placeholder="vacío = la elige la IA"
                  className="h-9 text-xs"
                />
              </div>
            </div>
          )}
        </div>
      )}

      {isPromptOnly ? (
        <div className="mt-3 rounded-md border border-purple-500/40 bg-purple-500/5 p-3">
          <p className="text-xs text-muted-foreground">Resultado</p>
          <p className="text-sm font-medium">
            Prompt generado al instante (no encola) — lo copias y pegas en Gemini chat.
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Coste Gemini: ~$0.004 Veo3 · ~$0.002 Nano Banana (modelo 2.5 Flash)
          </p>
        </div>
      ) : (
        <div className="mt-3 rounded-md border bg-primary/5 p-3">
          <p className="text-xs text-muted-foreground">Coste estimado</p>
          <p className="text-2xl font-semibold">${cost.toFixed(3)}</p>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b pb-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("text-sm font-medium", mono && "font-mono")}>{value}</span>
    </div>
  );
}

// Estimación local (espejo de cost_calculator.py para feedback inmediato).
function estimateCost(form: WizardForm): number {
  const ratePerSec: Record<Tier, number> = {
    standard: 0.018,
    advanced: 0.047,
    pro: 0.072,
    veo3_prompt_only: 0,
    nano_banana_prompt_only: 0,
  };
  const resMultiplier: Record<string, number> = {
    "480p": 0.7,
    "720p": 1.0,
    "1080p-SR": 1.5,
    "1440p-SR": 2.0,
  };
  const video = (ratePerSec[form.tier] ?? 0) * form.durationSeconds * (resMultiplier[form.resolution] ?? 1);
  const voice = form.voiceEnabled ? form.durationSeconds * 18 * 0.00006 : 0;
  return Math.round((video + voice) * 10000) / 10000;
}
