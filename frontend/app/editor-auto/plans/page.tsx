"use client";

import {
  Check,
  Clock,
  CreditCard,
  Crown,
  HeadphonesIcon,
  Loader2,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Trophy,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapsibleCard } from "@/components/ui/collapsible-card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateEditorPlan,
  useDeleteEditorPlan,
  useEditorAutoTools,
  useEditorPlans,
  useUpdateEditorPlan,
} from "@/lib/queries/editor-auto";
import type { Plan, PlanUpdateInput } from "@/lib/types/editor-auto";

export default function EditorAutoPlansPage() {
  const plans = useEditorPlans();
  const tools = useEditorAutoTools();
  const createPlan = useCreateEditorPlan();
  const deletePlan = useDeleteEditorPlan();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">
            Planes — Editor Auto
          </h1>
          <p className="text-sm text-muted-foreground">
            Configura los planes que se asignarán a los usuarios. Cada plan
            define cuota diaria, ventana horaria y tools permitidas. Los
            usuarios <strong>sin plan</strong> son tratados como modo prueba
            (sin límites — útil para QA o demos).
          </p>
        </div>
        <Button onClick={() => setCreatingNew(true)} disabled={creatingNew}>
          <Plus className="mr-2 h-4 w-4" /> Crear plan
        </Button>
      </header>

      {creatingNew && (
        <PlanForm
          initial={null}
          tools={(tools.data ?? []).map((t) => ({
            id: t.tool_id,
            label: t.display_name,
          }))}
          onCancel={() => setCreatingNew(false)}
          onSave={async (data) => {
            await createPlan.mutateAsync({
              slug: data.slug,
              name: data.name,
              description: data.description,
              daily_video_limit: data.daily_video_limit,
              monthly_video_limit: data.monthly_video_limit,
              allowed_tools: data.allowed_tools,
              processing_window_start_hour: data.processing_window_start_hour,
              processing_window_end_hour: data.processing_window_end_hour,
              spacing_minutes: data.spacing_minutes,
              queue_priority: data.queue_priority,
              queue_delay_minutes: data.queue_delay_minutes,
              support_level: data.support_level,
              features: data.features,
              price_eur_monthly: data.price_eur_monthly,
              price_eur_setup_once: data.price_eur_setup_once,
              is_active: data.is_active,
              is_promo: data.is_promo,
              promo_slots_total: data.promo_slots_total,
              sort_order: data.sort_order,
            });
            toast.success(`Plan '${data.slug}' creado`);
            setCreatingNew(false);
          }}
          submitting={createPlan.isPending}
        />
      )}

      {plans.isLoading && (
        <div className="flex h-32 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(plans.data ?? []).map((plan) =>
          editingId === plan.id ? (
            <div key={plan.id} className="sm:col-span-2 lg:col-span-3">
              <PlanForm
                initial={plan}
                tools={(tools.data ?? []).map((t) => ({
                  id: t.tool_id,
                  label: t.display_name,
                }))}
                onCancel={() => setEditingId(null)}
                onSave={() => setEditingId(null)}
              />
            </div>
          ) : (
            <PlanCard
              key={plan.id}
              plan={plan}
              onEdit={() => setEditingId(plan.id)}
              onDelete={() => {
                if (
                  confirm(
                    `¿Eliminar plan '${plan.name}'? Los users asignados quedarán sin plan (modo prueba).`,
                  )
                ) {
                  deletePlan.mutateAsync(plan.id).then(() =>
                    toast.success(`Plan '${plan.slug}' eliminado`),
                  );
                }
              }}
            />
          ),
        )}
      </div>

      {!plans.isLoading && (plans.data ?? []).length === 0 && !creatingNew && (
        <Card>
          <CardContent className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            Aún no hay planes. Crea el primero.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ===========================================================================
// PlanCard — visualización compacta de un plan
// ===========================================================================
const SUPPORT_LABEL: Record<string, { label: string; cls: string }> = {
  email: { label: "Email 24-48 h", cls: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
  telegram: { label: "Telegram <8 h", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300" },
  telegram_vip: {
    label: "Telegram VIP <2 h",
    cls: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  },
  dedicado: {
    label: "Dedicado <30 min",
    cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  dedicado_24_7: {
    label: "Dedicado 24/7",
    cls: "bg-amber-500/20 text-amber-700 dark:text-amber-300",
  },
};

function priorityLabel(p: number): { label: string; cls: string; icon: typeof Trophy } {
  if (p >= 500) return { label: "Máxima", cls: "bg-amber-500/20 text-amber-700 dark:text-amber-300", icon: Crown };
  if (p >= 200) return { label: "Top", cls: "bg-purple-500/15 text-purple-700 dark:text-purple-300", icon: Trophy };
  if (p >= 100) return { label: "Alta", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300", icon: Zap };
  if (p >= 50) return { label: "Normal", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300", icon: Zap };
  return { label: "Baja", cls: "bg-slate-500/15 text-slate-700 dark:text-slate-300", icon: Zap };
}

function PlanCard({
  plan,
  onEdit,
  onDelete,
}: {
  plan: Plan;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const remainingSlots =
    plan.is_promo && plan.promo_slots_total != null
      ? plan.promo_slots_total - plan.promo_slots_used
      : null;
  const support =
    SUPPORT_LABEL[plan.support_level] ??
    SUPPORT_LABEL.email ?? { label: "Email", cls: "bg-slate-500/15" };
  const prio = priorityLabel(plan.queue_priority);
  const PrioIcon = prio.icon;
  const isTop = plan.queue_priority >= 200;
  return (
    <Card
      className={
        isTop
          ? "border-amber-400/60 bg-gradient-to-br from-amber-50/40 to-transparent dark:from-amber-950/15"
          : plan.is_promo
            ? "border-amber-400/60 bg-amber-50/30 dark:bg-amber-950/10"
            : ""
      }
    >
      <CardHeader className="pb-3">
        <CardTitle className="flex items-start gap-2 text-base">
          <CreditCard className="mt-0.5 h-4 w-4 text-emerald-500" />
          <span className="flex-1 truncate">{plan.name}</span>
          {plan.is_promo && (
            <Badge className="bg-amber-500 text-black hover:bg-amber-500">
              <Sparkles className="mr-1 h-2.5 w-2.5" />
              promo
            </Badge>
          )}
        </CardTitle>
        <div className="flex items-baseline gap-1 pt-1">
          <span className="text-3xl font-bold">
            {plan.price_eur_monthly.toFixed(0)}
          </span>
          <span className="text-sm text-muted-foreground">€/mes</span>
          {plan.price_eur_setup_once > 0 && (
            <span className="ml-2 text-xs text-muted-foreground">
              + {plan.price_eur_setup_once.toFixed(0)}€ setup
            </span>
          )}
          {!plan.is_active && (
            <Badge variant="outline" className="ml-auto text-xs">
              inactivo
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5 pt-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${prio.cls}`}
          >
            <PrioIcon className="h-2.5 w-2.5" />
            Prioridad {prio.label}
          </span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${support.cls}`}
          >
            <HeadphonesIcon className="h-2.5 w-2.5" />
            {support.label}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <p className="text-muted-foreground line-clamp-3">{plan.description}</p>

        {/* Features list (visual, lo que diferencia el plan) */}
        {plan.features.length > 0 && (
          <ul className="space-y-1.5">
            {plan.features.map((f, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                <span className="break-words text-foreground/90">{f}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Resumen técnico (números crudos para el admin) */}
        <details className="rounded-md border border-muted-foreground/15 px-2 py-1.5">
          <summary className="cursor-pointer select-none text-[11px] text-muted-foreground">
            Detalles técnicos
          </summary>
          <ul className="mt-1.5 space-y-1 text-[11px]">
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Vídeos/día</span>
              <strong>
                {plan.daily_video_limit === 0 ? "∞" : plan.daily_video_limit}
              </strong>
            </li>
            {plan.monthly_video_limit != null && (
              <li className="flex items-center justify-between">
                <span className="text-muted-foreground">Vídeos/mes</span>
                <strong>{plan.monthly_video_limit}</strong>
              </li>
            )}
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Ventana</span>
              <strong className="font-mono">
                {plan.processing_window_start_hour}:00–
                {plan.processing_window_end_hour}:00
              </strong>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Espaciado</span>
              <strong>
                {plan.spacing_minutes === 0
                  ? "sin"
                  : `${plan.spacing_minutes} min`}
              </strong>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Delay cola</span>
              <strong>
                {plan.queue_delay_minutes === 0
                  ? "sin"
                  : `${plan.queue_delay_minutes} min`}
              </strong>
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Prioridad cola</span>
              <strong>{plan.queue_priority}</strong>
            </li>
            <li className="flex items-start justify-between gap-2">
              <span className="text-muted-foreground">Tools</span>
              <span className="text-right">
                {plan.allowed_tools.length > 0
                  ? plan.allowed_tools.join(", ")
                  : "todas"}
              </span>
            </li>
          </ul>
        </details>

        {remainingSlots !== null && (
          <div className="flex items-center justify-between rounded-md bg-amber-500/10 px-2 py-1 text-[11px]">
            <span className="text-amber-700 dark:text-amber-300">
              Slots promo restantes
            </span>
            <strong className="text-amber-700 dark:text-amber-300">
              {remainingSlots}/{plan.promo_slots_total}
            </strong>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={onEdit}
          >
            <Pencil className="mr-1.5 h-3 w-3" />
            Editar
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDelete}
            aria-label="Eliminar"
          >
            <Trash2 className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ===========================================================================
// PlanForm — crear o editar plan
// ===========================================================================
interface PlanFormData {
  slug: string;
  name: string;
  description: string;
  daily_video_limit: number;
  monthly_video_limit: number | null;
  allowed_tools: string[];
  processing_window_start_hour: number;
  processing_window_end_hour: number;
  spacing_minutes: number;
  queue_priority: number;
  queue_delay_minutes: number;
  support_level: string;
  features: string[];
  price_eur_monthly: number;
  price_eur_setup_once: number;
  is_active: boolean;
  is_promo: boolean;
  promo_slots_total: number | null;
  sort_order: number;
}

function PlanForm({
  initial,
  tools,
  onCancel,
  onSave,
  submitting,
}: {
  initial: Plan | null;
  tools: { id: string; label: string }[];
  onCancel: () => void;
  onSave: (data: PlanFormData) => void;
  submitting?: boolean;
}) {
  const [form, setForm] = useState<PlanFormData>(() => ({
    slug: initial?.slug ?? "",
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    daily_video_limit: initial?.daily_video_limit ?? 3,
    monthly_video_limit: initial?.monthly_video_limit ?? null,
    allowed_tools: initial?.allowed_tools ?? [],
    processing_window_start_hour: initial?.processing_window_start_hour ?? 9,
    processing_window_end_hour: initial?.processing_window_end_hour ?? 19,
    spacing_minutes: initial?.spacing_minutes ?? 0,
    queue_priority: initial?.queue_priority ?? 50,
    queue_delay_minutes: initial?.queue_delay_minutes ?? 0,
    support_level: initial?.support_level ?? "email",
    features: initial?.features ?? [],
    price_eur_monthly: initial?.price_eur_monthly ?? 149,
    price_eur_setup_once: initial?.price_eur_setup_once ?? 0,
    is_active: initial?.is_active ?? true,
    is_promo: initial?.is_promo ?? false,
    promo_slots_total: initial?.promo_slots_total ?? null,
    sort_order: initial?.sort_order ?? 100,
  }));

  const updateMutation = useUpdateEditorPlan(initial?.id ?? "");

  useEffect(() => {
    // Reset si cambia el plan editado
    if (initial) {
      setForm({
        slug: initial.slug,
        name: initial.name,
        description: initial.description,
        daily_video_limit: initial.daily_video_limit,
        monthly_video_limit: initial.monthly_video_limit,
        allowed_tools: initial.allowed_tools,
        processing_window_start_hour: initial.processing_window_start_hour,
        processing_window_end_hour: initial.processing_window_end_hour,
        spacing_minutes: initial.spacing_minutes,
        queue_priority: initial.queue_priority,
        queue_delay_minutes: initial.queue_delay_minutes,
        support_level: initial.support_level,
        features: initial.features,
        price_eur_monthly: initial.price_eur_monthly,
        price_eur_setup_once: initial.price_eur_setup_once,
        is_active: initial.is_active,
        is_promo: initial.is_promo,
        promo_slots_total: initial.promo_slots_total,
        sort_order: initial.sort_order,
      });
    }
  }, [initial?.id]);

  const handleSubmit = async () => {
    if (initial) {
      const patch: PlanUpdateInput = {
        name: form.name,
        description: form.description,
        daily_video_limit: form.daily_video_limit,
        monthly_video_limit: form.monthly_video_limit,
        allowed_tools: form.allowed_tools,
        processing_window_start_hour: form.processing_window_start_hour,
        processing_window_end_hour: form.processing_window_end_hour,
        spacing_minutes: form.spacing_minutes,
        queue_priority: form.queue_priority,
        queue_delay_minutes: form.queue_delay_minutes,
        support_level: form.support_level,
        features: form.features,
        price_eur_monthly: form.price_eur_monthly,
        price_eur_setup_once: form.price_eur_setup_once,
        is_active: form.is_active,
        is_promo: form.is_promo,
        promo_slots_total: form.promo_slots_total,
        sort_order: form.sort_order,
      };
      await updateMutation.mutateAsync(patch);
      toast.success(`Plan '${form.slug}' actualizado`);
      onSave(form);
    } else {
      onSave(form);
    }
  };

  const toggleTool = (tid: string) => {
    setForm((f) => ({
      ...f,
      allowed_tools: f.allowed_tools.includes(tid)
        ? f.allowed_tools.filter((t) => t !== tid)
        : [...f.allowed_tools, tid],
    }));
  };

  return (
    <Card className="border-emerald-500/40">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-base">
          {initial ? `Editar plan '${initial.slug}'` : "Crear plan nuevo"}
        </CardTitle>
        <Button variant="ghost" size="icon" onClick={onCancel}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="p-slug">Slug</Label>
          <Input
            id="p-slug"
            value={form.slug}
            onChange={(e) =>
              setForm((f) => ({ ...f, slug: e.target.value.toLowerCase() }))
            }
            disabled={!!initial}
            placeholder="starter"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-name">Nombre visible</Label>
          <Input
            id="p-name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Starter · 3 vídeos/día"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="p-desc">Descripción</Label>
          <Textarea
            id="p-desc"
            value={form.description}
            onChange={(e) =>
              setForm((f) => ({ ...f, description: e.target.value }))
            }
            rows={2}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-daily">Vídeos/día (0 = ∞)</Label>
          <Input
            id="p-daily"
            type="number"
            min={0}
            value={form.daily_video_limit}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                daily_video_limit: parseInt(e.target.value || "0", 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-monthly">Vídeos/mes (vacío = ∞)</Label>
          <Input
            id="p-monthly"
            type="number"
            min={0}
            value={form.monthly_video_limit ?? ""}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                monthly_video_limit:
                  e.target.value === "" ? null : parseInt(e.target.value, 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-start">
            <Clock className="mr-1 inline h-3 w-3" /> Ventana inicio (UTC, 0-23)
          </Label>
          <Input
            id="p-start"
            type="number"
            min={0}
            max={23}
            value={form.processing_window_start_hour}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                processing_window_start_hour: parseInt(e.target.value, 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-end">Ventana fin</Label>
          <Input
            id="p-end"
            type="number"
            min={0}
            max={23}
            value={form.processing_window_end_hour}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                processing_window_end_hour: parseInt(e.target.value, 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-spacing">
            Espaciado entre vídeos (min)
            <span
              className="ml-1 text-[10px] text-muted-foreground"
              title="Tiempo entre 2 encolados del mismo user. NO es tiempo de edición."
            >
              ⓘ
            </span>
          </Label>
          <Input
            id="p-spacing"
            type="number"
            min={0}
            value={form.spacing_minutes}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                spacing_minutes: parseInt(e.target.value || "0", 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-prio">
            Prioridad en cola
            <span
              className="ml-1 text-[10px] text-muted-foreground"
              title="Mayor = se procesa antes que planes con prioridad menor. Sugerido: Trial 0, Starter 10, Pro 50, Studio 100, Agencia 200, Enterprise 500."
            >
              ⓘ
            </span>
          </Label>
          <Input
            id="p-prio"
            type="number"
            min={0}
            value={form.queue_priority}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                queue_priority: parseInt(e.target.value || "0", 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-delay">
            Delay artificial cola (min)
            <span
              className="ml-1 text-[10px] text-muted-foreground"
              title="Tiempo mínimo entre encolar y empezar a procesar. Sirve para 'ralentizar' planes baratos."
            >
              ⓘ
            </span>
          </Label>
          <Input
            id="p-delay"
            type="number"
            min={0}
            value={form.queue_delay_minutes}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                queue_delay_minutes: parseInt(e.target.value || "0", 10),
              }))
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-support">Nivel de soporte</Label>
          <select
            id="p-support"
            value={form.support_level}
            onChange={(e) =>
              setForm((f) => ({ ...f, support_level: e.target.value }))
            }
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="email">Email 24-48 h</option>
            <option value="telegram">Telegram &lt;8 h</option>
            <option value="telegram_vip">Telegram VIP &lt;2 h</option>
            <option value="dedicado">Dedicado &lt;30 min</option>
            <option value="dedicado_24_7">Dedicado 24/7</option>
          </select>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label>
            Features (1 por línea — bullets visibles en la tarjeta)
            <span
              className="ml-1 text-[10px] text-muted-foreground"
              title="Frases cortas que el cliente verá. Usa emojis para que sea visual."
            >
              ⓘ
            </span>
          </Label>
          <Textarea
            value={form.features.join("\n")}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                features: e.target.value
                  .split("\n")
                  .map((s) => s.trim())
                  .filter(Boolean),
              }))
            }
            rows={Math.max(4, form.features.length + 1)}
            placeholder={
              "🎬 5 vídeos/día (≈150/mes)\n💬 Soporte Telegram <8 h\n⚡ Prioridad normal en cola"
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="p-price">Precio €/mes</Label>
          <Input
            id="p-price"
            type="number"
            min={0}
            step={1}
            value={form.price_eur_monthly}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                price_eur_monthly: parseFloat(e.target.value || "0"),
              }))
            }
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label>Tools permitidas (vacío = todas)</Label>
          <div className="flex flex-wrap gap-2">
            {tools.map((t) => {
              const on = form.allowed_tools.includes(t.id);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleTool(t.id)}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                    on
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : "border-muted hover:bg-accent/30"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Switch
            id="p-active"
            checked={form.is_active}
            onCheckedChange={(c) => setForm((f) => ({ ...f, is_active: c }))}
          />
          <Label htmlFor="p-active">Activo (asignable)</Label>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Switch
            id="p-promo"
            checked={form.is_promo}
            onCheckedChange={(c) => setForm((f) => ({ ...f, is_promo: c }))}
          />
          <Label htmlFor="p-promo">Es promoción (slots limitados)</Label>
        </div>
        {form.is_promo && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="p-promoslots">Slots totales (vacío = sin tope)</Label>
            <Input
              id="p-promoslots"
              type="number"
              min={0}
              value={form.promo_slots_total ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  promo_slots_total:
                    e.target.value === "" ? null : parseInt(e.target.value, 10),
                }))
              }
            />
          </div>
        )}
        <div className="flex gap-2 pt-3 sm:col-span-2">
          <Button
            className="flex-1"
            onClick={handleSubmit}
            disabled={
              !form.slug.trim() ||
              !form.name.trim() ||
              submitting ||
              updateMutation.isPending
            }
          >
            {submitting || updateMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Guardar
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
