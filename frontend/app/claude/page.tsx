"use client";

import {
  Bot,
  ExternalLink,
  Laptop,
  Server,
  Smartphone,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const CLAUDE_CODE_URL = "https://claude.ai/code";

export default function ClaudePage() {
  return (
    <div className="container mx-auto max-w-3xl space-y-5 p-3 sm:space-y-6 sm:p-6 md:p-10">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-lg font-bold tracking-tight sm:text-2xl">
          <Bot className="h-5 w-5 sm:h-6 sm:w-6" />
          Claude — Control remoto
        </h1>
        <p className="text-xs text-muted-foreground sm:text-sm">
          Tus chats de Claude viven en el VPS (encendido 24/7). Ábrelos desde
          aquí, el móvil o el PC — son los mismos.
        </p>
      </header>

      {/* Botón principal */}
      <div className="rounded-xl border bg-card p-4 text-center sm:p-6">
        <Server className="mx-auto h-8 w-8 text-primary" />
        <p className="mt-2 text-sm font-medium">VPS encendido siempre</p>
        <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
          12 proyectos con sus chats listos en el servidor. Abre el control
          remoto y elige el proyecto.
        </p>
        <Button asChild size="lg" className="mt-4 w-full sm:w-auto">
          <a href={CLAUDE_CODE_URL} target="_blank" rel="noopener noreferrer">
            Abrir control remoto
            <ExternalLink className="ml-1.5 h-4 w-4" />
          </a>
        </Button>
      </div>

      {/* Cómo funciona en cada sitio */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 rounded-lg border p-3 sm:p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Smartphone className="h-4 w-4" /> En el móvil
          </div>
          <p className="text-xs text-muted-foreground">
            Abre la <b>app de Claude</b> → pestaña <b>Code</b>. Verás tus
            proyectos del VPS. Entra en uno y chatea. Funciona con el PC
            apagado.
          </p>
        </div>
        <div className="space-y-1.5 rounded-lg border p-3 sm:p-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Laptop className="h-4 w-4" /> En el PC
          </div>
          <p className="text-xs text-muted-foreground">
            El botón de arriba abre <b>claude.ai/code</b> en el navegador. Son{" "}
            <b>los mismos chats</b> que ves en el móvil — el VPS es la fuente
            única.
          </p>
        </div>
      </div>

      {/* Nota de imágenes */}
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-muted-foreground sm:p-4">
        <p className="font-semibold text-amber-600 dark:text-amber-400">
          Sobre imágenes
        </p>
        <p className="mt-1">
          El control remoto (app oficial) no admite imágenes genéricas todavía
          (limitación de Anthropic). Si necesitas que Claude vea fotos/capturas
          desde la web, dímelo y reactivo el chat con imágenes en un minuto.
        </p>
      </div>
    </div>
  );
}
