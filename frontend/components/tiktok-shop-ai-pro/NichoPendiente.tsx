/** Página de un nicho del curso que todavía no tiene herramienta.
 *
 * Existe para que el menú esté completo desde ya: se entra, se ve de qué va el
 * módulo (con su portada) y dónde está su material en el Drive del curso. La
 * herramienta se va montando nicho a nicho.
 */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { moduloPorSlug, portadaDe } from "@/lib/tiktok-shop-ai-pro/modulos";
import { FolderOpen, Hammer } from "lucide-react";

export function NichoPendiente({ slug }: { slug: string }) {
  const m = moduloPorSlug(slug);
  if (!m) return null;
  const Icon = m.icon;

  return (
    <div className="container mx-auto max-w-3xl p-4 md:p-8">
      <Card className="overflow-hidden">
        {/* La portada es el recorte del banner del módulo en Skool: sirve de
            recordatorio visual de qué nicho es sin tener que leer nada. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={portadaDe(m.slug)}
          alt={m.titulo}
          className="h-auto w-full border-b"
        />
        <CardHeader className="pb-3">
          <div className="flex items-start gap-3">
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-brand-cyan" strokeWidth={1.75} />
            <div className="min-w-0">
              <CardTitle className="text-base sm:text-lg">{m.titulo}</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
                Módulo {m.modulo} · {m.resumen}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-xs sm:text-sm">
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            <Hammer className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" strokeWidth={1.75} />
            <p className="text-muted-foreground">
              Pendiente de configurar. El menú ya está creado; la herramienta de
              este nicho se monta cuando toque.
            </p>
          </div>
          {m.drive && (
            <div className="flex items-start gap-2 text-muted-foreground">
              <FolderOpen className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
              <p className="break-words">
                Material del curso en Drive:{" "}
                <code className="rounded bg-muted px-1 py-0.5">{m.drive}</code>
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
