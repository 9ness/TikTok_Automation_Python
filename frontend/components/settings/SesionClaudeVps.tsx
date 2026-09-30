"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, KeyRound, Loader2, LogIn, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

/** La sesión de claude.ai del VPS, renovable desde aquí sin terminal.
 *
 *  Caduca (≈ cada mes) y entonces Remote Control y el chat de la app dan
 *  «failed to fetch». Pasos: «Iniciar sesión» → abre el enlace de claude.com y
 *  entra con TU cuenta → copia el código que te da → pégalo aquí. El servidor lo
 *  teclea en `claude auth login` y vuelve a arrancar las sesiones remotas.
 */
type Estado = { logueado: boolean; cuenta?: string; metodo?: string };

const KEY = ["claude-vps", "estado"];

export function SesionClaudeVps() {
  const qc = useQueryClient();
  const estado = useQuery<Estado>({
    queryKey: KEY,
    queryFn: () => api.get<Estado>("/api/v1/claude-vps/estado"),
    refetchInterval: 60_000,
    retry: false,
  });
  const [url, setUrl] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");

  const iniciar = useMutation<{ url: string }, Error>({
    mutationFn: () => api.post<{ url: string }>("/api/v1/claude-vps/iniciar", {}),
    onSuccess: (r) => {
      if (!r.url) {
        toast.error("El servidor no devolvió el enlace. Vuelve a intentarlo.");
        return;
      }
      setUrl(r.url);
      setCodigo("");
    },
    onError: () => toast.error("No se pudo iniciar el login en el servidor"),
  });

  const enviar = useMutation<Estado & { ok: boolean; error?: string }, Error, string>({
    mutationFn: (c) =>
      api.post<Estado & { ok: boolean; error?: string }>("/api/v1/claude-vps/codigo", { codigo: c }),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("Claude conectado en el VPS. Las sesiones remotas se están reiniciando.");
        setUrl(null);
        setCodigo("");
        qc.setQueryData(KEY, { logueado: true, cuenta: r.cuenta, metodo: r.metodo });
      } else {
        toast.error(r.error || "Claude no aceptó el código");
      }
    },
    onError: () => toast.error("No se pudo enviar el código"),
  });

  const e = estado.data;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          🤖 Sesión de Claude en el VPS
          {e ? (
            <span
              className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                e.logueado
                  ? "bg-emerald-500/15 text-emerald-500"
                  : "bg-destructive/15 text-destructive"
              }`}
            >
              {e.logueado ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
              {e.logueado ? "Conectada" : "Caducada"}
            </span>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          La usan Claude remoto y el chat de la app. Caduca más o menos cada mes: cuando
          veas «failed to fetch», renuévala aquí.
          {e?.logueado && e.cuenta ? ` Cuenta: ${e.cuenta}.` : ""}
        </p>

        {estado.isError ? (
          <p className="text-xs text-destructive">No se pudo consultar el estado del servidor.</p>
        ) : null}

        {!url ? (
          <Button
            size="sm"
            variant={e?.logueado ? "outline" : "default"}
            disabled={iniciar.isPending}
            onClick={() => iniciar.mutate()}
          >
            {iniciar.isPending ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <LogIn className="mr-1.5 h-3.5 w-3.5" />
            )}
            {e?.logueado ? "Volver a iniciar sesión" : "Iniciar sesión"}
          </Button>
        ) : (
          <div className="space-y-2 rounded-lg border border-border/60 p-3">
            <p className="text-xs">
              <b>1.</b> Abre el enlace y entra con tu cuenta de Claude.
            </p>
            <Button asChild size="sm" variant="outline">
              <a href={url} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" /> Abrir claude.com
              </a>
            </Button>
            <p className="text-xs">
              <b>2.</b> Copia el código que te enseña al final y pégalo aquí.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={codigo}
                onChange={(ev) => setCodigo(ev.target.value)}
                placeholder="Pega aquí el código"
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-md border border-border/60 bg-background px-3 py-2 text-xs outline-none focus:border-primary/60 sm:text-sm"
              />
              <Button
                size="sm"
                disabled={!codigo.trim() || enviar.isPending}
                onClick={() => enviar.mutate(codigo.trim())}
              >
                {enviar.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <KeyRound className="mr-1.5 h-3.5 w-3.5" />
                )}
                Conectar
              </Button>
            </div>
            <button
              type="button"
              onClick={() => {
                setUrl(null);
                void api.post("/api/v1/claude-vps/cancelar", {});
              }}
              className="text-[11px] text-muted-foreground underline"
            >
              Cancelar
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
