"use client";

import { Ban, Globe, Link2, Loader2, ShieldCheck, Unlink } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useEditorUser,
  useUpdateEditorUser,
  useUpdateWebAccount,
} from "@/lib/queries/editor-auto";
import type { WebAccountRole } from "@/lib/types/editor-auto";

// Roles de la web (nebulabs-media). Cada uno desbloquea más menús al cliente.
const ROLES: { value: WebAccountRole; label: string }[] = [
  { value: "standard", label: "Estándar" },
  { value: "plus", label: "Plus" },
  { value: "pro", label: "Pro" },
  { value: "admin", label: "Admin" },
];

// Planes/tarifas de la web (ids de nebulabs-media/lib/pricing.ts). null = trial.
const WEB_PLANS: { value: string; label: string }[] = [
  { value: "", label: "Solo prueba (trial)" },
  { value: "starter", label: "Starter — 3 vídeos/día" },
  { value: "pro", label: "Pro — 5 vídeos/día" },
  { value: "studio", label: "Studio — 10 vídeos/día" },
  { value: "agencia", label: "Agencia — 15 vídeos/día" },
];

/**
 * Puente con la web de cliente (nebulabs-media). Vincula este usuario de
 * configuración a una cuenta web por EMAIL y permite al admin gestionar el
 * rol/plan/ban de esa cuenta sin entrar en la web. Los datos viven en Redis
 * con prefijo `nebulabs:` — los escribe la web al hacer login con Google.
 */
export function UserWebAccountPanel({ userId }: { userId: string }) {
  const userQ = useEditorUser(userId);
  const updateUser = useUpdateEditorUser(userId);
  const { setRole, setPlan, setBan } = useUpdateWebAccount();
  const [emailInput, setEmailInput] = useState("");

  if (userQ.isLoading || !userQ.data) {
    return (
      <Card>
        <CardContent className="flex h-24 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }
  const user = userQ.data;
  const acc = user.web_account;

  const link = (email: string) => {
    const em = email.trim().toLowerCase();
    if (!em || !em.includes("@")) {
      toast.error("Introduce un email válido.");
      return;
    }
    updateUser.mutate(
      { account_email: em },
      {
        onSuccess: () => {
          toast.success(`Cuenta web vinculada: ${em}`);
          setEmailInput("");
        },
        onError: (e) => toast.error((e as Error).message),
      },
    );
  };

  const unlink = () => {
    updateUser.mutate(
      { account_email: "" },
      {
        onSuccess: () => toast.success("Cuenta web desvinculada."),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="h-4 w-4 text-brand-cyan" />
          Cuenta web (nebulabs-media)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!user.account_email ? (
          // ─── Sin vincular: pedir email ───
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Vincula este usuario a una cuenta de la web por email. Cuando el
              cliente entre con Google en la web con ese mismo email, verás
              aquí su rol, plan y prueba — y podrás gestionarlos.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                type="email"
                placeholder="cliente@gmail.com"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && link(emailInput)}
              />
              <Button
                onClick={() => link(emailInput)}
                disabled={updateUser.isPending}
                className="shrink-0"
              >
                {updateUser.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Link2 className="mr-2 h-4 w-4" />
                )}
                Vincular
              </Button>
            </div>
          </div>
        ) : (
          // ─── Vinculado ───
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-2.5">
              {acc?.picture ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={acc.picture} alt="" className="h-8 w-8 rounded-full" />
              ) : (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-cyan/20 text-xs font-bold">
                  {(acc?.name || user.account_email).charAt(0).toUpperCase()}
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {acc?.name || "(aún no ha entrado)"}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {user.account_email}
                </p>
              </div>
              {acc ? (
                <Badge className="bg-emerald-500/90 text-black">activa</Badge>
              ) : (
                <Badge variant="outline" title="El email está vinculado pero el cliente aún no ha hecho login en la web.">
                  pendiente
                </Badge>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={unlink}
                disabled={updateUser.isPending}
                title="Desvincular"
              >
                <Unlink className="h-3.5 w-3.5" />
              </Button>
            </div>

            {!acc && (
              <p className="rounded-md border border-dashed border-amber-500/40 bg-amber-500/5 p-2.5 text-xs text-amber-700 dark:text-amber-300">
                Email vinculado, pero esta cuenta todavía no existe en la web.
                Pídele al cliente que entre en la web con Google usando{" "}
                <strong>{user.account_email}</strong>. Después podrás
                gestionar su rol y plan desde aquí.
              </p>
            )}

            {acc && (
              <>
                {/* Rol */}
                <div className="space-y-1.5">
                  <Label className="flex items-center gap-1.5 text-xs">
                    <ShieldCheck className="h-3.5 w-3.5" /> Rol (menús de la web)
                  </Label>
                  <div className="flex flex-wrap gap-1.5">
                    {ROLES.map((r) => (
                      <Button
                        key={r.value}
                        size="sm"
                        variant={acc.role === r.value ? "default" : "outline"}
                        disabled={setRole.isPending}
                        onClick={() =>
                          setRole.mutate(
                            { email: acc.email, role: r.value },
                            {
                              onSuccess: () => toast.success(`Rol → ${r.label}`),
                              onError: (e) => toast.error((e as Error).message),
                            },
                          )
                        }
                      >
                        {r.label}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Plan */}
                <div className="space-y-1.5">
                  <Label htmlFor="web-plan" className="text-xs">
                    Plan contratado
                  </Label>
                  <select
                    id="web-plan"
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                    value={acc.plan_id ?? ""}
                    disabled={setPlan.isPending}
                    onChange={(e) =>
                      setPlan.mutate(
                        { email: acc.email, plan_id: e.target.value || null },
                        {
                          onSuccess: () => toast.success("Plan actualizado."),
                          onError: (err) => toast.error((err as Error).message),
                        },
                      )
                    }
                  >
                    {WEB_PLANS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  {!acc.plan_id && (
                    <p className="text-[11px] text-muted-foreground">
                      Vídeos de prueba restantes:{" "}
                      <strong>{acc.trial_videos}</strong>
                    </p>
                  )}
                </div>

                {/* Ban */}
                <div className="flex items-center justify-between rounded-md border p-2.5">
                  <div className="flex items-center gap-2 text-sm">
                    <Ban
                      className={`h-4 w-4 ${acc.banned ? "text-red-500" : "text-muted-foreground"}`}
                    />
                    {acc.banned ? "Cuenta bloqueada" : "Cuenta activa"}
                  </div>
                  <Button
                    size="sm"
                    variant={acc.banned ? "outline" : "destructive"}
                    disabled={setBan.isPending}
                    onClick={() =>
                      setBan.mutate(
                        { email: acc.email, banned: !acc.banned },
                        {
                          onSuccess: () =>
                            toast.success(acc.banned ? "Desbloqueada." : "Bloqueada."),
                          onError: (e) => toast.error((e as Error).message),
                        },
                      )
                    }
                  >
                    {acc.banned ? "Desbloquear" : "Bloquear"}
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
