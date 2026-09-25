"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Copy, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Fila = { usuario: string; nombre: string; url: string };
type Conexion = {
  usuario?: string; url?: string; subir?: string; guias?: string; error?: string;
  /** Solo para el admin: la de cada usuario, que es quien monta los conectores. */
  todos?: Fila[];
};

function oculta(url: string): string {
  return url.replace(/\/api\/mcp\/.*/, "/api/mcp/••••••••");
}

/** La URL del MCP de este usuario, para conectar Claude o ChatGPT a la app.
 *
 *  Con ella la IA trabaja COMO este usuario (su progreso, sus vídeos), así que
 *  va escondida como una contraseña y solo se enseña al pedirla. */
export function ConectarIA() {
  const [ver, setVer] = useState(false);
  const q = useQuery<Conexion>({
    queryKey: ["agente", "mi-conexion"],
    queryFn: () => api.get<Conexion>("/api/v1/agente/mi-conexion"),
    staleTime: Infinity,
  });
  const url = q.data?.url ?? "";

  function copiar(texto: string, que: string) {
    void navigator.clipboard.writeText(texto);
    toast.success(`${que} copiada`);
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="h-4 w-4" /> Conectar una IA (MCP)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-xs sm:text-sm">
        <p className="text-muted-foreground">
          Para que Claude o ChatGPT hagan el trabajo de los menús de Tiktok Shop
          AI Pro por ti: preparar carpetas, sacar los prompts, subir los clips y
          recoger los vídeos. Esta dirección es <strong>personal</strong>: quien
          la tenga trabaja como tú.
        </p>
        {q.data?.error ? (
          <p className="text-amber-500">{q.data.error}</p>
        ) : (
          (q.data?.todos?.length
            ? q.data.todos
            : [{ usuario: q.data?.usuario ?? "", nombre: "", url }]
          ).map((f) => (
            <div key={f.usuario || "yo"} className="space-y-0.5">
              {q.data?.todos?.length ? (
                <p className="text-[11px] font-medium">
                  {f.nombre || f.usuario}{" "}
                  <span className="text-muted-foreground">· {f.usuario}</span>
                  {f.usuario === q.data?.usuario && (
                    <span className="text-muted-foreground"> (tú)</span>
                  )}
                </p>
              ) : null}
              <div className="flex gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-border/60 bg-muted/40 px-2 py-1.5 font-mono text-[11px]">
                  {f.url ? (ver ? f.url : oculta(f.url)) : "…"}
                </code>
                <Button size="icon" variant="outline" onClick={() => setVer((v) => !v)}
                  aria-label={ver ? "Ocultar" : "Mostrar"} disabled={!f.url}>
                  {ver ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
                <Button size="icon" variant="outline"
                  onClick={() => copiar(f.url, `URL de ${f.nombre || f.usuario || "tu usuario"}`)}
                  aria-label="Copiar" disabled={!f.url}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))
        )}
        {!!q.data?.todos?.length && (
          <p className="text-[11px] text-muted-foreground">
            Un conector por cuenta: añade cada URL con su nombre («TikTok AI Pro ·
            Ana»…) y en cada chat activa solo el de la cuenta con la que trabajas.
          </p>
        )}
        <ul className="space-y-1 text-[11px] text-muted-foreground sm:text-xs">
          <li>
            <strong className="text-foreground">Claude</strong> (web, escritorio,
            Cowork): Configuración › Conectores › Añadir conector personalizado ›
            pega la URL.
          </li>
          <li>
            <strong className="text-foreground">ChatGPT</strong>: Configuración ›
            Aplicaciones y conectores › Opciones avanzadas › Modo desarrollador ›
            Crear › pega la URL, sin autenticación.
          </li>
          <li>
            <strong className="text-foreground">Claude Code / Codex en el VPS</strong>:
            añade un servidor MCP de tipo HTTP con esa URL.
          </li>
          <li>
            Luego dile, por ejemplo: «Hazme la carpeta 24 del POV BOF Largo hasta
            dejar las imágenes». Lo primero que hará es leer las guías.
          </li>
        </ul>
        {q.data?.guias && (
          <a href={q.data.guias} target="_blank" rel="noopener"
            className="inline-block text-[11px] text-violet-400 underline">
            Ver las guías que lee la IA
          </a>
        )}
      </CardContent>
    </Card>
  );
}
