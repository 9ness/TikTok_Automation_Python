"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Captions,
  ChevronDown,
  ChevronRight,
  Crown,
  History,
  LayoutDashboard,
  Menu,
  Mic,
  Package,
  Settings,
  ShieldOff,
  ShoppingBag,
  Sparkles,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { QueueBadge } from "@/components/queue/QueueBadge";
import { ThemeToggle } from "./ThemeToggle";

import type { LucideIcon } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

type NavGroup =
  | { kind: "single"; item: NavItem }
  | { kind: "group"; title: string; basePath: string; icon: LucideIcon; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    kind: "single",
    item: { href: "/", label: "Dashboard", icon: LayoutDashboard },
  },
  {
    kind: "group",
    title: "Creator Reward",
    basePath: "/creator-reward",
    icon: Trophy,
    items: [
      { href: "/creator-reward/presidents", label: "Presidentes Top 5", icon: Crown },
      { href: "/creator-reward/pronosticos", label: "Pronósticos Diarios", icon: BarChart3 },
      { href: "/creator-reward/copyright", label: "Quitar Copy", icon: ShieldOff },
      { href: "/creator-reward/subs-auto", label: "Subs sobre Vídeo", icon: Captions },
    ],
  },
  {
    kind: "group",
    title: "TikTok Shop",
    basePath: "/tiktok-shop",
    icon: ShoppingBag,
    items: [
      { href: "/tiktok-shop/products", label: "Productos", icon: Package },
      { href: "/tiktok-shop/users", label: "Usuarios", icon: Users },
      { href: "/tiktok-shop/generate", label: "Generador", icon: Sparkles },
      { href: "/tiktok-shop/history", label: "Histórico", icon: History },
      { href: "/tiktok-shop/voices", label: "Voces", icon: Mic },
    ],
  },
  {
    kind: "single",
    item: { href: "/settings", label: "Settings", icon: Settings },
  },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  // Estado de cada grupo expandido — auto-abrir si la ruta actual cae dentro.
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const node of NAV) {
      if (node.kind === "group") init[node.title] = pathname?.startsWith(node.basePath) ?? false;
    }
    return init;
  });

  // Si cambia la ruta, asegurarse de que el grupo correspondiente sigue abierto.
  useEffect(() => {
    setExpanded((prev) => {
      const next = { ...prev };
      for (const node of NAV) {
        if (node.kind === "group" && pathname?.startsWith(node.basePath)) {
          next[node.title] = true;
        }
      }
      return next;
    });
  }, [pathname]);

  return (
    <>
      <div className="flex h-20 items-center gap-3 border-b px-5">
        <Image
          src="/brand/logo.png"
          alt="NebulabsAI"
          width={36}
          height={36}
          className="rounded-md"
          priority
        />
        <div className="leading-tight">
          <p className="brand-gradient-text text-base font-bold tracking-tight">
            NebulabsAI
          </p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            TikTok Automation
          </p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {NAV.map((node) =>
            node.kind === "single" ? (
              <SidebarLink
                key={node.item.href}
                item={node.item}
                pathname={pathname}
                onNavigate={onNavigate}
              />
            ) : (
              <li key={node.title}>
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [node.title]: !prev[node.title] }))
                  }
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors",
                    "text-muted-foreground hover:bg-accent/40 hover:text-foreground",
                  )}
                  aria-expanded={expanded[node.title] ?? false}
                >
                  <node.icon className="h-4 w-4" strokeWidth={1.75} />
                  {node.title}
                  {expanded[node.title] ? (
                    <ChevronDown className="ml-auto h-3 w-3" strokeWidth={2} />
                  ) : (
                    <ChevronRight className="ml-auto h-3 w-3" strokeWidth={2} />
                  )}
                </button>
                {expanded[node.title] && (
                  <ul className="ml-3 mt-1 space-y-0.5 border-l pl-3">
                    {node.items.map((item) => (
                      <SidebarLink
                        key={item.href}
                        item={item}
                        pathname={pathname}
                        onNavigate={onNavigate}
                      />
                    ))}
                  </ul>
                )}
              </li>
            ),
          )}
        </ul>
      </nav>

      <div className="space-y-2 border-t px-3 py-3">
        <QueueBadge />
        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-muted-foreground">v0.1.0</span>
          <ThemeToggle />
        </div>
      </div>
    </>
  );
}

function SidebarLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string | null;
  onNavigate?: () => void;
}) {
  const active =
    item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href) ?? false;
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href as never}
        onClick={onNavigate}
        className={cn(
          "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-200",
          active
            ? "nav-active-indicator bg-accent/70 font-medium text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4 transition-colors",
            active ? "text-brand-cyan" : "",
          )}
          strokeWidth={1.75}
        />
        {item.label}
      </Link>
    </li>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:bg-card">
        <SidebarContent />
      </aside>

      {/* Mobile trigger + drawer */}
      <div className="flex h-14 items-center justify-between border-b px-4 md:hidden">
        <div className="flex items-center gap-2">
          <Image
            src="/brand/logo.png"
            alt="NebulabsAI"
            width={28}
            height={28}
            className="rounded"
          />
          <span className="brand-gradient-text text-sm font-bold">NebulabsAI</span>
        </div>
        <div className="flex items-center gap-1">
          <QueueBadge />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Abrir menú"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={() => setMobileOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <div className="absolute left-0 top-0 flex h-full w-72 flex-col bg-card shadow-lg">
            <div className="flex justify-end p-2">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Cerrar menú"
                onClick={() => setMobileOpen(false)}
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
