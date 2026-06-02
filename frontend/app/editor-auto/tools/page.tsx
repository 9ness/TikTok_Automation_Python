"use client";

import { Loader2, Wrench } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEditorAutoTools } from "@/lib/queries/editor-auto";

export default function EditorAutoToolsPage() {
  const tools = useEditorAutoTools();

  if (tools.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (tools.isError) {
    return (
      <div className="p-6 text-sm text-destructive">
        Error cargando herramientas: {(tools.error as Error)?.message}
      </div>
    );
  }

  const items = tools.data ?? [];
  // Ordenadas por position_weight (orden real de ejecución del orchestrator).
  const sorted = [...items].sort((a, b) => a.position_weight - b.position_weight);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Herramientas disponibles</h1>
        <p className="text-sm text-muted-foreground">
          Catálogo de herramientas componibles del Editor Auto, ordenadas por
          peso (menor peso = se ejecuta antes en el flujo).
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        {sorted.map((tool) => (
          <Card key={tool.tool_id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Wrench className="h-4 w-4 text-emerald-500" />
                {tool.display_name}
                <span className="ml-auto rounded bg-muted px-2 py-0.5 text-xs font-mono">
                  peso {tool.position_weight}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{tool.description}</p>
              <div className="text-xs">
                <p className="font-medium text-foreground">slug:</p>
                <code className="rounded bg-muted px-1 py-0.5">{tool.tool_id}</code>
              </div>
              <details className="text-xs">
                <summary className="cursor-pointer font-medium text-foreground">
                  Config schema ({tool.config_schema.length} campos)
                </summary>
                <ul className="mt-2 space-y-1 pl-4">
                  {tool.config_schema.map((f) => (
                    <li key={f.key} className="text-muted-foreground">
                      <code className="font-mono">{f.key}</code> · {f.label} (
                      {f.type})
                    </li>
                  ))}
                </ul>
              </details>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
