"use client";

import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Eye,
  FlaskConical,
  Heart,
  Lightbulb,
  MessageSquare,
  Quote,
  Search,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { Product, ResearchContext } from "@/lib/types/product";
import { formatLocal } from "@/lib/dates";

interface Props {
  product: Product;
}

interface SectionProps {
  title: string;
  hint?: string;
  icon: typeof Search;
  items: string[];
  accentColor: string;
  emptyHint?: string;
}

function Section({ title, hint, icon: Icon, items, accentColor, emptyHint }: SectionProps) {
  if (items.length === 0) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5">
          <Icon className={`h-3.5 w-3.5 ${accentColor}`} />
          <h4 className="text-xs font-semibold sm:text-sm">{title}</h4>
        </div>
        <p className="rounded border border-dashed bg-muted/30 px-2 py-1.5 text-[10px] text-muted-foreground sm:text-xs">
          {emptyHint ?? "Sin datos. Pulsa Reanalizar producto para investigar."}
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Icon className={`h-3.5 w-3.5 ${accentColor}`} />
          <h4 className="text-xs font-semibold sm:text-sm">{title}</h4>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground sm:text-[10px]">
            {items.length}
          </span>
        </div>
        {hint && (
          <span className="text-[9px] text-muted-foreground sm:text-[10px]">
            {hint}
          </span>
        )}
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li
            key={i}
            className="rounded border border-muted bg-muted/20 px-2 py-1 text-[11px] leading-snug sm:text-xs"
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ResearchPanel({ product }: Props) {
  const rc: ResearchContext | undefined = product.research_context;

  if (!rc || !rc.analyzed_at) {
    return (
      <Card>
        <CardContent className="space-y-3 p-4 sm:p-6">
          <div className="flex items-start gap-2">
            <FlaskConical className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-500" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold sm:text-base">
                Investigación profunda no ejecutada todavía
              </h3>
              <p className="text-xs text-muted-foreground sm:text-sm">
                Pulsa <strong>Reanalizar producto</strong> (en la tab
                Análisis) para que el sistema:
              </p>
              <ul className="ml-3 list-disc space-y-0.5 text-xs text-muted-foreground sm:text-sm">
                <li>Busque reviews reales en Amazon/AliExpress + foros del nicho</li>
                <li>Analice los top vídeos virales del producto en TikTok</li>
                <li>Extraiga objeciones reales de los comentarios</li>
                <li>Detecte patrones visuales y de guión que funcionan</li>
              </ul>
              <p className="pt-2 text-[11px] text-muted-foreground sm:text-xs">
                Coste típico: ~$0.10-0.20 por reanálisis. Los guiones que
                genere a partir de esta info serán mucho más afilados —
                usan vocabulario real de la gente, no inventado.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const totalDatapoints =
    rc.customer_pains.length +
    rc.customer_benefits.length +
    rc.objections.length +
    rc.proven_hooks.length +
    rc.viral_patterns.length +
    rc.niche_keywords.length;

  return (
    <div className="space-y-4">
      {/* Header con métricas */}
      <Card>
        <CardContent className="p-3 sm:p-4">
          <div className="flex flex-wrap items-center gap-3 text-xs sm:text-sm">
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="font-medium">Investigación completa</span>
            </div>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">
              {formatLocal(rc.analyzed_at)}
            </span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground">
              {rc.sources_videos_count} vídeos · {rc.sources_reviews_count} datapoints reviews
            </span>
            {rc.research_cost_usd > 0 && (
              <>
                <span className="text-muted-foreground">·</span>
                <span className="rounded bg-purple-500/15 px-2 py-0.5 text-[10px] text-purple-700 dark:text-purple-300 sm:text-xs">
                  ${rc.research_cost_usd.toFixed(3)}
                </span>
              </>
            )}
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground sm:text-xs">
            Total {totalDatapoints} datos extraídos. Los prompts de guiones
            usan automáticamente esta info al generar presets.
          </p>
        </CardContent>
      </Card>

      {/* Grid 2-col en sm+ con todos los datos */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-3 sm:p-4">
            <Section
              title="Dolores reales"
              hint="de reviews 1-3 estrellas"
              icon={AlertCircle}
              items={rc.customer_pains}
              accentColor="text-red-500"
              emptyHint="Sin pains detectados."
            />
            <Section
              title="Objeciones"
              hint="dudas pre-compra"
              icon={MessageSquare}
              items={rc.objections}
              accentColor="text-orange-500"
              emptyHint="Sin objeciones detectadas."
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-3 sm:p-4">
            <Section
              title="Beneficios reales"
              hint="reviews 4-5 estrellas"
              icon={Heart}
              items={rc.customer_benefits}
              accentColor="text-emerald-500"
              emptyHint="Sin benefits detectados."
            />
            <Section
              title="Diferenciadores"
              hint="vs competencia"
              icon={Target}
              items={rc.competitive_diff}
              accentColor="text-blue-500"
              emptyHint="Sin diferenciadores detectados."
            />
          </CardContent>
        </Card>
      </div>

      {/* Hooks probados + patterns virales */}
      <Card>
        <CardContent className="space-y-3 p-3 sm:p-4">
          <Section
            title="Hooks probados"
            hint="de vídeos que viralizaron"
            icon={Quote}
            items={rc.proven_hooks}
            accentColor="text-purple-500"
            emptyHint="Apify no encontró vídeos virales del producto, o no se pudo analizar."
          />
          <Section
            title="Patrones virales"
            hint="estructura visual + guión"
            icon={TrendingUp}
            items={rc.viral_patterns}
            accentColor="text-pink-500"
            emptyHint="Sin patrones detectados."
          />
        </CardContent>
      </Card>

      {/* Top vídeos analizados */}
      {rc.top_videos.length > 0 && (
        <Card>
          <CardContent className="space-y-2 p-3 sm:p-4">
            <div className="flex items-center gap-1.5">
              <Eye className="h-3.5 w-3.5 text-cyan-500" />
              <h4 className="text-xs font-semibold sm:text-sm">
                Top {rc.top_videos.length} vídeos analizados
              </h4>
            </div>
            <div className="space-y-1.5">
              {rc.top_videos.map((v, i) => (
                <div
                  key={i}
                  className="rounded border bg-muted/20 p-2 text-[11px] sm:text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1.5 text-muted-foreground">
                      <span className="font-mono">
                        {v.view_count.toLocaleString()} views
                      </span>
                      <span>·</span>
                      <span>{v.like_count.toLocaleString()} ❤</span>
                      <span>·</span>
                      <span>{v.duration_s.toFixed(0)}s</span>
                      {v.hook_category && (
                        <>
                          <span>·</span>
                          <span className="rounded bg-purple-500/15 px-1.5 text-purple-700 dark:text-purple-300">
                            {v.hook_category}
                          </span>
                        </>
                      )}
                    </div>
                    {v.url && (
                      <a
                        href={v.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-cyan-600 hover:underline dark:text-cyan-400"
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                  {v.hook_text && (
                    <p className="mt-1 italic text-foreground">
                      “{v.hook_text}”
                    </p>
                  )}
                  {v.script_structure && (
                    <p className="mt-0.5 text-[10px] text-muted-foreground sm:text-[11px]">
                      {v.script_structure}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Keywords + inspiración del nicho */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <CardContent className="space-y-2 p-3 sm:p-4">
            <Section
              title="Keywords SEO"
              hint="del nicho"
              icon={Search}
              items={rc.niche_keywords}
              accentColor="text-indigo-500"
              emptyHint="Sin keywords."
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-2 p-3 sm:p-4">
            <Section
              title="Inspiración del nicho"
              hint="tendencias + ángulos"
              icon={Lightbulb}
              items={rc.niche_inspiration}
              accentColor="text-yellow-500"
              emptyHint="Sin inspiración."
            />
          </CardContent>
        </Card>
      </div>

      <Card className="bg-muted/30">
        <CardContent className="space-y-1 p-3 text-[11px] text-muted-foreground sm:p-4 sm:text-xs">
          <p>
            <Sparkles className="mr-1 inline h-3 w-3 text-amber-500" />
            Esta investigación se aplica automáticamente al generar nuevos
            presets desde la tab <strong>Presets</strong>. Los hooks,
            voice_script y estructura usarán dolores/objeciones reales
            (no inventados) y mimetizan patrones de vídeos virales.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
