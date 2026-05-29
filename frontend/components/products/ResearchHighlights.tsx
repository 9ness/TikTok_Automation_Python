"use client";

import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  Heart,
  HelpCircle,
  Lightbulb,
  MessageSquare,
  Music,
  Quote,
  Search,
  Target,
  TrendingUp,
  Video,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type {
  Product,
  ResearchContext,
  TrendingSound,
  ViralVideoSummary,
} from "@/lib/types/product";
import { cn } from "@/lib/utils";

interface Props {
  product: Product;
}

interface CategoryCard {
  key: string;
  icon: typeof Eye;
  title: string;
  count: number;
  accent: string;
  data: () => React.ReactNode;
}

/** Cards click-to-expand con resúmenes del research_context. Se usa
 *  en la tab Audiencia para tener los datos importantes a mano sin
 *  ocupar mucho espacio. */
export function ResearchHighlights({ product }: Props) {
  const rc: ResearchContext | undefined = product.research_context;
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (!rc || !rc.analyzed_at) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="p-3 text-center text-xs text-muted-foreground sm:text-sm">
          Sin investigación todavía. Ve a la tab Análisis y pulsa Analizar.
        </CardContent>
      </Card>
    );
  }

  const cards: CategoryCard[] = [
    {
      key: "videos",
      icon: Video,
      title: "Vídeos virales",
      count: rc.top_videos.length,
      accent: "text-cyan-500 border-cyan-500/40",
      data: () => <VideoList items={rc.top_videos} />,
    },
    {
      key: "pains",
      icon: AlertCircle,
      title: "Dolores reales",
      count: rc.customer_pains.length,
      accent: "text-red-500 border-red-500/40",
      data: () => <SimpleList items={rc.customer_pains} />,
    },
    {
      key: "benefits",
      icon: Heart,
      title: "Beneficios",
      count: rc.customer_benefits.length,
      accent: "text-emerald-500 border-emerald-500/40",
      data: () => <SimpleList items={rc.customer_benefits} />,
    },
    {
      key: "objections",
      icon: MessageSquare,
      title: "Objeciones",
      count: rc.objections.length,
      accent: "text-orange-500 border-orange-500/40",
      data: () => <SimpleList items={rc.objections} />,
    },
    {
      key: "hooks",
      icon: Quote,
      title: "Hooks probados",
      count: rc.proven_hooks.length,
      accent: "text-purple-500 border-purple-500/40",
      data: () => <SimpleList items={rc.proven_hooks} />,
    },
    {
      key: "questions",
      icon: HelpCircle,
      title: "Preguntas público",
      count: rc.audience_questions?.length ?? 0,
      accent: "text-teal-500 border-teal-500/40",
      data: () => <SimpleList items={rc.audience_questions ?? []} />,
    },
    {
      key: "sounds",
      icon: Music,
      title: "Sonidos trending",
      count: rc.trending_sounds?.length ?? 0,
      accent: "text-fuchsia-500 border-fuchsia-500/40",
      data: () => <SoundList items={rc.trending_sounds ?? []} />,
    },
    {
      key: "patterns",
      icon: TrendingUp,
      title: "Patrones virales",
      count: rc.viral_patterns.length,
      accent: "text-pink-500 border-pink-500/40",
      data: () => <SimpleList items={rc.viral_patterns} />,
    },
    {
      key: "differentiators",
      icon: Target,
      title: "Diferenciadores",
      count: rc.competitive_diff.length,
      accent: "text-blue-500 border-blue-500/40",
      data: () => <SimpleList items={rc.competitive_diff} />,
    },
    {
      key: "keywords",
      icon: Search,
      title: "Keywords SEO",
      count: rc.niche_keywords.length,
      accent: "text-indigo-500 border-indigo-500/40",
      data: () => <SimpleList items={rc.niche_keywords} />,
    },
    {
      key: "inspiration",
      icon: Lightbulb,
      title: "Inspiración nicho",
      count: rc.niche_inspiration.length,
      accent: "text-amber-500 border-amber-500/40",
      data: () => <SimpleList items={rc.niche_inspiration} />,
    },
  ].filter((c) => c.count > 0);

  if (cards.length === 0) {
    return null;
  }

  // Detectar análisis parcial: hubo videos en Apify pero Gemini no extrajo
  // patterns/hooks (downloads fallaron) → análisis incompleto.
  const analyzedVideos = rc.top_videos.filter((v) => v.hook_text).length;
  const totalVideos = rc.top_videos.length;
  const isPartial = totalVideos > 0 && analyzedVideos < totalVideos;
  const isFullySuccess = totalVideos > 0 && analyzedVideos === totalVideos;

  return (
    <div className="space-y-2">
      <StatusBanner
        analyzedAt={rc.analyzed_at}
        cost={rc.research_cost_usd}
        analyzedVideos={analyzedVideos}
        totalVideos={totalVideos}
        isPartial={isPartial}
        isFullySuccess={isFullySuccess}
      />
      {/* Grid de tarjetas — click para expandir */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon;
          const isOpen = openKey === c.key;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => setOpenKey(isOpen ? null : c.key)}
              className={cn(
                "flex items-center gap-2 rounded-lg border-2 p-2 text-left transition-colors hover:bg-muted/50 sm:p-3",
                c.accent,
                isOpen && "bg-muted/50 ring-1 ring-offset-1 ring-current",
              )}
            >
              <Icon className={cn("h-4 w-4 flex-shrink-0", c.accent.split(" ")[0])} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[10px] font-semibold sm:text-[11px]">
                  {c.title}
                </p>
                <p className="text-[9px] text-muted-foreground sm:text-[10px]">
                  {c.count} item{c.count === 1 ? "" : "s"}
                </p>
              </div>
              {isOpen ? (
                <ChevronDown className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              )}
            </button>
          );
        })}
      </div>

      {/* Contenido expandido — solo del card activo */}
      {openKey && (
        <Card>
          <CardContent className="p-3 sm:p-4">
            {cards.find((c) => c.key === openKey)?.data()}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatusBanner({
  analyzedAt,
  cost,
  analyzedVideos,
  totalVideos,
  isPartial,
  isFullySuccess,
}: {
  analyzedAt: string | null;
  cost: number;
  analyzedVideos: number;
  totalVideos: number;
  isPartial: boolean;
  isFullySuccess: boolean;
}) {
  const relativeTime = (() => {
    if (!analyzedAt) return "—";
    const d = new Date(analyzedAt);
    const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diffMin < 1) return "hace menos de 1 min";
    if (diffMin < 60) return `hace ${diffMin} min`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `hace ${diffH}h`;
    const diffD = Math.floor(diffH / 24);
    return `hace ${diffD}d`;
  })();

  const absoluteTime = analyzedAt
    ? new Date(analyzedAt).toLocaleString("es-ES", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const Icon = isFullySuccess ? CheckCircle2 : isPartial ? AlertTriangle : AlertCircle;
  const accent = isFullySuccess
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
    : isPartial
      ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
      : "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400";
  const status = isFullySuccess
    ? "Análisis completo"
    : isPartial
      ? `Parcial: ${analyzedVideos}/${totalVideos} vídeos analizados`
      : totalVideos === 0
        ? "Sin vídeos virales — Apify falló"
        : "Análisis incompleto";

  return (
    <div className={cn("flex items-center gap-2 rounded-lg border-2 px-3 py-2", accent)}>
      <Icon className="h-4 w-4 flex-shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold sm:text-sm">{status}</p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground sm:text-[11px]">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-2.5 w-2.5" />
            {relativeTime}
          </span>
          <span>·</span>
          <span className="font-mono">{absoluteTime}</span>
          <span>·</span>
          <span>${cost.toFixed(3)}</span>
        </p>
      </div>
    </div>
  );
}

function SimpleList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li
          key={i}
          className="rounded border border-muted bg-muted/20 px-2 py-1 text-[11px] leading-snug sm:text-xs"
        >
          {it}
        </li>
      ))}
    </ul>
  );
}

