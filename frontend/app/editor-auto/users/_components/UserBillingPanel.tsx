"use client";

import {
  Copy,
  CreditCard,
  Gift,
  Loader2,
  Percent,
  Sparkles,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useAssignSubscription,
  useClearSubscription,
  useEditorPlans,
  useEditorUser,
  useGenerateReferralForUser,
} from "@/lib/queries/editor-auto";

/**
 * Panel de billing que vive dentro de la página de Usuarios cuando hay
 * uno seleccionado. Muestra:
 *
 *  - Plan asignado o "modo prueba" si no tiene
 *  - Cuota usada hoy / mes
 *  - Referral code propio + estadísticas
 *  - Code que usó al registrarse (read-only)
 *
 * Permite:
 *  - Asignar otro plan / quitar plan (volver a modo prueba)
 *  - Generar referral code propio
 *  - Editar notas internas
 */
export function UserBillingPanel({ userId }: { userId: string }) {
  const userQ = useEditorUser(userId);
  const plansQ = useEditorPlans();
  const assign = useAssignSubscription(userId);
  const clear = useClearSubscription(userId);
  const genRef = useGenerateReferralForUser();

  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  if (userQ.isLoading || !userQ.data) {
    return (
      <Card>
        <CardContent className="flex h-32 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }
  const user = userQ.data;
  const sub = user.subscription;
  const usage = user.usage;

  const dailyPct =
    usage?.daily_limit && usage.daily_limit > 0
      ? Math.min(100, (usage.daily_videos_used / usage.daily_limit) * 100)
      : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CreditCard className="h-4 w-4 text-emerald-500" />
          Billing &amp; cuota
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Plan activo */}
        {sub ? (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-emerald-500 text-black hover:bg-emerald-500">
                {sub.status}
              </Badge>
              <strong className="text-sm">{sub.plan_name}</strong>
              <code className="rounded bg-muted px-1.5 py-0.5 text-[10px]">
                {sub.plan_slug}
              </code>
              {sub.discount_pct_next_period > 0 && (
                <Badge className="ml-auto bg-pink-500 text-white">
                  <Percent className="mr-1 h-3 w-3" />
                  {(sub.discount_pct_next_period * 100).toFixed(0)}% próx mes
                </Badge>
              )}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Desde {new Date(sub.started_at).toLocaleDateString()}
              {sub.notes && (
                <span>
                  {" · "}
                  <em>{sub.notes}</em>
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-3 text-xs">
            <strong className="text-amber-700 dark:text-amber-300">
              Modo prueba activo
            </strong>{" "}
            — el usuario no tiene plan asignado. Sin cuotas ni ventana horaria.
            Asígnale un plan abajo si es cliente real.
          </div>
        )}

        {/* Cuota / Uso */}
        {usage && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Hoy</span>
              <span className="font-mono">
                {usage.daily_videos_used} /{" "}
                {usage.daily_limit === null
                  ? "∞ (prueba)"
                  : usage.daily_limit === 0
                  ? "∞"
                  : usage.daily_limit}
              </span>
            </div>
            {usage.daily_limit && usage.daily_limit > 0 && (
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full transition-all ${
                    dailyPct > 80
                      ? "bg-rose-500"
                      : dailyPct > 50
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  }`}
                  style={{ width: `${dailyPct}%` }}
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-2 pt-1 text-xs text-muted-foreground">
              <div>
                Mes ({usage.month_period}):{" "}
                <strong>{usage.monthly_videos_used}</strong>
              </div>
              <div>
                Total histórico: <strong>{usage.total_videos_ever}</strong>
              </div>
            </div>
          </div>
        )}

        {/* Asignar/cambiar plan */}
        <div className="space-y-2 rounded-md border bg-card/40 p-3">
          <Label className="text-xs">Asignar / cambiar plan</Label>
          <select
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            value={selectedPlanId}
            onChange={(e) => setSelectedPlanId(e.target.value)}
          >
            <option value="">— selecciona plan —</option>
            {(plansQ.data ?? [])
              .filter((p) => p.is_active)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.price_eur_monthly}€/mes
                  {p.is_promo &&
                    p.promo_slots_total != null &&
                    ` (${p.promo_slots_total - p.promo_slots_used} slots)`}
                </option>
              ))}
          </select>
          <Textarea
            placeholder="Notas internas (ej. pagó por PayPal 14/05, descuento especial...)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="text-xs"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={!selectedPlanId || assign.isPending}
              onClick={() =>
                assign
                  .mutateAsync({
                    plan_id: selectedPlanId,
                    status: "active",
                    notes,
                  })
                  .then(() => {
                    toast.success("Plan asignado");
                    setSelectedPlanId("");
                    setNotes("");
                  })
                  .catch((e) => toast.error((e as Error).message))
              }
            >
              {assign.isPending ? (
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              ) : (
                <CreditCard className="mr-1.5 h-3 w-3" />
              )}
              Asignar
            </Button>
            {sub && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (
                    confirm(
                      "¿Quitar plan? El usuario quedará en modo prueba (sin cuotas).",
                    )
                  ) {
                    clear
                      .mutateAsync()
                      .then(() => toast.success("Plan eliminado — modo prueba"))
                      .catch((e) => toast.error((e as Error).message));
                  }
                }}
                disabled={clear.isPending}
              >
                <XCircle className="mr-1.5 h-3 w-3" />
                Quitar plan (modo prueba)
              </Button>
            )}
          </div>
        </div>

        {/* Referral propio */}
        <div className="space-y-2 rounded-md border bg-card/40 p-3">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Code de referido propio</Label>
            {user.referrals_count > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                {user.referrals_count} usos
              </Badge>
            )}
          </div>
          {user.referral_code ? (
            <div className="flex items-center gap-2">
              <Input
                value={user.referral_code}
                readOnly
                className="font-mono text-sm"
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  navigator.clipboard.writeText(user.referral_code!);
                  toast.success("Code copiado");
                }}
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                genRef
                  .mutateAsync(userId)
                  .then((r) => toast.success(`Code generado: ${r.code}`))
                  .catch((e) => toast.error((e as Error).message))
              }
              disabled={genRef.isPending}
            >
              {genRef.isPending ? (
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-3 w-3" />
              )}
              Generar code
            </Button>
          )}
          {user.referred_by_code && (
            <p className="text-xs text-muted-foreground">
              <Gift className="mr-1 inline h-3 w-3" />
              Se registró usando: <code>{user.referred_by_code}</code>
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
