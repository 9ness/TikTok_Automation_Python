"use client";

import { useState } from "react";
import { Film, Sparkles, Banana, Target } from "lucide-react";

import { cn } from "@/lib/utils";

import { AutoVideoCard } from "./shop/AutoVideoCard";
import { NanoBananaCard } from "./shop/NanoBananaCard";
import { Veo3Card } from "./shop/Veo3Card";
import { ViralReplicaCard } from "./shop/ViralReplicaCard";

interface Props {
  userId: string;
  username: string;
  productId: string;
  productName: string;
}

type TabKey = "auto_video" | "veo3" | "nano_banana" | "viral";

interface TabDef {
  key: TabKey;
  icon: typeof Film;
  iconColorClass: string;
  label: string;
  short: string; // versión corta mobile
  subtitle: string;
}

const TABS: TabDef[] = [
  {
    key: "auto_video",
    icon: Film,
    iconColorClass: "text-cyan-400",
    label: "Auto vídeo",
    short: "Auto",
    subtitle: "Seedance + voz + subs · se encola",
  },
  {
    key: "veo3",
    icon: Sparkles,
    iconColorClass: "text-purple-400",
    label: "Prompt Veo 3",
    short: "Veo 3",
    subtitle: "Prompt 8s · pegar en Gemini chat",
  },
  {
    key: "nano_banana",
    icon: Banana,
    iconColorClass: "text-yellow-400",
    label: "Nano Banana",
    short: "Nano",
    subtitle: "Prompt para fotos premium",
  },
  {
    key: "viral",
    icon: Target,
    iconColorClass: "text-rose-400",
    label: "Replicar viral",
    short: "Viral",
    subtitle: "Sube vídeo → detecta preset",
  },
];

/**
 * Landing TikTok Shop: 4 modos organizados como tabs (mobile-first).
 * Solo se renderiza el contenido del modo activo; en muy estrechas (< sm)
 * los tabs van en 2 filas de 2 columnas y por encima de sm en una fila de 4.
 * Default activo = `auto_video` (el flujo más usado).
 */
export function ShopGenerateCards({ userId, username, productId, productName }: Props) {
  const [tab, setTab] = useState<TabKey>("auto_video");
  const activeTab = TABS.find((t) => t.key === tab) ?? TABS[0]!;

  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 px-3 py-2">
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Generando para
        </p>
        <p className="text-sm font-medium truncate">
          {username} · {productName}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "group flex flex-col items-start gap-1 rounded-lg border p-2.5 text-left transition-colors sm:p-3",
                active
                  ? "border-primary bg-primary/10 ring-1 ring-primary/40"
                  : "border-border bg-card hover:border-primary/40 hover:bg-muted/30",
              )}
              aria-pressed={active}
            >
              <div className="flex w-full items-center gap-1.5">
                <Icon className={cn("h-4 w-4 shrink-0", active ? t.iconColorClass : "text-muted-foreground")} />
                <span
                  className={cn(
                    "text-xs font-semibold sm:text-sm",
                    active ? "text-foreground" : "text-foreground/80",
                  )}
                >
                  <span className="sm:hidden">{t.short}</span>
                  <span className="hidden sm:inline">{t.label}</span>
                </span>
              </div>
              <span className="hidden text-[10px] text-muted-foreground sm:block sm:text-[11px]">
                {t.subtitle}
              </span>
            </button>
          );
        })}
      </div>

      <div>
        <div className="mb-2 flex items-baseline gap-2 sm:hidden">
          <activeTab.icon className={cn("h-4 w-4", activeTab.iconColorClass)} />
          <p className="text-sm font-semibold">{activeTab.label}</p>
          <span className="text-[10px] text-muted-foreground truncate">
            {activeTab.subtitle}
          </span>
        </div>

        {tab === "auto_video" && (
          <AutoVideoCard userId={userId} username={username} productId={productId} hideTitle />
        )}
        {tab === "veo3" && (
          <Veo3Card userId={userId} username={username} productId={productId} hideTitle />
        )}
        {tab === "nano_banana" && (
          <NanoBananaCard userId={userId} username={username} productId={productId} hideTitle />
        )}
        {tab === "viral" && (
          <ViralReplicaCard userId={userId} productId={productId} hideTitle />
        )}
      </div>
    </div>
  );
}
