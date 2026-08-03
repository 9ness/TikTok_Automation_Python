"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";

/** Botón compacto que copia un texto sin enseñarlo.
 *
 *  Vive aquí y no dentro de la página de un nicho porque los nichos comparten
 *  el mismo flujo (caption, título de TikTok, tienda) y el operador quiere que
 *  se manejen IGUAL: tres personas suben productos y la interfaz tiene que
 *  resultarles familiar de un nicho a otro.
 */
export function CopyChip({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        toast.success("Copiado");
      }}
      title={`Copiar: ${label}`}
      className="inline-flex max-w-full items-center gap-1 truncate rounded-md border border-border/60 px-2 py-1 text-[11px] font-medium text-muted-foreground transition hover:border-foreground/40 hover:text-foreground"
    >
      <Copy className="h-3 w-3 shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  );
}
