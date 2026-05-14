"use client";

import { useState } from "react";
import {
  Check,
  Eye,
  EyeOff,
  ExternalLink,
  Loader2,
  Wifi,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { DeployPanel } from "@/components/settings/DeployPanel";
import { ApiError, api } from "@/lib/api";
import { checkApiHealth, type HealthResponse } from "@/lib/queries/queue";

export default function SettingsPage() {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runHealthCheck() {
    setTesting(true);
    setError(null);
    setResult(null);
    try {
      const res = await checkApiHealth();
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error de conexión");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="container mx-auto space-y-6 p-6 md:p-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">⚙️ Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configuración de la app y conexión al backend.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">API</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs">API base URL</Label>
            <Input value={api.baseUrl} readOnly className="font-mono text-sm" />
            <p className="text-xs text-muted-foreground">
              Configura con <code className="font-mono">NEXT_PUBLIC_API_URL</code> en{" "}
              <code className="font-mono">.env.local</code>.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">API Key</Label>
            <div className="flex gap-2">
              <Input
                type={showKey ? "text" : "password"}
                value={apiKey ?? ""}
                placeholder={apiKey ? undefined : "(sin API key configurada)"}
                readOnly
                className="font-mono text-sm"
              />
              <Button
                size="icon"
                variant="outline"
                onClick={() => setShowKey((v) => !v)}
                disabled={!apiKey}
                aria-label={showKey ? "Ocultar API Key" : "Mostrar API Key"}
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Button onClick={runHealthCheck} disabled={testing}>
              {testing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wifi className="h-4 w-4" />
              )}
              Test connection
            </Button>

            {result && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-green-500/40 bg-green-500/5 p-3 text-sm text-green-700 dark:text-green-300">
                <Check className="h-4 w-4" />
                <span className="font-medium">{result.status}</span>
                <Badge variant="outline">v{result.version}</Badge>
                <Badge variant={result.redis_configured ? "default" : "secondary"}>
                  Redis: {result.redis_configured ? "configurado" : "no configurado"}
                </Badge>
              </div>
            )}
            {error && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                <WifiOff className="mt-0.5 h-4 w-4" />
                <div>
                  <p className="font-medium">Sin conexión al backend</p>
                  <p className="text-xs">{error}</p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <DeployPanel />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Apariencia</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <div>
            <p className="text-sm">Modo claro / oscuro</p>
            <p className="text-xs text-muted-foreground">
              Cambia el tema de toda la interfaz.
            </p>
          </div>
          <ThemeToggle />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sobre</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Versión" value="0.1.0" />
          <Row
            label="Documentación API"
            value={
              <a
                href={`${api.baseUrl}/api/docs`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                <ExternalLink className="h-3 w-3" />
                {api.baseUrl}/api/docs
              </a>
            }
          />
          <Row label="Backend" value="FastAPI + WebSocket" />
          <Row label="Frontend" value="Next.js 14 + Tailwind + shadcn/ui" />
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b pb-2 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}

