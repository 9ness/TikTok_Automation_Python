"use client";

import { Bot } from "lucide-react";

import { api } from "@/lib/api";

/** Enlace a la guía paso a paso de esta pantalla para una IA (Claude en
 *  Chrome, ChatGPT Agent, o por el MCP). Las guías son Markdown que sirve la
 *  API tal cual desde `src/agente_mcp/guias/` —la misma fuente que lee el
 *  MCP—, públicas y sin login. Va en la cabecera de cada nicho, siempre en el
 *  mismo sitio, para que el agente la encuentre sin buscar. */
export function GuiaIA({ guia }: { guia: string }) {
  const href = `${api.baseUrl}/api/v1/agente/guias/${guia}.md`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      data-guia-ia={href}
      title="Instrucciones paso a paso de esta pantalla para un agente de IA"
      className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-[10px] text-muted-foreground transition hover:border-violet-500/60 hover:text-foreground"
    >
      <Bot className="h-3 w-3" /> Guía IA
    </a>
  );
}
