"use client";

import { Hand, Pencil, Sparkles, Wand2 } from "lucide-react";

import { cn } from "@/lib/utils";

type TabMode = "auto" | "manual" | "mixed";

const MODE_LABEL: Record<
  TabMode,
  { label: string; icon: typeof Sparkles; cls: string }
> = {
  auto: {
    label: "Auto-generado",
    icon: Sparkles,
    cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  manual: {
    label: "Manual",
    icon: Hand,
    cls: "border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-300",
  },
  mixed: {
    label: "Auto + editable",
    icon: Wand2,
    cls: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
};

/** Banner pequeño al inicio de un tab para que se sepa de un vistazo qué
 *  se genera automáticamente con IA y qué hay que rellenar a mano.
 *
 *  Uso: `<TabHint mode="auto" source="Análisis (Re-analizar)">
 *         Audiencia / features / selling points los rellena Gemini desde
 *         las fotos source. Puedes editar a mano cuando quieras.
 *       </TabHint>` */
export function TabHint({
  mode,
  source,
  children,
}: {
  mode: TabMode;
  source?: string;
  children: React.ReactNode;
}) {
  const meta = MODE_LABEL[mode];
  const Icon = meta.icon;
  return (
    <div
      className={cn(
        "mb-4 flex items-start gap-3 rounded-md border-2 px-3 py-2 text-xs",
        meta.cls,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <strong className="text-[11px] uppercase tracking-wide">
            {meta.label}
          </strong>
          {source && (
            <span className="text-[10px] opacity-70">· {source}</span>
          )}
          <span className="ml-auto inline-flex items-center gap-1 text-[10px] opacity-70">
            <Pencil className="h-2.5 w-2.5" /> editable
          </span>
        </div>
        <p className="mt-0.5 leading-snug opacity-90">{children}</p>
      </div>
    </div>
  );
}