function SoundList({ items }: { items: TrendingSound[] }) {
  return (
    <div className="space-y-1.5">
      {items.map((s, i) => (
        <div
          key={i}
          className="flex items-center gap-2 rounded border bg-muted/20 p-2"
        >
          <Music className="h-3.5 w-3.5 flex-shrink-0 text-fuchsia-500" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-medium sm:text-xs">
              {s.title || s.music_id || "Sonido"}
              {s.is_original && (
                <span className="ml-1 rounded bg-muted px-1 text-[9px] uppercase text-muted-foreground">
                  original
                </span>
              )}
            </p>
            <p className="text-[9px] text-muted-foreground sm:text-[10px]">
              {s.author ? `${s.author} · ` : ""}en {s.used_count} vídeo
              {s.used_count === 1 ? "" : "s"} · {s.total_views.toLocaleString()} views
            </p>
          </div>
          {s.url && (
            <a
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 text-fuchsia-500 hover:text-fuchsia-400"
              title="Escuchar sonido"
            >
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

function VideoList({ items }: { items: ViralVideoSummary[] }) {
  const organic = items.filter((v) => v.traffic_type === "organic");
  const paid = items.filter((v) => v.traffic_type === "paid");
  const untagged = items.filter(
    (v) => v.traffic_type !== "organic" && v.traffic_type !== "paid",
  );

  // Si hay split paid/organic, mostramos dos grupos con cabecera.
  if (organic.length > 0 || paid.length > 0) {
    return (
      <div className="space-y-3">
        {organic.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase text-emerald-600 dark:text-emerald-400 sm:text-[11px]">
              🌱 Virales orgánicos ({organic.length}) — qué engancha solo
            </p>
            <VideoCards items={organic} />
          </div>
        )}
        {paid.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold uppercase text-orange-600 dark:text-orange-400 sm:text-[11px]">
              💸 Alcance pagado ({paid.length}) — qué se escala con ads
            </p>
            <VideoCards items={paid} />
          </div>
        )}
        {untagged.length > 0 && <VideoCards items={untagged} />}
      </div>
    );
  }
  return <VideoCards items={items} />;
}

function VideoCards({ items }: { items: ViralVideoSummary[] }) {
  return (
    <div className="space-y-1.5">
      {items.map((v, i) => (
        <a
          key={i}
          href={v.url || "#"}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded border bg-muted/20 p-2 transition-colors hover:bg-muted/40"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground sm:text-[11px]">
            <div className="flex flex-wrap items-center gap-1.5">
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
            <ExternalLink className="h-3 w-3 text-cyan-500" />
          </div>
          {v.hook_text && (
            <p className="mt-1 text-[11px] italic text-foreground sm:text-xs">
              “{v.hook_text}”
            </p>
          )}
          {v.script_structure && (
            <p className="mt-0.5 text-[10px] text-muted-foreground sm:text-[11px]">
              {v.script_structure}
            </p>
          )}
        </a>
      ))}
    </div>
  );
}
